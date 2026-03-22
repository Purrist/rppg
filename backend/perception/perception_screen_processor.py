# perception/perception_screen_processor.py
# 投影摄像头处理 - 脚部检测

import cv2
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
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "corners": state["corners"],
                "zones": state["zones"],
                "zone_id_counter": state["zone_id_counter"],
                "admin_bg": state["admin_bg"],
                "projection_bg": state["projection_bg"]
            }, f, indent=2)
        return True
    except:
        return False


def load_config_from_file():
    global state
    if not os.path.exists(CONFIG_FILE):
        return False
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if "corners" in config: state["corners"] = config["corners"]
        if "zones" in config: state["zones"] = config["zones"]
        if "zone_id_counter" in config: state["zone_id_counter"] = config["zone_id_counter"]
        if "admin_bg" in config: state["admin_bg"] = config["admin_bg"]
        if "projection_bg" in config: state["projection_bg"] = config["projection_bg"]
        return True
    except:
        return False


# ============================================================================
# 处理器类
# ============================================================================
class ScreenProcessor:
    def __init__(self, camera_source=1, socketio=None):
        self.socketio = socketio
        
        # 打开摄像头
        self.cap = cv2.VideoCapture(camera_source)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        
        # 摄像头设置
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
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
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.005)
                continue
            
            frame = cv2.flip(frame, 0)
            frame = cv2.flip(frame, 1)
            
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
                
                if left_ankle.visibility > 0.4 and right_ankle.visibility > 0.4:
                    l_pt = (int(left_ankle.x * w), int(left_ankle.y * h))
                    r_pt = (int(right_ankle.x * w), int(right_ankle.y * h))
                    
                    cv2.circle(frame, l_pt, 15, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 15, (0, 255, 0), -1)
                    
                    center = ((l_pt[0] + r_pt[0]) // 2, (l_pt[1] + r_pt[1]) // 2)
                    cv2.circle(frame, center, 10, (255, 0, 255), -1)
                    
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
