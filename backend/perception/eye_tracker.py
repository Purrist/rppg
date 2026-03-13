# perception/eye_tracker.py
# 眼部追踪模块

import cv2
import numpy as np
from typing import Dict, Any, Optional
from collections import deque
import time

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class EyeTracker:
    EAR_THRESHOLD = 0.2
    EAR_CONSEC_FRAMES = 3
    
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        if HAS_MEDIAPIPE:
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5, min_tracking_confidence=0.5)
            self.LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
            self.RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
        self.blink_counter = 0
        self.blink_total = 0
        self.blink_start_time = time.time()
        self.blink_history = deque(maxlen=1800)
        self.gaze_start_time = None
        self.current_gaze = "unknown"
        self.gaze_history = deque(maxlen=300)
        self.attention_history = deque(maxlen=300)
        self.eyes_closed = False
        self.last_ear = 0.3
        self.prev_gray = None
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        result = {"blink_rate": 0, "blink_frequency": 0.0, "gaze_direction": "unknown", "gaze_duration": 0, "attention_score": 0.0, "eye_contact": False}
        if frame is None or frame.size == 0: return result
        try:
            if HAS_MEDIAPIPE:
                result = self._detect_with_mediapipe(frame)
            else:
                result = self._detect_simple(frame)
            result["blink_rate"] = self._calculate_blink_rate()
            result["blink_frequency"] = result["blink_rate"] / 60.0
            result["attention_score"] = self._calculate_attention()
            self.attention_history.append({"attention": result["attention_score"], "gaze": result["gaze_direction"], "time": time.time()})
        except Exception as e:
            print(f"[眼部追踪] 错误: {e}")
        return result
    
    def _detect_with_mediapipe(self, frame: np.ndarray) -> Dict[str, Any]:
        result = {"blink_rate": 0, "blink_frequency": 0.0, "gaze_direction": "unknown", "gaze_duration": 0, "attention_score": 0.0, "eye_contact": False}
        h, w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_mesh_result = self.face_mesh.process(rgb_frame)
        if face_mesh_result.multi_face_landmarks:
            landmarks = face_mesh_result.multi_face_landmarks[0].landmark
            left_ear = self._calculate_ear(landmarks, self.LEFT_EYE_INDICES, w, h)
            right_ear = self._calculate_ear(landmarks, self.RIGHT_EYE_INDICES, w, h)
            avg_ear = (left_ear + right_ear) / 2
            avg_ear = 0.7 * self.last_ear + 0.3 * avg_ear
            self.last_ear = avg_ear
            
            if avg_ear < self.EAR_THRESHOLD:
                if not self.eyes_closed:
                    self.blink_counter += 1
                    if self.blink_counter >= self.EAR_CONSEC_FRAMES:
                        self.eyes_closed = True
                        self.blink_total += 1
                        self.blink_history.append(time.time())
            else:
                if self.eyes_closed: self.eyes_closed = False
                self.blink_counter = 0
            
            if self.eyes_closed: result["gaze_direction"] = "closed"
            else: result["gaze_direction"] = "screen"
            result["eye_contact"] = result["gaze_direction"] == "screen"
            
            if result["gaze_direction"] == self.current_gaze:
                if self.gaze_start_time: result["gaze_duration"] = time.time() - self.gaze_start_time
            else:
                self.current_gaze = result["gaze_direction"]
                self.gaze_start_time = time.time()
            self.gaze_history.append({"gaze": result["gaze_direction"], "time": time.time()})
        return result
    
    def _detect_simple(self, frame: np.ndarray) -> Dict[str, Any]:
        result = {"blink_rate": 15, "blink_frequency": 0.25, "gaze_direction": "screen", "gaze_duration": 0, "attention_score": 0.5, "eye_contact": True}
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.prev_gray is not None:
            diff = cv2.absdiff(gray, self.prev_gray)
            h, w = diff.shape
            eye_region = diff[int(h*0.2):int(h*0.4), int(w*0.3):int(w*0.7)]
            if eye_region.size > 0:
                change = np.mean(eye_region)
                if change > 30:
                    if not self.eyes_closed:
                        self.eyes_closed = True
                        self.blink_total += 1
                        self.blink_history.append(time.time())
                else: self.eyes_closed = False
        self.prev_gray = gray
        return result
    
    def _calculate_ear(self, landmarks, indices, w, h) -> float:
        p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in indices]
        vertical_1 = np.sqrt((p2.x - p6.x)**2 + (p2.y - p6.y)**2)
        vertical_2 = np.sqrt((p3.x - p5.x)**2 + (p3.y - p5.y)**2)
        horizontal = np.sqrt((p1.x - p4.x)**2 + (p1.y - p4.y)**2)
        return (vertical_1 + vertical_2) / (2.0 * horizontal) if horizontal > 0 else 0.3
    
    def _calculate_blink_rate(self) -> int:
        if len(self.blink_history) < 2: return 0
        now = time.time()
        recent_blinks = [t for t in self.blink_history if now - t < 60]
        return len(recent_blinks)
    
    def _calculate_attention(self) -> float:
        if len(self.gaze_history) < 10: return 0.5
        recent = list(self.gaze_history)[-60:]
        screen_count = sum(1 for g in recent if g["gaze"] == "screen")
        closed_count = sum(1 for g in recent if g["gaze"] == "closed")
        total = len(recent)
        if total == 0: return 0.5
        screen_ratio = screen_count / total
        closed_penalty = closed_count / total * 0.5
        return max(0.0, min(1.0, screen_ratio - closed_penalty))
