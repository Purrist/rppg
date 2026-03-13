# perception/perception_manager.py
# 感知管理器 - 整合所有感知模块，统一输出用户状态

import cv2
import numpy as np
import time
import threading
from typing import Dict, Any, Optional
from collections import deque

from .emotion_detector import EmotionDetector
from .heart_rate_detector import HeartRateDetector
from .environment_detector import EnvironmentDetector
from .body_state_detector import BodyStateDetector
from .eye_tracker import EyeTracker


class PerceptionManager:
    """感知管理器"""
    
    def __init__(self):
        self.emotion_detector = EmotionDetector()
        self.heart_rate_detector = HeartRateDetector()
        self.environment_detector = EnvironmentDetector()
        self.body_state_detector = BodyStateDetector()
        self.eye_tracker = EyeTracker()
        
        self.user_state = {
            "emotion": {"primary": "neutral", "confidence": 0.0, "valence": 0.5, "arousal": 0.5},
            "heart_rate": {"bpm": None, "hrv": None, "confidence": 0.0, "trend": "stable"},
            "environment": {"light_level": "normal", "light_value": 0, "person_count": 0, "person_present": False, "person_distance": None, "face_detected": False, "face_id": None},
            "body_state": {"posture": "unknown", "activity_level": 0.0, "activity_duration": 0, "head_pose": "frontal", "movement_frequency": 0.0, "stillness_duration": 0},
            "eye_state": {"blink_rate": 0, "blink_frequency": 0.0, "gaze_direction": "screen", "gaze_duration": 0, "attention_score": 0.0, "eye_contact": False},
            "overall": {"fatigue_level": 0.0, "engagement_level": 0.0, "comfort_level": 0.5, "state_summary": "normal"},
            "meta": {"last_update": 0, "frame_count": 0, "detection_success": True}
        }
        
        self.history = {"heart_rate": deque(maxlen=60), "emotion": deque(maxlen=30), "activity": deque(maxlen=100), "attention": deque(maxlen=60)}
        self.lock = threading.Lock()
    
    def process_frame(self, frame: np.ndarray, source: str = "tablet") -> Dict[str, Any]:
        if frame is None or frame.size == 0:
            return self.user_state
        
        with self.lock:
            try:
                env_result = self.environment_detector.detect(frame)
                self._update_environment(env_result)
                
                if env_result.get("person_present", False):
                    emotion_result = self.emotion_detector.detect(frame)
                    self._update_emotion(emotion_result)
                    
                    hr_result = self.heart_rate_detector.detect(frame)
                    self._update_heart_rate(hr_result)
                    
                    body_result = self.body_state_detector.detect(frame)
                    self._update_body_state(body_result)
                    
                    eye_result = self.eye_tracker.detect(frame)
                    self._update_eye_state(eye_result)
                    
                    self._calculate_overall_state()
                
                self.user_state["meta"]["last_update"] = time.time()
                self.user_state["meta"]["frame_count"] += 1
                self.user_state["meta"]["detection_success"] = True
            except Exception as e:
                print(f"[感知管理器] 处理错误: {e}")
                self.user_state["meta"]["detection_success"] = False
        
        return self.user_state
    
    def _update_environment(self, result: Dict):
        if not result: return
        env = self.user_state["environment"]
        env["light_level"] = result.get("light_level", "normal")
        env["light_value"] = result.get("light_value", 0)
        env["person_count"] = result.get("person_count", 0)
        env["person_present"] = result.get("person_present", False)
        env["person_distance"] = result.get("person_distance")
        env["face_detected"] = result.get("face_detected", False)
        env["face_id"] = result.get("face_id")
    
    def _update_emotion(self, result: Dict):
        if not result: return
        emotion = self.user_state["emotion"]
        emotion["primary"] = result.get("primary", "neutral")
        emotion["confidence"] = result.get("confidence", 0.0)
        emotion["valence"] = result.get("valence", 0.5)
        emotion["arousal"] = result.get("arousal", 0.5)
        self.history["emotion"].append({"emotion": emotion["primary"], "valence": emotion["valence"], "time": time.time()})
    
    def _update_heart_rate(self, result: Dict):
        if not result: return
        hr = self.user_state["heart_rate"]
        if result.get("confidence", 0) > 0.5:
            new_bpm = result.get("bpm")
            if new_bpm and hr["bpm"]:
                max_change = 5
                diff = new_bpm - hr["bpm"]
                if abs(diff) > max_change:
                    new_bpm = hr["bpm"] + (max_change if diff > 0 else -max_change)
            hr["bpm"] = new_bpm
            hr["hrv"] = result.get("hrv")
            hr["confidence"] = result.get("confidence", 0)
            hr["trend"] = result.get("trend", "stable")
            if new_bpm:
                self.history["heart_rate"].append({"bpm": new_bpm, "time": time.time()})
    
    def _update_body_state(self, result: Dict):
        if not result: return
        body = self.user_state["body_state"]
        body["posture"] = result.get("posture", "unknown")
        body["activity_level"] = result.get("activity_level", 0.0)
        body["head_pose"] = result.get("head_pose", "frontal")
        body["movement_frequency"] = result.get("movement_frequency", 0.0)
        self.history["activity"].append({"activity_level": body["activity_level"], "posture": body["posture"], "time": time.time()})
    
    def _update_eye_state(self, result: Dict):
        if not result: return
        eye = self.user_state["eye_state"]
        eye["blink_rate"] = result.get("blink_rate", 0)
        eye["blink_frequency"] = result.get("blink_frequency", 0.0)
        eye["gaze_direction"] = result.get("gaze_direction", "screen")
        eye["gaze_duration"] = result.get("gaze_duration", 0)
        eye["attention_score"] = result.get("attention_score", 0.0)
        eye["eye_contact"] = result.get("eye_contact", False)
        self.history["attention"].append({"attention_score": eye["attention_score"], "time": time.time()})
    
    def _calculate_overall_state(self):
        overall = self.user_state["overall"]
        fatigue = 0.0
        eye = self.user_state["eye_state"]
        if eye["blink_rate"] < 10: fatigue += 0.2
        if eye["gaze_duration"] > 30: fatigue += 0.2
        body = self.user_state["body_state"]
        if body["posture"] == "sitting" and body["stillness_duration"] > 1800: fatigue += 0.3
        hr = self.user_state["heart_rate"]
        if hr["bpm"] and hr["bpm"] < 60: fatigue += 0.2
        overall["fatigue_level"] = min(1.0, fatigue)
        
        engagement = 0.0
        if eye["attention_score"] > 0.7: engagement += 0.4
        if eye["eye_contact"]: engagement += 0.2
        if body["activity_level"] > 0.3: engagement += 0.2
        if self.user_state["emotion"]["valence"] > 0.6: engagement += 0.2
        overall["engagement_level"] = min(1.0, engagement)
        
        comfort = 0.5
        if self.user_state["emotion"]["valence"] > 0.6: comfort += 0.2
        if hr["bpm"] and 60 <= hr["bpm"] <= 100: comfort += 0.1
        if body["posture"] in ["sitting", "standing"]: comfort += 0.1
        overall["comfort_level"] = min(1.0, max(0.0, comfort))
        
        if overall["fatigue_level"] > 0.6: overall["state_summary"] = "fatigued"
        elif overall["engagement_level"] > 0.7: overall["state_summary"] = "engaged"
        elif overall["comfort_level"] < 0.4: overall["state_summary"] = "uncomfortable"
        else: overall["state_summary"] = "normal"
    
    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            return self.user_state.copy()
    
    def get_summary(self) -> Dict[str, Any]:
        state = self.user_state
        return {
            "emotion": state["emotion"]["primary"],
            "heart_rate": state["heart_rate"]["bpm"],
            "posture": state["body_state"]["posture"],
            "attention": state["eye_state"]["attention_score"],
            "fatigue": state["overall"]["fatigue_level"],
            "engagement": state["overall"]["engagement_level"],
            "summary": state["overall"]["state_summary"],
            "person_present": state["environment"]["person_present"],
        }
    
    def reset(self):
        with self.lock:
            self.history["heart_rate"].clear()
            self.history["emotion"].clear()
            self.history["activity"].clear()
            self.history["attention"].clear()
            self.heart_rate_detector.reset()
