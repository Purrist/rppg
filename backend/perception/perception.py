# -*- coding: utf-8 -*-
"""
Perception - 情绪与生理数据综合展示模块
整合 AU+FER 情绪数据与心率呼吸率数据，提供进一步的情感分析
同时整合人脸年龄和性别分析功能
"""
import os
import cv2
import numpy as np
import onnxruntime as ort
import json
import time
import threading
import requests
import subprocess
import atexit
import sys
from collections import deque, Counter
import logging
from flask import Flask, render_template, jsonify, request, Response

# 完全禁用Flask日志
logging.getLogger('werkzeug').setLevel(logging.CRITICAL)
logging.getLogger('flask').setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.CRITICAL)

# 关键！先导入关键第三方库，然后临时移除当前目录，导入sixdrepnet！
try:
    import mediapipe as mp
    from deepface import DeepFace
    
    # 保存当前sys.path
    original_sys_path = sys.path.copy()
    # 移除当前目录，防止sixdrepnet导入错误的utils.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path = [p for p in sys.path if p != current_dir and p != '']
    
    try:
        from sixdrepnet import SixDRepNet
    except Exception:
        SixDRepNet = None
    finally:
        # 恢复原始sys.path
        sys.path = original_sys_path
    
    # 关键！设置DeepFace去正确的父目录，因为它会自动加一层.deepface！
    os.environ['DEEPFACE_HOME'] = "C:\\Users\\purriste"
except Exception as e:
    print(f"警告: 无法导入人脸分析相关库: {e}")
    mp = None
    DeepFace = None
    SixDRepNet = None

app = Flask(__name__)

AU_EMOTION_API = "http://127.0.0.1:5010/api/fusion"

from dda import DDASystem
dda_system = DDASystem()
# 开局默认难度为4，DDA是唯一的难度调整源
dda_system.current_difficulty = 4
AU_STATUS_API = "http://127.0.0.1:5010/api/status"
HLKK_DATA_API = "http://127.0.0.1:5020/data"

PERSON_HTTP_PORT = 5090
IP_CAMERA_URL = "http://192.168.137.25:8080/video"

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core", "models")
AGE_MODEL_PATH = os.path.join(MODEL_DIR, "age_googlenet.onnx")
GENDER_MODEL_PATH = os.path.join(MODEL_DIR, "gender_googlenet.onnx")
FACE_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'face_database')

os.makedirs(FACE_DB_DIR, exist_ok=True)

AGE_RANGES = ['0-20', '20-40', '40-60', '60-80', '80-100']
RECOGNITION_THRESHOLD = 0.3  # 人脸匹配阈值

# ── 人脸识别组件 ──
class FaceDatabase:
    """人脸数据库管理类"""
    
    def __init__(self, db_dir):
        self.db_dir = db_dir
        self.db_file = os.path.join(db_dir, "face_db.json")
        self.face_embeddings_dir = os.path.join(db_dir, "embeddings")
        os.makedirs(self.face_embeddings_dir, exist_ok=True)
        self.db = self._load_db()
    
    def _load_db(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"users": [], "next_id": 1}
    
    def _save_db(self):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, ensure_ascii=False, indent=2)
    
    def _generate_user_id(self):
        user_id = self.db["next_id"]
        self.db["next_id"] += 1
        return user_id
    
    def get_all_embeddings(self):
        all_embeddings = []
        all_user_ids = []
        for user in self.db["users"]:
            user_id = user["id"]
            emb_file = os.path.join(self.face_embeddings_dir, f"{user_id}_embedding.npy")
            if os.path.exists(emb_file):
                embedding = np.load(emb_file)
                all_embeddings.append(embedding)
                all_user_ids.append(user_id)
        return np.array(all_embeddings), all_user_ids
    
    def add_new_user(self, embedding):
        user_id = self._generate_user_id()
        user_name = f"用户{user_id:04d}"
        user = {
            "id": user_id,
            "name": user_name,
            "created_at": time.time()
        }
        self.db["users"].append(user)
        self._save_db()
        
        emb_file = os.path.join(self.face_embeddings_dir, f"{user_id}_embedding.npy")
        np.save(emb_file, embedding)
        
        return user
    
    def find_user(self, user_id):
        for user in self.db["users"]:
            if user["id"] == user_id:
                return user
        return None


