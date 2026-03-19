# perception/perception_manager.py
# 感知管理器 - 专业版
# 基于文献调研的三维指标体系：身体负荷、认知负荷、参与意愿
# 参考：Sweller (1988), Csikszentmihalyi (1990), Shute (2008) 等75篇文献

import cv2
import numpy as np
import threading
import time
from collections import deque
from typing import Dict, Any, Optional, Tuple


class PerceptionManager:
    """
    感知管理器 - 专业版
    
    理论基础：
    - 认知负荷理论 (Sweller, 1988)
    - 心流理论 (Csikszentmihalyi, 1990)
    - 自适应学习系统 (Shute, 2008)
    - 自我决定理论 (Deci & Ryan, 2000)
    
    三维指标体系：
    - 身体负荷 (Physical Load): 心率、运动强度、姿态稳定性、疲劳迹象
    - 认知负荷 (Cognitive Load): 反应时间、错误率、犹豫次数、注意力稳定性
    - 参与意愿 (Engagement): 正面情绪、主动性、坚持性、享受程度
    """
    
    def __init__(self, age: int = 70):
        """初始化感知管理器"""
        self.age = age
        
        # ==================== 用户状态 ====================
        self.user_state = {
            # 基础检测
            "person_detected": False,
            "face_detected": False,
            "body_detected": False,
            "face_count": 0,
            
            # ==================== 三维指标 ====================
            # 1. 身体负荷 (0-1, 越高越累)
            # 参考: Achten & Jeukendrup (2003), Rubenstein (2006)
            "physical_load": {
                "value": 0.0,
                "heart_rate": None,           # 心率 (BPM)
                "hr_factor": 0.0,             # 心率因子
                "movement_intensity": 0.0,    # 运动强度
                "posture_stability": 1.0,     # 姿态稳定性
                "fatigue_signs": 0.0,         # 疲劳迹象
                "fall_detected": False,       # 摔倒检测
            },
            
            # 2. 认知负荷 (0-1, 越高越难)
            # 参考: Sweller (1988), Paas et al. (2003)
            "cognitive_load": {
                "value": 0.0,
                "reaction_time": None,        # 平均反应时间 (ms)
                "rt_factor": 0.3,             # 反应时间因子
                "error_rate": 0.0,            # 错误率
                "hesitation_count": 0,        # 犹豫次数
                "attention_stability": 1.0,   # 注意力稳定性
            },
            
            # 3. 参与意愿 (0-1, 越高越愿意)
            # 参考: Deci & Ryan (2000), Fredricks et al. (2004)
            "engagement": {
                "value": 0.5,
                "emotion_positive": 0.5,      # 正面情绪
                "initiative_level": 0.5,      # 主动性
                "persistence": 0.5,           # 坚持性
                "enjoyment": 0.5,             # 享受程度
            },
            
            # ==================== 详细数据 ====================
            "emotion": {
                "primary": "neutral",
                "positive": 0.5,
                "arousal": 0.5,
                "valence": 0.5,
                "is_smiling": False,
            },
            
            "posture": {
                "type": "standing",
                "stability": 1.0,
                "lean_angle": 0.0,
            },
            
            "environment": {
                "light_level": "normal",
                "light_value": 128,
                "person_present": False,
                "person_count": 0,
            },
            
            "activity": {
                "level": 0.0,
                "duration": 0,
            },
            
            # 兼容旧结构
            "body_state": {"posture": "unknown", "activity_level": 0},
            "eye_state_detail": {"attention_score": 0.5},
            "overall": {"fatigue_level": 0, "state_summary": "normal"},
        }
        
        # ==================== 权重设置 ====================
        # 基于AHP方法确定，参考: Saaty (1980)
        self.weights = {
            # 身体负荷权重 (参考: Achten & Jeukendrup, 2003)
            "physical": {
                "hr": 0.40,           # 心率因子权重
                "motion": 0.22,       # 运动强度权重
                "stability": 0.22,    # 姿态稳定性权重
                "fatigue": 0.16,      # 疲劳迹象权重
            },
            # 认知负荷权重 (参考: Paas et al., 2003)
            "cognitive": {
                "rt": 0.30,           # 反应时间权重
                "error": 0.28,        # 错误率权重
                "hesitation": 0.22,   # 犹豫次数权重
                "attention": 0.20,    # 注意力稳定性权重
            },
            # 参与意愿权重 (参考: Fredricks et al., 2004)
            "engagement": {
                "emotion": 0.30,      # 正面情绪权重
                "initiative": 0.30,   # 主动性权重
                "persistence": 0.20,  # 坚持性权重
                "enjoyment": 0.20,    # 享受程度权重
            },
        }
        
        # ==================== 历史数据 ====================
        self.history = {
            "frames": deque(maxlen=30),
            "motion": deque(maxlen=60),
            "heart_rate": deque(maxlen=60),
            "reaction_times": deque(maxlen=20),
            "errors": deque(maxlen=20),
            "emotions": deque(maxlen=30),
        }
        
        self.lock = threading.Lock()
        self._prev_gray = None
        self._last_update_time = time.time()
        
        # ==================== 检测器 ====================
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.profile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_profileface.xml'
        )
        self.body_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_fullbody.xml'
        )
        self.upperbody_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_upperbody.xml'
        )
        self.smile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_smile.xml'
        )
        
        # rPPG心率检测
        self._signal_buffer = deque(maxlen=300)
        
        # 游戏数据
        self.game_data = {
            "reaction_times": [],
            "errors": 0,
            "successes": 0,
            "total_actions": 0,
            "hesitation_count": 0,
        }
    
    def process_frame(self, frame, source: str = "tablet") -> Dict[str, Any]:
        """
        处理帧，返回用户状态
        
        参数:
            frame: 输入帧
            source: 数据源 ("tablet" 或 "projection")
        
        返回:
            用户状态字典
        """
        if frame is None:
            return self.user_state
        
        with self.lock:
            try:
                h, w = frame.shape[:2]
                
                # 缩小图像加速处理
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
                self.user_state["activity"]["level"] = motion_level
                
                # ========== 3. 人物检测（多重验证）============
                face_detected, face_count, faces = self._detect_faces(gray)
                body_detected = self._detect_body(gray)
                
                # 只要有人脸或身体就认为有人
                person_detected = face_detected or body_detected
                self.user_state["person_detected"] = person_detected
                self.user_state["face_detected"] = face_detected
                self.user_state["body_detected"] = body_detected
                self.user_state["face_count"] = face_count
                self.user_state["environment"]["person_present"] = person_detected
                self.user_state["environment"]["person_count"] = face_count if face_count > 0 else (1 if body_detected else 0)
                
                # ========== 4. 如果有人，进行详细检测 ==========
                if person_detected:
                    if len(faces) > 0:
                        face = max(faces, key=lambda f: f[2] * f[3])
                        x, y, fw, fh = face
                        
                        # 情绪检测
                        self._detect_emotion(gray, x, y, fw, fh)
                        
                        # 心率检测
                        self._detect_heart_rate(frame, face)
                    
                    # 姿态检测（包括摔倒）
                    self._detect_posture(gray, h, w)
                    
                    # 计算三维指标
                    self._calculate_indicators()
                else:
                    self._reset_person_state()
                
                self._prev_gray = gray.copy()
                self._last_update_time = time.time()
                
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
        
        self.user_state["environment"]["light_level"] = light_level
        self.user_state["environment"]["light_value"] = float(light_value)
    
    def _detect_motion(self, gray) -> float:
        """
        运动检测
        参考: Chen & Bassett (2005)
        """
        if self._prev_gray is None:
            return 0.0
        
        diff = cv2.absdiff(self._prev_gray, gray)
        motion_level = np.mean(diff) / 255.0
        
        self.history["motion"].append(motion_level)
        if len(self.history["motion"]) > 10:
            motion_level = np.mean(list(self.history["motion"])[-10:])
        
        return float(min(1.0, motion_level * 5))
    
    def _detect_faces(self, gray) -> Tuple[bool, int, list]:
        """
        人脸检测 - 多重验证
        参考: Viola & Jones (2001)
        """
        # 正面人脸
        faces = list(self.face_cascade.detectMultiScale(
            gray, 1.2, 4, minSize=(40, 40)
        ))
        
        # 侧脸检测
        try:
            profiles = list(self.profile_cascade.detectMultiScale(
                gray, 1.2, 4, minSize=(40, 40)
            ))
            
            for p in profiles:
                overlap = False
                for f in faces:
                    if self._rect_overlap(p, f, 0.3):
                        overlap = True
                        break
                if not overlap:
                    faces.append(p)
        except:
            pass
        
        face_detected = len(faces) > 0
        face_count = len(faces)
        
        return face_detected, face_count, faces
    
    def _detect_body(self, gray) -> bool:
        """
        身体/骨骼检测
        参考: Rubenstein (2006), Mancini et al. (2019)
        """
        try:
            bodies = self.body_cascade.detectMultiScale(
                gray, 1.1, 3, minSize=(60, 120)
            )
            upper_bodies = self.upperbody_cascade.detectMultiScale(
                gray, 1.1, 3, minSize=(60, 80)
            )
            return len(bodies) > 0 or len(upper_bodies) > 0
        except:
            return False
    
    def _rect_overlap(self, r1, r2, threshold: float = 0.3) -> bool:
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
    
    def _detect_emotion(self, gray, fx, fy, fw, fh):
        """
        情绪检测
        参考: Ekman & Friesen (1978), Isen (2001)
        """
        # 微笑检测
        roi = gray[fy+fh//2:fy+fh, fx:fx+fw]
        is_smiling = False
        
        if roi.size > 0:
            try:
                smiles = self.smile_cascade.detectMultiScale(roi, 1.7, 10, minSize=(15, 15))
                is_smiling = len(smiles) > 0
            except:
                pass
        
        self.user_state["emotion"]["is_smiling"] = is_smiling
        
        # 基于微笑和运动计算情绪
        motion = self.user_state["activity"]["level"]
        
        if is_smiling:
            self.user_state["emotion"]["primary"] = "happy"
            self.user_state["emotion"]["positive"] = 0.8
            self.user_state["emotion"]["valence"] = 0.8
            self.user_state["emotion"]["arousal"] = 0.6
        elif motion > 0.3:
            self.user_state["emotion"]["primary"] = "engaged"
            self.user_state["emotion"]["positive"] = 0.6
            self.user_state["emotion"]["valence"] = 0.6
            self.user_state["emotion"]["arousal"] = 0.7
        elif motion > 0.1:
            self.user_state["emotion"]["primary"] = "neutral"
            self.user_state["emotion"]["positive"] = 0.5
            self.user_state["emotion"]["valence"] = 0.5
            self.user_state["emotion"]["arousal"] = 0.4
        else:
            self.user_state["emotion"]["primary"] = "calm"
            self.user_state["emotion"]["positive"] = 0.5
            self.user_state["emotion"]["valence"] = 0.5
            self.user_state["emotion"]["arousal"] = 0.3
    
    def _detect_heart_rate(self, frame, face):
        """
        rPPG心率检测
        参考: Poh et al. (2010), Sun et al. (2012)
        """
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
            self.user_state["physical_load"]["heart_rate"] = int(bpm)
            self.history["heart_rate"].append(int(bpm))
    
    def _detect_posture(self, gray, img_h, img_w):
        """
        姿态检测 - 包括摔倒检测
        参考: Rubenstein (2006), Mancini et al. (2019)
        """
        try:
            bodies = self.body_cascade.detectMultiScale(
                gray, 1.1, 3, minSize=(60, 120)
            )
            
            if len(bodies) > 0:
                body = max(bodies, key=lambda b: b[2] * b[3])
                bx, by, bw, bh = body
                
                # 宽高比判断姿态
                aspect_ratio = bh / bw if bw > 0 else 1
                
                if aspect_ratio < 1.2:
                    # 可能摔倒
                    self.user_state["posture"]["type"] = "falling"
                    self.user_state["posture"]["stability"] = 0.2
                    self.user_state["physical_load"]["fall_detected"] = True
                elif aspect_ratio < 1.8:
                    self.user_state["posture"]["type"] = "unstable"
                    self.user_state["posture"]["stability"] = 0.6
                    self.user_state["physical_load"]["fall_detected"] = False
                else:
                    self.user_state["posture"]["type"] = "standing"
                    self.user_state["posture"]["stability"] = 0.9
                    self.user_state["physical_load"]["fall_detected"] = False
            else:
                self.user_state["posture"]["type"] = "unknown"
                self.user_state["posture"]["stability"] = 0.5
                self.user_state["physical_load"]["fall_detected"] = False
        except:
            pass
        
        self.user_state["body_state"]["posture"] = self.user_state["posture"]["type"]
    
    def _calculate_indicators(self):
        """
        计算三维指标
        参考: Sweller (1988), Csikszentmihalyi (1990), Deci & Ryan (2000)
        """
        # ==================== 1. 身体负荷 ====================
        # 参考: Achten & Jeukendrup (2003), Karvonen et al. (1957)
        
        # 心率因子
        hr = self.user_state["physical_load"]["heart_rate"]
        hr_factor = self._calculate_hr_factor(hr)
        self.user_state["physical_load"]["hr_factor"] = hr_factor
        
        # 运动强度因子
        motion = self.user_state["activity"]["level"]
        motion_factor = motion ** 0.8  # 指数平滑
        
        # 姿态稳定性因子
        stability = self.user_state["posture"]["stability"]
        stability_factor = 1 - stability
        
        # 疲劳迹象因子
        fatigue_factor = self._calculate_fatigue_factor(hr, motion)
        
        # 综合计算
        w = self.weights["physical"]
        physical_load = (
            w["hr"] * hr_factor +
            w["motion"] * motion_factor +
            w["stability"] * stability_factor +
            w["fatigue"] * fatigue_factor
        )
        
        self.user_state["physical_load"]["value"] = min(1.0, physical_load)
        self.user_state["physical_load"]["movement_intensity"] = motion
        self.user_state["physical_load"]["posture_stability"] = stability
        self.user_state["physical_load"]["fatigue_signs"] = fatigue_factor
        
        # ==================== 2. 认知负荷 ====================
        # 参考: Sweller (1988), Paas et al. (2003), Wickelgren (1977)
        
        # 反应时间因子
        rt_factor = self._calculate_rt_factor()
        self.user_state["cognitive_load"]["rt_factor"] = rt_factor
        
        # 错误率因子
        total = self.game_data["total_actions"]
        error_rate = self.game_data["errors"] / max(1, total) if total > 0 else 0
        error_factor = min(1.0, error_rate * 2)
        
        # 犹豫因子
        hesitation_factor = 0.3  # 默认值
        
        # 注意力稳定性因子
        motion_var = np.var(list(self.history["motion"])[-20:]) if len(self.history["motion"]) > 5 else 0
        attention_stability = max(0, 1 - motion_var * 5)
        attention_factor = 1 - attention_stability
        
        # 综合计算
        w = self.weights["cognitive"]
        cognitive_load = (
            w["rt"] * rt_factor +
            w["error"] * error_factor +
            w["hesitation"] * hesitation_factor +
            w["attention"] * attention_factor
        )
        
        self.user_state["cognitive_load"]["value"] = min(1.0, cognitive_load)
        self.user_state["cognitive_load"]["error_rate"] = error_rate
        self.user_state["cognitive_load"]["attention_stability"] = attention_stability
        
        # ==================== 3. 参与意愿 ====================
        # 参考: Deci & Ryan (2000), Fredricks et al. (2004)
        
        # 正面情绪因子
        emotion_positive = self.user_state["emotion"]["positive"]
        if self.user_state["emotion"]["is_smiling"]:
            emotion_positive = min(1.0, emotion_positive + 0.1)
        
        # 主动性因子
        initiative = min(1.0, motion * 2)
        
        # 坚持性因子
        persistence = self.game_data["successes"] / max(1, total) if total > 0 else 0.5
        
        # 享受程度因子
        enjoyment = (emotion_positive + initiative) / 2
        
        # 综合计算
        w = self.weights["engagement"]
        engagement = (
            w["emotion"] * emotion_positive +
            w["initiative"] * initiative +
            w["persistence"] * persistence +
            w["enjoyment"] * enjoyment
        )
        
        self.user_state["engagement"]["value"] = min(1.0, engagement)
        self.user_state["engagement"]["emotion_positive"] = emotion_positive
        self.user_state["engagement"]["initiative_level"] = initiative
        self.user_state["engagement"]["persistence"] = persistence
        self.user_state["engagement"]["enjoyment"] = enjoyment
        
        # ==================== 更新兼容字段 ====================
        self.user_state["overall"]["fatigue_level"] = self.user_state["physical_load"]["value"]
        self.user_state["eye_state_detail"]["attention_score"] = 1 - self.user_state["cognitive_load"]["value"]
        
        # 状态总结
        if self.user_state["physical_load"]["value"] > 0.7:
            self.user_state["overall"]["state_summary"] = "fatigued"
        elif self.user_state["engagement"]["value"] > 0.7:
            self.user_state["overall"]["state_summary"] = "engaged"
        elif self.user_state["cognitive_load"]["value"] > 0.7:
            self.user_state["overall"]["state_summary"] = "struggling"
        else:
            self.user_state["overall"]["state_summary"] = "normal"
    
    def _calculate_hr_factor(self, hr) -> float:
        """
        计算心率因子
        参考: Karvonen et al. (1957), Achten & Jeukendrup (2003)
        """
        if hr is None:
            return 0.3
        
        # 最大心率估算 (220 - 年龄)
        max_hr = 220 - self.age
        resting_hr = 70
        hr_reserve = max_hr - resting_hr
        
        if hr_reserve <= 0:
            return 0.3
        
        relative_intensity = (hr - resting_hr) / hr_reserve
        return max(0, min(1, relative_intensity))
    
    def _calculate_rt_factor(self) -> float:
        """
        计算反应时间因子
        参考: Wickelgren (1977), Salthouse (1996)
        """
        if not self.game_data["reaction_times"]:
            return 0.3
        
        avg_rt = np.mean(self.game_data["reaction_times"][-10:])
        self.user_state["cognitive_load"]["reaction_time"] = avg_rt
        
        # 500ms以下为低负荷，2000ms以上为高负荷
        rt_factor = max(0, min(1, (avg_rt - 500) / 1500))
        return rt_factor
    
    def _calculate_fatigue_factor(self, hr, motion) -> float:
        """
        计算疲劳迹象因子
        参考: Hartley & Bye (1980)
        """
        fatigue = 0
        
        if hr and hr > 100:
            fatigue += 0.3
        
        if len(self.history["heart_rate"]) > 10:
            recent_hr = list(self.history["heart_rate"])[-10:]
            if recent_hr[-1] > recent_hr[0] + 5:
                fatigue += 0.2
        
        if motion < 0.1:
            fatigue += 0.2
        
        return min(1.0, fatigue)
    
    def _reset_person_state(self):
        """重置人员相关状态"""
        self.user_state["face_count"] = 0
        self.user_state["emotion"]["primary"] = "unknown"
        self.user_state["emotion"]["positive"] = 0.5
        self.user_state["posture"]["type"] = "unknown"
        self.user_state["posture"]["stability"] = 0.5
        self.user_state["physical_load"]["heart_rate"] = None
        self.user_state["physical_load"]["fall_detected"] = False
        self.user_state["body_state"]["posture"] = "unknown"
    
    def update_game_data(self, reaction_time: float = None, success: bool = None):
        """
        更新游戏数据
        
        参数:
            reaction_time: 反应时间 (毫秒)
            success: 是否成功
        """
        with self.lock:
            if reaction_time is not None:
                self.game_data["reaction_times"].append(reaction_time)
                self.history["reaction_times"].append(reaction_time)
                if len(self.game_data["reaction_times"]) > 20:
                    self.game_data["reaction_times"] = self.game_data["reaction_times"][-20:]
            
            if success is not None:
                self.game_data["total_actions"] += 1
                if success:
                    self.game_data["successes"] += 1
                else:
                    self.game_data["errors"] += 1
    
    def get_difficulty_adjustment(self) -> Dict[str, Any]:
        """
        获取难度调整建议
        参考: Csikszentmihalyi (1990), Shute (2008), Hunicke (2005)
        
        返回:
            难度调整建议字典
        """
        with self.lock:
            physical = self.user_state["physical_load"]["value"]
            cognitive = self.user_state["cognitive_load"]["value"]
            engagement = self.user_state["engagement"]["value"]
            
            adjustment = 0
            reason = "normal"
            suggestions = []
            
            # 身体负荷判断
            if physical > 0.7:
                adjustment -= 2
                reason = "high_physical_load"
                suggestions.append("身体负荷较高，建议降低难度")
            elif physical > 0.5:
                adjustment -= 1
                suggestions.append("身体负荷略高")
            
            # 认知负荷判断
            if cognitive > 0.7:
                adjustment -= 2
                reason = "high_cognitive_load"
                suggestions.append("认知负荷较高，建议降低难度")
            elif cognitive > 0.5:
                adjustment -= 1
                suggestions.append("认知负荷略高")
            
            # 参与意愿判断
            if engagement < 0.3:
                adjustment -= 1
                reason = "low_engagement"
                suggestions.append("参与意愿较低，建议增加激励")
            elif engagement < 0.5:
                suggestions.append("参与意愿一般")
            
            # 最佳状态判断
            if physical < 0.4 and cognitive < 0.4 and engagement > 0.7:
                adjustment += 1
                reason = "optimal_state"
                suggestions.append("状态良好，可以适当增加挑战")
            
            # 限制调整幅度
            adjustment = max(-3, min(2, adjustment))
            
            return {
                "adjustment": adjustment,
                "reason": reason,
                "suggestions": suggestions,
                "physical_load": physical,
                "cognitive_load": cognitive,
                "engagement": engagement,
            }
    
    def safety_check(self) -> Dict[str, Any]:
        """
        安全检查
        参考: Rubenstein (2006)
        
        返回:
            安全检查结果
        """
        with self.lock:
            physical = self.user_state["physical_load"]["value"]
            fall_detected = self.user_state["physical_load"]["fall_detected"]
            
            if fall_detected:
                return {
                    "action": "pause",
                    "reason": "fall_detected",
                    "message": "检测到摔倒，游戏暂停",
                    "urgent": True
                }
            
            if physical > 0.9:
                return {
                    "action": "pause",
                    "reason": "physical_overload",
                    "message": "身体负荷过高，请休息",
                    "urgent": True
                }
            
            return {
                "action": "continue",
                "urgent": False
            }
    
    def get_state(self) -> Dict:
        """获取完整状态"""
        with self.lock:
            return self.user_state.copy()
    
    def get_summary(self) -> Dict:
        """获取状态摘要"""
        with self.lock:
            return {
                "person_detected": self.user_state["person_detected"],
                "face_detected": self.user_state["face_detected"],
                "body_detected": self.user_state["body_detected"],
                "face_count": self.user_state["face_count"],
                "heart_rate": self.user_state["physical_load"]["heart_rate"],
                "physical_load": self.user_state["physical_load"]["value"],
                "cognitive_load": self.user_state["cognitive_load"]["value"],
                "engagement": self.user_state["engagement"]["value"],
                "emotion": self.user_state["emotion"]["primary"],
                "is_smiling": self.user_state["emotion"]["is_smiling"],
                "posture": self.user_state["posture"]["type"],
                "fall_detected": self.user_state["physical_load"]["fall_detected"],
                "activity_level": self.user_state["activity"]["level"],
                "state_summary": self.user_state["overall"]["state_summary"],
            }
