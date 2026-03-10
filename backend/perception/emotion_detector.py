# perception/emotion_detector.py
# 情绪检测模块

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
from collections import deque
import time

# 尝试导入DeepFace
try:
    from deepface import DeepFace
    HAS_DEEPFACE = True
except ImportError:
    HAS_DEEPFACE = False
    print("[情绪检测] DeepFace未安装，使用简化版情绪检测")

# 尝试导入MediaPipe
try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class EmotionDetector:
    """
    情绪检测器
    
    检测用户的情绪状态：
    - primary: 主要情绪 (happy, sad, angry, fear, surprise, neutral, disgust)
    - confidence: 置信度
    - valence: 情感效价 (0-1, 负面-正面)
    - arousal: 情感唤醒度 (0-1, 平静-激动)
    """
    
    # 情绪到效价的映射
    EMOTION_VALENCE = {
        "happy": 0.9,
        "surprise": 0.6,
        "neutral": 0.5,
        "fear": 0.3,
        "sad": 0.2,
        "angry": 0.2,
        "disgust": 0.2,
    }
    
    # 情绪到唤醒度的映射
    EMOTION_AROUSAL = {
        "angry": 0.9,
        "surprise": 0.8,
        "happy": 0.7,
        "fear": 0.7,
        "sad": 0.3,
        "neutral": 0.3,
        "disgust": 0.5,
    }
    
    def __init__(self):
        self.last_emotion = "neutral"
        self.last_confidence = 0.0
        self.last_time = 0
        
        # 情绪历史（平滑用）
        self.emotion_history = deque(maxlen=10)
        
        # MediaPipe人脸检测（用于简化版）
        if HAS_MEDIAPIPE:
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5
            )
        
        # 跳帧处理（情绪检测较慢）
        self.frame_count = 0
        self.process_every_n = 5  # 每5帧处理一次
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        检测情绪
        
        Args:
            frame: BGR图像
        
        Returns:
            {
                "primary": "happy",
                "confidence": 0.85,
                "valence": 0.9,
                "arousal": 0.7
            }
        """
        self.frame_count += 1
        
        # 跳帧处理
        if self.frame_count % self.process_every_n != 0:
            return {
                "primary": self.last_emotion,
                "confidence": self.last_confidence,
                "valence": self.EMOTION_VALENCE.get(self.last_emotion, 0.5),
                "arousal": self.EMOTION_AROUSAL.get(self.last_emotion, 0.5)
            }
        
        result = None
        
        if HAS_DEEPFACE:
            result = self._detect_with_deepface(frame)
        else:
            result = self._detect_simple(frame)
        
        if result:
            # 平滑处理
            self.emotion_history.append(result)
            smoothed = self._smooth_emotion()
            
            self.last_emotion = smoothed["primary"]
            self.last_confidence = smoothed["confidence"]
            self.last_time = time.time()
            
            return smoothed
        
        return {
            "primary": self.last_emotion,
            "confidence": self.last_confidence,
            "valence": self.EMOTION_VALENCE.get(self.last_emotion, 0.5),
            "arousal": self.EMOTION_AROUSAL.get(self.last_emotion, 0.5)
        }
    
    def _detect_with_deepface(self, frame: np.ndarray) -> Optional[Dict]:
        """使用DeepFace检测情绪"""
        try:
            # DeepFace需要RGB图像
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 分析情绪
            result = DeepFace.analyze(
                rgb_frame,
                actions=['emotion'],
                enforce_detection=False,
                silent=True
            )
            
            if isinstance(result, list):
                result = result[0]
            
            emotion = result.get('dominant_emotion', 'neutral')
            emotion_scores = result.get('emotion', {})
            confidence = emotion_scores.get(emotion, 0) / 100.0
            
            return {
                "primary": emotion,
                "confidence": confidence,
                "valence": self.EMOTION_VALENCE.get(emotion, 0.5),
                "arousal": self.EMOTION_AROUSAL.get(emotion, 0.5)
            }
            
        except Exception as e:
            print(f"[情绪检测] DeepFace错误: {e}")
            return None
    
    def _detect_simple(self, frame: np.ndarray) -> Optional[Dict]:
        """简化版情绪检测（基于人脸检测）"""
        try:
            if not HAS_MEDIAPIPE:
                return None
            
            # 检测人脸
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)
            
            if results.detections:
                # 有人脸，返回中性情绪
                # 实际应用中可以基于面部特征点做简单分析
                return {
                    "primary": "neutral",
                    "confidence": 0.6,
                    "valence": 0.5,
                    "arousal": 0.3
                }
            
            return None
            
        except Exception as e:
            print(f"[情绪检测] 简化版错误: {e}")
            return None
    
    def _smooth_emotion(self) -> Dict:
        """平滑情绪结果"""
        if not self.emotion_history:
            return {
                "primary": "neutral",
                "confidence": 0.5,
                "valence": 0.5,
                "arousal": 0.3
            }
        
        # 统计各情绪出现次数
        emotion_counts = {}
        total_confidence = 0
        total_valence = 0
        total_arousal = 0
        
        for e in self.emotion_history:
            emotion = e["primary"]
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            total_confidence += e["confidence"]
            total_valence += e["valence"]
            total_arousal += e["arousal"]
        
        n = len(self.emotion_history)
        
        # 选择出现最多的情绪
        primary = max(emotion_counts, key=emotion_counts.get)
        
        return {
            "primary": primary,
            "confidence": total_confidence / n,
            "valence": total_valence / n,
            "arousal": total_arousal / n
        }
    
    def get_emotion_trend(self) -> str:
        """获取情绪趋势"""
        if len(self.emotion_history) < 5:
            return "stable"
        
        recent = list(self.emotion_history)[-5:]
        valences = [e["valence"] for e in recent]
        
        # 简单线性趋势
        if valences[-1] > valences[0] + 0.1:
            return "improving"
        elif valences[-1] < valences[0] - 0.1:
            return "declining"
        else:
            return "stable"
