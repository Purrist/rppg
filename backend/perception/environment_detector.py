# perception/environment_detector.py
# 环境检测模块

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
from collections import deque

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class EnvironmentDetector:
    LIGHT_THRESHOLDS = {"dark": 50, "dim": 100, "normal": 180, "bright": 220}
    
    def __init__(self):
        if HAS_MEDIAPIPE:
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.5)
        else:
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.light_history = deque(maxlen=30)
        self.last_result = {"light_level": "normal", "light_value": 0, "person_count": 0, "person_present": False, "person_distance": None, "face_detected": False, "face_id": None}
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        if frame is None or frame.size == 0: return self.last_result
        result = self.last_result.copy()
        try:
            light_level, light_value = self._detect_light(frame)
            result["light_level"] = light_level
            result["light_value"] = light_value
            self.light_history.append(light_value)
            person_info = self._detect_persons(frame)
            result.update(person_info)
            self.last_result = result
        except Exception as e:
            print(f"[环境检测] 错误: {e}")
        return result
    
    def _detect_light(self, frame: np.ndarray) -> Tuple[str, int]:
        if len(frame.shape) == 3: gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else: gray = frame
        light_value = int(np.mean(gray))
        if light_value < self.LIGHT_THRESHOLDS["dark"]: light_level = "dark"
        elif light_value < self.LIGHT_THRESHOLDS["dim"]: light_level = "dim"
        elif light_value < self.LIGHT_THRESHOLDS["bright"]: light_level = "normal"
        else: light_level = "bright"
        return light_level, light_value
    
    def _detect_persons(self, frame: np.ndarray) -> Dict[str, Any]:
        result = {"person_count": 0, "person_present": False, "person_distance": None, "face_detected": False, "face_id": None}
        h, w = frame.shape[:2]
        if HAS_MEDIAPIPE:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)
            if results.detections:
                result["person_count"] = len(results.detections)
                result["person_present"] = True
                result["face_detected"] = True
                detection = results.detections[0]
                bboxC = detection.location_data.relative_bounding_box
                face_width = bboxC.width * w
                face_height = bboxC.height * h
                face_area = face_width * face_height
                normal_area = w * h * 0.05
                if face_area > 0:
                    distance_ratio = normal_area / face_area
                    result["person_distance"] = max(0.3, min(3.0, distance_ratio))
                face_x = int(bboxC.xmin * w)
                face_y = int(bboxC.ymin * h)
                result["face_id"] = f"face_{face_x//100}_{face_y//100}"
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            if len(faces) > 0:
                result["person_count"] = len(faces)
                result["person_present"] = True
                result["face_detected"] = True
                x, y, face_w, face_h = faces[0]
                face_area = face_w * face_h
                normal_area = w * h * 0.05
                if face_area > 0:
                    distance_ratio = normal_area / face_area
                    result["person_distance"] = max(0.3, min(3.0, distance_ratio))
                result["face_id"] = f"face_{x//100}_{y//100}"
        return result
