# perception/perception_manager.py
# 感知管理器 - 整合所有检测

import cv2

# 抑制OpenCV警告
import logging
logging.getLogger('cv2').setLevel(logging.ERROR)

import numpy as np
import threading
from collections import deque
from typing import Dict, Any


class PerceptionManager:
    """感知管理器 - 整合所有检测"""
    
    def __init__(self):
        self.user_state = {
            "emotion": {"primary": "neutral", "confidence": 0.5, "valence": 0.5, "arousal": 0.5},
            "heart_rate": {"bpm": None, "hrv": None, "confidence": 0, "trend": "stable"},
            "environment": {"light_level": "normal", "light_value": 128, "person_present": False, 
                           "person_count": 0, "person_distance": None, "face_detected": False, "face_id": None},
            "body_state": {"posture": "unknown", "activity_level": 0, "activity_duration": 0,
                          "head_pose": None, "movement_frequency": 0, "stillness_duration": 0},
            "eye_state": {"blink_rate": 0, "blink_frequency": 0, "gaze_direction": None,
                         "gaze_duration": 0, "attention_score": 0.5, "eye_contact": False},
            "overall": {"fatigue_level": 0, "engagement_level": 0.5, "comfort_level": 0.5, 
                       "state_summary": "normal"},
        }
        
        self.history = {
            "heart_rate": deque(maxlen=60),
            "emotion": deque(maxlen=30),
            "activity": deque(maxlen=100),
        }
        
        self.lock = threading.Lock()
        self._last_frame_time = 0
        
        # 人脸检测器
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
    
    def process_frame(self, frame, source="tablet") -> Dict[str, Any]:
        """处理帧，返回用户状态 - 优化版"""
        if frame is None:
            return self.user_state
        
        with self.lock:
            try:
                # ⭐ 缩小图像加速处理
                h, w = frame.shape[:2]
                if w > 320:
                    scale = 320 / w
                    frame = cv2.resize(frame, (320, int(h * scale)))
                    h, w = frame.shape[:2]
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # 1. 环境检测
                self._detect_environment(frame, gray)
                
                # 2. 人脸检测 - 使用更快的参数
                faces = self.face_cascade.detectMultiScale(gray, 1.4, 6, minSize=(30, 30))
                person_present = len(faces) > 0
                
                self.user_state["environment"]["person_present"] = person_present
                self.user_state["environment"]["person_count"] = len(faces)
                self.user_state["environment"]["face_detected"] = person_present
                
                # 3. 如果有人，进行更多检测
                if person_present:
                    self._detect_emotion(frame, faces)
                    self._detect_body_state(frame, faces)
                    self._detect_eye_state(frame, faces)
                
                # 4. 综合状态
                self._calculate_overall()
                
            except Exception as e:
                pass  # ⭐ 静默处理错误
        
        return self.user_state
    
    def _detect_environment(self, frame, gray):
        """环境检测"""
        # 光照
        light_value = np.mean(gray)
        if light_value < 50:
            light_level = "dark"
        elif light_value > 200:
            light_level = "bright"
        else:
            light_level = "normal"
        
        self.user_state["environment"]["light_level"] = light_level
        self.user_state["environment"]["light_value"] = float(light_value)
    
    def _detect_emotion(self, frame, faces):
        """情绪检测（简化版）"""
        # 这里使用简化逻辑，实际可以接入深度学习模型
        self.user_state["emotion"]["primary"] = "neutral"
        self.user_state["emotion"]["confidence"] = 0.7
        self.user_state["emotion"]["valence"] = 0.5
        self.user_state["emotion"]["arousal"] = 0.5
    
    def _detect_body_state(self, frame, faces):
        """身体状态检测"""
        # 简化版
        self.user_state["body_state"]["posture"] = "sitting"
        self.user_state["body_state"]["activity_level"] = 0.3
    
    def _detect_eye_state(self, frame, faces):
        """眼部状态检测"""
        # 简化版
        self.user_state["eye_state"]["attention_score"] = 0.7
        self.user_state["eye_state"]["eye_contact"] = True
    
    def _calculate_overall(self):
        """计算综合状态"""
        fatigue = 0.0
        
        # 基于注意力
        if self.user_state["eye_state"]["attention_score"] < 0.5:
            fatigue += 0.3
        
        # 基于心率
        hr = self.user_state["heart_rate"]["bpm"]
        if hr and hr < 60:
            fatigue += 0.2
        
        # 基于活动量
        if self.user_state["body_state"]["activity_level"] < 0.2:
            fatigue += 0.2
        
        self.user_state["overall"]["fatigue_level"] = min(1.0, fatigue)
        
        # 参与度
        engagement = self.user_state["eye_state"]["attention_score"]
        self.user_state["overall"]["engagement_level"] = engagement
        
        # 状态总结
        if fatigue > 0.6:
            self.user_state["overall"]["state_summary"] = "fatigued"
        elif engagement > 0.7:
            self.user_state["overall"]["state_summary"] = "engaged"
        else:
            self.user_state["overall"]["state_summary"] = "normal"
    
    def get_state(self) -> Dict:
        with self.lock:
            return self.user_state.copy()
    
    def get_summary(self) -> Dict:
        """获取状态摘要"""
        with self.lock:
            return {
                "emotion": self.user_state["emotion"]["primary"],
                "heart_rate": self.user_state["heart_rate"]["bpm"],
                "posture": self.user_state["body_state"]["posture"],
                "attention": self.user_state["eye_state"]["attention_score"],
                "fatigue": self.user_state["overall"]["fatigue_level"],
                "summary": self.user_state["overall"]["state_summary"],
                "person_present": self.user_state["environment"]["person_present"],
            }
    
    def update_heart_rate(self, bpm: float, confidence: float = 1.0):
        """更新心率（由外部rPPG模块调用）"""
        with self.lock:
            self.user_state["heart_rate"]["bpm"] = bpm
            self.user_state["heart_rate"]["confidence"] = confidence
            self.history["heart_rate"].append(bpm)
            
            # 计算趋势
            if len(self.history["heart_rate"]) >= 10:
                recent = list(self.history["heart_rate"])[-10:]
                if recent[-1] > recent[0] + 5:
                    self.user_state["heart_rate"]["trend"] = "increasing"
                elif recent[-1] < recent[0] - 5:
                    self.user_state["heart_rate"]["trend"] = "decreasing"
                else:
                    self.user_state["heart_rate"]["trend"] = "stable"
