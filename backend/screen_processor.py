import cv2
import numpy as np
import threading
from queue import Queue
import time
import os

# 导入MediaPipe Hands
try:
    import mediapipe as mp
    mp_hands = mp.solutions.hands
except ImportError:
    try:
        import mediapipe.python.solutions.hands as mp_hands
        import mediapipe.python.solutions.drawing_utils as drawing_utils
        mp = None
    except ImportError:
        print("[警告] 未找到MediaPipe，将使用替代方法")
        mp = None
        mp_hands = None
        drawing_utils = None

class ScreenProcessor:
    def __init__(self, camera_url):
        self.camera_url = camera_url
        self.cap = None
        self.running = False
        self.thread = None
        
        # MediaPipe Hands初始化，优化参数以提高半手掌检测准确性
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.25,  # 进一步降低检测阈值，提高检测灵敏度
            min_tracking_confidence=0.25,   # 进一步降低跟踪阈值，提高跟踪稳定性
            model_complexity=0            # 使用低复杂度模型，提高性能
        )
        
        # 区域识别状态
        self.regions_detected = False
        self.detected_regions = {}
        
        # 手检测状态
        self.hand_detected = False
        self.hand_landmarks = None
        self.index_finger_tip = None
        self.selected_region = None
        self.selection_confidence = 0.0
        
        # 进度环配置
        self.selection_start_time = None
        self.MIN_SELECTION_TIME = 1.5  # 从3秒缩短到1.5秒
        
        self.frame_queue = Queue(maxsize=1)
        
        # 调试信息
        self.debug_info = "初始化中..."
        
        # 颜色检测阈值 - 优化为更准确的范围
        self.color_ranges = {
            "red": {"lower": np.array([0, 80, 80]), "upper": np.array([15, 255, 255])},
            "yellow": {"lower": np.array([20, 80, 80]), "upper": np.array([35, 255, 255])},
            "blue": {"lower": np.array([100, 80, 80]), "upper": np.array([135, 255, 255])}
        }
        
        # 肉色检测阈值，用于提高手检测准确性
        self.skin_color_ranges = {
            "lower": np.array([0, 20, 70]),
            "upper": np.array([20, 255, 255])
        }
    
    def connect_camera(self):
        """连接摄像头，使用更稳定的连接参数"""
        if self.cap is not None:
            self.cap.release()
        
        print(f"[外接摄像头] 正在连接: {self.camera_url}")
        
        # 使用多线程实现超时控制
        import threading
        
        self.cap = None
        connect_error = None
        
        def connect_task():
            nonlocal self, connect_error
            try:
                # 对于网络摄像头，使用更稳定的连接参数
                if isinstance(self.camera_url, str) and (self.camera_url.startswith('http://') or self.camera_url.startswith('https://')):
                    # 尝试不同的连接参数
                    self.cap = cv2.VideoCapture()
                    
                    # 设置连接超时
                    self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)  # 8秒超时
                    
                    # 设置读取超时
                    self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)  # 3秒超时
                    
                    # 设置缓存大小为1
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # 设置为低延迟模式
                    self.cap.set(cv2.CAP_PROP_FPS, 6)
                    
                    # 打开连接
                    success = self.cap.open(self.camera_url)
                    
                    if not success:
                        connect_error = Exception(f"无法打开外接摄像头: {self.camera_url}")
                        return
                else:
                    # 本地摄像头
                    self.cap = cv2.VideoCapture(self.camera_url)
                
                if not self.cap.isOpened():
                    connect_error = Exception(f"无法打开外接摄像头: {self.camera_url}")
                    return
                
                # 设置更低的分辨率和帧率，减少带宽占用
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 240)  # 更低的分辨率
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 180)  # 更低的分辨率，保持4:3比例
                self.cap.set(cv2.CAP_PROP_FPS, 6)  # 更低的帧率
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 减少缓冲区大小
                
                # 禁用自动调整
                self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
                
            except Exception as e:
                connect_error = e
        
        # 创建线程并启动
        thread = threading.Thread(target=connect_task)
        thread.daemon = True
        thread.start()
        
        # 等待最多15秒
        thread.join(timeout=15)
        
        if thread.is_alive():
            # 线程超时，强制退出
            raise Exception(f"外接摄像头连接超时: {self.camera_url}")
        
        if connect_error:
            raise connect_error
        
        if not self.cap or not self.cap.isOpened():
            raise Exception(f"无法打开外接摄像头: {self.camera_url}")
        
        print("[外接摄像头] 连接成功！")
    
    def detect_colored_regions(self, frame):
        """检测三个彩色区域（红、黄、蓝），结合颜色、形状和定位点进行综合检测"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w = frame.shape[:2]
        
        detected_regions = {}
        
        # 定位点坐标（四个角的视觉定位点）
        corner_points = [
            (0.05 * w, 0.05 * h),  # 左上角
            (0.95 * w, 0.05 * h),  # 右上角
            (0.05 * w, 0.95 * h),  # 左下角
            (0.95 * w, 0.95 * h)   # 右下角
        ]
        
        # 地鼠洞的预期位置范围（根据前端页面布局，固定位置）
        # 16:10布局下，地鼠洞应该在中间区域，水平排列
        min_x = 0.15 * w
        max_x = 0.85 * w
        min_y = 0.4 * h
        max_y = 0.75 * h
        
        # 预期的地鼠洞水平位置（左、中、右）
        expected_x_positions = [0.3, 0.5, 0.7]  # 相对宽度
        expected_x_tolerance = 0.15  # 容差范围
        
        for color_name, color_range in self.color_ranges.items():
            # 创建颜色掩码
            mask = cv2.inRange(hsv, color_range["lower"], color_range["upper"])
            
            # 形态学操作，去除噪声
            kernel = np.ones((5, 5), np.uint8)  # 适中的卷积核，平衡噪声去除和细节保留
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # 寻找轮廓
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 按照面积排序轮廓
            contours = sorted(contours, key=cv2.contourArea, reverse=True)
            
            # 遍历轮廓，寻找最符合条件的区域
            best_region = None
            best_score = 0
            
            for contour in contours:
                area = cv2.contourArea(contour)
                
                # 过滤条件：
                # 1. 面积适中，排除太小的噪声和太大的干扰
                if area < 300 or area > 2500:
                    continue
                
                # 计算轮廓的边界框
                x, y, width, height = cv2.boundingRect(contour)
                
                # 计算中心点
                cx = x + width // 2
                cy = y + height // 2
                
                # 过滤条件：
                # 2. 位于中间区域，不在角落
                if cx < min_x or cx > max_x or cy < min_y or cy > max_y:
                    continue
                
                # 过滤条件：
                # 3. 形状近似圆形（宽高比接近1）
                aspect_ratio = width / height
                if aspect_ratio < 0.8 or aspect_ratio > 1.2:
                    continue
                
                # 过滤条件：
                # 4. 距离定位点较远，避免将定位点误识别为区域
                too_close_to_corner = False
                for (corner_x, corner_y) in corner_points:
                    distance = np.sqrt((cx - corner_x)**2 + (cy - corner_y)**2)
                    if distance < 0.12 * w:  # 距离定位点太近
                        too_close_to_corner = True
                        break
                if too_close_to_corner:
                    continue
                
                # 计算轮廓的圆形度
                perimeter = cv2.arcLength(contour, True)
                if perimeter == 0:
                    continue
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                
                # 过滤条件：
                # 5. 圆形度适中，排除过于不规则的形状
                if circularity < 0.6:
                    continue
                
                # 计算轮廓的填充度（面积与边界框面积的比值）
                fill_ratio = area / (width * height)
                # 过滤条件：
                # 6. 填充度较高，排除空心或过于扁平的形状
                if fill_ratio < 0.5:
                    continue
                
                # 评分系统：综合考虑多个因素
                score = 0
                
                # 根据颜色名称匹配预期位置（红色在左，黄色在中，蓝色在右）
                expected_x = expected_x_positions[0] if color_name == "red" else \
                           expected_x_positions[1] if color_name == "yellow" else \
                           expected_x_positions[2]
                
                # 位置评分：越接近预期位置得分越高
                position_diff = abs(cx/w - expected_x)
                if position_diff < expected_x_tolerance:
                    score += (1 - position_diff/expected_x_tolerance) * 50
                else:
                    continue  # 不在预期位置范围内，直接跳过
                
                # 圆形度评分
                score += circularity * 20
                
                # 面积评分：适中的面积得分高
                ideal_area = 1000
                area_score = max(0, 1 - abs(area - ideal_area)/1000) * 20
                score += area_score
                
                # 填充度评分
                score += fill_ratio * 10
                
                # 宽高比评分
                aspect_score = max(0, 1 - abs(aspect_ratio - 1)/0.5) * 10
                score += aspect_score
                
                # 更新最佳区域
                if score > best_score:
                    best_score = score
                    best_region = {
                        "cx": cx,
                        "cy": cy,
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "area": area,
                        "circularity": circularity,
                        "fill_ratio": fill_ratio,
                        "score": score
                    }
            
            # 如果找到了最佳区域
            if best_region:
                cx = best_region["cx"]
                cy = best_region["cy"]
                x = best_region["x"]
                y = best_region["y"]
                width = best_region["width"]
                height = best_region["height"]
                
                # 找到了符合条件的区域
                detected_regions[color_name] = {
                    "x": cx / w,
                    "y": cy / h,
                    "width": width / w,
                    "height": height / h,
                    "bbox": (x, y, width, height),
                    "area": best_region["area"],
                    "circularity": best_region["circularity"]
                }
                
                # 在图像上绘制轮廓和中心点
                cv2.drawContours(frame, [contour], -1, (0, 255, 0), 2)
                cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)
                cv2.putText(frame, color_name, (x, y - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # 更新检测状态
        self.regions_detected = len(detected_regions) >= 3
        self.detected_regions = detected_regions
        
        return detected_regions
    
    def detect_hand(self, frame):
        """使用MediaPipe检测手和手部关键点，结合肉色检测提高准确性"""
        h, w = frame.shape[:2]
        
        # 首先进行肉色检测，提高检测效率
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        skin_mask = cv2.inRange(hsv, self.skin_color_ranges["lower"], self.skin_color_ranges["upper"])
        
        # 检查是否有足够的肉色区域，只有在有肉色区域时才进行MediaPipe检测
        skin_area = cv2.countNonZero(skin_mask)
        has_skin = skin_area > 100  # 至少有100个像素的肉色区域
        
        self.hand_detected = False
        self.hand_landmarks = None
        self.index_finger_tip = None
        
        if has_skin:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)
            
            self.hand_detected = results.multi_hand_landmarks is not None
            
            if self.hand_detected and results.multi_hand_landmarks:
                hand_landmarks = results.multi_hand_landmarks[0]
                self.hand_landmarks = hand_landmarks
                
                # 获取食指指尖坐标（关键点8）
                index_finger_landmark = hand_landmarks.landmark[8]
                
                # 转换为像素坐标
                x = int(index_finger_landmark.x * w)
                y = int(index_finger_landmark.y * h)
                
                self.index_finger_tip = (x, y)
                
                # 绘制手部关键点（简化绘制，只绘制食指）
                if mp is not None:
                    # 只绘制食指相关的关键点连接
                    index_finger_keypoints = [0, 5, 6, 7, 8]  # 手腕到食指指尖
                    for i in range(len(index_finger_keypoints)-1):
                        pt1 = hand_landmarks.landmark[index_finger_keypoints[i]]
                        pt2 = hand_landmarks.landmark[index_finger_keypoints[i+1]]
                        cv2.line(frame, 
                                (int(pt1.x*w), int(pt1.y*h)), 
                                (int(pt2.x*w), int(pt2.y*h)), 
                                (0, 255, 0), 2)
                
                # 突出显示食指指尖
                cv2.circle(frame, (x, y), 10, (0, 255, 255), -1)
                cv2.putText(frame, "食指", (x + 10, y - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        return self.hand_detected
    
    def process_index_finger(self, frame):
        """处理食指位置，判断指向哪个区域"""
        if not self.hand_detected or not self.index_finger_tip or not self.regions_detected:
            self.selected_region = None
            return None
        
        x, y = self.index_finger_tip
        selected_region = None
        
        for color_name, region in self.detected_regions.items():
            rx, ry, rw, rh = region["bbox"]
            
            # 检查食指是否在区域内
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                selected_region = color_name
                break
        
        self.selected_region = selected_region
        
        if selected_region:
            # 更新选择状态
            if self.selection_start_time is None:
                self.selection_start_time = time.time()
            else:
                elapsed = time.time() - self.selection_start_time
                self.selection_confidence = min(1.0, elapsed / self.MIN_SELECTION_TIME)
        else:
            # 重置选择状态
            self.selection_start_time = None
            self.selection_confidence = 0.0
        
        return selected_region
    
    def process_frame(self, frame):
        """处理每一帧图像"""
        h, w = frame.shape[:2]
        
        # 1. 检测彩色区域
        self.detect_colored_regions(frame)
        
        # 2. 检测手部
        self.detect_hand(frame)
        
        # 3. 处理食指位置
        self.process_index_finger(frame)
        
        # 更新调试信息
        if self.regions_detected:
            self.debug_info = "已识别到三个目标区域"
            if self.hand_detected:
                if self.selected_region:
                    self.debug_info = f"已识别到三个目标区域，已检测到手在画面内，食指指向{self.selected_region}区域"
                else:
                    self.debug_info = "已识别到三个目标区域，已检测到手在画面内"
            else:
                self.debug_info = "已识别到三个目标区域，未检测到手在画面内"
        else:
            self.debug_info = f"已检测{len(self.detected_regions)}/3个目标区域"
        
        # 在图像上显示调试信息
        cv2.putText(frame, self.debug_info, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return frame
    
    def get_state(self):
        return {
            "hand_detected": self.hand_detected,
            "selected_region": self.selected_region,
            "selection_confidence": self.selection_confidence,
            "selection_time": time.time() - self.selection_start_time if self.selection_start_time else 0,
            "regions_detected": self.regions_detected,
            "detected_regions_count": len(self.detected_regions),
            "debug_info": self.debug_info,
            "index_finger_detected": self.index_finger_tip is not None
        }
    
    def capture_loop(self):
        """优化的视频捕获循环，减少断开连接问题"""
        reconnect_attempts = 0
        max_reconnect_attempts = 10  # 增加最大重连次数
        consecutive_fails = 0
        max_consecutive_fails = 5  # 减少连续失败次数阈值
        last_valid_frame = None
        reconnect_delay = 1.0  # 初始重连延迟
        max_reconnect_delay = 30.0  # 最大重连延迟
        frame_counter = 0
        
        # 创建一个占位帧，避免在相机断开时返回空帧
        placeholder_frame = np.ones((240, 320, 3), dtype=np.uint8) * 200
        cv2.putText(placeholder_frame, 'Camera Disconnected', (10, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        
        while self.running:
            try:
                # 检查摄像头是否打开
                if not self.cap or not self.cap.isOpened():
                    if reconnect_attempts < max_reconnect_attempts:
                        print(f"[外接摄像头] 摄像头未打开，尝试重连 ({reconnect_attempts+1}/{max_reconnect_attempts})")
                        try:
                            self.connect_camera()
                            print(f"[外接摄像头] 重连成功")
                            reconnect_attempts = 0
                            consecutive_fails = 0
                            reconnect_delay = 1.0  # 重置重连延迟
                            frame_counter = 0
                        except Exception as e:
                            print(f"[外接摄像头] 重连失败: {e}")
                            reconnect_attempts += 1
                            # 指数退避重连
                            time.sleep(reconnect_delay)
                            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
                    else:
                        # 达到最大重连次数，使用占位帧
                        print(f"[外接摄像头] 达到最大重连次数，使用占位帧")
                        if not self.frame_queue.full():
                            try:
                                self.frame_queue.put(placeholder_frame, timeout=0.1)
                            except Exception as e:
                                pass
                        time.sleep(1.0)
                        continue
                
                # 读取帧，增加超时处理
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 确保缓冲区大小为1
                
                # 使用非阻塞方式读取，避免长时间阻塞
                self.cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)
                ret, frame = self.cap.read()
                frame_counter += 1
                
                if ret and frame is not None:
                    # 重置计数
                    reconnect_attempts = 0
                    consecutive_fails = 0
                    last_valid_frame = frame.copy()  # 保存最新有效帧
                    
                    # 处理帧
                    processed_frame = self.process_frame(frame)
                    
                    # 放入队列（非阻塞，避免队列满导致阻塞）
                    if not self.frame_queue.full():
                        try:
                            self.frame_queue.put(processed_frame, timeout=0.05)  # 更短的超时时间
                        except Exception as e:
                            # 队列已满，跳过当前帧
                            pass
                    
                else:
                    # 读取失败
                    consecutive_fails += 1
                    print(f"[外接摄像头] 帧读取失败 {consecutive_fails}/{max_consecutive_fails}")
                    
                    # 如果有有效帧，继续使用它
                    if last_valid_frame is not None:
                        processed_frame = self.process_frame(last_valid_frame)
                        if not self.frame_queue.full():
                            try:
                                self.frame_queue.put(processed_frame, timeout=0.05)
                            except Exception as e:
                                pass
                    else:
                        # 如果没有有效帧，使用占位帧
                        if not self.frame_queue.full():
                            try:
                                self.frame_queue.put(placeholder_frame, timeout=0.05)
                            except Exception as e:
                                pass
                    
                    # 只有连续多次失败才尝试重连
                    if consecutive_fails >= max_consecutive_fails:
                        print(f"[外接摄像头] 连续 {consecutive_fails} 帧读取失败，尝试重连")
                        # 释放当前连接
                        if self.cap:
                            self.cap.release()
                            self.cap = None
                        
                        # 重置计数器
                        consecutive_fails = 0
                        reconnect_attempts += 1
                        reconnect_delay = 1.0  # 重置重连延迟
                
                # 降低CPU使用率，但保持流畅性
                time.sleep(0.02)  # 降低CPU占用，避免过度轮询
            
            except Exception as e:
                # 捕获所有异常，避免崩溃
                print(f"[外接摄像头] 捕获异常: {e}")
                consecutive_fails += 1
                
                # 释放当前连接，准备重连
                if self.cap:
                    self.cap.release()
                    self.cap = None
                
                # 使用有效帧或占位帧
                if last_valid_frame is not None:
                    processed_frame = self.process_frame(last_valid_frame)
                    if not self.frame_queue.full():
                        try:
                            self.frame_queue.put(processed_frame, timeout=0.05)
                        except Exception as e:
                            pass
                else:
                    if not self.frame_queue.full():
                        try:
                            self.frame_queue.put(placeholder_frame, timeout=0.05)
                        except Exception as e:
                            pass
                
                # 延迟后重试
                time.sleep(1.0)
    
    def start(self):
        self.connect_camera()
        self.running = True
        self.thread = threading.Thread(target=self.capture_loop)
        self.thread.daemon = True
        self.thread.start()
        print("[外接摄像头] 处理线程已启动")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        print("[外接摄像头] 已停止")
    
    def get_frame(self):
        if not self.frame_queue.empty():
            return self.frame_queue.get()
        return None