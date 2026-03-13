# perception/heart_rate_detector.py
# 心率检测模块 - 改进版rPPG

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
from collections import deque
import time

try:
    from scipy import signal
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class HeartRateDetector:
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        self.rgb_buffer = deque(maxlen=300)
        self.time_buffer = deque(maxlen=300)
        
        if HAS_MEDIAPIPE:
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.5)
        else:
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        self.bpm = None
        self.hrv = None
        self.confidence = 0.0
        self.bpm_history = deque(maxlen=30)
        self.smoothed_bpm = None
        self.last_face_rect = None
        self.last_rois = None
        self.last_ear = 0.3
        self.frame_count = 0
        self.process_every_n = 2
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        self.frame_count += 1
        if self.frame_count % self.process_every_n != 0:
            return {"bpm": self.smoothed_bpm, "hrv": self.hrv, "confidence": self.confidence, "trend": "stable"}
        
        rois = self._detect_face_rois(frame)
        if rois is None:
            self.confidence = max(0, self.confidence - 0.1)
            return {"bpm": self.smoothed_bpm, "hrv": self.hrv, "confidence": self.confidence, "trend": "stable"}
        
        rgb_means = self._extract_rgb_means(frame, rois)
        if rgb_means is None:
            return {"bpm": self.smoothed_bpm, "hrv": self.hrv, "confidence": self.confidence, "trend": "stable"}
        
        self.rgb_buffer.append(rgb_means)
        self.time_buffer.append(time.time())
        
        if len(self.rgb_buffer) >= 150:
            bpm, hrv, conf = self._calculate_hr()
            if bpm is not None and conf > 0.3:
                self.bpm_history.append(bpm)
                if len(self.bpm_history) >= 5:
                    recent = list(self.bpm_history)[-15:]
                    self.smoothed_bpm = float(np.median(recent))
                self.bpm = bpm
                self.hrv = hrv
                self.confidence = conf
        
        return {"bpm": self.smoothed_bpm, "hrv": self.hrv, "confidence": self.confidence, "trend": "stable"}
    
    def _detect_face_rois(self, frame: np.ndarray) -> Optional[list]:
        h, w = frame.shape[:2]
        if HAS_MEDIAPIPE:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)
            if results.detections:
                detection = results.detections[0]
                bboxC = detection.location_data.relative_bounding_box
                x = int(bboxC.xmin * w)
                y = int(bboxC.ymin * h)
                width = int(bboxC.width * w)
                height = int(bboxC.height * h)
                x = max(0, min(x, w - 10))
                y = max(0, min(y, h - 10))
                width = max(10, min(width, w - x))
                height = max(10, min(height, h - y))
                roi_x = x + int(width * 0.25)
                roi_y = y + int(height * 0.08)
                roi_w = int(width * 0.5)
                roi_h = int(height * 0.2)
                return [(roi_x, roi_y, roi_w, roi_h)]
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
            if len(faces) > 0:
                x, y, width, height = faces[0]
                roi_x = x + int(width * 0.25)
                roi_y = y + int(height * 0.08)
                roi_w = int(width * 0.5)
                roi_h = int(height * 0.2)
                return [(roi_x, roi_y, roi_w, roi_h)]
        return self.last_rois
    
    def _extract_rgb_means(self, frame: np.ndarray, rois: list) -> Optional[Tuple]:
        if not rois: return None
        rgb_means = []
        for roi in rois:
            x, y, w, h = roi
            if w <= 0 or h <= 0: continue
            x, y = max(0, x), max(0, y)
            w, h = min(w, frame.shape[1] - x), min(h, frame.shape[0] - y)
            if w <= 0 or h <= 0: continue
            roi_frame = frame[y:y+h, x:x+w]
            if roi_frame.size == 0: continue
            mean = cv2.mean(roi_frame)[:3]
            rgb_means.append(mean)
        if not rgb_means: return None
        return (np.mean([m[0] for m in rgb_means]), np.mean([m[1] for m in rgb_means]), np.mean([m[2] for m in rgb_means]))
    
    def _calculate_hr(self) -> Tuple[Optional[float], Optional[float], float]:
        if len(self.rgb_buffer) < 150: return None, None, 0.0
        signals = np.array(list(self.rgb_buffer))
        B, G, R = signals[:, 0], signals[:, 1], signals[:, 2]
        B_norm = (B - np.mean(B)) / (np.std(B) + 1e-10)
        G_norm = (G - np.mean(G)) / (np.std(G) + 1e-10)
        R_norm = (R - np.mean(R)) / (np.std(R) + 1e-10)
        Xs = 3 * R_norm - 2 * G_norm
        Ys = 1.5 * R_norm + G_norm - 1.5 * B_norm
        Xs = (Xs - np.mean(Xs)) / (np.std(Xs) + 1e-10)
        Ys = (Ys - np.mean(Ys)) / (np.std(Ys) + 1e-10)
        alpha = np.std(Xs) / (np.std(Ys) + 1e-10)
        S = Xs - alpha * Ys
        
        if HAS_SCIPY:
            try:
                nyq = 0.5 * self.fps
                low, high = 0.67 / nyq, min(3.0 / nyq, 0.99)
                if low < high:
                    b, a = signal.butter(4, [low, high], btype='band')
                    S = signal.filtfilt(b, a, S)
            except: pass
        
        n = len(S)
        freqs = np.fft.rfftfreq(n, 1.0 / self.fps)
        fft_vals = np.abs(np.fft.rfft(S))
        min_freq, max_freq = 50 / 60, 120 / 60
        min_idx = np.argmax(freqs >= min_freq)
        max_idx = np.argmax(freqs >= max_freq)
        if max_idx <= min_idx: max_idx = len(freqs)
        search_range = fft_vals[min_idx:max_idx]
        if len(search_range) == 0: return None, None, 0.0
        peak_idx = np.argmax(search_range) + min_idx
        bpm = freqs[peak_idx] * 60
        noise_level = np.mean(fft_vals[min_idx:max_idx]) + 1e-10
        peak_power = fft_vals[peak_idx]
        confidence = min(1.0, peak_power / noise_level / 5)
        if bpm < 50 or bpm > 120: confidence *= 0.5
        return bpm, None, confidence
    
    def reset(self):
        self.rgb_buffer.clear()
        self.time_buffer.clear()
        self.bpm_history.clear()
        self.bpm = None
        self.smoothed_bpm = None
        self.hrv = None
        self.confidence = 0.0