class PersonAnalyzer:
    def __init__(self):
        # 视频流用 emotion.py 的（只用来显示，分析只用对齐人脸）
        self.video_stream_url = "http://127.0.0.1:5010/video_feed"
        self.aligned_face_url = "http://127.0.0.1:5010/api/aligned_face"
        self.cap = None
        self._reconnect_attempts = 0

        # 模型选择: 'deepface' 或 'onnx'
        self.current_model = 'deepface'

        self.age_session = None
        self.gender_session = None
        self.load_models()
        
        # 保留haar级联检测器用于ONNX模型分析（备用）
        self.face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        self.lock = threading.Lock()
        self.running = False
        self.raw_frame = None
        self.last_encoded_frame = None
        
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
        
        self.age_buffer = []
        self.gender_buffer = []
        self.buffer_size = 2
        
        self.last_detection_time = 0
        # 改为每10帧检测一次
        self.detection_interval = 0.3
        
        self.max_reconnect_attempts = 10
        
        # 帧计数
        self._fc = 0
        
        # HLKK定时更新相关
        self.last_hlkk_update_time = 0
        self.hlkk_update_interval = 20  # 20秒发送一次
        self.cached_age = 0
        self.cached_gender = "--"
    
    def _connect(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
        
        self.cap = cv2.VideoCapture(self.video_stream_url)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._reconnect_attempts = 0
            return True
        
        self.cap.release()
        self.cap = None
        return False

    def load_models(self):
        try:
            if os.path.exists(AGE_MODEL_PATH):
                self.age_session = ort.InferenceSession(AGE_MODEL_PATH, providers=['CPUExecutionProvider'])
                print("年龄模型加载成功")
            else:
                print(f"年龄模型未找到: {AGE_MODEL_PATH}")
            
            if os.path.exists(GENDER_MODEL_PATH):
                self.gender_session = ort.InferenceSession(GENDER_MODEL_PATH, providers=['CPUExecutionProvider'])
                print("性别模型加载成功")
            else:
                print(f"性别模型未找到: {GENDER_MODEL_PATH}")
        except Exception as e:
            print(f"模型加载失败: {e}")

    def preprocess_face(self, face_img):
        if len(face_img.shape) == 2:
            face_img = cv2.cvtColor(face_img, cv2.COLOR_GRAY2RGB)
        elif face_img.shape[2] == 4:
            face_img = cv2.cvtColor(face_img, cv2.COLOR_BGRA2RGB)
        
        face_img = cv2.resize(face_img, (224, 224))
        
        mean = np.array([123.68, 116.779, 103.939])
        std = np.array([58.395, 57.12, 57.375])
        face_img = (face_img - mean) / std
        
        face_img = np.transpose(face_img, (2, 0, 1))
        face_img = np.expand_dims(face_img, axis=0).astype(np.float32)
        
        return face_img

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
            print(f"获取情绪状态失败: {e}")
        return None

    def _age_to_range(self, age):
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

    def fetch_aligned_face(self):
        """从emotion模块获取对齐后的人脸图像"""
        try:
            resp = requests.get(self.aligned_face_url, timeout=0.5)
            if resp.status_code == 200:
                img_array = np.asarray(bytearray(resp.content), dtype=np.uint8)
                return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"获取对齐人脸失败: {e}")
        return None

    def analyze_face_deepface(self, frame):
        """使用DeepFace分析：只用emotion.py对齐好的高质量人脸！"""
        if DeepFace is None:
            return None
        
        # 直接尝试获取 emotion.py 对齐好的高质量人脸（唯一选择！）
        aligned_face = self.fetch_aligned_face()
        if aligned_face is None:
            return None
        
        try:
            result = DeepFace.analyze(
                aligned_face,
                actions=['age', 'gender'],
                enforce_detection=False,
                detector_backend='skip',  # 已经对齐好了，不要再检测！
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
        except Exception:
            return None

    def analyze_face_onnx(self, frame):
        """使用ONNX模型分析：只用emotion.py对齐好的高质量人脸！"""
        # 直接尝试获取 emotion.py 对齐好的高质量人脸（唯一选择！）
        aligned_face = self.fetch_aligned_face()
        if aligned_face is None:
            return None
        
        face_img = aligned_face
        
        age_model_result = {"available": False}
        gender_model_result = {"available": False}
        
        try:
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
                    "ranges": AGE_RANGES
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
                "age_range": AGE_RANGES[age_pred] if age_pred is not None else "--",
                "age_confidence": age_conf if age_pred is not None else 0.0,
                "gender": "男" if gender_pred == 0 else "女" if gender_pred == 1 else "--",
                "gender_confidence": gender_conf if gender_pred is not None else 0.0,
                "face_count": 1,
                "age_model": age_model_result,
                "gender_model": gender_model_result,
                "using_onnx": True
            }
        except Exception as e:
            print(f"ONNX人脸分析失败: {e}")
            return None

    def analyze_face(self, frame):
        """根据当前设置的模型进行分析"""
        if self.current_model == 'onnx':
            return self.analyze_face_onnx(frame)
        else:
            return self.analyze_face_deepface(frame)

    def smooth_result(self, result):
        if result["age"] is not None and result["age"] > 0:
            self.age_buffer.append(result["age"])
            if len(self.age_buffer) > self.buffer_size:
                self.age_buffer.pop(0)
            result["age"] = int(np.mean(self.age_buffer))
        
        gender_val = result.get("gender", "")
        if gender_val in ["Man", "Woman", "男", "女"]:
            self.gender_buffer.append(gender_val)
            if len(self.gender_buffer) > self.buffer_size:
                self.gender_buffer.pop(0)
            counter = Counter(self.gender_buffer)
            result["gender"] = counter.most_common(1)[0][0]
        
        return result

    def update(self):
        current_time = time.time()
        
        # 确保视频流已连接
        if self.cap is None or not self.cap.isOpened():
            self._connect()
            self._reconnect_attempts += 1
            with self.lock:
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
            return
        
        ret, frame = self.cap.read()
        if not ret:
            self._reconnect_attempts += 1
            with self.lock:
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
            return
        
        self._reconnect_attempts = 0
        self.raw_frame = frame
        
        try:
            _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            self.last_encoded_frame = encoded
        except:
            pass
        
        self._fc += 1
        
        # 获取emotion模块的人脸和姿态信息
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
                    "timestamp": time.time()
                })
                
                # 只在正脸且有帧时进行年龄性别分析
                # 每10帧检测一次
                should_detect = emotion_status["pose"] == 'front' and frame is not None and self._fc % 10 == 0
                if should_detect:
                    # 根据当前模型选择进行分析
                    analysis = self.analyze_face(frame)
                    
                    if analysis:
                        # 添加置信度过滤，只接受高置信度的结果
                        min_confidence = 0.5
                        if analysis["age_confidence"] >= min_confidence and analysis["gender_confidence"] >= min_confidence:
                            # analysis = self.smooth_result(analysis)  # 暂时注释掉平滑
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

    def get_result(self):
        with self.lock:
            return self.result.copy()

    def generate_frame(self):
        while self.running:
            if self.last_encoded_frame is not None:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + 
                       self.last_encoded_frame.tobytes() + b'\r\n')
            time.sleep(0.033)

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()

    def _run_loop(self):
        while self.running:
            self.update()
            self._try_update_hlkk()
            time.sleep(0.033)
    
    def _try_update_hlkk(self):
        """实时向hlkk.py发送年龄和性别数据（由hlkk.py每10秒取均值）"""
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
        except Exception as e:
            self._hlkk_fail_count = getattr(self, '_hlkk_fail_count', 0) + 1
            if self._hlkk_fail_count >= 5:
                print(f"[Perception] HLKK服务连接失败次数: {self._hlkk_fail_count}")
            if self._hlkk_fail_count >= 20:
                print(f"[Perception] HLKK服务持续失败，建议检查服务状态")


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

    def fetch_au_emotion(self):
        try:
            resp = requests.get(AU_EMOTION_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
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
            print(f"获取生理数据失败: {e}")
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
        au_data = self.fetch_au_emotion()
        physio = self.fetch_physio_data()
        face = self.fetch_face_status()

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


processor = EmotionProcessor()
person_analyzer = PersonAnalyzer()

child_processes = []

def start_child_processes():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    au_emotion_script = os.path.join(script_dir, "au", "emotion.py")
    if os.path.exists(au_emotion_script):
        print(f"启动 AU 情绪模块: {au_emotion_script}")
        au_proc = subprocess.Popen([sys.executable, au_emotion_script], 
                                  cwd=os.path.join(script_dir, "au"))
        child_processes.append(au_proc)
    else:
        print(f"警告: AU 情绪模块未找到: {au_emotion_script}")
    
    hlkk_script = os.path.join(script_dir, "hlkk.py")
    if os.path.exists(hlkk_script):
        print(f"启动 HLKK 生理模块: {hlkk_script}")
        hlkk_proc = subprocess.Popen([sys.executable, hlkk_script], 
                                    cwd=script_dir)
        child_processes.append(hlkk_proc)
    else:
        print(f"警告: HLKK 生理模块未找到: {hlkk_script}")
    
    gamedemo_script = os.path.join(script_dir, "gamedemo.py")
    if os.path.exists(gamedemo_script):
        gamedemo_proc = subprocess.Popen([sys.executable, gamedemo_script], 
                                        cwd=script_dir)
        child_processes.append(gamedemo_proc)
    else:
        print(f"警告: 打地鼠游戏模块未找到: {gamedemo_script}")


def cleanup():
    print("正在停止子进程...")
    for proc in child_processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in child_processes:
        try:
            proc.wait(timeout=2)
        except:
            proc.kill()
    print("所有子进程已停止")


atexit.register(cleanup)


def update_loop():
    last_dda_update = time.time()
    last_game_sync = time.time()
    last_processor_update = time.time()
    
    while True:
        current_time = time.time()
        
        if current_time - last_processor_update >= 0.5:
            last_processor_update = current_time
            processor.update()
        
        if current_time - last_dda_update >= 2:
            last_dda_update = current_time
            run_dda_update()
        
        if current_time - last_game_sync >= 1:
            last_game_sync = current_time
            sync_difficulty_to_game()
        
        time.sleep(0.1)

def run_dda_update():
    """执行DDA更新：收集数据 -> 更新DDA -> 获取调整建议"""
    global last_dda_data, last_game_status
    try:
        unified = get_unified_dda_data()
        last_dda_data = unified
        
        game_status = unified.get('game_status', 'idle')
        
        if last_game_status != 'playing' and game_status == 'playing':
            dda_system.reset_for_new_game()
            print("[DDA] 检测到新游戏开始，重置状态")
        
        last_game_status = game_status
        
        if game_status != 'playing':
            return None
        
        result = dda_system.update_from_unified(unified)
        print(f"[DDA] 更新结果: 难度={result['current_difficulty']}, 状态={result['flow_state']}, 调整={result['adjustment']}")
        
        return result
    except Exception as e:
        print(f"[DDA] 更新失败: {e}")
        return None


last_dda_data = {}
last_game_status = 'idle'

def get_unified_dda_data():
    """产出一个统一的 JSON，包含所有 perception 已经算好的标签 - 直接传给 DDA"""
    with processor.lock:
        physio = processor.physio_data
        emotion = processor.processed_emotion
        face_data = processor.face_data
    
    hr_valid = physio.get('hr_valid', False)
    hrr_pct = physio.get('hrr_pct', 0)
    hr_slope = physio.get('hr_slope', 0)
    
    face_detected = face_data.get('face_detected', True)
    face_count = face_data.get('face_count', 1)
    
    # HRR 强度标签（和 hlkk.py 保持一致）
    if hrr_pct < 40:
        hrr_level = '低强度'
    elif hrr_pct <= 60:
        hrr_level = '中强度'
    else:
        hrr_level = '高强度'
    
    # Slope 标签（和 hlkk.py 保持一致）
    if hr_slope < -0.5:
        slope_label = '快速下降'
    elif hr_slope <= 0.5:
        slope_label = '平稳'
    elif hr_slope <= 2.0:
        slope_label = '缓慢上升'
    else:
        slope_label = '快速上升'
    
    label = emotion.get('label', 'neutral')
    label_map = {
        'positive_high': '积极高信度',
        'positive_low': '积极低信度',
        'negative_high': '消极高信度',
        'negative_low': '消极低信度',
        'neutral_high': '中性高信度',
        'neutral': '中性'
    }
    emotion_cn = label_map.get(label, '中性')
    
    game_data = {
        'status': 'idle',
        'running': False,
        'timeLeft': 180,
        'score': 0,
        'difficulty': 1,
        'accuracy': '--',
        'results': []
    }
    try:
        resp = requests.get("http://127.0.0.1:5050/api/game-state", timeout=1.0)
        if resp.status_code == 200:
            game_data = resp.json()
    except Exception as e:
        print(f"[DDA] 获取游戏数据失败: {e}")
    
    hr_valid_since = physio.get('hr_valid_since', 0)
    hr_age = time.time() - hr_valid_since if hr_valid_since > 0 else float('inf')
    
    unified = {
        'hr_valid': hr_valid,
        'hr_valid_since': hr_valid_since,
        'hr_age': hr_age,
        'hrr_pct': hrr_pct,
        'hrr': hrr_level,
        'hr_slope': hr_slope,
        'slope_label': slope_label,
        'emotion': label,
        'emotion_cn': emotion_cn,
        'confidence': emotion.get('confidence', 0),
        'face_detected': face_detected,
        'face_count': face_count,
        'timeLeft': game_data.get('timeLeft', 180),
        'score': game_data.get('score', 0),
        'difficulty': game_data.get('difficulty', 1),
        'accuracy': game_data.get('accuracy', '--'),
        'game_status': game_data.get('status', 'idle'),
        'last_result': None
    }
    
    results = game_data.get('results', [])
    if results:
        last = results[-1]
        time_val = last.get('time', 0)
        # 确保时间是整数，过滤掉 '--' 字符串
        if not isinstance(time_val, int):
            time_val = 0
        unified['last_result'] = {
            'type': last.get('type', 'hit'),
            'time': time_val
        }
        
        # 传递完整的游戏结果历史，用于DDA趋势分析
        unified['results'] = []
        for result in results[-10:]:  # 最多传递最近10条
            r_time = result.get('time', 0)
            if not isinstance(r_time, int):
                r_time = 0
            unified['results'].append({
                'seq': result.get('seq', None),
                'type': result.get('type', 'miss'),
                'time': r_time,
                'difficulty': result.get('difficulty', 1),
                'score': result.get('score', 0)
            })
    else:
        unified['results'] = []
    
    return unified

def get_physiology_data_for_dda():
    """获取生理数据用于DDA"""
    with processor.lock:
        physio = processor.physio_data
    
    hr_valid_since = physio.get('hr_valid_since', 0)
    hr_age = time.time() - hr_valid_since if hr_valid_since > 0 else float('inf')
    
    return {
        'hr_valid': physio.get('hr_valid', False),
        'hrr_pct': physio.get('hrr_pct', 0),
        'hr_slope': physio.get('hr_slope', 0),
        'hr_age': hr_age
    }

def get_emotion_data_for_dda():
    """获取情绪数据用于DDA"""
    with processor.lock:
        emotion = processor.processed_emotion
    
    return {
        'emotion': emotion.get('label', 'neutral'),
        'confidence': emotion.get('confidence', 0)
    }

def get_game_data_for_dda():
    """获取游戏数据用于DDA"""
    try:
        resp = requests.get("http://127.0.0.1:5050/api/game-state", timeout=1.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[DDA] 获取游戏数据失败: {e}")
    
    return {
        'status': 'idle',
        'running': False,
        'difficulty': 1,
        'results': []
    }

def sync_difficulty_to_game():
    """将DDA建议的难度同步到游戏 - DDA是唯一的难度调整源"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            resp = requests.get("http://127.0.0.1:5050/api/game-state", timeout=2.0)
            if resp.status_code == 200:
                game_state = resp.json()
                current_game_diff = game_state.get('difficulty', 4)
                game_status = game_state.get('status', 'idle')
                
                if game_status != 'playing':
                    return
                
                if dda_system.current_difficulty != current_game_diff:
                    sync_resp = requests.post("http://127.0.0.1:5050/api/game/difficulty",
                                json={'difficulty': dda_system.current_difficulty},
                                timeout=2.0)
                    if sync_resp.status_code == 200:
                        print(f"[DDA] 同步难度到游戏: {current_game_diff} -> {dda_system.current_difficulty}")
                return
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[DDA] 同步难度失败: {e}")
            time.sleep(0.1 * (attempt + 1))


@app.route("/")
def index():
    return render_template("perception.html")


@app.route("/api/current")
def api_current():
    return jsonify(processor.get_current())


@app.route("/api/gate", methods=["POST"])
def api_gate():
    enabled = request.json.get("enabled", True)
    processor.gate_enabled = enabled
    return jsonify({"ok": True, "gate_enabled": enabled})


@app.route("/api/data")
def api_data():
    return jsonify(person_analyzer.get_result())


@app.route("/api/model", methods=["POST"])
def api_model():
    """切换年龄性别分析模型"""
    model = request.json.get("model", "deepface")
    if model in ["deepface", "onnx"]:
        person_analyzer.current_model = model
        return jsonify({"ok": True, "model": model})
    return jsonify({"ok": False, "message": "无效的模型"})


@app.route("/api/model")
def api_model_get():
    """获取当前使用的模型"""
    return jsonify({"model": person_analyzer.current_model})


@app.route("/api/hlkk")
def api_hlkk():
    """代理获取hlkk数据，避免跨域"""
    try:
        resp = requests.get(HLKK_DATA_API, timeout=1.0)
        if resp.status_code == 200:
            return jsonify(resp.json())
    except Exception as e:
        print(f"获取hlkk数据失败: {e}")
    return jsonify({})

@app.route("/api/game")
def api_game():
    """代理获取游戏状态，避免跨域"""
    try:
        resp = requests.get("http://127.0.0.1:5050/api/game-state", timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            return jsonify(data)
    except requests.exceptions.ConnectionError:
        pass
    except requests.exceptions.Timeout:
        pass
    except Exception:
        pass
    # 返回默认数据
    return jsonify({
        'status': 'idle',
        'running': False,
        'timeLeft': 180,
        'score': 0,
        'difficulty': 1,
        'difficultyName': '简单',
        'accuracy': '--',
        'results': []
    })

@app.route("/api/dda")
def api_dda():
    """获取DDA系统状态"""
    try:
        physio_data = get_physiology_data_for_dda()
        emotion_data = get_emotion_data_for_dda()
        
        return jsonify({
            'current_difficulty': dda_system.current_difficulty,
            'min_difficulty': dda_system.min_difficulty,
            'max_difficulty': dda_system.max_difficulty,
            'physiology': physio_data,
            'emotion': emotion_data,
            'stats': {
                'total_hits': dda_system.total_hits,
                'total_misses': dda_system.total_misses,
                'total_errors': dda_system.total_errors,
                'total_bombs': dda_system.total_bombs,
                'overall_accuracy': (dda_system.total_hits / (dda_system.total_hits + dda_system.total_misses + dda_system.total_errors + dda_system.total_bombs)) if (dda_system.total_hits + dda_system.total_misses + dda_system.total_errors + dda_system.total_bombs) > 0 else 0
            },
            'window_size': len(dda_system.question_history)
        })
    except Exception as e:
        print(f"[DDA] API获取失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/dda/update", methods=['POST'])
def api_dda_update():
    """更新DDA状态并获取难度调整建议"""
    try:
        data = request.json
        physiology_data = data.get('physiology', {})
        emotion_data = data.get('emotion', {})
        game_data = data.get('game', {})
        
        result = dda_system.update(physiology_data, emotion_data, game_data)
        return jsonify(result)
    except Exception as e:
        print(f"DDA更新失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/dda/input")
def api_dda_input():
    """获取传给DDA的统一输入数据 - perception已算好所有标签"""
    unified = get_unified_dda_data()
    
    try:
        unified['dda_output'] = {
            'current_difficulty': dda_system.current_difficulty,
            'adjustment': dda_system.last_adjustment if hasattr(dda_system, 'last_adjustment') else 0,
            'adjustment_made': False,
            'reason': "查询状态",
            'flow_state': dda_system._last_flow_state if hasattr(dda_system, '_last_flow_state') else 'flow',
            'can_continue': {'state': dda_system._last_can_state if hasattr(dda_system, '_last_can_state') else 'Capable', 'score': dda_system._last_can_score if hasattr(dda_system, '_last_can_score') else 50},
            'want_continue': {'state': dda_system._last_want_state if hasattr(dda_system, '_last_want_state') else 'Engaged', 'score': dda_system._last_want_score if hasattr(dda_system, '_last_want_score') else 50},
            'safety_rules': dda_system._last_safety_rules if hasattr(dda_system, '_last_safety_rules') else {'hr_abnormal': False, 'sustained_high_hrr': False, 'negative_consecutive': False, 'accuracy_collapse': False}
        }
    except Exception as e:
        print(f"[DDA] 查询状态失败: {e}")
    
    return jsonify(unified)


@app.route("/video_feed")
def video_feed():
    return Response(person_analyzer.generate_frame(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    start_child_processes()
    time.sleep(3)
    person_analyzer.start()
    threading.Thread(target=update_loop, daemon=True).start()
    print("Perception 服务已启动!")
    print("访问: http://127.0.0.1:5090")
    app.run(host="127.0.0.1", port=5090, debug=False, use_reloader=False)
