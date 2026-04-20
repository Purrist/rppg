""" feel.py - 多模态感知系统 V3.3

V3.3 改动：
- [修复] 情绪识别：用面部轮廓关键点精确裁剪 + 降低平滑(0.45) + 降低切换门槛
- [修复] 属性识别：同上精确裁剪
- [新增] 情绪模式切换：/api/set_emotion_mode 可切换 model/rule
- [保留] ThreadedCamera 低延迟读取
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file, request
import mediapipe as mp
import threading
import time
import os
from collections import deque

app = Flask(__name__)

LOCAL_CAMERA_ID = 1
DEFAULT_IP_CAMERA_URL = "http://10.215.158.45:8080/video"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SCRIPT_DIR, '..', 'backend', 'core', 'models')
EMOTION_MODEL_PATH = os.path.join(MODELS_DIR, 'emotion-ferplus-8.onnx')
AGE_MODEL_PATH = os.path.join(MODELS_DIR, 'age_googlenet.onnx')
GENDER_MODEL_PATH = os.path.join(MODELS_DIR, 'gender_googlenet.onnx')

MOTION_WINDOW = 60
FOCUS_SMOOTH = 0.70
EMOTION_SMOOTH = 0.45        # [V3.3] 从 0.80 降到 0.45，响应更灵敏
PERSON_TIMEOUT = 3.0
BLINK_EAR_CLOSE = 0.18
BLINK_EAR_OPEN = 0.22
BLINK_WINDOW = 30
ATTR_INFER_INTERVAL = 10

# 面部轮廓关键点（38 个点，定义精确的人脸边界）
FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10,
]

# 画面绘制用轮廓（保留原有）
FACE_CONTOURS = [
    FACE_OVAL,
    [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33],
    [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466, 263],
    [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409,
     270, 269, 267, 0, 37, 39, 40, 185, 61],
    [70, 63, 105, 66, 107],
    [300, 293, 334, 296, 336],
]

EMOTION_META = {
    'happy':     ('开心', (0, 200, 100)),
    'surprised': ('惊讶', (0, 200, 255)),
    'angry':     ('愤怒', (0, 0, 255)),
    'sad':       ('悲伤', (255, 150, 0)),
    'neutral':   ('平静', (150, 150, 150)),
    'drowsy':    ('困倦', (200, 100, 255)),
}

FER8_LABELS = ['neutral', 'happiness', 'surprise', 'sadness',
               'anger', 'disgust', 'fear', 'contempt']
FER8TO6 = {
    'neutral': 'neutral', 'happiness': 'happy', 'surprise': 'surprised',
    'sadness': 'sad', 'anger': 'angry', 'disgust': 'angry',
    'fear': 'sad', 'contempt': 'neutral',
}

AGE_LABELS = ['(0-2)', '(4-6)', '(8-12)', '(15-20)',
              '(25-32)', '(38-43)', '(48-53)', '(60-100)']
GENDER_LABELS = ['Male', 'Female']

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    HAS_ORT = False
    print("[WARN] onnxruntime 未安装，pip install onnxruntime")


# ============================================================
# ThreadedCamera（V3.2 保留）
# ============================================================
class ThreadedCamera:
    def __init__(self, src, buffer_size=1):
        self.cap = cv2.VideoCapture(src)
        if not self.cap.isOpened():
            self._ok = False; return
        try: self.cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
        except: pass
        self._ok = True
        self._frame = None
        self._ret = False
        self._running = True
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        while self._running:
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self._ret = True; self._frame = frame
            else:
                time.sleep(0.005)

    def read(self):
        with self._lock:
            return self._ret, self._frame.copy() if self._frame is not None else None

    def isOpened(self): return self._ok and self.cap.isOpened()

    def get(self, prop, default=0.0):
        try: return self.cap.get(prop)
        except: return default

    def release(self):
        self._running = False
        time.sleep(0.05)
        try: self.cap.release()
        except: pass


# ============================================================
# FERPlus 情绪识别器
# ============================================================
class FERPlusRecognizer:
    def __init__(self, model_path):
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"文件不存在: {model_path}")
        if not HAS_ORT:
            raise RuntimeError("onnxruntime 未安装")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, opts,
                                            providers=['CPUExecutionProvider'])
        inp = self.session.get_inputs()[0]
        out = self.session.get_outputs()[0]
        self.input_name = inp.name
        self.output_name = out.name
        self.in_h = int(inp.shape[2]) if inp.shape[2] > 0 else 64
        self.in_w = int(inp.shape[3]) if inp.shape[3] > 0 else 64
        print(f"[OK] FERPlus 已加载: {os.path.basename(model_path)}")

    def predict(self, face_bgr):
        """输入 BGR 人脸图像，输出 6 类情绪概率 dict"""
        if face_bgr is None or face_bgr.size == 0:
            return None
        try:
            gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (self.in_w, self.in_h),
                                 interpolation=cv2.INTER_LINEAR)
            # 归一化 0-1
            blob = (resized.astype(np.float32) / 255.0)
            blob = blob[np.newaxis, np.newaxis, :, :]
            raw = self.session.run([self.output_name],
                                   {self.input_name: blob})[0]
            scores = raw[0].astype(np.float64)
            # softmax
            if (scores < 0).any() or abs(scores.sum() - 1.0) > 0.1:
                s = np.exp(scores - scores.max())
                scores = s / (s.sum() + 1e-10)
            # 8→6
            result6 = {k: 0.0 for k in
                       ['happy', 'surprised', 'angry', 'sad', 'neutral', 'drowsy']}
            for i, label in enumerate(FER8_LABELS):
                if i < len(scores):
                    result6[FER8TO6.get(label, 'neutral')] += float(scores[i])
            total = sum(result6.values())
            if total > 0:
                for k in result6:
                    result6[k] /= total
            return result6
        except:
            return None


# ============================================================
# 年龄+性别识别器（不变）
# ============================================================
class AgeGenderRecognizer:
    MEAN = np.array([104.0, 117.0, 123.0], dtype=np.float32)

    def __init__(self, age_path, gender_path):
        if not os.path.isfile(age_path):
            raise FileNotFoundError(f"文件不存在: {age_path}")
        if not os.path.isfile(gender_path):
            raise FileNotFoundError(f"文件不存在: {gender_path}")
        if not HAS_ORT:
            raise RuntimeError("onnxruntime 未安装")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.age_session = ort.InferenceSession(age_path, opts,
                                                providers=['CPUExecutionProvider'])
        self.gender_session = ort.InferenceSession(gender_path, opts,
                                                   providers=['CPUExecutionProvider'])
        self.age_input = self.age_session.get_inputs()[0].name
        self.age_output = self.age_session.get_outputs()[0].name
        self.gender_input = self.gender_session.get_inputs()[0].name
        self.gender_output = self.gender_session.get_outputs()[0].name
        print(f"[OK] Age model:   {os.path.basename(age_path)}")
        print(f"[OK] Gender model: {os.path.basename(gender_path)}")

    def predict(self, face_bgr):
        if face_bgr is None or face_bgr.size == 0:
            return None
        try:
            img = cv2.resize(face_bgr, (224, 224), interpolation=cv2.INTER_LINEAR)
            img = img.astype(np.float32) - self.MEAN
            blob = img.transpose(2, 0, 1)[np.newaxis, :, :, :]
            age_out = self.age_session.run([self.age_output],
                                          {self.age_input: blob})[0]
            age_scores = age_out[0].astype(np.float64)
            s = np.exp(age_scores - age_scores.max())
            age_probs = s / (s.sum() + 1e-10)
            age_idx = int(np.argmax(age_probs))
            gender_out = self.gender_session.run([self.gender_output],
                                                {self.gender_input: blob})[0]
            gender_scores = gender_out[0].astype(np.float64)
            s = np.exp(gender_scores - gender_scores.max())
            gender_probs = s / (s.sum() + 1e-10)
            gender_idx = int(np.argmax(gender_probs))
            return {
                'age': AGE_LABELS[age_idx],
                'age_confidence': round(float(age_probs[age_idx]), 2),
                'age_probs': {AGE_LABELS[i]: round(float(p), 3)
                              for i, p in enumerate(age_probs)},
                'gender': GENDER_LABELS[gender_idx],
                'gender_confidence': round(float(gender_probs[gender_idx]), 2),
                'gender_probs': {GENDER_LABELS[i]: round(float(p), 3)
                                 for i, p in enumerate(gender_probs)},
            }
        except:
            return None


# ============================================================
# 多模态感知处理器 V3.3
# ============================================================
class MultiModalProcessor:
    def __init__(self):
        self.local_cap = None
        self.ip_cap = None
        self.local_running = False
        self.ip_running = False

        self.person_detected_local = False
        self.person_detected_ip = False
        self.person_detected = False
        self.person_last_seen = 0.0
        self.person_status = "offline"

        self.emotion = "neutral"
        self.emotion_confidence = 0.0
        self.emotion_scores = {}
        self.emotion_history = deque(maxlen=60)
        self.emotion_method = "none"
        self.emotion_mode = "auto"   # [V3.3] auto / model / rule

        self.face_attribute = None
        self.attr_method = "none"
        self._attr_frame_counter = 0

        self.focus_score = 50.0
        self.focus_history = deque(maxlen=120)
        self.blink_count = 0
        self.blink_rate = 0.0
        self.head_yaw = 0.0
        self.head_pitch = 0.0
        self.head_motion_score = 0.0
        self.eye_openness = 0.0

        self.motion_intensity = 0.0
        self.motion_history = deque(maxlen=120)
        self.motion_accumulator = 0.0
        self.motion_window = deque(maxlen=MOTION_WINDOW)
        self.prev_pose_points = None

        self.local_fps = 0.0
        self.ip_fps = 0.0
        self._local_fc = 0
        self._ip_fc = 0
        self._fps_time = time.time()

        self.local_frame_out = None
        self.ip_frame_out = None

        self._blink_state = 'open'
        self._blink_timestamps = deque(maxlen=50)
        self._prev_face_pts = None
        self._face_motion_win = deque(maxlen=30)

        self._debug_timer = 0.0   # [V3.3] 调试输出计时

        self.lock = threading.Lock()
        self.running = True
        self.start_time = time.time()

        self.face_mesh = None
        self.face_detection = None
        self.pose_detector = None

        self.emotion_recognizer = None
        self.attribute_recognizer = None

    # ============================================================
    def start(self):
        print("[INIT] 初始化 MediaPipe ...")
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.3)
        self.pose_detector = mp.solutions.pose.Pose(
            model_complexity=1,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        print("[OK] MediaPipe 就绪")

        self._load_emotion_model()
        self._load_attribute_model()

        # 默认模式：有模型用模型，没有用规则
        if self.emotion_recognizer:
            self.emotion_mode = "model"
        else:
            self.emotion_mode = "rule"

        print(f"[INIT] 打开本地摄像头 {LOCAL_CAMERA_ID} ...")
        self.local_cap = ThreadedCamera(LOCAL_CAMERA_ID)
        if self.local_cap.isOpened():
            self.local_running = True
            w = int(self.local_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.local_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[OK] 本地摄像头 {LOCAL_CAMERA_ID}: {w}x{h}")
        else:
            print(f"[WARN] 本地摄像头 {LOCAL_CAMERA_ID} 打开失败")

        print(f"[INIT] 打开 IP 摄像头 ...")
        self.ip_cap = ThreadedCamera(DEFAULT_IP_CAMERA_URL)
        if self.ip_cap.isOpened():
            self.ip_running = True
            w = int(self.ip_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.ip_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[OK] IP 摄像头: {w}x{h}")
        else:
            print(f"[WARN] IP 摄像头打开失败: {DEFAULT_IP_CAMERA_URL}")

        if not self.local_running and not self.ip_running:
            raise RuntimeError("所有摄像头均无法打开")

        if self.local_running:
            threading.Thread(target=self._local_worker, daemon=True).start()
        if self.ip_running:
            threading.Thread(target=self._ip_worker, daemon=True).start()

    def stop(self):
        self.running = False
        if self.local_cap: self.local_cap.release()
        if self.ip_cap: self.ip_cap.release()

    def _load_emotion_model(self):
        if not HAS_ORT:
            print("[INFO] 情绪: 规则方法 (onnxruntime 未安装)")
            self.emotion_method = "rule"; return
        if not os.path.isfile(EMOTION_MODEL_PATH):
            print(f"[INFO] 情绪: 规则方法 ({EMOTION_MODEL_PATH} 不存在)")
            self.emotion_method = "rule"; return
        try:
            self.emotion_recognizer = FERPlusRecognizer(EMOTION_MODEL_PATH)
            self.emotion_method = "model"
            print("[INFO] 情绪模型: FERPlus ONNX")
        except Exception as e:
            print(f"[WARN] FERPlus 加载失败: {e}")
            self.emotion_method = "rule"; self.emotion_recognizer = None

    def _load_attribute_model(self):
        if not HAS_ORT:
            print("[INFO] 属性: 跳过 (onnxruntime 未安装)"); return
        if not os.path.isfile(AGE_MODEL_PATH):
            print(f"[INFO] 属性: 跳过 ({AGE_MODEL_PATH} 不存在)"); return
        if not os.path.isfile(GENDER_MODEL_PATH):
            print(f"[INFO] 属性: 跳过 ({GENDER_MODEL_PATH} 不存在)"); return
        try:
            self.attribute_recognizer = AgeGenderRecognizer(
                AGE_MODEL_PATH, GENDER_MODEL_PATH)
            self.attr_method = "model"
            print("[INFO] 属性模型: age+gender GoogleNet ONNX")
        except Exception as e:
            print(f"[WARN] 属性模型加载失败: {e}")
            self.attr_method = "none"; self.attribute_recognizer = None

    # ============================================================
    # [V3.3] 情绪模式切换
    # ============================================================
    def set_emotion_mode(self, mode):
        """mode: 'auto' | 'model' | 'rule'"""
        with self.lock:
            if mode == 'auto':
                self.emotion_mode = "model" if self.emotion_recognizer else "rule"
            elif mode == 'model' and self.emotion_recognizer:
                self.emotion_mode = "model"
            elif mode == 'rule':
                self.emotion_mode = "rule"
            print(f"[INFO] 情绪模式切换: {self.emotion_mode}")

    # ============================================================
    # [V3.3] 用面部轮廓关键点精确裁剪人脸
    # ============================================================
    def _crop_face_from_oval(self, frame, face_landmarks, padding=0.20):
        """
        只用 FACE_OVAL 的 38 个轮廓关键点计算人脸边界，
        生成紧凑正方形裁剪。
        比 Face Detection bbox 和全部 468 点都更精确。
        """
        h, w = frame.shape[:2]
        # 只取轮廓点
        pts = np.array([(face_landmarks.landmark[i].x * w,
                         face_landmarks.landmark[i].y * h)
                        for i in FACE_OVAL])

        x_min, x_max = pts[:, 0].min(), pts[:, 0].max()
        y_min, y_max = pts[:, 1].min(), pts[:, 1].max()

        # 居中取正方形
        cx = (x_min + x_max) / 2
        cy = (y_min + y_max) / 2
        size = max(x_max - x_min, y_max - y_min)
        size *= (1 + padding)

        x1 = max(0, int(cx - size / 2))
        y1 = max(0, int(cy - size / 2))
        x2 = min(w, int(cx + size / 2))
        y2 = min(h, int(cy + size / 2))

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
            return None
        return crop

    # ============================================================
    # 本地摄像头线程
    # ============================================================
    def _local_worker(self):
        while self.running:
            try:
                ret, frame = self.local_cap.read()
                if frame is None:
                    time.sleep(0.01); continue
                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self.pose_detector.process(rgb)
                with self.lock:
                    self._local_fc += 1
                    if result.pose_landmarks:
                        self.person_detected_local = True
                        self._compute_motion(result.pose_landmarks)
                        self._draw_pose(frame, result.pose_landmarks, w, h)
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, f"MOTION: {self.motion_intensity:.1f}%",
                                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 229, 160), 1)
                        cv2.putText(frame, f"ACC: {self.motion_accumulator:.1f}",
                                    (w - 180, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        bar_w = int(w * min(self.motion_intensity, 100) / 100)
                        bar_c = (0, 229, 160) if self.motion_intensity < 30 else \
                                (0, 180, 120) if self.motion_intensity < 60 else (0, 100, 255)
                        cv2.rectangle(frame, (0, h - 4), (bar_w, h), bar_c, -1)
                    else:
                        self.person_detected_local = False
                        self.prev_pose_points = None
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, "NO PERSON", (10, 24),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
                    self._update_person()
                    self._update_fps()
                    self.local_frame_out = frame
            except Exception as e:
                print(f"[LOCAL ERROR] {e}"); time.sleep(0.01)

    # ============================================================
    # IP 摄像头线程
    # ============================================================
    def _ip_worker(self):
        while self.running:
            try:
                ret, frame = self.ip_cap.read()
                if frame is None:
                    time.sleep(0.01); continue
                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                det = self.face_detection.process(rgb)
                has_face = det.detections is not None and len(det.detections) > 0
                mesh_result = None
                if has_face:
                    mesh_result = self.face_mesh.process(rgb)
                    has_mesh = (mesh_result.multi_face_landmarks is not None
                                and len(mesh_result.multi_face_landmarks) > 0)
                else:
                    has_mesh = False

                with self.lock:
                    self._ip_fc += 1
                    if has_mesh:
                        self.person_detected_ip = True
                        lm = mesh_result.multi_face_landmarks[0]

                        # [V3.3] 用轮廓关键点精确裁剪
                        face_crop = self._crop_face_from_oval(frame, lm)

                        # 情绪（根据模式选择 model/rule）
                        self._compute_emotion(face_crop, lm)

                        # 年龄+性别（每 N 帧）
                        self._attr_frame_counter += 1
                        if (self.attribute_recognizer is not None
                                and face_crop is not None
                                and self._attr_frame_counter >= ATTR_INFER_INTERVAL):
                            self._attr_frame_counter = 0
                            attr = self.attribute_recognizer.predict(face_crop)
                            if attr is not None:
                                self.face_attribute = attr

                        # 专注度
                        self._compute_focus(lm)

                        # 绘制
                        self._draw_face_contours(frame, lm, w, h)

                        # HUD
                        cv2.rectangle(frame, (0, 0), (w, 72), (0, 0, 0), -1)
                        cn, color = EMOTION_META.get(self.emotion, ('?', (150, 150, 150)))
                        mode_tag = "[M]" if self.emotion_method == "model" else "[R]"
                        cv2.putText(frame, f"{mode_tag} {cn} ({self.emotion_confidence:.0%})",
                                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                        fc = (0, 229, 160) if self.focus_score > 60 else \
                             (0, 180, 120) if self.focus_score > 30 else (0, 80, 255)
                        cv2.putText(frame, f"Focus: {self.focus_score:.0f}%",
                                    (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.45, fc, 1)
                        cv2.putText(frame, f"Blink: {self.blink_rate:.0f}/min",
                                    (w - 170, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        cv2.putText(frame, f"Eye: {self.eye_openness:.2f}",
                                    (w - 170, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        if self.face_attribute:
                            attr_s = (f"{self.face_attribute.get('age','?')}  "
                                      f"{self.face_attribute.get('gender','?')}")
                            cv2.putText(frame, attr_s,
                                        (10, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1)
                        bar_w = int(w * min(self.focus_score, 100) / 100)
                        cv2.rectangle(frame, (0, h - 4), (bar_w, h), fc, -1)

                        # [V3.3] 调试输出（每 3 秒打印一次原始分数）
                        now = time.time()
                        if now - self._debug_timer > 3.0:
                            self._debug_timer = now
                            scores = self.emotion_scores
                            top3 = sorted(scores.items(), key=lambda x: -x[1])[:3]
                            print(f"[DEBUG] 情绪 {self.emotion}({self.emotion_confidence:.2f}) "
                                  f"| 方法:{self.emotion_method} 模式:{self.emotion_mode} "
                                  f"| TOP3: {top3}")
                    else:
                        self.person_detected_ip = False
                        self.emotion = "neutral"
                        self.emotion_confidence = max(0, self.emotion_confidence - 0.02)
                        self.focus_score = self.focus_score * 0.98
                        self.face_attribute = None
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, "NO FACE", (10, 24),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
                    self._update_person()
                    self._update_fps()
                    self.ip_frame_out = frame
            except Exception as e:
                print(f"[IP ERROR] {e}"); time.sleep(0.01)

    # ============================================================
    # 公共方法
    # ============================================================
    def _update_person(self):
        self.person_detected = self.person_detected_local or self.person_detected_ip
        if self.person_detected:
            self.person_last_seen = time.time()
            self.person_status = "present"
        elif time.time() - self.person_last_seen > PERSON_TIMEOUT:
            self.person_status = "offline"
        elif self.person_status == "present":
            self.person_status = "lost"

    def _update_fps(self):
        now = time.time()
        dt = now - self._fps_time
        if dt >= 1.0:
            self.local_fps = self._local_fc / dt if dt > 0 else 0
            self.ip_fps = self._ip_fc / dt if dt > 0 else 0
            self._local_fc = 0; self._ip_fc = 0; self._fps_time = now

    # ============================================================
    # 运动量
    # ============================================================
    def _compute_motion(self, pose_landmarks):
        pts = np.array([(lm.x, lm.y) for lm in pose_landmarks.landmark])
        if self.prev_pose_points is not None:
            diff = np.sqrt(np.sum((pts - self.prev_pose_points) ** 2, axis=1))
            fm = float(np.mean(diff))
            self.motion_window.append(fm)
            avg = float(np.mean(self.motion_window))
            self.motion_intensity = min(100.0, avg * 3000)
            self.motion_accumulator += fm
            self.motion_history.append(round(self.motion_intensity, 1))
        self.prev_pose_points = pts.copy()

    # ============================================================
    # [V3.3] 情绪识别（支持模式切换 + 低门槛）
    # ============================================================
    def _compute_emotion(self, face_crop, face_landmarks):
        lm = np.array([(p.x, p.y, p.z) for p in face_landmarks.landmark])
        fh = np.linalg.norm(lm[10][:2] - lm[152][:2])

        is_drowsy = False; ear = 0.3; mouth_open = 0.0
        if fh > 1e-6:
            l_ear = abs(lm[159][1] - lm[145][1]) / (abs(lm[33][0] - lm[133][0]) + 1e-8)
            r_ear = abs(lm[386][1] - lm[374][1]) / (abs(lm[362][0] - lm[263][0]) + 1e-8)
            ear = (l_ear + r_ear) / 2
            self.eye_openness = ear
            mouth_open = abs(lm[13][1] - lm[14][1]) / fh
            if ear < 0.15 and mouth_open > 0.04:
                is_drowsy = True

        # [V3.3] 根据模式决定用模型还是规则
        use_model = (self.emotion_mode == "model" and self.emotion_recognizer is not None)

        if use_model and face_crop is not None:
            model_scores = self.emotion_recognizer.predict(face_crop)
            if model_scores is not None:
                if is_drowsy:
                    model_scores['drowsy'] = max(model_scores.get('drowsy', 0), 0.6)
                    for k in model_scores:
                        if k != 'drowsy':
                            model_scores[k] *= 0.3
                    total = sum(model_scores.values())
                    if total > 0:
                        for k in model_scores:
                            model_scores[k] /= total
                self.emotion_scores = {k: round(v, 3) for k, v in model_scores.items()}
                self._apply_emotion_smooth(model_scores)
                return

        # 规则方法
        self.emotion_method = "rule"
        self._compute_emotion_rules(lm, fh, ear, mouth_open)

    def _apply_emotion_smooth(self, scores):
        """[V3.3] 大幅降低切换门槛，让情绪响应更灵敏"""
        max_emo = max(scores, key=scores.get)
        total = sum(scores.values())
        raw_conf = scores[max_emo] / (total + 1e-8)

        self.emotion_method = "model" if self.emotion_mode == "model" else "rule"

        if self.emotion == max_emo:
            # 同一情绪：平滑累积置信度
            self.emotion_confidence = min(
                1.0, self.emotion_confidence * EMOTION_SMOOTH
                + raw_conf * (1 - EMOTION_SMOOTH) + 0.008)
        else:
            # [V3.3] 切换条件大幅降低：置信度 > 0.18 且略高于当前即可切换
            if raw_conf > 0.18 and raw_conf > self.emotion_confidence * 1.02:
                self.emotion = max_emo
                self.emotion_confidence = raw_conf * 0.6
            else:
                self.emotion_confidence *= 0.92

        self.emotion_history.append({
            'emotion': self.emotion,
            'confidence': round(self.emotion_confidence, 2),
            'scores': self.emotion_scores,
        })

    def _compute_emotion_rules(self, lm, fh, ear, mouth_open):
        if fh < 1e-6: return
        smile = ((lm[17][1] - lm[61][1]) + (lm[17][1] - lm[291][1])) / (2 * fh)
        brow_h = ((lm[159][1] - lm[107][1]) + (lm[386][1] - lm[336][1])) / (2 * fh)
        frown_r = (np.linalg.norm(lm[107][:2] - lm[336][:2])
                   / (np.linalg.norm(lm[133][:2] - lm[362][:2]) + 1e-8))
        s = {'happy': 0., 'surprised': 0., 'angry': 0., 'sad': 0., 'neutral': 0.25, 'drowsy': 0.}
        if smile > 0.005: s['happy'] += min(smile * 40, 0.8)
        if mouth_open > 0.04 and smile > 0.003: s['happy'] += 0.2
        if mouth_open > 0.06: s['surprised'] += min((mouth_open - 0.06) * 15, 0.5)
        if brow_h > 0.09: s['surprised'] += min((brow_h - 0.09) * 20, 0.3)
        if brow_h < 0.04: s['angry'] += min((0.04 - brow_h) * 25, 0.5)
        if frown_r < 0.85: s['angry'] += min((0.85 - frown_r) * 5, 0.3)
        if smile < -0.003: s['sad'] += min(abs(smile) * 50, 0.5)
        if ear < 0.18: s['drowsy'] += min((0.18 - ear) * 15, 0.6)
        if mouth_open > 0.04 and ear < 0.22: s['drowsy'] += 0.25
        if abs(smile) < 0.003 and mouth_open < 0.03 and 0.04 < brow_h < 0.08:
            s['neutral'] += 0.3
        self.emotion_scores = {k: round(v, 3) for k, v in s.items()}
        self._apply_emotion_smooth(s)

    # ============================================================
    # 专注度
    # ============================================================
    def _compute_focus(self, face_landmarks):
        lm = np.array([(p.x, p.y, p.z) for p in face_landmarks.landmark])
        fh = np.linalg.norm(lm[10][:2] - lm[152][:2])
        if fh < 1e-6: return
        nose = lm[1]; l_ch = lm[234]; r_ch = lm[454]; chin = lm[152]; forehead = lm[10]
        fw = abs(r_ch[0] - l_ch[0]) + 1e-8
        fhv = abs(chin[1] - forehead[1]) + 1e-8
        self.head_yaw = (nose[0] - (l_ch[0] + r_ch[0]) / 2) / fw
        self.head_pitch = (nose[1] - (forehead[1] + chin[1]) / 2) / fhv
        head_dev = abs(self.head_yaw) + abs(self.head_pitch)
        l_ear = abs(lm[159][1] - lm[145][1]) / (abs(lm[33][0] - lm[133][0]) + 1e-8)
        r_ear = abs(lm[386][1] - lm[374][1]) / (abs(lm[362][0] - lm[263][0]) + 1e-8)
        ear = (l_ear + r_ear) / 2; self.eye_openness = ear
        now = time.time()
        if ear < BLINK_EAR_CLOSE and self._blink_state == 'open':
            self._blink_state = 'closed'; self.blink_count += 1
            self._blink_timestamps.append(now)
        elif ear > BLINK_EAR_OPEN:
            self._blink_state = 'open'
        recent = [t for t in self._blink_timestamps if now - t < BLINK_WINDOW]
        self.blink_rate = len(recent) * (60.0 / BLINK_WINDOW)
        if self._prev_face_pts is not None:
            fm = float(np.mean(np.sqrt(np.sum((lm[:, :2] - self._prev_face_pts) ** 2, axis=1))))
        else: fm = 0.0
        self._prev_face_pts = lm[:, :2].copy()
        self._face_motion_win.append(fm)
        self.head_motion_score = float(np.mean(self._face_motion_win))
        score = 100.0
        score -= head_dev * 100
        score -= max(0, head_dev - 0.15) * 200
        if self.blink_rate > 25: score -= (self.blink_rate - 25) * 4
        elif self.blink_rate < 5 and len(recent) > 2: score -= (5 - self.blink_rate) * 6
        if self.head_motion_score > 0.3: score -= (self.head_motion_score - 0.3) * 60
        if ear < 0.2: score -= (0.2 - ear) * 400
        score = float(np.clip(score, 0, 100))
        self.focus_score = self.focus_score * FOCUS_SMOOTH + score * (1 - FOCUS_SMOOTH)
        self.focus_history.append(round(self.focus_score, 1))

    # ============================================================
    # 绘制
    # ============================================================
    def _draw_pose(self, frame, pose_landmarks, w, h):
        conns = mp.solutions.pose.POSE_CONNECTIONS
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in pose_landmarks.landmark]
        for c in conns:
            i, j = c
            if i < len(pts) and j < len(pts):
                cv2.line(frame, pts[i], pts[j], (0, 229, 160), 2)
        for idx in [0, 11, 12, 15, 16, 23, 24, 25, 26, 27, 28]:
            if idx < len(pts):
                cv2.circle(frame, pts[idx], 4, (0, 229, 160), -1)

    def _draw_face_contours(self, frame, face_landmarks, w, h):
        pts = [(int(p.x * w), int(p.y * h)) for p in face_landmarks.landmark]
        for contour in FACE_CONTOURS:
            for i in range(len(contour) - 1):
                a, b = contour[i], contour[i + 1]
                if a < len(pts) and b < len(pts):
                    cv2.line(frame, pts[a], pts[b], (0, 200, 140), 1)

    # ============================================================
    # API 数据
    # ============================================================
    def get_status(self):
        with self.lock:
            result = {
                'person': {
                    'detected': self.person_detected,
                    'local': self.person_detected_local,
                    'ip': self.person_detected_ip,
                    'status': self.person_status,
                    'uptime': round(time.time() - self.start_time, 0),
                },
                'emotion': {
                    'current': self.emotion,
                    'cn': EMOTION_META.get(self.emotion, ('?',))[0],
                    'confidence': round(self.emotion_confidence, 2),
                    'method': self.emotion_method,
                    'mode': self.emotion_mode,
                    'scores': self.emotion_scores,
                    'history': list(self.emotion_history)[-30:],
                },
                'focus': {
                    'score': round(self.focus_score, 1),
                    'history': list(self.focus_history)[-60:],
                    'blink_rate': round(self.blink_rate, 1),
                    'head_yaw': round(self.head_yaw, 3),
                    'head_pitch': round(self.head_pitch, 3),
                    'head_motion': round(self.head_motion_score, 4),
                    'eye_openness': round(self.eye_openness, 3),
                },
                'motion': {
                    'intensity': round(self.motion_intensity, 1),
                    'history': list(self.motion_history)[-60:],
                    'accumulated': round(self.motion_accumulator, 2),
                },
                'attribute': {'method': self.attr_method},
                'system': {
                    'local_fps': round(self.local_fps, 1),
                    'ip_fps': round(self.ip_fps, 1),
                    'local_cam': f'Local {LOCAL_CAMERA_ID}',
                    'ip_cam': DEFAULT_IP_CAMERA_URL,
                    'emotion_method': self.emotion_method,
                    'emotion_mode': self.emotion_mode,
                    'attr_method': self.attr_method,
                },
            }
            if self.face_attribute:
                result['attribute'].update(self.face_attribute)
            return result


processor = MultiModalProcessor()
processor.start()

# ============================================================
@app.route('/')
def index():
    p = os.path.join(SCRIPT_DIR, 'camm.html')
    return send_file(p) if os.path.exists(p) else "<h1>camm.html not found</h1>"


def _stream(frame_attr, label, dw=640, dh=360):
    while processor.running:
        with processor.lock:
            frame = getattr(processor, frame_attr, None)
        if frame is not None:
            ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                       + jpeg.tobytes() + b'\r\n')
        else:
            ph = np.zeros((dh, dw, 3), dtype=np.uint8)
            cv2.putText(ph, label, (dw // 2 - 120, dh // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 1)
            ok, jpeg = cv2.imencode('.jpg', ph, [cv2.IMWRITE_JPEG_QUALITY, 50])
            if ok:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                       + jpeg.tobytes() + b'\r\n')
        time.sleep(0.033)


@app.route('/video_local')
def video_local():
    return Response(_stream('local_frame_out', 'Local Camera Offline'),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_ip')
def video_ip():
    return Response(_stream('ip_frame_out', 'IP Camera Offline'),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/status')
def api_status():
    return jsonify(processor.get_status())


@app.route('/api/set_emotion_mode', methods=['POST'])
def api_set_emotion_mode():
    """切换情绪识别模式: model / rule / auto"""
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get('mode', 'auto')
    if mode not in ('model', 'rule', 'auto'):
        return jsonify({'error': 'mode must be model/rule/auto'}), 400
    processor.set_emotion_mode(mode)
    return jsonify({
        'emotion_mode': processor.emotion_mode,
        'emotion_method': processor.emotion_method,
    })


if __name__ == '__main__':
    try:
        print("=" * 64)
        print("  Multi-Modal Perception System V3.3")
        print(f"  Emotion : {processor.emotion_mode} "
              f"(model: {'loaded' if processor.emotion_recognizer else 'N/A'})")
        print(f"  Attribute: {'ONNX' if processor.attr_method == 'model' else 'N/A'}")
        print(f"  Camera  : ThreadedCamera")
        print("-" * 64)
        print(f"  Local : Camera {LOCAL_CAMERA_ID}")
        print(f"  IP    : {DEFAULT_IP_CAMERA_URL}")
        print(f"  http://localhost:5000")
        print("=" * 64)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down ...")
    finally:
        processor.stop()
