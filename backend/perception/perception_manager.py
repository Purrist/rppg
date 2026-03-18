# perception/perception_manager.py
# 感知管理器 - 整合所有检测（增强版）

import cv2
import numpy as np
import threading
import time
from collections import deque
from typing import Dict, Any, Tuple, Optional


class PerceptionManager:
    """感知管理器 - 整合所有检测"""
    
    def __init__(self):
        # 用户状态 - 保持兼容旧结构
        self.user_state = {
            # ⭐ 核心状态
            "person_detected": False,  # 是否检测到人
            
            # ⭐ 10个高价值数据（顶层）
            "face_count": 0,           # 人数
            "heart_rate": None,        # 心率(BPM)
            "blink_count": 0,          # 眨眼次数（最近30秒）
            "eye_state": "open",       # 眼睛状态: open/closed/unknown
            "head_direction": "front", # 头部朝向: front/left/right/up/down
            "is_smiling": False,       # 是否微笑
            "light_level": "normal",   # 环境亮度: dark/normal/bright
            "posture": "standing",     # 姿态: standing/sitting/unknown
            "activity_level": 0.0,     # 活动强度 0-1
            "attention_score": 0.5,    # 注意力得分 0-1
            
            # ⭐ 兼容旧结构（供 state_manager 使用）
            "emotion": {"primary": "neutral", "confidence": 0.5},
            "heart_rate_detail": {"bpm": None, "hrv": None, "confidence": 0, "trend": "stable"},
            "environment": {
                "light_level": "normal",
                "light_value": 128,
                "person_present": False,
                "person_count": 0,
            },
            "body_state": {
                "posture": "unknown",
                "activity_level": 0,
                "head_pose": None,
            },
            "eye_state_detail": {
                "blink_rate": 0,
                "left_eye_open": True,
                "right_eye_open": True,
                "attention_score": 0.5,
            },
            "overall": {
                "fatigue_level": 0,
                "engagement_level": 0.5,
                "state_summary": "normal",
            },
        }
        
        # 历史数据
        self.history = {
            "frames": deque(maxlen=30),
            "blink_times": deque(maxlen=100),
            "heart_rate": deque(maxlen=60),
            "activity": deque(maxlen=100),
        }
        
        self.lock = threading.Lock()
        self._last_frame_time = 0
        self._prev_gray = None
        
        # ⭐ 人脸检测器
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        # ⭐ 眼睛检测器
        self.eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )
        
        # ⭐ 微笑检测器
        self.smile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_smile.xml'
        )
        
        # ⭐ 侧脸检测器
        self.profile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_profileface.xml'
        )
        
        # rPPG相关
        self._signal_buffer = deque(maxlen=300)
        
    def process_frame(self, frame, source="tablet") -> Dict[str, Any]:
        """处理帧，返回用户状态"""
        if frame is None:
            return self.user_state
        
        with self.lock:
            try:
                h, w = frame.shape[:2]
                
                # ⭐ 缩小图像加速处理
                if w > 320:
                    scale = 320 / w
                    frame = cv2.resize(frame, (320, int(h * scale)))
                    h, w = frame.shape[:2]
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)
                
                # ========== 1. 环境检测 ==========
                self._detect_environment(gray)
                
                # ========== 2. 运动检测 ==========
                motion_level = self._detect_motion(gray)
                self.user_state["activity_level"] = motion_level
                self.user_state["body_state"]["activity_level"] = motion_level
                
                # ========== 3. 人脸检测 ==========
                faces = self._detect_faces(gray)
                person_detected = len(faces) > 0
                self.user_state["person_detected"] = person_detected
                self.user_state["face_count"] = len(faces)
                self.user_state["environment"]["person_present"] = person_detected
                self.user_state["environment"]["person_count"] = len(faces)
                
                # ========== 4. 如果有人，进行更多检测 ==========
                if person_detected and len(faces) > 0:
                    face = max(faces, key=lambda f: f[2] * f[3])
                    x, y, fw, fh = face
                    
                    self._detect_eyes(gray, x, y, fw, fh)
                    self._detect_smile(gray, x, y, fw, fh)
                    self._detect_head_direction(face, w, h)
                    self._estimate_posture(face, h)
                    self._detect_heart_rate(frame, face)
                    self._calculate_attention()
                else:
                    self._reset_person_state()
                
                # ========== 5. 综合状态计算 ==========
                self._calculate_overall()
                
                self._prev_gray = gray.copy()
                
            except Exception as e:
                pass
        
        return self.user_state
    
    def _detect_environment(self, gray):
        """环境检测"""
        light_value = np.mean(gray)
        
        if light_value < 50:
            light_level = "dark"
        elif light_value > 200:
            light_level = "bright"
        else:
            light_level = "normal"
        
        self.user_state["light_level"] = light_level
        self.user_state["environment"]["light_level"] = light_level
        self.user_state["environment"]["light_value"] = float(light_value)
    
    def _detect_motion(self, gray):
        """运动检测"""
        if self._prev_gray is None:
            return 0.0
        
        diff = cv2.absdiff(self._prev_gray, gray)
        motion_level = np.mean(diff) / 255.0
        
        self.history["activity"].append(motion_level)
        if len(self.history["activity"]) > 10:
            motion_level = np.mean(list(self.history["activity"])[-10:])
        
        return float(min(1.0, motion_level * 5))
    
    def _detect_faces(self, gray):
        """人脸检测"""
        faces = list(self.face_cascade.detectMultiScale(
            gray, 1.3, 5, minSize=(30, 30)
        ))
        
        profiles = list(self.profile_cascade.detectMultiScale(
            gray, 1.3, 5, minSize=(30, 30)
        ))
        
        for p in profiles:
            overlap = False
            for f in faces:
                if self._rect_overlap(p, f):
                    overlap = True
                    break
            if not overlap:
                faces.append(p)
        
        return faces
    
    def _rect_overlap(self, r1, r2, threshold=0.3):
        """判断两个矩形是否重叠"""
        x1, y1, w1, h1 = r1
        x2, y2, w2, h2 = r2
        
        xi = max(x1, x2)
        yi = max(y1, y2)
        xf = min(x1 + w1, x2 + w2)
        yf = min(y1 + h1, y2 + h2)
        
        if xi >= xf or yi >= yf:
            return False
        
        inter = (xf - xi) * (yf - yi)
        area1 = w1 * h1
        area2 = w2 * h2
        
        return inter / min(area1, area2) > threshold
    
    def _detect_eyes(self, gray, fx, fy, fw, fh):
        """眼睛状态检测"""
        roi = gray[fy:fy+fh//2, fx:fx+fw]
        
        if roi.size == 0:
            return
        
        eyes = self.eye_cascade.detectMultiScale(roi, 1.1, 5, minSize=(10, 10))
        eye_count = len(eyes)
        
        if eye_count >= 2:
            self.user_state["eye_state"] = "open"
            self.user_state["eye_state_detail"]["left_eye_open"] = True
            self.user_state["eye_state_detail"]["right_eye_open"] = True
        elif eye_count == 1:
            self.user_state["eye_state"] = "partial"
        else:
            self.user_state["eye_state"] = "closed"
            self._record_blink()
    
    def _record_blink(self):
        """记录眨眼"""
        now = time.time()
        self.history["blink_times"].append(now)
        
        recent = [t for t in self.history["blink_times"] if now - t < 30]
        self.user_state["blink_count"] = len(recent)
    
    def _detect_smile(self, gray, fx, fy, fw, fh):
        """微笑检测"""
        roi = gray[fy+fh//2:fy+fh, fx:fx+fw]
        
        if roi.size == 0:
            self.user_state["is_smiling"] = False
            return
        
        try:
            smiles = self.smile_cascade.detectMultiScale(roi, 1.7, 10, minSize=(15, 15))
            self.user_state["is_smiling"] = len(smiles) > 0
        except:
            self.user_state["is_smiling"] = False
    
    def _detect_head_direction(self, face, img_w, img_h):
        """头部朝向估计"""
        x, y, w, h = face
        
        face_cx = x + w // 2
        img_cx = img_w // 2
        
        offset_x = (face_cx - img_cx) / img_w
        
        if offset_x < -0.2:
            self.user_state["head_direction"] = "left"
        elif offset_x > 0.2:
            self.user_state["head_direction"] = "right"
        else:
            face_ratio = w / img_w
            if face_ratio < 0.2:
                self.user_state["head_direction"] = "far"
            else:
                self.user_state["head_direction"] = "front"
        
        self.user_state["body_state"]["head_pose"] = self.user_state["head_direction"]
    
    def _estimate_posture(self, face, img_h):
        """姿态估计"""
        x, y, w, h = face
        
        face_y_ratio = y / img_h
        
        if face_y_ratio < 0.5:
            self.user_state["posture"] = "standing"
        else:
            self.user_state["posture"] = "sitting"
        
        self.user_state["body_state"]["posture"] = self.user_state["posture"]
    
    def _detect_heart_rate(self, frame, face):
        """rPPG心率检测"""
        x, y, w, h = face
        
        roi = frame[y:y+h, x:x+w]
        if roi.size == 0:
            return
        
        green_mean = np.mean(roi[:, :, 1])
        self._signal_buffer.append(green_mean)
        
        if len(self._signal_buffer) < 150:
            return
        
        signal = np.array(list(self._signal_buffer)[-150:])
        signal = signal - np.mean(signal)
        
        peaks = 0
        threshold = np.std(signal) * 0.5
        
        for i in range(1, len(signal) - 1):
            if signal[i] > signal[i-1] and signal[i] > signal[i+1]:
                if signal[i] > threshold:
                    peaks += 1
        
        if peaks > 0:
            bpm = peaks * 12
            bpm = max(50, min(120, bpm))
            self.user_state["heart_rate"] = int(bpm)
            self.user_state["heart_rate_detail"]["bpm"] = int(bpm)
    
    def _calculate_attention(self):
        """计算注意力得分"""
        score = 0.5
        
        if self.user_state["head_direction"] == "front":
            score += 0.2
        
        if self.user_state["eye_state"] == "open":
            score += 0.2
        
        if 0.1 < self.user_state["activity_level"] < 0.5:
            score += 0.1
        
        self.user_state["attention_score"] = min(1.0, score)
        self.user_state["eye_state_detail"]["attention_score"] = self.user_state["attention_score"]
    
    def _reset_person_state(self):
        """重置人员相关状态"""
        self.user_state["face_count"] = 0
        self.user_state["eye_state"] = "unknown"
        self.user_state["is_smiling"] = False
        self.user_state["head_direction"] = "unknown"
        self.user_state["posture"] = "unknown"
        self.user_state["attention_score"] = 0.0
        self.user_state["heart_rate"] = None
        
        # 兼容旧结构
        self.user_state["body_state"]["posture"] = "unknown"
        self.user_state["body_state"]["head_pose"] = None
        self.user_state["eye_state_detail"]["attention_score"] = 0.0
        self.user_state["heart_rate_detail"]["bpm"] = None
    
    def _calculate_overall(self):
        """计算综合状态"""
        fatigue = 0.0
        
        if self.user_state["blink_count"] > 20:
            fatigue += 0.3
        
        if self.user_state["attention_score"] < 0.5:
            fatigue += 0.2
        
        if self.user_state["activity_level"] < 0.1:
            fatigue += 0.2
        
        self.user_state["overall"]["fatigue_level"] = min(1.0, fatigue)
        self.user_state["overall"]["engagement_level"] = self.user_state["attention_score"]
        
        if fatigue > 0.6:
            self.user_state["overall"]["state_summary"] = "fatigued"
        elif self.user_state["attention_score"] > 0.7:
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
                "person_detected": self.user_state["person_detected"],
                "face_count": self.user_state["face_count"],
                "heart_rate": self.user_state["heart_rate"],
                "blink_count": self.user_state["blink_count"],
                "eye_state": self.user_state["eye_state"],
                "head_direction": self.user_state["head_direction"],
                "is_smiling": self.user_state["is_smiling"],
                "light_level": self.user_state["light_level"],
                "posture": self.user_state["posture"],
                "activity_level": self.user_state["activity_level"],
                "attention_score": self.user_state["attention_score"],
                "fatigue_level": self.user_state["overall"]["fatigue_level"],
                "state_summary": self.user_state["overall"]["state_summary"],
            }
