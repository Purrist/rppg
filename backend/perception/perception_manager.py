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
    """
    感知管理器
    
    整合所有感知模块，统一输出用户状态向量：
    - 情绪状态
    - 心率与HRV
    - 环境数据
    - 身体状态
    - 眼部状态
    """
    
    def __init__(self):
        # 初始化各感知模块
        self.emotion_detector = EmotionDetector()
        self.heart_rate_detector = HeartRateDetector()
        self.environment_detector = EnvironmentDetector()
        self.body_state_detector = BodyStateDetector()
        self.eye_tracker = EyeTracker()
        
        # 用户状态
        self.user_state = {
            # 情绪状态
            "emotion": {
                "primary": "neutral",
                "confidence": 0.0,
                "valence": 0.5,  # 情感效价 (0-1, 负面-正面)
                "arousal": 0.5,  # 情感唤醒度 (0-1, 平静-激动)
            },
            
            # 心率状态
            "heart_rate": {
                "bpm": None,
                "hrv": None,
                "confidence": 0.0,
                "trend": "stable",  # stable, rising, falling
            },
            
            # 环境状态
            "environment": {
                "light_level": "normal",  # dark, dim, normal, bright
                "light_value": 0,
                "person_count": 0,
                "person_present": False,
                "person_distance": None,
                "face_detected": False,
                "face_id": None,
            },
            
            # 身体状态
            "body_state": {
                "posture": "unknown",  # sitting, standing, walking, lying, unknown
                "activity_level": 0.0,  # 0-1
                "activity_duration": 0,
                "head_pose": "frontal",  # frontal, left, right, up, down
                "movement_frequency": 0.0,
                "stillness_duration": 0,
            },
            
            # 眼部状态
            "eye_state": {
                "blink_rate": 0,  # 每分钟眨眼次数
                "blink_frequency": 0.0,
                "gaze_direction": "screen",  # screen, away, closed
                "gaze_duration": 0,
                "attention_score": 0.0,  # 0-1
                "eye_contact": False,
            },
            
            # 综合状态
            "overall": {
                "fatigue_level": 0.0,  # 0-1
                "engagement_level": 0.0,  # 0-1
                "comfort_level": 0.5,  # 0-1
                "state_summary": "normal",
            },
            
            # 元数据
            "meta": {
                "last_update": 0,
                "frame_count": 0,
                "detection_success": True,
            }
        }
        
        # 历史记录（用于趋势分析）
        self.history = {
            "heart_rate": deque(maxlen=60),
            "emotion": deque(maxlen=30),
            "activity": deque(maxlen=100),
            "attention": deque(maxlen=60),
        }
        
        # 线程锁
        self.lock = threading.Lock()
        
        # 性能统计
        self.process_times = {}
    
    def process_frame(self, frame: np.ndarray, source: str = "tablet") -> Dict[str, Any]:
        """
        处理单帧图像，更新用户状态
        
        Args:
            frame: BGR图像
            source: 图像来源 ("tablet" 或 "projection")
        
        Returns:
            更新后的用户状态
        """
        start_time = time.time()
        
        if frame is None or frame.size == 0:
            return self.user_state
        
        with self.lock:
            try:
                # 1. 环境检测（最快，先做）
                env_result = self.environment_detector.detect(frame)
                self._update_environment(env_result)
                
                # 2. 如果检测到人，进行后续检测
                if env_result.get("person_present", False):
                    # 并行处理各模块
                    # 情绪检测
                    emotion_result = self.emotion_detector.detect(frame)
                    self._update_emotion(emotion_result)
                    
                    # 心率检测
                    hr_result = self.heart_rate_detector.detect(frame)
                    self._update_heart_rate(hr_result)
                    
                    # 身体状态检测
                    body_result = self.body_state_detector.detect(frame)
                    self._update_body_state(body_result)
                    
                    # 眼部追踪
                    eye_result = self.eye_tracker.detect(frame)
                    self._update_eye_state(eye_result)
                    
                    # 计算综合状态
                    self._calculate_overall_state()
                
                # 更新元数据
                self.user_state["meta"]["last_update"] = time.time()
                self.user_state["meta"]["frame_count"] += 1
                self.user_state["meta"]["detection_success"] = True
                
            except Exception as e:
                print(f"[感知管理器] 处理错误: {e}")
                self.user_state["meta"]["detection_success"] = False
        
        # 记录处理时间
        self.process_times[source] = time.time() - start_time
        
        return self.user_state
    
    def _update_environment(self, result: Dict):
        """更新环境状态"""
        if not result:
            return
        
        env = self.user_state["environment"]
        env["light_level"] = result.get("light_level", "normal")
        env["light_value"] = result.get("light_value", 0)
        env["person_count"] = result.get("person_count", 0)
        env["person_present"] = result.get("person_present", False)
        env["person_distance"] = result.get("person_distance")
        env["face_detected"] = result.get("face_detected", False)
        env["face_id"] = result.get("face_id")
    
    def _update_emotion(self, result: Dict):
        """更新情绪状态"""
        if not result:
            return
        
        emotion = self.user_state["emotion"]
        emotion["primary"] = result.get("primary", "neutral")
        emotion["confidence"] = result.get("confidence", 0.0)
        emotion["valence"] = result.get("valence", 0.5)
        emotion["arousal"] = result.get("arousal", 0.5)
        
        # 记录历史
        self.history["emotion"].append({
            "emotion": emotion["primary"],
            "valence": emotion["valence"],
            "time": time.time()
        })
    
    def _update_heart_rate(self, result: Dict):
        """更新心率状态"""
        if not result:
            return
        
        hr = self.user_state["heart_rate"]
        
        # 只在置信度足够时更新
        if result.get("confidence", 0) > 0.5:
            new_bpm = result.get("bpm")
            
            # 平滑更新（避免跳变）
            if new_bpm and hr["bpm"]:
                # 限制变化幅度
                max_change = 5  # 每次最多变化5 BPM
                diff = new_bpm - hr["bpm"]
                if abs(diff) > max_change:
                    new_bpm = hr["bpm"] + (max_change if diff > 0 else -max_change)
            
            hr["bpm"] = new_bpm
            hr["hrv"] = result.get("hrv")
            hr["confidence"] = result.get("confidence", 0)
            
            # 计算趋势
            if len(self.history["heart_rate"]) > 10:
                recent = list(self.history["heart_rate"])[-10:]
                avg_recent = np.mean([r["bpm"] for r in recent if r["bpm"]])
                if new_bpm:
                    if new_bpm > avg_recent + 3:
                        hr["trend"] = "rising"
                    elif new_bpm < avg_recent - 3:
                        hr["trend"] = "falling"
                    else:
                        hr["trend"] = "stable"
            
            # 记录历史
            if new_bpm:
                self.history["heart_rate"].append({
                    "bpm": new_bpm,
                    "time": time.time()
                })
    
    def _update_body_state(self, result: Dict):
        """更新身体状态"""
        if not result:
            return
        
        body = self.user_state["body_state"]
        body["posture"] = result.get("posture", "unknown")
        body["activity_level"] = result.get("activity_level", 0.0)
        body["head_pose"] = result.get("head_pose", "frontal")
        body["movement_frequency"] = result.get("movement_frequency", 0.0)
        
        # 记录历史
        self.history["activity"].append({
            "activity_level": body["activity_level"],
            "posture": body["posture"],
            "time": time.time()
        })
    
    def _update_eye_state(self, result: Dict):
        """更新眼部状态"""
        if not result:
            return
        
        eye = self.user_state["eye_state"]
        eye["blink_rate"] = result.get("blink_rate", 0)
        eye["blink_frequency"] = result.get("blink_frequency", 0.0)
        eye["gaze_direction"] = result.get("gaze_direction", "screen")
        eye["gaze_duration"] = result.get("gaze_duration", 0)
        eye["attention_score"] = result.get("attention_score", 0.0)
        eye["eye_contact"] = result.get("eye_contact", False)
        
        # 记录历史
        self.history["attention"].append({
            "attention_score": eye["attention_score"],
            "time": time.time()
        })
    
    def _calculate_overall_state(self):
        """计算综合状态"""
        overall = self.user_state["overall"]
        
        # 疲劳度计算
        fatigue = 0.0
        # 眨眼频率低 + 注视时间长 = 疲劳
        eye = self.user_state["eye_state"]
        if eye["blink_rate"] < 10:  # 正常15-20次/分钟
            fatigue += 0.2
        if eye["gaze_duration"] > 30:  # 注视超过30秒
            fatigue += 0.2
        
        # 久坐
        body = self.user_state["body_state"]
        if body["posture"] == "sitting" and body["stillness_duration"] > 1800:  # 30分钟
            fatigue += 0.3
        
        # 心率低
        hr = self.user_state["heart_rate"]
        if hr["bpm"] and hr["bpm"] < 60:
            fatigue += 0.2
        
        overall["fatigue_level"] = min(1.0, fatigue)
        
        # 参与度计算
        engagement = 0.0
        if eye["attention_score"] > 0.7:
            engagement += 0.4
        if eye["eye_contact"]:
            engagement += 0.2
        if body["activity_level"] > 0.3:
            engagement += 0.2
        if self.user_state["emotion"]["valence"] > 0.6:
            engagement += 0.2
        
        overall["engagement_level"] = min(1.0, engagement)
        
        # 舒适度计算
        comfort = 0.5
        if self.user_state["emotion"]["valence"] > 0.6:
            comfort += 0.2
        if hr["bpm"] and 60 <= hr["bpm"] <= 100:
            comfort += 0.1
        if body["posture"] in ["sitting", "standing"]:
            comfort += 0.1
        
        overall["comfort_level"] = min(1.0, max(0.0, comfort))
        
        # 状态总结
        if overall["fatigue_level"] > 0.6:
            overall["state_summary"] = "fatigued"
        elif overall["engagement_level"] > 0.7:
            overall["state_summary"] = "engaged"
        elif overall["comfort_level"] < 0.4:
            overall["state_summary"] = "uncomfortable"
        else:
            overall["state_summary"] = "normal"
    
    def get_state(self) -> Dict[str, Any]:
        """获取当前用户状态"""
        with self.lock:
            return self.user_state.copy()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取状态摘要（简化版）"""
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
        """重置状态"""
        with self.lock:
            self.history["heart_rate"].clear()
            self.history["emotion"].clear()
            self.history["activity"].clear()
            self.history["attention"].clear()
            
            self.heart_rate_detector.reset()
