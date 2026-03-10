# perception/eye_tracker.py
# 眼部追踪模块

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
from collections import deque
import time

# 尝试导入MediaPipe
try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class EyeTracker:
    """
    眼部追踪器
    
    检测：
    - blink_rate: 眨眼频率（每分钟次数）
    - blink_frequency: 眨眼频率（Hz）
    - gaze_direction: 注视方向 (screen, away, closed)
    - gaze_duration: 注视时间
    - attention_score: 注意力分数 (0-1)
    - eye_contact: 是否有眼神接触
    """
    
    # 眨眼检测参数
    EAR_THRESHOLD = 0.2  # 眼睛纵横比阈值
    EAR_CONSEC_FRAMES = 3  # 连续帧数
    
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        
        # MediaPipe Face Mesh
        if HAS_MEDIAPIPE:
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            
            # 眼睛关键点索引
            # 左眼
            self.LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
            # 右眼
            self.RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
            # 虹膜
            self.LEFT_IRIS = [468, 469, 470, 471, 472]
            self.RIGHT_IRIS = [473, 474, 475, 476, 477]
        
        # 眨眼检测
        self.blink_counter = 0
        self.blink_total = 0
        self.blink_start_time = time.time()
        self.blink_history = deque(maxlen=1800)  # 60秒历史
        
        # 注视检测
        self.gaze_start_time = None
        self.current_gaze = "unknown"
        self.gaze_history = deque(maxlen=300)
        
        # 注意力
        self.attention_history = deque(maxlen=300)
        
        # 眼睛状态
        self.eyes_closed = False
        self.last_ear = 0.3
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        """检测眼部状态"""
        result = {
            "blink_rate": 0,
            "blink_frequency": 0.0,
            "gaze_direction": "unknown",
            "gaze_duration": 0,
            "attention_score": 0.0,
            "eye_contact": False,
        }
        
        if frame is None or frame.size == 0:
            return result
        
        try:
            if HAS_MEDIAPIPE:
                result = self._detect_with_mediapipe(frame)
            else:
                result = self._detect_simple(frame)
            
            # 计算眨眼频率
            result["blink_rate"] = self._calculate_blink_rate()
            result["blink_frequency"] = result["blink_rate"] / 60.0
            
            # 计算注意力分数
            result["attention_score"] = self._calculate_attention()
            
            # 记录历史
            self.attention_history.append({
                "attention": result["attention_score"],
                "gaze": result["gaze_direction"],
                "time": time.time()
            })
            
        except Exception as e:
            print(f"[眼部追踪] 错误: {e}")
        
        return result
    
    def _detect_with_mediapipe(self, frame: np.ndarray) -> Dict[str, Any]:
        """使用MediaPipe检测"""
        result = {
            "blink_rate": 0,
            "blink_frequency": 0.0,
            "gaze_direction": "unknown",
            "gaze_duration": 0,
            "attention_score": 0.0,
            "eye_contact": False,
        }
        
        h, w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        face_mesh_result = self.face_mesh.process(rgb_frame)
        
        if face_mesh_result.multi_face_landmarks:
            landmarks = face_mesh_result.multi_face_landmarks[0].landmark
            
            # 计算眼睛纵横比(EAR)
            left_ear = self._calculate_ear(landmarks, self.LEFT_EYE_INDICES, w, h)
            right_ear = self._calculate_ear(landmarks, self.RIGHT_EYE_INDICES, w, h)
            avg_ear = (left_ear + right_ear) / 2
            
            # 平滑EAR
            avg_ear = 0.7 * self.last_ear + 0.3 * avg_ear
            self.last_ear = avg_ear
            
            # 眨眼检测
            if avg_ear < self.EAR_THRESHOLD:
                if not self.eyes_closed:
                    self.blink_counter += 1
                    if self.blink_counter >= self.EAR_CONSEC_FRAMES:
                        self.eyes_closed = True
                        self.blink_total += 1
                        self.blink_history.append(time.time())
            else:
                if self.eyes_closed:
                    self.eyes_closed = False
                self.blink_counter = 0
            
            # 注视方向检测
            # 使用虹膜位置判断
            if len(landmarks) > 477:  # 有虹膜检测
                left_iris_x = landmarks[468].x
                right_iris_x = landmarks[473].x
                
                # 计算虹膜相对于眼睛中心的位置
                avg_iris_x = (left_iris_x + right_iris_x) / 2
                
                if avg_iris_x < 0.45:
                    result["gaze_direction"] = "left"
                elif avg_iris_x > 0.55:
                    result["gaze_direction"] = "right"
                elif self.eyes_closed:
                    result["gaze_direction"] = "closed"
                else:
                    result["gaze_direction"] = "screen"
            else:
                # 简化判断
                if self.eyes_closed:
                    result["gaze_direction"] = "closed"
                else:
                    result["gaze_direction"] = "screen"
            
            # 眼神接触（正视前方）
            result["eye_contact"] = result["gaze_direction"] == "screen"
            
            # 注视时间
            if result["gaze_direction"] == self.current_gaze:
                if self.gaze_start_time:
                    result["gaze_duration"] = time.time() - self.gaze_start_time
            else:
                self.current_gaze = result["gaze_direction"]
                self.gaze_start_time = time.time()
            
            # 记录注视历史
            self.gaze_history.append({
                "gaze": result["gaze_direction"],
                "time": time.time()
            })
        
        return result
    
    def _detect_simple(self, frame: np.ndarray) -> Dict[str, Any]:
        """简化版检测"""
        result = {
            "blink_rate": 15,  # 默认正常值
            "blink_frequency": 0.25,
            "gaze_direction": "screen",
            "gaze_duration": 0,
            "attention_score": 0.5,
            "eye_contact": True,
        }
        
        # 使用帧差法检测眨眼
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        if hasattr(self, 'prev_gray') and self.prev_gray is not None:
            diff = cv2.absdiff(gray, self.prev_gray)
            
            # 检测眼睛区域的变化
            h, w = diff.shape
            eye_region = diff[int(h*0.2):int(h*0.4), int(w*0.3):int(w*0.7)]
            
            if eye_region.size > 0:
                change = np.mean(eye_region)
                
                # 简单的眨眼检测
                if change > 30:
                    if not self.eyes_closed:
                        self.eyes_closed = True
                        self.blink_total += 1
                        self.blink_history.append(time.time())
                else:
                    self.eyes_closed = False
        
        self.prev_gray = gray
        return result
    
    def _calculate_ear(self, landmarks, indices, w, h) -> float:
        """计算眼睛纵横比(Eye Aspect Ratio)"""
        # 获取关键点
        p1 = landmarks[indices[0]]
        p2 = landmarks[indices[1]]
        p3 = landmarks[indices[2]]
        p4 = landmarks[indices[3]]
        p5 = landmarks[indices[4]]
        p6 = landmarks[indices[5]]
        
        # 计算垂直距离
        vertical_1 = np.sqrt((p2.x - p6.x)**2 + (p2.y - p6.y)**2)
        vertical_2 = np.sqrt((p3.x - p5.x)**2 + (p3.y - p5.y)**2)
        
        # 计算水平距离
        horizontal = np.sqrt((p1.x - p4.x)**2 + (p1.y - p4.y)**2)
        
        # EAR
        if horizontal > 0:
            ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
        else:
            ear = 0.3
        
        return ear
    
    def _calculate_blink_rate(self) -> int:
        """计算眨眼频率（每分钟）"""
        if len(self.blink_history) < 2:
            return 0
        
        # 过滤最近60秒的眨眼
        now = time.time()
        recent_blinks = [t for t in self.blink_history if now - t < 60]
        
        return len(recent_blinks)
    
    def _calculate_attention(self) -> float:
        """计算注意力分数"""
        if len(self.gaze_history) < 10:
            return 0.5
        
        # 基于注视方向计算
        recent = list(self.gaze_history)[-60:]  # 最近2秒
        
        screen_count = sum(1 for g in recent if g["gaze"] == "screen")
        closed_count = sum(1 for g in recent if g["gaze"] == "closed")
        
        total = len(recent)
        if total == 0:
            return 0.5
        
        # 注视屏幕的比例
        screen_ratio = screen_count / total
        
        # 闭眼惩罚
        closed_penalty = closed_count / total * 0.5
        
        attention = screen_ratio - closed_penalty
        
        return max(0.0, min(1.0, attention))
    
    def get_fatigue_indicator(self) -> float:
        """获取疲劳指标"""
        blink_rate = self._calculate_blink_rate()
        
        # 正常眨眼频率：15-20次/分钟
        # 低于10次或高于30次可能表示疲劳
        if blink_rate < 10:
            return 0.7  # 眨眼太少，可能疲劳
        elif blink_rate > 30:
            return 0.8  # 眨眼太多，眼睛干涩
        else:
            return 0.3  # 正常
    
    def get_attention_trend(self) -> str:
        """获取注意力趋势"""
        if len(self.attention_history) < 30:
            return "stable"
        
        recent = list(self.attention_history)[-30:]
        scores = [a["attention"] for a in recent]
        
        if scores[-1] > scores[0] + 0.1:
            return "improving"
        elif scores[-1] < scores[0] - 0.1:
            return "declining"
        else:
            return "stable"
