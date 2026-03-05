# -*- coding: utf-8 -*-
"""
地面投影交互系统 - Screen Processor
从 camera_calibrate.py 完整迁移
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import base64
import threading
import json
import os

# ============================================================================
# 配置文件路径
# ============================================================================
CONFIG_FILE = "projection_config.json"

# ============================================================================
# 平滑滤波器
# ============================================================================
class SmoothFilter:
    """自适应滤波器，快速响应大变化，平滑小抖动"""
    def __init__(self, alpha=0.5, threshold=30):
        self.alpha = alpha
        self.threshold = threshold
        self.value = None
    
    def update(self, new_value):
        if self.value is None:
            self.value = new_value
            return new_value
        diff = abs(new_value - self.value)
        alpha = 0.8 if diff > self.threshold else self.alpha
        self.value = alpha * new_value + (1 - alpha) * self.value
        return self.value

class PositionSmoother:
    """位置平滑器，处理X和Y坐标"""
    def __init__(self):
        self.x_filter = SmoothFilter(alpha=0.4, threshold=25)
        self.y_filter = SmoothFilter(alpha=0.4, threshold=25)
        self.last_x = None
        self.last_y = None
        self.last_time = 0
    
    def update(self, x, y, detected):
        if detected:
            smooth_x = self.x_filter.update(x)
            smooth_y = self.y_filter.update(y)
            self.last_x = smooth_x
            self.last_y = smooth_y
            self.last_time = time.time()
            return int(smooth_x), int(smooth_y), True
        elif self.last_x is not None and time.time() - self.last_time < 0.3:
            return int(self.last_x), int(self.last_y), True
        return x, y, False

# ============================================================================
# 全局状态
# ============================================================================
state = {
    "corners": [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]],
    "zones": [
        {"id": 1, "name": "1", "type": "rect", "points": [[50, 80], [180, 80], [180, 280], [50, 280]], "color": "#33B555"},
        {"id": 2, "name": "2", "type": "rect", "points": [[230, 80], [410, 80], [410, 280], [230, 280]], "color": "#FF7222"},
        {"id": 3, "name": "3", "type": "rect", "points": [[460, 80], [590, 80], [590, 280], [460, 280]], "color": "#2196F3"}
    ],
    "feet_x": 320,
    "feet_y": 180,
    "feet_detected": False,
    "active_zones": [],
    "matrix": None,
    "zone_id_counter": 4,
    "admin_bg": "#ffffff",
    "projection_bg": "#000000"
}

ZONE_COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", 
               "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B",
               "#4CAF50", "#3F51B5"]

# ============================================================================
# 配置保存/加载
# ============================================================================
def save_config_to_file():
    config = {
        "corners": state["corners"],
        "zones": state["zones"],
        "zone_id_counter": state["zone_id_counter"],
        "admin_bg": state["admin_bg"],
        "projection_bg": state["projection_bg"]
    }
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
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

# 启动时加载配置
load_config_from_file()

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
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # MediaPipe Pose
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
            model_complexity=1,
            smooth_landmarks=True
        )
        
        self.raw_frame = None
        self.corrected_frame = None
        self.running = True
        self.position_smoother = PositionSmoother()
        
        # 进度跟踪（用于游戏交互）
        self.progress = [0, 0, 0]
        self.hover_start = [0, 0, 0]
        
        # 启动处理线程
        threading.Thread(target=self._loop, daemon=True).start()
    
    def _loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # 水平+垂直翻转
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
                
                if left_ankle.visibility > 0.5 and right_ankle.visibility > 0.5:
                    l_pt = (int(left_ankle.x * w), int(left_ankle.y * h))
                    r_pt = (int(right_ankle.x * w), int(right_ankle.y * h))
                    
                    cv2.circle(frame, l_pt, 15, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 15, (0, 255, 0), -1)
                    cv2.line(frame, l_pt, r_pt, (0, 255, 255), 3)
                    
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
            
            # 平滑滤波
            smooth_x, smooth_y, smooth_detected = self.position_smoother.update(
                raw_feet_x, raw_feet_y, raw_feet_detected
            )
            
            # 区域碰撞检测
            active_zones = []
            active_zone_index = -1
            if smooth_detected:
                for i, zone in enumerate(state["zones"]):
                    if self._point_in_zone(smooth_x, smooth_y, zone):
                        active_zones.append(zone["id"])
                        active_zone_index = i
            
            # 更新全局状态
            state["feet_x"] = smooth_x
            state["feet_y"] = smooth_y
            state["feet_detected"] = smooth_detected
            state["active_zones"] = active_zones
            
            # 更新进度（用于游戏交互）
            now = time.time()
            for i in range(3):
                if i == active_zone_index:
                    if self.hover_start[i] == 0:
                        self.hover_start[i] = now
                    self.progress[i] = min(100, int((now - self.hover_start[i]) / 2.0 * 100))
                else:
                    if self.hover_start[i] != 0 and now - self.hover_start[i] > 0.5:
                        self.hover_start[i] = 0
                        self.progress[i] = 0
            
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
            
            # 绘制区域
            for zone in state["zones"]:
                self._draw_zone(corrected, zone, zone["id"] in active_zones)
            
            # 绘制脚部位置
            if smooth_detected:
                cv2.circle(corrected, (smooth_x, smooth_y), 20, (0, 200, 0), -1)
            
            self.raw_frame = frame
            self.corrected_frame = corrected
            time.sleep(0.005)
    
    def _point_in_zone(self, x, y, zone):
        """判断点是否在区域内"""
        if zone.get("type") == "circle":
            cx, cy, r = int(zone["center"][0]), int(zone["center"][1]), int(zone["radius"])
            return (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2
        else:
            pts = np.array(zone["points"], dtype=np.int32)
            return cv2.pointPolygonTest(pts, (x, y), False) >= 0
    
    def _draw_zone(self, img, zone, is_active):
        """绘制区域"""
        hex_color = zone["color"].lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        bgr = (rgb[2], rgb[1], rgb[0])
        
        if zone.get("type") == "circle":
            cx, cy, r = int(zone["center"][0]), int(zone["center"][1]), int(zone["radius"])
            cv2.circle(img, (cx, cy), r, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.circle(overlay, (cx, cy), r, bgr, -1)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            cv2.putText(img, zone.get("name", str(zone["id"])), (cx-10, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)
        else:
            pts = np.array(zone["points"], dtype=np.int32)
            cv2.polylines(img, [pts], True, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.fillPoly(overlay, [pts], bgr)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            cx = int(np.mean([p[0] for p in zone["points"]]))
            cy = int(np.mean([p[1] for p in zone["points"]]))
            cv2.putText(img, zone.get("name", str(zone["id"])), (cx-10, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)
    
    def get_raw_jpeg(self):
        """获取原始画面的JPEG"""
        if self.raw_frame is None: return None
        _, buf = cv2.imencode('.jpg', self.raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def get_corrected_jpeg(self):
        """获取校正后画面的JPEG"""
        if self.corrected_frame is None: return None
        _, buf = cv2.imencode('.jpg', self.corrected_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def update_matrix(self):
        """更新透视变换矩阵"""
        if self.raw_frame is None: return
        h, w = self.raw_frame.shape[:2]
        src = np.array([[c[0]*w, c[1]*h] for c in state["corners"]], dtype=np.float32)
        dst = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], dtype=np.float32)
        state["matrix"] = cv2.getPerspectiveTransform(src, dst)
    
    def get_state(self):
        """获取全局状态"""
        return state
    
    def get_config(self):
        """获取配置"""
        return {
            "corners": state["corners"],
            "zones": state["zones"],
            "zone_id_counter": state["zone_id_counter"],
            "admin_bg": state["admin_bg"],
            "projection_bg": state["projection_bg"]
        }
    
    def update_corners(self, corners):
        """更新校准点"""
        state["corners"] = corners
        self.update_matrix()
    
    def update_zones(self, zones, zone_id_counter=None):
        """更新区域"""
        state["zones"] = zones
        if zone_id_counter is not None:
            state["zone_id_counter"] = zone_id_counter
    
    def update_settings(self, admin_bg=None, projection_bg=None):
        """更新设置"""
        if admin_bg is not None:
            state["admin_bg"] = admin_bg
        if projection_bg is not None:
            state["projection_bg"] = projection_bg
    
    def get_status(self):
        """获取实时状态"""
        return {
            "feet_detected": state["feet_detected"],
            "feet_x": state["feet_x"],
            "feet_y": state["feet_y"],
            "active_zones": state["active_zones"]
        }
    
    def save_config(self):
        """保存配置到文件"""
        return save_config_to_file()
    
    def load_config(self):
        """从文件加载配置"""
        if load_config_from_file():
            self.update_matrix()
            return True
        return False
    
    def get_latest(self):
        """获取最新的处理数据（用于Socket推送）"""
        # 获取校正后的JPEG并转为base64
        if self.corrected_frame is not None:
            _, buf = cv2.imencode('.jpg', self.corrected_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            image_base64 = base64.b64encode(buf).decode('utf-8')
        else:
            image_base64 = ""
        
        # 计算命中索引
        hit_index = -1
        for i, p in enumerate(self.progress):
            if p >= 100:
                hit_index = i
                break
        
        return {
            "image": image_base64,
            "interact": {
                "progress": self.progress.copy(),
                "hit_index": hit_index
            },
            "status": self.get_status(),
            "calibration": {
                "points": state["corners"],
                "holes": state["zones"],
                "calibrated": state["matrix"] is not None
            }
        }

# 创建全局处理器实例
screen_processor = None

def init_screen_processor(camera_source=1, socketio=None):
    """初始化屏幕处理器"""
    global screen_processor
    screen_processor = ScreenProcessor(camera_source, socketio)
    return screen_processor

def get_screen_processor():
    """获取屏幕处理器实例"""
    return screen_processor
