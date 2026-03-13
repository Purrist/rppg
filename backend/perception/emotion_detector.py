# perception/emotion_detector.py
# 情绪检测模块

import cv2
import numpy as np
from typing import Dict, Any, Optional
from collections import deque
import time

try:
    from deepface import DeepFace
    HAS_DEEPFACE = True
except ImportError:
    HAS_DEEPFACE = False
    print("[情绪检测] DeepFace未安装，使用简化版情绪检测")

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class EmotionDetector:
    EMOTION_VALENCE = {"happy": 0.9, "surprise": 0.6, "neutral": 0.5, "fear": 0.3, "sad": 0.2, "angry": 0.2, "disgust": 0.2}
    EMOTION_AROUSAL = {"angry": 0.9, "surprise": 0.8, "happy": 0.7, "fear": 0.7, "sad": 0.3, "neutral": 0.3, "disgust": 0.5}
    
    def __init__(self):
        self.last_emotion = "neutral"
        self.last_confidence = 0.0
        self.emotion_history = deque(maxlen=10)
        if HAS_MEDIAPIPE:
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.5)
        self.frame_count = 0
        self.process_every_n = 5
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        self.frame_count += 1
        if self.frame_count % self.process_every_n != 0:
            return {"primary": self.last_emotion, "confidence": self.last_confidence, "valence": self.EMOTION_VALENCE.get(self.last_emotion, 0.5), "arousal": self.EMOTION_AROUSAL.get(self.last_emotion, 0.5)}
        
        result = None
        if HAS_DEEPFACE:
            result = self._detect_with_deepface(frame)
        else:
            result = self._detect_simple(frame)
        
        if result:
            self.emotion_history.append(result)
            smoothed = self._smooth_emotion()
            self.last_emotion = smoothed["primary"]
            self.last_confidence = smoothed["confidence"]
            return smoothed
        
        return {"primary": self.last_emotion, "confidence": self.last_confidence, "valence": self.EMOTION_VALENCE.get(self.last_emotion, 0.5), "arousal": self.EMOTION_AROUSAL.get(self.last_emotion, 0.5)}
    
    def _detect_with_deepface(self, frame: np.ndarray) -> Optional[Dict]:
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = DeepFace.analyze(rgb_frame, actions=['emotion'], enforce_detection=False, silent=True)
            if isinstance(result, list): result = result[0]
            emotion = result.get('dominant_emotion', 'neutral')
            emotion_scores = result.get('emotion', {})
            confidence = emotion_scores.get(emotion, 0) / 100.0
            return {"primary": emotion, "confidence": confidence, "valence": self.EMOTION_VALENCE.get(emotion, 0.5), "arousal": self.EMOTION_AROUSAL.get(emotion, 0.5)}
        except Exception as e:
            return None
    
    def _detect_simple(self, frame: np.ndarray) -> Optional[Dict]:
        try:
            if not HAS_MEDIAPIPE: return None
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)
            if results.detections:
                return {"primary": "neutral", "confidence": 0.6, "valence": 0.5, "arousal": 0.3}
            return None
        except Exception as e:
            return None
    
    def _smooth_emotion(self) -> Dict:
        if not self.emotion_history:
            return {"primary": "neutral", "confidence": 0.5, "valence": 0.5, "arousal": 0.3}
        emotion_counts = {}
        total_confidence = total_valence = total_arousal = 0
        for e in self.emotion_history:
            emotion = e["primary"]
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            total_confidence += e["confidence"]
            total_valence += e["valence"]
            total_arousal += e["arousal"]
        n = len(self.emotion_history)
        primary = max(emotion_counts, key=emotion_counts.get)
        return {"primary": primary, "confidence": total_confidence / n, "valence": total_valence / n, "arousal": total_arousal / n}
