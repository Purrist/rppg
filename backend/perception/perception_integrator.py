
# -*- coding: utf-8 -*-
"""
Perception Integrator - 感知系统整合模块
将 perception.py 中的核心逻辑提取为可导入模块
不启动独立的 Flask 应用，而是集成到 app.py 主系统
"""

import os
import sys
import time
import threading
import atexit
import requests
from collections import deque

# 导入 DDA 系统
from .dda import DDASystem

# ========================================
# 常量配置
# ========================================
AU_ALL_API = "http://127.0.0.1:5010/api/all"  # 获取完整的 AU/FER/Fusion 数据
AU_EMOTION_API = "http://127.0.0.1:5010/api/fusion"
AU_STATUS_API = "http://127.0.0.1:5010/api/status"
HLKK_DATA_API = "http://127.0.0.1:5020/data"


# ========================================
# EmotionProcessor - 情绪与生理数据处理
# ========================================
class EmotionProcessor:
    def __init__(self):
        self.emotion_data = {
            "neutral": 0.0,
            "positive": 0.0,
            "negative": 0.0,
            "confidence": 0.0,
            "emotion": "neutral",
            "engagement": "None",
            "timestamp": 0
        }
        self.physio_data = {
            "heart": 0,
            "breath": 0,
            "human": False,
            "timestamp": 0,
            "hr_valid": False,
            "hr_valid_since": 0,
            "hrr_pct": 0,
            "hr_slope": 0
        }
        self.face_data = {
            "face_detected": False,
            "face_count": 0,
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "pose": "-",
            "is_front_face": False
        }
        self.processed_emotion = {
            "label": "neutral",
            "confidence": 0.0,
            "value": 0,
            "timestamp": 0
        }
        self.lock = threading.Lock()
        self.enabled = True
        self.gate_enabled = True
        self.history = []
        self.history_max = 300
        self.start_time = time.time()
        self.startup_grace_period = 30
        
        # ⭐ 保存原始 API 数据
        self._raw_physio_data = None
        self._raw_au_data = None
        self._raw_fer_data = None
        self._raw_fusion_data = None

    def fetch_au_emotion(self):
        try:
            resp = requests.get(AU_EMOTION_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                # ⭐ 保存原始 fusion 数据
                self._raw_fusion_data = d
                scores = d.get("scores", {})
                return {
                    "neutral": scores.get("neutral", 0),
                    "positive": scores.get("positive", 0),
                    "negative": scores.get("negative", 0),
                    "confidence": d.get("confidence", 0),
                    "emotion": d.get("emotion", "neutral"),
                    "engagement": d.get("tag", "None"),
                    "timestamp": time.time()
                }
        except Exception:
            pass
        return None

    def fetch_face_status(self):
        try:
            resp = requests.get(AU_STATUS_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                # ⭐ 保存原始 AU 和 FER 数据
                self._raw_au_data = d.get('au', d)
                self._raw_fer_data = d.get('fer', None)
                return {
                    "face_detected": d.get("face_detected", False),
                    "face_count": d.get("face_count", 0),
                    "pitch": d.get("pitch", 0.0),
                    "yaw": d.get("yaw", 0.0),
                    "roll": d.get("roll", 0.0),
                    "pose": d.get("pose", "-"),
                    "is_front_face": abs(d.get("yaw", 0)) < 35 and abs(d.get("pitch", 0)) < 25
                }
        except Exception:
            pass
        return None

    def fetch_physio_data(self):
        try:
            resp = requests.get(HLKK_DATA_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                # ⭐ 保存原始生理数据
                self._raw_physio_data = d
                raw = d.get("raw", {})
                physiology = d.get("physiology", {})
                return {
                    "heart": raw.get("hr", 0),
                    "breath": raw.get("br", 0),
                    "human": raw.get("is_human", 0) == 1,
                    "timestamp": time.time(),
                    "hr_valid": raw.get("hr_valid", False),
                    "hrr_pct": physiology.get("hrr_pct", 0),
                    "hr_slope": physiology.get("hr_slope", 0)
                }
        except Exception as e:
            pass
        return None
    
    def fetch_all_emotion_data(self):
        """
        获取完整的 AU/FER/Fusion 数据（使用 /api/all 接口）
        """
        try:
            resp = requests.get(AU_ALL_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                # ⭐ 保存所有原始数据
                self._raw_au_data = d.get('au', {})
                self._raw_fer_data = d.get('fer', {})
                self._raw_fusion_data = d.get('fusion', {})
                return d
        except Exception as e:
            pass
        return None

    def apply_gate(self, emotion_data):
        if not self.gate_enabled:
            return {
                "label": emotion_data.get("emotion", "neutral"),
                "confidence": emotion_data.get("confidence", 0),
                "value": self.emotion_to_value(emotion_data.get("emotion", "neutral")),
                "timestamp": emotion_data.get("timestamp", time.time())
            }

        emotion = emotion_data.get("emotion", "neutral")

        special_states = {'no_face', 'out_of_range', 'speaking', 'uncalibrated'}
        if emotion in special_states:
            return {
                "label": emotion,
                "confidence": 0,
                "value": 0,
                "timestamp": emotion_data.get("timestamp", time.time())
            }

        scores = {
            'positive': emotion_data.get("positive", 0),
            'neutral': emotion_data.get("neutral", 0),
            'negative': emotion_data.get("negative", 0)
        }
        conf = emotion_data.get("confidence", 0)

        label_cn = self.classify_confidence(scores)
        label = self.cn_label_to_en(label_cn)
        value = self.emotion_to_value(label)

        p1 = max(scores.values())
        confidence = min(p1 * conf * 1.5, 1.0)

        return {
            "label": label,
            "confidence": confidence,
            "value": value,
            "timestamp": emotion_data.get("timestamp", time.time())
        }

    def classify_confidence(self, scores):
        p_pos = scores['positive']
        p_neu = scores['neutral']
        p_neg = scores['negative']

        items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        (e1, p1), (e2, p2), (e3, p3) = items

        mu = p_pos - p_neg

        if p1 >= 0.70 and (p1 - p2) >= 0.20:
            if e1 == 'positive' and p_neg <= 0.15:
                return '积极高信度'
            if e1 == 'negative' and p_pos <= 0.15:
                return '消极高信度'
            if e1 == 'neutral' and max(p_pos, p_neg) <= 0.15:
                return '中性高信度'

        if p_pos > 0.10 and p_neg > 0.10 and abs(mu) < 0.25:
            return '中性'

        if p1 - p3 <= 0.20:
            return '中性'

        if e1 == 'neutral' and p_neu >= 0.50:
            if abs(mu) >= 0.30:
                return '积极低信度' if mu > 0 else '消极低信度'
            return '中性'

        if e1 == 'positive':
            if mu < 0.20:
                return '中性'
            return '积极低信度'

        if e1 == 'negative':
            if -mu < 0.20:
                return '中性'
            return '消极低信度'

        if abs(mu) >= 0.25:
            return '积极低信度' if mu > 0 else '消极低信度'

        return '中性'

    def cn_label_to_en(self, label_cn):
        mapping = {
            '积极高信度': 'positive_high',
            '消极高信度': 'negative_high',
            '中性高信度': 'neutral_high',
            '积极低信度': 'positive_low',
            '消极低信度': 'negative_low',
            '中性': 'neutral'
        }
        return mapping.get(label_cn, 'neutral')

    def emotion_to_value(self, label):
        mapping = {
            'positive_high': 1,
            'positive_low': 0.5,
            'neutral': 0,
            'neutral_high': 0,
            'negative_low': -0.5,
            'negative_high': -1,
            'positive': 1,
            'negative': -1
        }
        return mapping.get(label, 0)

    def update(self):
        # ⭐ 优先使用 /api/all 获取完整数据
        all_emotion_data = self.fetch_all_emotion_data()
        au_data = None
        face = None
        
        if all_emotion_data:
            # 从完整数据中提取需要的部分
            fusion_data = all_emotion_data.get('fusion', {})
            au_info = all_emotion_data.get('au', {})
            if fusion_data:
                scores = fusion_data.get("scores", {})
                au_data = {
                    "neutral": scores.get("neutral", 0),
                    "positive": scores.get("positive", 0),
                    "negative": scores.get("negative", 0),
                    "confidence": fusion_data.get("confidence", 0),
                    "emotion": fusion_data.get("emotion", "neutral"),
                    "engagement": fusion_data.get("tag", "None"),
                    "timestamp": time.time()
                }
            if au_info:
                face = {
                    "face_detected": au_info.get("face_detected", False),
                    "face_count": au_info.get("face_count", 0),
                    "pitch": au_info.get("pitch", 0.0),
                    "yaw": au_info.get("yaw", 0.0),
                    "roll": au_info.get("roll", 0.0),
                    "pose": au_info.get("pose", "-"),
                    "is_front_face": abs(au_info.get("yaw", 0)) < 35 and abs(au_info.get("pitch", 0)) < 25
                }
        else:
            # 回退到旧的方法
            au_data = self.fetch_au_emotion()
            face = self.fetch_face_status()
        
        physio = self.fetch_physio_data()

        with self.lock:
            if au_data:
                self.emotion_data = au_data
                self.processed_emotion = self.apply_gate(au_data)
                self.history.append({
                    "emotion": self.emotion_data.copy(),
                    "processed": self.processed_emotion.copy(),
                    "timestamp": time.time()
                })
                if len(self.history) > self.history_max:
                    self.history.pop(0)

            if physio:
                if physio.get("hr_valid", False):
                    physio["hr_valid_since"] = time.time()
                else:
                    physio["hr_valid_since"] = self.physio_data.get("hr_valid_since", 0)
                self.physio_data = physio

            if face:
                self.face_data = face

    def get_current(self):
        with self.lock:
            return {
                "emotion": self.emotion_data.copy(),
                "processed": self.processed_emotion.copy(),
                "physio": self.physio_data.copy(),
                "face": self.face_data.copy(),
                "history": list(self.history)
            }


# ========================================
# PersonAnalyzer - 年龄性别识别分析
# ========================================
class PersonAnalyzer:
    def __init__(self):
        # 从 emotion.py 获取对齐人脸的地址
        self.aligned_face_url = "http://127.0.0.1:5010/api/aligned_face"
        
        # 模型选择：'deepface' 或 'onnx'
        self.current_model = 'deepface'
        
        # 加载 ONNX 模型（如果可用）
        self.age_session = None
        self.gender_session = None
        self.load_onnx_models()
        
        # 人脸数据库相关
        self.face_detector = None  # 暂时不需要，因为 emotion.py 已经对齐好了
        
        # 结果存储
        self.lock = threading.Lock()
        self.result = {
            "age": 0,
            "age_range": "--",
            "age_confidence": 0.0,
            "gender": "--",
            "gender_confidence": 0.0,
            "face_detected": False,
            "face_count": 0,
            "timestamp": time.time(),
            "age_model": {"available": False},
            "gender_model": {"available": False},
            "user_id": None,
            "user_name": "--",
            "user_confidence": 0.0,
            "is_new_user": False,
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "pose": "-",
            "is_front_face": False
        }
        
        # 平滑缓存
        self.age_buffer = []
        self.gender_buffer = []
        self.buffer_size = 2
        
        # 帧计数
        self._fc = 0
        
        # HLKK 发送相关
        self.last_hlkk_update_time = 0
        self.hlkk_update_interval = 20  # 20秒发送一次
        self.cached_age = 0
        self.cached_gender = "--"
        self._hlkk_fail_count = 0
        
        # 初始化 DeepFace
        self.deepface_available = False
        try:
            import mediapipe as mp
            from deepface import DeepFace
            self.deepface_available = True
            print("[PersonAnalyzer] DeepFace 已初始化")
        except Exception as e:
            print(f"[PersonAnalyzer] DeepFace 初始化失败: {e}")
    
    def load_onnx_models(self):
        """尝试加载 ONNX 模型"""
        try:
            import onnxruntime as ort
            model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core", "models")
            age_model_path = os.path.join(model_dir, "age_googlenet.onnx")
            gender_model_path = os.path.join(model_dir, "gender_googlenet.onnx")
            
            if os.path.exists(age_model_path):
                self.age_session = ort.InferenceSession(age_model_path, providers=['CPUExecutionProvider'])
                print(f"[PersonAnalyzer] 年龄模型加载成功: {age_model_path}")
            
            if os.path.exists(gender_model_path):
                self.gender_session = ort.InferenceSession(gender_model_path, providers=['CPUExecutionProvider'])
                print(f"[PersonAnalyzer] 性别模型加载成功: {gender_model_path}")
                
        except Exception as e:
            print(f"[PersonAnalyzer] ONNX 模型加载失败: {e}")
    
    def preprocess_face(self, face_img):
        """人脸预处理（用于 ONNX 模型）"""
        import cv2
        import numpy as np
        
        if len(face_img.shape) == 2:
            face_img = cv2.cvtColor(face_img, cv2.COLOR_GRAY2RGB)
        elif face_img.shape[2] == 4:
            face_img = cv2.cvtColor(face_img, cv2.COLOR_BGRA2RGB)
        
        face_img = cv2.resize(face_img, (224, 224))
        
        mean = np.array([123.68, 116.779, 103.939])
        std = np.array([58.395, 57.125, 57.375])
        face_img = (face_img - mean) / std
        
        face_img = np.transpose(face_img, (2, 0, 1))
        face_img = np.expand_dims(face_img, axis=0).astype(np.float32)
        
        return face_img
    
    def fetch_aligned_face(self):
        """从 emotion.py 获取对齐后的人脸图像"""
        try:
            import cv2
            import numpy as np
            
            resp = requests.get(self.aligned_face_url, timeout=0.5)
            if resp.status_code == 200:
                img_array = np.asarray(bytearray(resp.content), dtype=np.uint8)
                return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"[PersonAnalyzer] 获取对齐人脸失败: {e}")
        return None
    
    def _age_to_range(self, age):
        """年龄转换为范围"""
        age = int(age)
        if age < 20:
            return '0-20'
        elif age < 40:
            return '20-40'
        elif age < 60:
            return '40-60'
        elif age < 80:
            return '60-80'
        else:
            return '80-100'
    
    def analyze_face_deepface(self):
        """使用 DeepFace 分析年龄性别"""
        if not self.deepface_available:
            return None
        
        aligned_face = self.fetch_aligned_face()
        if aligned_face is None:
            return None
        
        try:
            from deepface import DeepFace
            
            result = DeepFace.analyze(
                aligned_face,
                actions=['age', 'gender'],
                enforce_detection=False,
                detector_backend='skip',
                silent=True
            )
            
            if result:
                if isinstance(result, list):
                    result = result[0]
                
                age = result.get('age', 0)
                dominant_gender = result.get('dominant_gender', '--')
                gender_dict = result.get('gender', {})
                
                # 获取性别置信度
                if isinstance(gender_dict, dict):
                    if dominant_gender == 'Man':
                        gender_conf = gender_dict.get('Man', 0.5)
                    elif dominant_gender == 'Woman':
                        gender_conf = gender_dict.get('Woman', 0.5)
                    else:
                        gender_conf = 0.5
                else:
                    gender_conf = 0.5
                
                # 置信度标准化
                if gender_conf > 1.5:
                    gender_conf = gender_conf / 100
                gender_conf = max(0.0, min(1.0, gender_conf))
                
                return {
                    "age": age,
                    "age_range": self._age_to_range(age),
                    "age_confidence": 0.85,
                    "gender": "男" if dominant_gender == 'Man' else "女" if dominant_gender == 'Woman' else "--",
                    "gender_confidence": gender_conf,
                    "face_count": 1,
                    "age_model": {"available": True, "model": "DeepFace"},
                    "gender_model": {"available": True, "model": "DeepFace"},
                    "using_aligned_face": True
                }
        except Exception as e:
            print(f"[PersonAnalyzer] DeepFace 分析失败: {e}")
        return None
    
    def analyze_face_onnx(self):
        """使用 ONNX 模型分析年龄性别"""
        if not self.age_session and not self.gender_session:
            return None
        
        aligned_face = self.fetch_aligned_face()
        if aligned_face is None:
            return None
        
        face_img = aligned_face
        age_model_result = {"available": False}
        gender_model_result = {"available": False}
        
        try:
            import numpy as np
            
            input_tensor = self.preprocess_face(face_img)
            
            age_pred = None
            age_conf = 0.0
            age_scores = []
            if self.age_session:
                age_output = self.age_session.run(None, {self.age_session.get_inputs()[0].name: input_tensor})[0]
                age_pred = np.argmax(age_output[0])
                age_conf = float(age_output[0][age_pred])
                age_scores = [float(x) for x in age_output[0]]
                age_model_result = {
                    "available": True,
                    "prediction": int(age_pred),
                    "confidence": age_conf,
                    "scores": age_scores,
                    "ranges": ['0-20', '20-40', '40-60', '60-80', '80-100']
                }
            
            gender_pred = None
            gender_conf = 0.0
            gender_scores = []
            if self.gender_session:
                gender_output = self.gender_session.run(None, {self.gender_session.get_inputs()[0].name: input_tensor})[0]
                gender_pred = np.argmax(gender_output[0])
                gender_conf = float(gender_output[0][gender_pred])
                gender_scores = [float(x) for x in gender_output[0]]
                gender_model_result = {
                    "available": True,
                    "prediction": int(gender_pred),
                    "confidence": gender_conf,
                    "scores": gender_scores,
                    "labels": ["男", "女"]
                }
            
            return {
                "age": age_pred,
                "age_range": ['0-20', '20-40', '40-60', '60-80', '80-100'][age_pred] if age_pred is not None else "--",
                "age_confidence": age_conf if age_pred is not None else 0.0,
                "gender": "男" if gender_pred == 0 else "女" if gender_pred == 1 else "--",
                "gender_confidence": gender_conf if gender_pred is not None else 0.0,
                "face_count": 1,
                "age_model": age_model_result,
                "gender_model": gender_model_result,
                "using_onnx": True
            }
        except Exception as e:
            print(f"[PersonAnalyzer] ONNX 人脸分析失败: {e}")
        return None
    
    def analyze_face(self):
        """根据当前设置的模型进行分析"""
        if self.current_model == 'onnx':
            return self.analyze_face_onnx()
        else:
            return self.analyze_face_deepface()
    
    def smooth_result(self, result):
        """平滑结果"""
        if result["age"] is not None and result["age"] > 0:
            self.age_buffer.append(result["age"])
            if len(self.age_buffer) > self.buffer_size:
                self.age_buffer.pop(0)
            result["age"] = int(sum(self.age_buffer) / len(self.age_buffer))
        
        gender_val = result.get("gender", "")
        if gender_val in ["Man", "Woman", "男", "女"]:
            self.gender_buffer.append(gender_val)
            if len(self.gender_buffer) > self.buffer_size:
                self.gender_buffer.pop(0)
            # 简单多数投票
            from collections import Counter
            counter = Counter(self.gender_buffer)
            result["gender"] = counter.most_common(1)[0][0]
        
        return result
    
    def fetch_emotion_status(self):
        """从emotion模块获取人脸和姿态信息"""
        try:
            resp = requests.get(AU_STATUS_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "face_detected": d.get('face_detected', False),
                    "face_count": d.get('face_count', 0),
                    "pitch": d.get('pitch', 0),
                    "yaw": d.get('yaw', 0),
                    "roll": d.get('roll', 0),
                    "pose": d.get('pose', '-'),
                    "is_front_face": abs(d.get('yaw', 0)) < 35 and abs(d.get('pitch', 0)) < 25
                }
        except Exception as e:
            print(f"[PersonAnalyzer] 获取情绪状态失败: {e}")
        return None
    
    def update(self):
        """更新分析"""
        current_time = time.time()
        
        # 获取情绪模块的人脸和姿态信息
        emotion_status = self.fetch_emotion_status()
        
        with self.lock:
            res = dict(self.result)
            
            if emotion_status:
                res.update({
                    "face_detected": emotion_status["face_detected"],
                    "face_count": emotion_status["face_count"],
                    "pitch": round(emotion_status["pitch"], 1),
                    "yaw": round(emotion_status["yaw"], 1),
                    "roll": round(emotion_status["roll"], 1),
                    "pose": emotion_status["pose"],
                    "is_front_face": emotion_status["is_front_face"],
                    "timestamp": current_time
                })
                
                # 只在正脸且每10帧检测一次年龄性别
                self._fc += 1
                should_detect = emotion_status["pose"] == 'front' and self._fc % 10 == 0
                if should_detect:
                    analysis = self.analyze_face()
                    
                    if analysis:
                        # 添加置信度过滤，只接受高置信度的结果
                        min_confidence = 0.5
                        if analysis["age_confidence"] >= min_confidence and analysis["gender_confidence"] >= min_confidence:
                            analysis = self.smooth_result(analysis)
                            res.update({
                                "age": analysis["age"],
                                "age_range": analysis["age_range"],
                                "age_confidence": analysis["age_confidence"],
                                "gender": analysis["gender"],
                                "gender_confidence": analysis["gender_confidence"],
                                "age_model": analysis["age_model"],
                                "gender_model": analysis["gender_model"],
                            })
            
            self.result = res
    
    def _try_update_hlkk(self):
        """向 hlkk.py 发送年龄和性别数据"""
        current_time = time.time()
        if current_time - self.last_hlkk_update_time < self.hlkk_update_interval:
            return
        
        with self.lock:
            age = self.result.get("age", 0)
            gender = self.result.get("gender", "--")
        
        try:
            if age > 0 and gender in ["男", "女"]:
                gender_en = "male" if gender == "男" else "female"
                url = f"http://127.0.0.1:5020/person?age={age}&gender={gender_en}"
            else:
                url = "http://127.0.0.1:5020/person?age=-&gender=-"
            
            resp = requests.get(url, timeout=0.5)
            if resp.status_code == 200:
                self.last_hlkk_update_time = current_time
                if age > 0 and gender in ["男", "女"]:
                    self.cached_age = age
                    self.cached_gender = gender
                self._hlkk_fail_count = 0
                print(f"[PersonAnalyzer] 成功向 HLKK 发送数据: age={age}, gender={gender}")
        except Exception as e:
            self._hlkk_fail_count += 1
            if self._hlkk_fail_count % 10 == 0:
                print(f"[PersonAnalyzer] HLKK 服务连接失败次数: {self._hlkk_fail_count}")
    
    def get_result(self):
        """获取当前结果"""
        with self.lock:
            return self.result.copy()
    
    def start(self):
        """启动分析循环"""
        def run_loop():
            while True:
                try:
                    self.update()
                    self._try_update_hlkk()
                except Exception as e:
                    print(f"[PersonAnalyzer] 循环错误: {e}")
                time.sleep(0.1)
        
        threading.Thread(target=run_loop, daemon=True).start()
        print("[PersonAnalyzer] 已启动")


# ========================================
# 更新 PerceptionIntegrator 以包含 PersonAnalyzer
# ========================================
# 修改 PerceptionIntegrator 类的 __init__ 方法，添加 PersonAnalyzer
class PerceptionIntegrator:
    def __init__(self, socketio=None, system_core=None):
        self.socketio = socketio
        self.system_core = system_core

        # 初始化组件
        self.emotion_processor = EmotionProcessor()
        
        # ⭐ 新增：PersonAnalyzer 年龄性别分析
        self.person_analyzer = PersonAnalyzer()

        # 子进程管理
        self.child_processes = []
        self.running = False

        # 注册退出清理
        atexit.register(self.cleanup)

    def start_child_processes(self):
        """启动子进程（au/emotion.py, hlkk.py）"""
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # 启动 AU 情绪模块
        au_emotion_script = os.path.join(script_dir, "au", "emotion.py")
        if os.path.exists(au_emotion_script):
            print(f"[PerceptionIntegrator] 启动 AU 情绪模块: {au_emotion_script}")
            import subprocess
            au_proc = subprocess.Popen([sys.executable, au_emotion_script],
                                        cwd=os.path.join(script_dir, "au"))
            self.child_processes.append(au_proc)

        # 启动 HLKK 生理模块
        hlkk_script = os.path.join(script_dir, "hlkk.py")
        if os.path.exists(hlkk_script):
            print(f"[PerceptionIntegrator] 启动 HLKK 生理模块: {hlkk_script}")
            import subprocess
            hlkk_proc = subprocess.Popen([sys.executable, hlkk_script],
                                          cwd=script_dir)
            self.child_processes.append(hlkk_proc)

    def cleanup(self):
        """清理子进程"""
        print("[PerceptionIntegrator] 正在停止子进程...")
        for proc in self.child_processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in self.child_processes:
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        print("[PerceptionIntegrator] 所有子进程已停止")

    def update_perception_to_system_core(self):
        """将感知数据更新到 system_core"""
        try:
            with self.emotion_processor.lock:
                # 获取原始 API 数据
                raw_physio_data = self.emotion_processor._raw_physio_data if hasattr(self.emotion_processor, '_raw_physio_data') else None
                raw_au_data = self.emotion_processor._raw_au_data if hasattr(self.emotion_processor, '_raw_au_data') else None
                raw_fer_data = self.emotion_processor._raw_fer_data if hasattr(self.emotion_processor, '_raw_fer_data') else None
                raw_fusion_data = self.emotion_processor._raw_fusion_data if hasattr(self.emotion_processor, '_raw_fusion_data') else None
                
                # 获取原始处理后的数据
                physio = self.emotion_processor.physio_data
                emotion = self.emotion_processor.processed_emotion
                face_data = self.emotion_processor.face_data

            # 获取数据
            hr_valid = physio.get('hr_valid', False)
            hrr_pct = physio.get('hrr_pct', 0)
            hr_slope = physio.get('hr_slope', 0)
            heart_rate = physio.get('heart', 0)

            face_detected = face_data.get('face_detected', True)
            face_count = face_data.get('face_count', 1)

            label = emotion.get('label', 'neutral')
            confidence = emotion.get('confidence', 0)

            # 将情绪标签转换为 system_core 能用的格式
            emotion_map = {
                'positive_high': 'happy',
                'positive_low': 'happy',
                'negative_high': 'sad',
                'negative_low': 'sad',
                'neutral_high': 'neutral',
                'neutral': 'neutral'
            }
            simple_emotion = emotion_map.get(label, 'neutral')

            if self.system_core:
                # 调用 system_core 的 update_perception 方法
                self.system_core.update_perception({
                    'personDetected': face_detected,
                    'personCount': face_count,
                    'faceCount': face_count,
                    'bodyDetected': face_detected,
                    'emotion': simple_emotion,
                    'attention': confidence if confidence else 0.5,
                    'fatigue': 0,  # 暂时由其他模块处理
                    'heartRate': heart_rate if hr_valid else None,
                    'activity': 'standing' if face_detected else 'unknown',
                })

                # 同时保存 DDA 专用的完整感知数据
                self.system_core.set_dda_perception_data({
                    'hr_valid': hr_valid,
                    'hrr_pct': hrr_pct,
                    'hr_slope': hr_slope,
                    'emotion': label,
                    'confidence': confidence,
                    'face_detected': face_detected,
                    'face_count': face_count
                })
                
                # ⭐ 更新完整的生理数据（来自 hlkk.py）
                if raw_physio_data:
                    raw_data = raw_physio_data.get('raw', {})
                    physiology_data = raw_physio_data.get('physiology', {})
                    
                    # ⭐ 字段映射和标签生成
                    analysis_data = {}
                    
                    # 映射原始字段
                    analysis_data['hrr'] = physiology_data.get('hrr_pct')
                    analysis_data['slope'] = physiology_data.get('hr_slope')
                    analysis_data['brv'] = physiology_data.get('brv_cv')
                    analysis_data['brel'] = physiology_data.get('br_elevation')
                    analysis_data['cr'] = physiology_data.get('cr_ratio')
                    analysis_data['plv'] = physiology_data.get('plv_r')
                    analysis_data['mean_phase_diff'] = physiology_data.get('mean_phase_diff')
                    
                    # ⭐ 生成标签
                    # HRR 标签
                    hrr_val = physiology_data.get('hrr_pct')
                    if hrr_val is not None:
                        if hrr_val < 30:
                            analysis_data['hrr_label'] = '静息'
                        elif hrr_val < 50:
                            analysis_data['hrr_label'] = '低强度'
                        elif hrr_val < 70:
                            analysis_data['hrr_label'] = '中等强度'
                        else:
                            analysis_data['hrr_label'] = '高强度'
                    else:
                        analysis_data['hrr_label'] = None
                    
                    # 斜率标签
                    slope_val = physiology_data.get('hr_slope')
                    if slope_val is not None:
                        if slope_val > 0.5:
                            analysis_data['slope_label'] = '快速上升'
                        elif slope_val > 0.1:
                            analysis_data['slope_label'] = '缓慢上升'
                        elif slope_val < -0.5:
                            analysis_data['slope_label'] = '快速下降'
                        elif slope_val < -0.1:
                            analysis_data['slope_label'] = '缓慢下降'
                        else:
                            analysis_data['slope_label'] = '稳定'
                    else:
                        analysis_data['slope_label'] = None
                    
                    # BRV 标签
                    brv_val = physiology_data.get('brv_cv')
                    if brv_val is not None:
                        if brv_val < 0.2:
                            analysis_data['brv_label'] = '规律'
                        elif brv_val < 0.4:
                            analysis_data['brv_label'] = '一般'
                        else:
                            analysis_data['brv_label'] = '不规律'
                    else:
                        analysis_data['brv_label'] = None
                    
                    # BRE 标签
                    brel_val = physiology_data.get('br_elevation')
                    if brel_val is not None:
                        if brel_val < 8:
                            analysis_data['brel_label'] = '偏低'
                        elif brel_val < 15:
                            analysis_data['brel_label'] = '正常'
                        else:
                            analysis_data['brel_label'] = '偏高'
                    else:
                        analysis_data['brel_label'] = None
                    
                    # CR 标签
                    cr_val = physiology_data.get('cr_ratio')
                    if cr_val is not None:
                        if cr_val < 3:
                            analysis_data['cr_label'] = '偏低'
                        elif cr_val < 6:
                            analysis_data['cr_label'] = '正常'
                        else:
                            analysis_data['cr_label'] = '偏高'
                    else:
                        analysis_data['cr_label'] = None
                    
                    # PLV 标签
                    plv_val = physiology_data.get('plv_r')
                    if plv_val is not None:
                        if plv_val < 0.3:
                            analysis_data['plv_label'] = '弱耦合'
                        elif plv_val < 0.7:
                            analysis_data['plv_label'] = '中等耦合'
                        else:
                            analysis_data['plv_label'] = '深度放松'
                    else:
                        analysis_data['plv_label'] = None
                    self.system_core.update_physiology_data(raw_data, analysis_data)
                
                # ⭐ 更新完整的面部/情绪数据（来自 emotion.py）
                self.system_core.update_face_emotion_data(
                    au_data=raw_au_data,
                    fer_data=raw_fer_data,
                    fusion_data=raw_fusion_data
                )

        except Exception as e:
            print(f"[PerceptionIntegrator] 更新感知数据失败: {e}")

    def update_loop(self):
        """主更新循环"""
        last_processor_update = time.time()
        last_core_update = time.time()

        while self.running:
            current_time = time.time()

            # 更新情绪与生理数据
            if current_time - last_processor_update >= 0.5:
                last_processor_update = current_time
                self.emotion_processor.update()

            # 定期更新到 system_core
            if current_time - last_core_update >= 1.0:
                last_core_update = current_time
                self.update_perception_to_system_core()

            time.sleep(0.1)

    def start(self):
        """启动整合器"""
        print("[PerceptionIntegrator] 正在启动...")
        self.running = True

        # 启动子进程
        self.start_child_processes()

        # 等待子进程启动
        time.sleep(3)

        # 启动更新循环
        threading.Thread(target=self.update_loop, daemon=True).start()
        
        # ⭐ 启动 PersonAnalyzer
        self.person_analyzer.start()
        
        print("[PerceptionIntegrator] 已启动")

    def stop(self):
        """停止整合器"""
        self.running = False
        self.cleanup()


