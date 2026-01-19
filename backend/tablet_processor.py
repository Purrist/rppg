import cv2
import numpy as np
from scipy.signal import butter, filtfilt, detrend
import threading
from queue import Queue
import time
import os

try:
    import mediapipe.python.solutions.face_mesh as mp_face_mesh
except ImportError:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh

class TabletProcessor:
    def __init__(self, camera_url):
        self.camera_url = camera_url
        self.cap = None
        self.running = False
        self.thread = None
        
        self.face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)
        
        self.FS = 30
        self.BUFFER_SIZE = 150
        self.raw_signals = []
        self.filtered_signals = []
        
        self.current_bpm = "--"
        self.current_emotion = "neutral"
        self.emotion_confidence = 0.0
        self.fatigue_level = "unknown"
        self.attention_score = 0.0
        self.posture_state = "unknown"
        
        self.frame_queue = Queue(maxsize=1)
        
        self.emotion_labels = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
    
    def connect_camera(self):
        """连接摄像头，使用更稳定的连接参数"""
        if self.cap is not None:
            self.cap.release()
        
        print(f"[平板摄像头] 正在连接: {self.camera_url}")
        
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
                    self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)  # 10秒超时
                    
                    # 设置读取超时
                    self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)  # 5秒超时
                    
                    # 设置缓存大小为1
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # 设置为低延迟模式
                    self.cap.set(cv2.CAP_PROP_FPS, 10)
                    
                    # 打开连接
                    success = self.cap.open(self.camera_url)
                    
                    if not success:
                        connect_error = Exception(f"无法打开平板摄像头: {self.camera_url}")
                        return
                else:
                    # 本地摄像头
                    self.cap = cv2.VideoCapture(self.camera_url)
                
                if not self.cap.isOpened():
                    connect_error = Exception(f"无法打开平板摄像头: {self.camera_url}")
                    return
                
                # 设置较低的分辨率和帧率，减少带宽占用
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)  # 非常低的分辨率
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)  # 非常低的分辨率
                self.cap.set(cv2.CAP_PROP_FPS, 10)  # 非常低的帧率
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
            raise Exception(f"平板摄像头连接超时: {self.camera_url}")
        
        if connect_error:
            raise connect_error
        
        if not self.cap or not self.cap.isOpened():
            raise Exception(f"无法打开平板摄像头: {self.camera_url}")
        
        print("[平板摄像头] 连接成功！")
    
    def butter_bandpass(self, data, lowcut=0.75, highcut=3.0, fs=30, order=2):
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return filtfilt(b, a, data)
    
    def detect_emotion(self, landmarks, frame):
        h, w = frame.shape[:2]
        
        # 眼睛相关特征点
        left_eye_top = landmarks[159]
        left_eye_bottom = landmarks[145]
        left_eye_left = landmarks[33]
        left_eye_right = landmarks[133]
        
        right_eye_top = landmarks[386]
        right_eye_bottom = landmarks[374]
        right_eye_left = landmarks[362]
        right_eye_right = landmarks[263]
        
        # 眉毛相关特征点
        left_eyebrow_inner = landmarks[27]
        left_eyebrow_outer = landmarks[22]
        right_eyebrow_inner = landmarks[257]
        right_eyebrow_outer = landmarks[262]
        
        # 嘴巴相关特征点
        mouth_top = landmarks[13]
        mouth_bottom = landmarks[14]
        mouth_left = landmarks[61]
        mouth_right = landmarks[291]
        mouth_left_corner = landmarks[17]
        mouth_right_corner = landmarks[267]
        
        # 计算眼睛高度和宽度
        eye_height_left = abs(left_eye_top.y - left_eye_bottom.y)
        eye_height_right = abs(right_eye_top.y - right_eye_bottom.y)
        eye_width_left = abs(left_eye_right.x - left_eye_left.x)
        eye_width_right = abs(right_eye_right.x - right_eye_left.x)
        avg_eye_height = (eye_height_left + eye_height_right) / 2
        avg_eye_width = (eye_width_left + eye_width_right) / 2
        eye_aspect_ratio = avg_eye_height / (avg_eye_width + 1e-6)
        
        # 计算嘴巴参数
        mouth_width = abs(mouth_right.x - mouth_left.x)
        mouth_height = abs(mouth_bottom.y - mouth_top.y)
        mouth_aspect = mouth_height / (mouth_width + 1e-6)
        mouth_corner_lift = (landmarks[61].y + landmarks[291].y) - (landmarks[17].y + landmarks[267].y)
        
        # 计算眉毛参数
        left_eyebrow_height = left_eyebrow_inner.y - landmarks[10].y
        right_eyebrow_height = right_eyebrow_inner.y - landmarks[152].y
        eyebrow_height_diff = abs(left_eyebrow_height - right_eyebrow_height)
        
        # 计算鼻子相关参数
        nose_tip = landmarks[4]
        nose_bridge = landmarks[168]
        nose_angle = abs(nose_tip.y - nose_bridge.y)
        
        # 情绪识别逻辑
        emotions = []
        
        # 检测开心
        if mouth_aspect > 0.22 and mouth_corner_lift < -0.02:
            emotions.append(("happy", 0.85))
        
        # 检测惊讶
        if avg_eye_height > 0.025 and mouth_aspect > 0.18:
            emotions.append(("surprise", 0.8))
        
        # 检测愤怒
        if (left_eyebrow_height < -0.04 or right_eyebrow_height < -0.04) and mouth_aspect < 0.12:
            emotions.append(("angry", 0.75))
        
        # 检测悲伤
        if mouth_corner_lift > 0.02 and avg_eye_height < 0.015:
            emotions.append(("sad", 0.7))
        
        # 检测厌恶
        if nose_angle > 0.03 and mouth_aspect > 0.15:
            emotions.append(("disgust", 0.65))
        
        # 检测恐惧
        if eyebrow_height_diff > 0.02 and avg_eye_height > 0.02 and mouth_aspect < 0.15:
            emotions.append(("fear", 0.6))
        
        # 始终将中性情绪作为备选
        emotions.append(("neutral", 0.5))
        
        # 选择置信度最高的情绪
        emotion, confidence = max(emotions, key=lambda x: x[1])
        
        return emotion, confidence
    
    def detect_posture(self, landmarks, frame):
        h, w = frame.shape[:2]
        
        nose = landmarks[1]
        left_shoulder = landmarks[11]
        right_shoulder = landmarks[12]
        
        shoulder_slope = abs(left_shoulder.y - right_shoulder.y)
        head_tilt = abs(nose.x - (left_shoulder.x + right_shoulder.x) / 2)
        
        if shoulder_slope < 0.02 and head_tilt < 0.05:
            posture = "focused"
        elif shoulder_slope < 0.02 and head_tilt > 0.1:
            posture = "relaxed"
        elif shoulder_slope > 0.05:
            posture = "slouching"
        elif head_tilt > 0.15:
            posture = "leaning"
        else:
            posture = "neutral"
        
        return posture
    
    def detect_fatigue(self, landmarks, frame):
        h, w = frame.shape[:2]
        
        left_eye_top = landmarks[159]
        left_eye_bottom = landmarks[145]
        right_eye_top = landmarks[386]
        right_eye_bottom = landmarks[374]
        
        left_eye_height = abs(left_eye_top.y - left_eye_bottom.y)
        right_eye_height = abs(right_eye_top.y - right_eye_bottom.y)
        avg_eye_height = (left_eye_height + right_eye_height) / 2
        
        if avg_eye_height < 0.015:
            fatigue = "high"
        elif avg_eye_height < 0.025:
            fatigue = "medium"
        else:
            fatigue = "low"
        
        return fatigue
    
    def process_frame(self, frame):
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.face_mesh.process(rgb)
        
        if res.multi_face_landmarks and len(res.multi_face_landmarks) > 0:
            landmarks = res.multi_face_landmarks[0].landmark
            
            rois = [10, 234, 454]
            current_g_pool = []
            
            for idx in rois:
                if idx < len(landmarks):
                    cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
                    r = 15
                    if 0 < cy-r < h and 0 < cx-r < w:
                        roi_zone = frame[cy-r:cy+r, cx-r:cx+r]
                        current_g_pool.append(np.mean(roi_zone[:,:,1]))
                        cv2.circle(frame, (cx, cy), r, (0, 255, 0), -1)
            
            if current_g_pool:
                avg_g = np.mean(current_g_pool)
                global_g = np.mean(frame[:,:,1]) + 1e-6
                self.raw_signals.append(avg_g / global_g)
                
                if len(self.raw_signals) > self.BUFFER_SIZE:
                    self.raw_signals.pop(0)
                
                if len(self.raw_signals) == self.BUFFER_SIZE:
                    try:
                        processed = detrend(np.array(self.raw_signals))
                        y = self.butter_bandpass(processed)
                        self.filtered_signals = y.tolist()
                        
                        fft = np.abs(np.fft.rfft(y))
                        freqs = np.fft.rfftfreq(self.BUFFER_SIZE, 1/self.FS)
                        self.current_bpm = int(freqs[np.argmax(fft[1:])+1]) * 60
                    except:
                        pass
            
            # 只有在检测到面部时才进行情绪和姿态检测
            if res.multi_face_landmarks and len(res.multi_face_landmarks) > 0:
                face_landmarks = res.multi_face_landmarks[0]
                if face_landmarks.landmark and len(face_landmarks.landmark) > 0:
                    landmarks = face_landmarks.landmark
                    
                    emotion, emotion_conf = self.detect_emotion(landmarks, frame)
                    self.current_emotion = emotion
                    self.emotion_confidence = emotion_conf
                    
                    fatigue = self.detect_fatigue(landmarks, frame)
                    self.fatigue_level = fatigue
                    
                    posture = self.detect_posture(landmarks, frame)
                    self.posture_state = posture
                    
                    self.attention_score = 0.5 + (0.5 * (1.0 - emotion_conf))
                    
                    # 在面部关键点上绘制矩形
                    if 1 < len(landmarks) and 152 < len(landmarks) and 10 < len(landmarks):
                        cv2.rectangle(frame, (int(landmarks[1].x * w - 50), int(landmarks[1].y * h - 50)), 
                                   (int(landmarks[1].x * w + 50), int(landmarks[1].y * h + 50)), (0, 255, 0), 2)
                        cv2.rectangle(frame, (int(landmarks[152].x * w - 30), int(landmarks[152].y * h - 30)), 
                                   (int(landmarks[152].x * w + 30), int(landmarks[152].y * h + 30)), (0, 255, 0), 2)
                        cv2.rectangle(frame, (int(landmarks[10].x * w - 40), int(landmarks[10].y * h - 40)), 
                                   (int(landmarks[10].x * w + 40), int(landmarks[10].y * h + 40)), (0, 255, 0), 2)
        
        return frame
    
    def get_state(self):
        return {
            "bpm": self.current_bpm,
            "emotion": self.current_emotion,
            "emotion_confidence": self.emotion_confidence,
            "fatigue_level": self.fatigue_level,
            "attention_score": self.attention_score,
            "posture_state": self.posture_state
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
                        print(f"[平板摄像头] 摄像头未打开，尝试重连 ({reconnect_attempts+1}/{max_reconnect_attempts})")
                        try:
                            self.connect_camera()
                            print(f"[平板摄像头] 重连成功")
                            reconnect_attempts = 0
                            consecutive_fails = 0
                            reconnect_delay = 1.0  # 重置重连延迟
                            frame_counter = 0
                        except Exception as e:
                            print(f"[平板摄像头] 重连失败: {e}")
                            reconnect_attempts += 1
                            # 指数退避重连
                            time.sleep(reconnect_delay)
                            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
                    else:
                        # 达到最大重连次数，使用占位帧
                        print(f"[平板摄像头] 达到最大重连次数，使用占位帧")
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
                    print(f"[平板摄像头] 帧读取失败 {consecutive_fails}/{max_consecutive_fails}")
                    
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
                        print(f"[平板摄像头] 连续 {consecutive_fails} 帧读取失败，尝试重连")
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
                print(f"[平板摄像头] 捕获异常: {e}")
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
        print("[平板摄像头] 处理线程已启动")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        print("[平板摄像头] 已停止")
    
    def get_frame(self):
        if not self.frame_queue.empty():
            return self.frame_queue.get()
        return None