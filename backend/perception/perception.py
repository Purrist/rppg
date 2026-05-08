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
from flask import Flask, render_template, jsonify, request, Response

app = Flask(__name__)

AU_EMOTION_API = "http://127.0.0.1:5010/api/fusion"
HLKK_DATA_API = "http://127.0.0.1:5020/data"

PERSON_HTTP_PORT = 5030
IP_CAMERA_URL = "http://10.158.7.180:8080/video"

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core", "models")
AGE_MODEL_PATH = os.path.join(MODEL_DIR, "age_googlenet.onnx")
GENDER_MODEL_PATH = os.path.join(MODEL_DIR, "gender_googlenet.onnx")

AGE_RANGES = ['0-2', '4-6', '8-12', '15-20', '25-32', '38-43', '48-53', '60-100']

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "au", "config.json")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emodata")

class PersonAnalyzer:
    def __init__(self):
        self.video_stream_url = "http://127.0.0.1:5010/video_feed"
        self.cap = None
        self._reconnect_attempts = 0
        
        self.age_session = None
        self.gender_session = None
        self.load_models()
        
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
            "gender_model": {"available": False}
        }
        
        self.age_buffer = []
        self.gender_buffer = []
        self.buffer_size = 5
        
        self.last_detection_time = 0
        self.detection_interval = 0.3
        
        self.max_reconnect_attempts = 10
    
    def _connect(self):
        """尝试连接到视频流"""
        if self.cap and self.cap.isOpened():
            self.cap.release()
        
        self.cap = cv2.VideoCapture(self.video_stream_url)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._reconnect_attempts = 0
            return True
        return False

    def load_models(self):
        try:
            if os.path.exists(AGE_MODEL_PATH):
                self.age_session = ort.InferenceSession(AGE_MODEL_PATH, providers=['CPUExecutionProvider'])
                print(f"✓ 年龄模型加载成功: {AGE_MODEL_PATH}")
            else:
                print(f"✗ 年龄模型未找到: {AGE_MODEL_PATH}")
            
            if os.path.exists(GENDER_MODEL_PATH):
                self.gender_session = ort.InferenceSession(GENDER_MODEL_PATH, providers=['CPUExecutionProvider'])
                print(f"✓ 性别模型加载成功: {GENDER_MODEL_PATH}")
            else:
                print(f"✗ 性别模型未找到: {GENDER_MODEL_PATH}")
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

    def analyze_face(self, frame):
        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_detector.detectMultiScale(
            gray, 
            scaleFactor=1.2, 
            minNeighbors=4, 
            minSize=(30, 30)
        )
        
        if len(faces) == 0:
            return None
        
        max_area = 0
        best_face = None
        for (x, y, w, h) in faces:
            area = w * h
            if area > max_area:
                max_area = area
                best_face = (x, y, w, h)
        
        if best_face is None:
            return None
        
        x, y, w, h = best_face
        x = int(x * 2)
        y = int(y * 2)
        w = int(w * 2)
        h = int(h * 2)
        
        padding = int(w * 0.2)
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(frame.shape[1] - x, w + 2 * padding)
        h = min(frame.shape[0] - y, h + 2 * padding)
        
        face_img = frame[y:y+h, x:x+w]
        
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
                "face_count": len(faces),
                "age_model": age_model_result,
                "gender_model": gender_model_result
            }
        except Exception as e:
            print(f"人脸分析失败: {e}")
            return None

    def smooth_result(self, result):
        if result["age"] is not None:
            self.age_buffer.append(result["age"])
            if len(self.age_buffer) > self.buffer_size:
                self.age_buffer.pop(0)
            result["age"] = int(np.mean(self.age_buffer))
        
        if result["gender"] in ["男", "女"]:
            self.gender_buffer.append(result["gender"])
            if len(self.gender_buffer) > self.buffer_size:
                self.gender_buffer.pop(0)
            from collections import Counter
            counter = Counter(self.gender_buffer)
            result["gender"] = counter.most_common(1)[0][0]
        
        return result

    def update(self):
        current_time = time.time()
        
        # 确保视频流已连接
        if self.cap is None or not self.cap.isOpened():
            if self._reconnect_attempts % self.max_reconnect_attempts == 0:
                print(f"[PersonAnalyzer] 尝试连接视频流: {self.video_stream_url}")
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
                    "gender_model": {"available": False}
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
                    "gender_model": {"available": False}
                }
            return
        
        self._reconnect_attempts = 0
        self.raw_frame = frame
        
        # 只在需要时编码帧
        try:
            _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            self.last_encoded_frame = encoded
        except:
            pass
        
        if current_time - self.last_detection_time >= self.detection_interval:
            self.last_detection_time = current_time
            
            analysis = self.analyze_face(frame)
            with self.lock:
                if analysis:
                    analysis = self.smooth_result(analysis)
                    self.result = {
                        "age": analysis["age"],
                        "age_range": analysis["age_range"],
                        "age_confidence": analysis["age_confidence"],
                        "gender": analysis["gender"],
                        "gender_confidence": analysis["gender_confidence"],
                        "face_detected": True,
                        "face_count": analysis["face_count"],
                        "timestamp": time.time(),
                        "age_model": analysis["age_model"],
                        "gender_model": analysis["gender_model"]
                    }
                else:
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
                        "gender_model": {"available": False}
                    }

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
            time.sleep(0.033)

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
            "timestamp": 0
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
        except Exception as e:
            print(f"获取情绪数据失败: {e}")
        return None

    def fetch_physio_data(self):
        try:
            resp = requests.get(HLKK_DATA_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                raw = d.get("raw", {})
                return {
                    "heart": raw.get("hr", 0),
                    "breath": raw.get("br", 0),
                    "human": raw.get("is_human", 0) == 1,
                    "timestamp": time.time()
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
        
        # 基于势场深度计算置信度
        p1 = max(scores.values())
        confidence = min(p1 * conf * 1.5, 1.0)
        
        return {
            "label": label,
            "confidence": confidence,
            "value": value,
            "timestamp": emotion_data.get("timestamp", time.time())
        }

    def classify_confidence(self, scores):
        """
        基于多稳态势场理论的实时情绪状态分类器。
        核心思想：分类不取决于单一概率的最大值，而取决于该状态在势场中形成的“势阱深度”是否足以抵抗帧间噪声扰动。
        """
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
                self.physio_data = physio

    def get_current(self):
        with self.lock:
            return {
                "emotion": self.emotion_data.copy(),
                "processed": self.processed_emotion.copy(),
                "physio": self.physio_data.copy(),
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
    while True:
        processor.update()
        time.sleep(0.1)

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

@app.route("/person")
def person_index():
    return render_template("person.html")

@app.route("/api/data")
def api_data():
    return jsonify(person_analyzer.get_result())

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
