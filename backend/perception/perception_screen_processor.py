# perception/perception_screen_processor.py
# 投影摄像头处理 - 脚部检测

import cv2

# 抑制OpenCV警告
import logging
logging.getLogger('cv2').setLevel(logging.ERROR)

import numpy as np
import time
import threading
import json
import os

# 配置文件路径（在perception目录下）
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "projection_config.json")

# 全局状态
state = {
    "corners": [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]],
    "zones": [],
    "feet_x": 320,
    "feet_y": 180,
    "feet_detected": False,
    "active_zones": [],
    "matrix": None,
    "zone_id_counter": 4,
    "admin_bg": "#ffffff",
    "projection_bg": "#000000"
}


# ============================================================================
# 平滑滤波器
# ============================================================================
class SmoothFilter:
    """自适应滤波器"""
    def __init__(self, alpha=0.5, threshold=20):
        self.alpha = alpha
        self.threshold = threshold
        self.value = None
    
    def update(self, new_value):
        if self.value is None:
            self.value = new_value
            return new_value
        diff = abs(new_value - self.value)
        alpha = 0.85 if diff > self.threshold else self.alpha
        self.value = alpha * new_value + (1 - alpha) * self.value
        return self.value


class PositionSmoother:
    """位置平滑器"""
    def __init__(self):
        self.x_filter = SmoothFilter(alpha=0.5, threshold=20)
        self.y_filter = SmoothFilter(alpha=0.5, threshold=20)
        self.last_x = 320
        self.last_y = 180
        self.last_time = 0
        self.lost_count = 0
    
    def update(self, x, y, detected):
        if detected:
            x = max(50, min(590, x))
            y = max(50, min(310, y))
            
            smooth_x = self.x_filter.update(x)
            smooth_y = self.y_filter.update(y)
            self.last_x = smooth_x
            self.last_y = smooth_y
            self.last_time = time.time()
            self.lost_count = 0
            return int(smooth_x), int(smooth_y), True
        else:
            self.lost_count += 1
            if self.lost_count < 18:
                return int(self.last_x), int(self.last_y), True
            return int(self.last_x), int(self.last_y), False


# ============================================================================
# 配置保存/加载
# ============================================================================
def save_config_to_file():
    try:
        # 确保目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "corners": state["corners"],
                "zones": state["zones"],
                "zone_id_counter": state["zone_id_counter"],
                "admin_bg": state["admin_bg"],
                "projection_bg": state["projection_bg"]
            }, f, indent=2)
        
        print(f"[ScreenProcessor] 配置已保存到: {CONFIG_FILE}")
        print(f"[ScreenProcessor] 配置内容: corners={state['corners']}")
        return True
    except Exception as e:
        print(f"[ScreenProcessor] 保存配置失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def load_config_from_file():
    global state
    if not os.path.exists(CONFIG_FILE):
        print(f"[ScreenProcessor] 配置文件不存在: {CONFIG_FILE}")
        return False
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if "corners" in config: 
            state["corners"] = config["corners"]
            print(f"[ScreenProcessor] 加载 corners: {state['corners']}")
        if "zones" in config: 
            state["zones"] = config["zones"]
        if "zone_id_counter" in config: 
            state["zone_id_counter"] = config["zone_id_counter"]
        if "admin_bg" in config: 
            state["admin_bg"] = config["admin_bg"]
        if "projection_bg" in config: 
            state["projection_bg"] = config["projection_bg"]
        
        print(f"[ScreenProcessor] 配置加载成功")
        return True
    except json.JSONDecodeError as e:
        print(f"[ScreenProcessor] 配置文件格式错误: {e}")
        return False
    except Exception as e:
        print(f"[ScreenProcessor] 加载配置失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# 处理器类
# ============================================================================
class ScreenProcessor:
    def __init__(self, camera_source=1, socketio=None):
        self.socketio = socketio
        
        # ⭐ 初始化时尝试加载配置
        if os.path.exists(CONFIG_FILE):
            print("[ScreenProcessor] 发现配置文件，正在加载...")
            load_config_from_file()
        else:
            print("[ScreenProcessor] 未发现配置文件，使用默认配置")
        
        # 尝试打开摄像头
        self.cap = None
        
        # 尝试多个可能的摄像头源
        camera_sources = [camera_source, 0, 2, 3]
        for src in camera_sources:
            try:
                self.cap = cv2.VideoCapture(src)
                if self.cap.isOpened():
                    # 测试读取一帧
                    ret, _ = self.cap.read()
                    if ret:
                        print(f"[ScreenProcessor] 成功打开摄像头: {src}")
                        break
                    else:
                        print(f"[ScreenProcessor] 摄像头 {src} 打开失败: 无法读取帧")
                        self.cap.release()
                        self.cap = None
                else:
                    print(f"[ScreenProcessor] 摄像头 {src} 打开失败")
                    self.cap = None
            except Exception as e:
                print(f"[ScreenProcessor] 尝试打开摄像头 {src} 时出错: {e}")
                self.cap = None
        
        if not self.cap:
            print("[ScreenProcessor] 所有摄像头都无法打开，使用虚拟摄像头")
            # 创建一个虚拟摄像头（黑色画面）
            self.cap = None
            self.frame_w = 640
            self.frame_h = 480
        else:
            # 摄像头设置
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[ScreenProcessor] 摄像头分辨率: {self.frame_w}x{self.frame_h}")
        
        # MediaPipe Pose
        import mediapipe as mp
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=0.55,
            min_tracking_confidence=0.55,
            model_complexity=1,
            smooth_landmarks=True
        )
        
        self.raw_frame = None
        self.corrected_frame = None
        self.running = True
        self.position_smoother = PositionSmoother()
        
        load_config_from_file()
        threading.Thread(target=self._loop, daemon=True).start()
    
    def _loop(self):
        import mediapipe as mp
        while self.running:
            if self.cap:
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.005)
                    continue
                
                frame = cv2.flip(frame, 0)
                frame = cv2.flip(frame, 1)
            else:
                # 使用虚拟摄像头（黑色画面）
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
            
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb)
            
            raw_feet_detected = False
            raw_feet_x, raw_feet_y = 320, 180
            
            if results.pose_landmarks:
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)
                
                lm = results.pose_landmarks.landmark
                left_ankle = lm[27]
                right_ankle = lm[28]
                
                # ⭐ 多人场景过滤逻辑：优先选择站在标定区域内的人
                # 1. 脚踝可见性检查（降低阈值以支持不同身高的人）
                if left_ankle.visibility > 0.3 and right_ankle.visibility > 0.3:
                    l_pt = (int(left_ankle.x * w), int(left_ankle.y * h))
                    r_pt = (int(right_ankle.x * w), int(right_ankle.y * h))
                    
                    cv2.circle(frame, l_pt, 15, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 15, (0, 255, 0), -1)
                    
                    center = ((l_pt[0] + r_pt[0]) // 2, (l_pt[1] + r_pt[1]) // 2)
                    cv2.circle(frame, center, 10, (255, 0, 255), -1)
                    
                    # 2. 计算标定区域中心点（用于距离比较）
                    pts = np.array([[int(c[0]*w), int(c[1]*h)] for c in state["corners"]], np.int32)
                    
                    # 计算标定区域的中心点
                    pts_center_x = int(np.mean(pts[:, 0]))
                    pts_center_y = int(np.mean(pts[:, 1]))
                    
                    # 计算脚踝中心到标定区域中心的距离
                    dist_to_center = np.sqrt((center[0] - pts_center_x)**2 + (center[1] - pts_center_y)**2)
                    
                    # 检查脚踝是否在标定区域内
                    is_inside = cv2.pointPolygonTest(pts, (center[0], center[1]), False) >= 0
                    
                    # 3. 检查是否是近距离的人（宽松阈值，支持小孩）
                    # 使用脚踝和膝盖的距离来判断大致身高
                    left_knee = lm[25]
                    right_knee = lm[26]
                    has_knee_data = left_knee.visibility > 0.2 or right_knee.visibility > 0.2
                    
                    # 计算脚踝中心点 y 坐标
                    ankle_center_y = (left_ankle.y + right_ankle.y) / 2 * h
                    
                    if has_knee_data:
                        knee_center_y = ((left_knee.y if left_knee.visibility > 0.2 else right_knee.y) + 
                                        (right_knee.y if right_knee.visibility > 0.2 else left_knee.y)) / 2 * h
                        leg_length = abs(ankle_center_y - knee_center_y)
                        # 宽松的最小腿长阈值（支持小孩）
                        is_close_enough = leg_length >= h * 0.08  # 至少占画面高度的8%
                    else:
                        # 如果膝盖数据不可用，放宽要求
                        is_close_enough = True
                    
                    # 判断条件：在区域内 OR 非常靠近区域中心
                    # 优先选择站在区域内的人
                    if (is_inside or dist_to_center < w * 0.15) and is_close_enough:
                        if state["matrix"] is not None:
                            try:
                                src_pt = np.array([[[center[0], center[1]]]], dtype=np.float32)
                                dst_pt = cv2.perspectiveTransform(src_pt, state["matrix"])[0][0]
                                raw_feet_x, raw_feet_y = int(dst_pt[0]), int(dst_pt[1])
                                raw_feet_detected = True
                            except:
                                pass
            
            # 平滑处理
            smooth_x, smooth_y, smooth_detected = self.position_smoother.update(
                raw_feet_x, raw_feet_y, raw_feet_detected
            )
            
            # 边界检查
            smooth_x = max(50, min(590, smooth_x))
            smooth_y = max(50, min(310, smooth_y))
            
            state["feet_x"] = smooth_x
            state["feet_y"] = smooth_y
            state["feet_detected"] = smooth_detected
            
            # 绘制校准框
            pts = np.array([[int(c[0]*w), int(c[1]*h)] for c in state["corners"]], np.int32)
            cv2.polylines(frame, [pts], True, (255, 0, 0), 2)
            for i, c in enumerate(state["corners"]):
                x, y = int(c[0]*w), int(c[1]*h)
                cv2.circle(frame, (x, y), 10, (255, 0, 0), -1)
                cv2.putText(frame, str(i+1), (x-6, y+4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
            
            # 透视变换
            corrected = np.ones((360, 640, 3), dtype=np.uint8) * 255
            if state["matrix"] is not None:
                try:
                    corrected = cv2.warpPerspective(frame, state["matrix"], (640, 360))
                except:
                    pass
            
            # 绘制脚部位置
            if smooth_detected:
                cv2.circle(corrected, (smooth_x, smooth_y), 20, (0, 200, 0), -1)
            
            self.raw_frame = frame
            self.corrected_frame = corrected
            time.sleep(0.002)
    
    def get_raw_jpeg(self):
        if self.raw_frame is None: return None
        _, buf = cv2.imencode('.jpg', self.raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def get_corrected_jpeg(self):
        if self.corrected_frame is None: return None
        _, buf = cv2.imencode('.jpg', self.corrected_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def update_matrix(self):
        if self.raw_frame is None: return
        h, w = self.raw_frame.shape[:2]
        src = np.array([[c[0]*w, c[1]*h] for c in state["corners"]], dtype=np.float32)
        dst = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], dtype=np.float32)
        state["matrix"] = cv2.getPerspectiveTransform(src, dst)
    
    def get_status(self):
        return {
            "feet_detected": state["feet_detected"],
            "feet_x": state["feet_x"],
            "feet_y": state["feet_y"],
            "active_zones": state["active_zones"]
        }
    
    def get_config(self):
        return {
            "corners": state["corners"],
            "zones": state["zones"],
            "zone_id_counter": state["zone_id_counter"],
            "admin_bg": state["admin_bg"],
            "projection_bg": state["projection_bg"]
        }
    
    def get_state(self):
        return state
    
    def update_corners(self, corners):
        state["corners"] = corners
        self.update_matrix()
    
    def update_zones(self, zones, zone_id_counter=None):
        state["zones"] = zones
        if zone_id_counter is not None:
            state["zone_id_counter"] = zone_id_counter
    
    def save_config(self):
        return save_config_to_file()
    
    def load_config(self):
        if load_config_from_file():
            self.update_matrix()
            return True
        return False


# 全局实例
screen_processor = None

def init_screen_processor(camera_source=1, socketio=None):
    global screen_processor
    screen_processor = ScreenProcessor(camera_source, socketio)
    return screen_processor

def get_screen_processor():
    return screen_processor
