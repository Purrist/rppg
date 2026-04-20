"""feel.py - 多模态感知系统 V4.1

模块：情绪 + 属性(年龄/性别) + 专注度 + 活动量
情绪后端：DeepFace / ONNX FERPlus / 规则 / LLM（可切换，互不影响）
属性后端：ONNX AgeGender（始终运行，不受情绪切换影响）
专注度：MediaPipe FaceMesh（头部姿态+眨眼+面部运动）
活动量：MediaPipe Pose（关键点位移）
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file, request
import mediapipe as mp
import threading
import time
import os
import base64
from collections import deque

app = Flask(__name__)

# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════
LOCAL_CAMERA_ID = 1
DEFAULT_IP_CAMERA_URL = "http://10.215.158.45:8080/video"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SCRIPT_DIR, '..', 'backend', 'core', 'models')
FERPLUS_PATH = os.path.join(MODELS_DIR, 'emotion-ferplus-8.onnx')
AGE_PATH = os.path.join(MODELS_DIR, 'age_googlenet.onnx')
GENDER_PATH = os.path.join(MODELS_DIR, 'gender_googlenet.onnx')

LLM_API_URL = None
LLM_API_KEY = None
LLM_MODEL = None

MOTION_WINDOW = 60
FOCUS_SMOOTH = 0.70
EMOTION_SMOOTH = 0.45
PERSON_TIMEOUT = 3.0
BLINK_EAR_CLOSE = 0.18
BLINK_EAR_OPEN = 0.22
BLINK_WINDOW = 30
DEEPFACE_INTERVAL = 15
ONNX_EMOTION_INTERVAL = 5
ONNX_ATTR_INTERVAL = 15
LLM_INTERVAL = 30

FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10]
FACE_CONTOURS = [
    FACE_OVAL,
    [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33],
    [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466, 263],
    [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409,
     270, 269, 267, 0, 37, 39, 40, 185, 61],
    [70, 63, 105, 66, 107], [300, 293, 334, 296, 336]]

EMOTION_META = {
    'happy': ('开心', (0, 200, 100)), 'surprised': ('惊讶', (0, 200, 255)),
    'angry': ('愤怒', (0, 0, 255)), 'sad': ('悲伤', (255, 150, 0)),
    'neutral': ('平静', (150, 150, 150)), 'drowsy': ('困倦', (200, 100, 255))}

FER8_LABELS = ['neutral', 'happiness', 'surprise', 'sadness',
               'anger', 'disgust', 'fear', 'contempt']
FER8TO6 = {'neutral': 'neutral', 'happiness': 'happy', 'surprise': 'surprised',
           'sadness': 'sad', 'anger': 'angry', 'disgust': 'angry',
           'fear': 'sad', 'contempt': 'neutral'}

AGE_LABELS = ['(0-2)', '(4-6)', '(8-12)', '(15-20)',
              '(25-32)', '(38-43)', '(48-53)', '(60-100)']
GENDER_LABELS = ['Male', 'Female']
DF_TO_6 = {'happy': 'happy', 'surprise': 'surprised', 'angry': 'angry',
           'sad': 'sad', 'neutral': 'neutral', 'disgust': 'angry', 'fear': 'sad'}

try:
    import onnxruntime as ort; HAS_ORT = True
except ImportError:
    HAS_ORT = False; print("[WARN] onnxruntime 未安装")
try:
    from deepface import DeepFace; HAS_DF = True; print("[OK] deepface")
except ImportError:
    HAS_DF = False; print("[INFO] deepface 未安装 (pip install deepface)")
try:
    import requests; HAS_REQ = True
except ImportError:
    HAS_REQ = False


# ═══════════════════════════════════════════
# ThreadedCamera
# ═══════════════════════════════════════════
class ThreadedCamera:
    def __init__(self, src, buffer_size=1):
        self.cap = cv2.VideoCapture(src)
        self._ok = self.cap.isOpened()
        if self._ok:
            try: self.cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
            except: pass
        self._frame = None; self._running = True; self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while self._running:
            ret, f = self.cap.read()
            if ret:
                with self._lock: self._frame = f
            else: time.sleep(0.005)

    def read(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def isOpened(self): return self._ok and self.cap.isOpened()
    def get(self, p, d=0.0):
        try: return self.cap.get(p)
        except: return d

    def release(self):
        self._running = False; time.sleep(0.05)
        try: self.cap.release()
        except: pass


# ═══════════════════════════════════════════
# DeepFace（情绪+年龄+性别）
# ═══════════════════════════════════════════
class DeepFaceBackend:
    def __init__(self):
        self.ready = HAS_DF; self._warm = False

    def analyze(self, face_bgr):
        if not self.ready or face_bgr is None or face_bgr.size == 0:
            return None
        try:
            result = DeepFace.analyze(
                face_bgr, actions=['emotion', 'age', 'gender'],
                enforce_detection=False, silent=True)
            self._warm = True
            if isinstance(result, list): r = result[0]
            elif hasattr(result, 'iloc'): r = result.iloc[0].to_dict()
            elif isinstance(result, dict): r = result
            else: return None
            raw_em = r.get('emotion', {})
            scores = {k: 0.0 for k in ['happy','surprised','angry','sad','neutral','drowsy']}
            for k, v in raw_em.items():
                scores[DF_TO_6.get(k, 'neutral')] += float(v)
            total = sum(scores.values())
            if total > 0:
                for k in scores: scores[k] /= total
            age = r.get('age', 0)
            if isinstance(age, (list, tuple)): age = age[0] if age else 0
            age = int(age)
            g = r.get('dominant_gender', r.get('gender', 'Man'))
            if isinstance(g, (list, tuple)): g = g[0] if g else 'Man'
            gender = 'Male' if str(g).lower().startswith('man') else 'Female'
            return {'emotion_scores': {k: round(v, 3) for k, v in scores.items()},
                    'age': age, 'gender': gender}
        except Exception as e:
            if not self._warm:
                self._warm = True; print(f"[DeepFace] 首次加载中... ({e})")
            return None


# ═══════════════════════════════════════════
# FERPlus ONNX（情绪 only）
# ═══════════════════════════════════════════
class FERPlusBackend:
    """官方预处理：灰度 64x64，0-255 原始像素值，不做归一化"""
    def __init__(self, path):
        if not HAS_ORT: raise RuntimeError("onnxruntime 未安装")
        if not os.path.isfile(path): raise FileNotFoundError(path)
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2; opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(path, opts, providers=['CPUExecutionProvider'])
        inp = self.session.get_inputs()[0]; out = self.session.get_outputs()[0]
        self.in_name = inp.name; self.out_name = out.name
        self.h = int(inp.shape[2]) if inp.shape[2] > 0 else 64
        self.w = int(inp.shape[3]) if inp.shape[3] > 0 else 64
        self.ready = True
        print(f"[OK] FERPlus ONNX: {os.path.basename(path)}")

    def predict(self, face_bgr):
        if face_bgr is None or face_bgr.size == 0: return None
        try:
            gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (self.w, self.h))
            blob = resized.astype(np.float32).reshape(1, 1, self.h, self.w)
            raw = self.session.run([self.out_name], {self.in_name: blob})[0][0].astype(np.float64)
            s = np.exp(raw - raw.max()); scores = s / (s.sum() + 1e-10)
            r6 = {k: 0.0 for k in ['happy','surprised','angry','sad','neutral','drowsy']}
            for i, lb in enumerate(FER8_LABELS):
                if i < len(scores): r6[FER8TO6.get(lb, 'neutral')] += float(scores[i])
            t = sum(r6.values())
            if t > 0:
                for k in r6: r6[k] /= t
            return {k: round(v, 3) for k, v in r6.items()}
        except: return None


# ═══════════════════════════════════════════
# Age/Gender ONNX（属性 only，始终运行）
# ═══════════════════════════════════════════
class AgeGenderBackend:
    """官方预处理：BGR→RGB，224x224，减均值 [104,117,123]"""
    MEAN = np.array([104.0, 117.0, 123.0], dtype=np.float32)

    def __init__(self, age_path, gender_path):
        if not HAS_ORT: raise RuntimeError("onnxruntime 未安装")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2; opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.age_s = ort.InferenceSession(age_path, opts, providers=['CPUExecutionProvider'])
        self.gen_s = ort.InferenceSession(gender_path, opts, providers=['CPUExecutionProvider'])
        self.a_in = self.age_s.get_inputs()[0].name
        self.a_out = self.age_s.get_outputs()[0].name
        self.g_in = self.gen_s.get_inputs()[0].name
        self.g_out = self.gen_s.get_outputs()[0].name
        self.ready = True; print("[OK] Age/Gender ONNX")

    def predict(self, face_bgr):
        if face_bgr is None or face_bgr.size == 0: return None
        try:
            rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            img = cv2.resize(rgb, (224, 224)).astype(np.float32) - self.MEAN
            blob = img.transpose(2, 0, 1)[np.newaxis]
            ar = self.age_s.run([self.a_out], {self.a_in: blob})[0][0].astype(np.float64)
            s = np.exp(ar - ar.max()); ap = s / (s.sum() + 1e-10); ai = int(np.argmax(ap))
            gr = self.gen_s.run([self.g_out], {self.g_in: blob})[0][0].astype(np.float64)
            s = np.exp(gr - gr.max()); gp = s / (s.sum() + 1e-10); gi = int(np.argmax(gp))
            return {
                'age': AGE_LABELS[ai], 'age_confidence': round(float(ap[ai]), 2),
                'age_probs': {AGE_LABELS[i]: round(float(p), 3) for i, p in enumerate(ap)},
                'gender': GENDER_LABELS[gi], 'gender_confidence': round(float(gp[gi]), 2),
                'gender_probs': {GENDER_LABELS[i]: round(float(p), 3) for i, p in enumerate(gp)}}
        except: return None


# ═══════════════════════════════════════════
# LLM Vision（情绪 only，可选）
# ═══════════════════════════════════════════
class LLMBackend:
    PROMPT = ("Look at this face and respond with ONLY ONE emotion word. "
              "Choose: happy, surprised, angry, sad, neutral, drowsy. Answer:")
    WMAP = {'happy': 'happy', 'happiness': 'happy', 'joy': 'happy', 'smile': 'happy',
            'surprised': 'surprised', 'surprise': 'surprised', 'shocked': 'surprised',
            'angry': 'angry', 'anger': 'angry', 'furious': 'angry',
            'sad': 'sad', 'sadness': 'sad', 'crying': 'sad',
            'neutral': 'neutral', 'calm': 'neutral',
            'drowsy': 'drowsy', 'sleepy': 'drowsy', 'tired': 'drowsy'}

    def __init__(self, url, key, model):
        if not HAS_REQ: raise RuntimeError("requests 未安装")
        self.url = url.rstrip('/'); self.key = key or "none"; self.model = model
        self.ready = True; print(f"[OK] LLM: {model} @ {url}")

    def predict(self, face_bgr):
        if face_bgr is None or face_bgr.size == 0: return None
        try:
            _, buf = cv2.imencode('.jpg', face_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buf).decode()
            resp = requests.post(self.url, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}"
            }, json={
                "model": self.model,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": self.PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}],
                "max_tokens": 10, "temperature": 0.0
            }, timeout=5.0)
            if resp.status_code != 200: return None
            text = resp.json()["choices"][0]["message"]["content"].strip().lower()
            mapped = 'neutral'
            for w in text.split():
                if w in self.WMAP: mapped = self.WMAP[w]; break
            scores = {k: 0.0 for k in ['happy','surprised','angry','sad','neutral','drowsy']}
            scores[mapped] = 1.0
            print(f"[LLM] \"{text}\" -> {mapped}")
            return {k: round(v, 3) for k, v in scores.items()}
        except: return None


# ═══════════════════════════════════════════
# 主处理器
# ═══════════════════════════════════════════
class Processor:
    def __init__(self):
        self.local_cap = None; self.ip_cap = None
        self.local_running = False; self.ip_running = False
        self.person_detected_local = False; self.person_detected_ip = False
        self.person_detected = False; self.person_last_seen = 0.0
        self.person_status = "offline"

        # 情绪
        self.emotion = "neutral"; self.emotion_confidence = 0.0
        self.emotion_scores = {}; self.emotion_history = deque(maxlen=60)
        self.emotion_method = "none"
        self.backend = "auto"  # deepface / onnx / rule / llm / auto

        # 属性（始终独立运行）
        self.face_attribute = None; self.attr_method = "none"

        # 专注度
        self.focus_score = 50.0; self.focus_history = deque(maxlen=120)
        self.blink_count = 0; self.blink_rate = 0.0
        self.head_yaw = 0.0; self.head_pitch = 0.0
        self.head_motion_score = 0.0; self.eye_openness = 0.0

        # 活动量
        self.motion_intensity = 0.0; self.motion_history = deque(maxlen=120)
        self.motion_accumulator = 0.0; self.motion_window = deque(maxlen=MOTION_WINDOW)
        self.prev_pose_points = None

        self.local_fps = 0.0; self.ip_fps = 0.0
        self._lfc = 0; self._ifc = 0; self._ft = time.time()
        self.local_frame_out = None; self.ip_frame_out = None
        self._bs = 'open'; self._bt = deque(maxlen=50)
        self._prev_fp = None; self._fmw = deque(maxlen=30)
        self._dbg_t = 0.0; self._frame_cnt = 0

        self.lock = threading.Lock(); self.running = True
        self.start_time = time.time()
        self.face_mesh = None; self.face_detection = None; self.pose_detector = None

        # 后端实例
        self.df = DeepFaceBackend()
        self.ferplus = None; self.agnet = None; self.llm = None
        self._df_busy = False; self._llm_busy = False

    def start(self):
        print("[INIT] MediaPipe ...")
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.3)
        self.pose_detector = mp.solutions.pose.Pose(
            model_complexity=1,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        print("[OK] MediaPipe")

        # 加载 ONNX 情绪
        if HAS_ORT and os.path.isfile(FERPLUS_PATH):
            try: self.ferplus = FERPlusBackend(FERPLUS_PATH)
            except Exception as e: print(f"[WARN] FERPlus: {e}")
        # 加载 ONNX 属性（始终运行，不受情绪后端影响）
        if HAS_ORT and os.path.isfile(AGE_PATH) and os.path.isfile(GENDER_PATH):
            try:
                self.agnet = AgeGenderBackend(AGE_PATH, GENDER_PATH)
                self.attr_method = "onnx"
                print("[INFO] 属性模型: age+gender ONNX (始终运行)")
            except Exception as e: print(f"[WARN] AgeGender: {e}")
        # 加载 LLM
        if LLM_API_URL and LLM_MODEL:
            try: self.llm = LLMBackend(LLM_API_URL, LLM_API_KEY, LLM_MODEL)
            except Exception as e: print(f"[WARN] LLM: {e}")

        # 默认情绪后端
        if self.df.ready: self.backend = "deepface"
        elif self.ferplus: self.backend = "onnx"
        else: self.backend = "rule"

        # 摄像头
        self.local_cap = ThreadedCamera(LOCAL_CAMERA_ID)
        if self.local_cap.isOpened():
            self.local_running = True; print(f"[OK] 本地摄像头 {LOCAL_CAMERA_ID}")
        else: print("[WARN] 本地摄像头失败")
        self.ip_cap = ThreadedCamera(DEFAULT_IP_CAMERA_URL)
        if self.ip_cap.isOpened():
            self.ip_running = True; print("[OK] IP 摄像头")
        else: print("[WARN] IP 摄像头失败")

        if not self.local_running and not self.ip_running:
            raise RuntimeError("摄像头无法打开")
        if self.local_running:
            threading.Thread(target=self._local_w, daemon=True).start()
        if self.ip_running:
            threading.Thread(target=self._ip_w, daemon=True).start()

    def stop(self):
        self.running = False
        if self.local_cap: self.local_cap.release()
        if self.ip_cap: self.ip_cap.release()

    def set_backend(self, b):
        with self.lock:
            if b == 'auto':
                self.backend = 'deepface' if self.df.ready else ('onnx' if self.ferplus else 'rule')
            elif b == 'deepface' and self.df.ready: self.backend = 'deepface'
            elif b == 'onnx' and self.ferplus: self.backend = 'onnx'
            elif b == 'llm' and self.llm: self.backend = 'llm'
            elif b == 'rule': self.backend = 'rule'
            print(f"[INFO] 情绪后端: {self.backend}")

    def _crop_oval(self, frame, lm, pad=0.18):
        h, w = frame.shape[:2]
        pts = np.array([(lm.landmark[i].x * w, lm.landmark[i].y * h) for i in FACE_OVAL])
        x0, x1 = pts[:, 0].min(), pts[:, 0].max()
        y0, y1 = pts[:, 1].min(), pts[:, 1].max()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sz = max(x1 - x0, y1 - y0) * (1 + pad)
        x1 = max(0, int(cx - sz / 2)); y1 = max(0, int(cy - sz / 2))
        x2 = min(w, int(cx + sz / 2)); y2 = min(h, int(cy + sz / 2))
        c = frame[y1:y2, x1:x2]
        return c if c.size > 0 and c.shape[0] >= 20 and c.shape[1] >= 20 else None

    def _update_person(self):
        self.person_detected = self.person_detected_local or self.person_detected_ip
        if self.person_detected:
            self.person_last_seen = time.time(); self.person_status = "present"
        elif time.time() - self.person_last_seen > PERSON_TIMEOUT:
            self.person_status = "offline"
        elif self.person_status == "present":
            self.person_status = "lost"

    def _update_fps(self):
        now = time.time(); dt = now - self._ft
        if dt >= 1.0:
            self.local_fps = self._lfc / dt; self.ip_fps = self._ifc / dt
            self._lfc = 0; self._ifc = 0; self._ft = now

    # ──────── 活动量 ────────
    def _compute_motion(self, pl):
        pts = np.array([(l.x, l.y) for l in pl.landmark])
        if self.prev_pose_points is not None:
            d = np.sqrt(np.sum((pts - self.prev_pose_points) ** 2, axis=1))
            fm = float(np.mean(d)); self.motion_window.append(fm)
            self.motion_intensity = min(100.0, float(np.mean(self.motion_window)) * 3000)
            self.motion_accumulator += fm
            self.motion_history.append(round(self.motion_intensity, 1))
        self.prev_pose_points = pts.copy()

    # ──────── 情绪（根据后端分发） ────────
    def _run_emotion(self, crop, lm, is_drowsy):
        self._frame_cnt += 1

        if self.backend == "deepface" and not self._df_busy:
            if self._frame_cnt % DEEPFACE_INTERVAL == 0 and crop is not None:
                self._df_busy = True; cp = crop.copy()
                threading.Thread(target=self._df_infer, args=(cp, is_drowsy), daemon=True).start()
            return

        if self.backend == "llm" and self.llm and not self._llm_busy:
            if self._frame_cnt % LLM_INTERVAL == 0 and crop is not None:
                self._llm_busy = True; cp = crop.copy()
                threading.Thread(target=self._llm_infer, args=(cp, is_drowsy), daemon=True).start()
            return

        if self.backend == "onnx" and self.ferplus and crop is not None:
            if self._frame_cnt % ONNX_EMOTION_INTERVAL == 0:
                sc = self.ferplus.predict(crop)
                if sc:
                    if is_drowsy:
                        sc['drowsy'] = max(sc.get('drowsy', 0), 0.6)
                        for k in sc:
                            if k != 'drowsy': sc[k] *= 0.3
                        t = sum(sc.values())
                        if t > 0:
                            for k in sc: sc[k] /= t
                    self.emotion_scores = sc; self._smooth(sc, "onnx")
            return

        # 规则兜底
        pts = np.array([(p.x, p.y, p.z) for p in lm.landmark])
        fh = np.linalg.norm(pts[10][:2] - pts[152][:2])
        ear = 0.3; mo = 0.0
        if fh > 1e-6:
            le = abs(pts[159][1] - pts[145][1]) / (abs(pts[33][0] - pts[133][0]) + 1e-8)
            re = abs(pts[386][1] - pts[374][1]) / (abs(pts[362][0] - pts[263][0]) + 1e-8)
            ear = (le + re) / 2; mo = abs(pts[13][1] - pts[14][1]) / fh
        self.emotion_method = "rule"
        self._rule_emotion(pts, fh, ear, mo)

    def _df_infer(self, crop, is_drowsy):
        try:
            r = self.df.analyze(crop)
            if r:
                sc = r['emotion_scores']
                if is_drowsy:
                    sc['drowsy'] = max(sc.get('drowsy', 0), 0.6)
                    for k in sc:
                        if k != 'drowsy': sc[k] *= 0.3
                    t = sum(sc.values())
                    if t > 0:
                        for k in sc: sc[k] /= t
                with self.lock:
                    self.emotion_scores = sc; self._smooth(sc, "deepface")
        except: pass
        finally: self._df_busy = False

    def _llm_infer(self, crop, is_drowsy):
        try:
            sc = self.llm.predict(crop)
            if sc:
                if is_drowsy:
                    sc['drowsy'] = max(sc.get('drowsy', 0), 0.6)
                    for k in sc:
                        if k != 'drowsy': sc[k] *= 0.3
                    t = sum(sc.values())
                    if t > 0:
                        for k in sc: sc[k] /= t
                with self.lock:
                    self.emotion_scores = sc; self._smooth(sc, "llm")
        except: pass
        finally: self._llm_busy = False

    def _smooth(self, scores, method):
        mx = max(scores, key=scores.get)
        rc = scores[mx] / (sum(scores.values()) + 1e-8)
        self.emotion_method = method
        if self.emotion == mx:
            self.emotion_confidence = min(1.0,
                self.emotion_confidence * EMOTION_SMOOTH + rc * (1 - EMOTION_SMOOTH) + 0.008)
        else:
            if rc > 0.18 and rc > self.emotion_confidence * 1.02:
                self.emotion = mx; self.emotion_confidence = rc * 0.6
            else:
                self.emotion_confidence *= 0.92
        self.emotion_history.append({
            'emotion': self.emotion, 'confidence': round(self.emotion_confidence, 2),
            'scores': self.emotion_scores})

    def _rule_emotion(self, lm, fh, ear, mo):
        if fh < 1e-6: return
        sm = ((lm[17][1] - lm[61][1]) + (lm[17][1] - lm[291][1])) / (2 * fh)
        bh = ((lm[159][1] - lm[107][1]) + (lm[386][1] - lm[336][1])) / (2 * fh)
        fr = np.linalg.norm(lm[107][:2] - lm[336][:2]) / (np.linalg.norm(lm[133][:2] - lm[362][:2]) + 1e-8)
        s = {'happy': 0., 'surprised': 0., 'angry': 0., 'sad': 0., 'neutral': 0.25, 'drowsy': 0.}
        if sm > 0.005: s['happy'] += min(sm * 40, 0.8)
        if mo > 0.04 and sm > 0.003: s['happy'] += 0.2
        if mo > 0.06: s['surprised'] += min((mo - 0.06) * 15, 0.5)
        if bh > 0.09: s['surprised'] += min((bh - 0.09) * 20, 0.3)
        if bh < 0.04: s['angry'] += min((0.04 - bh) * 25, 0.5)
        if fr < 0.85: s['angry'] += min((0.85 - fr) * 5, 0.3)
        if sm < -0.003: s['sad'] += min(abs(sm) * 50, 0.5)
        if ear < 0.18: s['drowsy'] += min((0.18 - ear) * 15, 0.6)
        if mo > 0.04 and ear < 0.22: s['drowsy'] += 0.25
        if abs(sm) < 0.003 and mo < 0.03 and 0.04 < bh < 0.08: s['neutral'] += 0.3
        self.emotion_scores = {k: round(v, 3) for k, v in s.items()}
        self._smooth(s, "rule")

    # ──────── 专注度 ────────
    def _compute_focus(self, lm):
        pts = np.array([(p.x, p.y, p.z) for p in lm.landmark])
        fh = np.linalg.norm(pts[10][:2] - pts[152][:2])
        if fh < 1e-6: return
        n = pts[1]; lc = pts[234]; rc = pts[454]; ch = pts[152]; ft = pts[10]
        fw = abs(rc[0] - lc[0]) + 1e-8; fhw = abs(ch[1] - ft[1]) + 1e-8
        self.head_yaw = (n[0] - (lc[0] + rc[0]) / 2) / fw
        self.head_pitch = (n[1] - (ft[1] + ch[1]) / 2) / fhw
        hd = abs(self.head_yaw) + abs(self.head_pitch)
        le = abs(pts[159][1] - pts[145][1]) / (abs(pts[33][0] - pts[133][0]) + 1e-8)
        re = abs(pts[386][1] - pts[374][1]) / (abs(pts[362][0] - pts[263][0]) + 1e-8)
        ear = (le + re) / 2; self.eye_openness = ear
        now = time.time()
        if ear < BLINK_EAR_CLOSE and self._bs == 'open':
            self._bs = 'closed'; self.blink_count += 1; self._bt.append(now)
        elif ear > BLINK_EAR_OPEN: self._bs = 'open'
        rec = [t for t in self._bt if now - t < BLINK_WINDOW]
        self.blink_rate = len(rec) * (60.0 / BLINK_WINDOW)
        if self._prev_fp is not None:
            fm = float(np.mean(np.sqrt(np.sum((pts[:, :2] - self._prev_fp) ** 2, axis=1))))
        else: fm = 0.0
        self._prev_fp = pts[:, :2].copy(); self._fmw.append(fm)
        self.head_motion_score = float(np.mean(self._fmw))
        sc = 100.0 - hd * 100 - max(0, hd - 0.15) * 200
        if self.blink_rate > 25: sc -= (self.blink_rate - 25) * 4
        elif self.blink_rate < 5 and len(rec) > 2: sc -= (5 - self.blink_rate) * 6
        if self.head_motion_score > 0.3: sc -= (self.head_motion_score - 0.3) * 60
        if ear < 0.2: sc -= (0.2 - ear) * 400
        self.focus_score = self.focus_score * FOCUS_SMOOTH + float(np.clip(sc, 0, 100)) * (1 - FOCUS_SMOOTH)
        self.focus_history.append(round(self.focus_score, 1))

    # ──────── 绘制 ────────
    def _draw_pose(self, f, pl, w, h):
        ps = [(int(l.x * w), int(l.y * h)) for l in pl.landmark]
        for c in mp.solutions.pose.POSE_CONNECTIONS:
            if c[0] < len(ps) and c[1] < len(ps):
                cv2.line(f, ps[c[0]], ps[c[1]], (0, 229, 160), 2)
        for i in [0, 11, 12, 15, 16, 23, 24, 25, 26, 27, 28]:
            if i < len(ps): cv2.circle(f, ps[i], 4, (0, 229, 160), -1)

    def _draw_face(self, f, lm, w, h):
        ps = [(int(p.x * w), int(p.y * h)) for p in lm.landmark]
        for c in FACE_CONTOURS:
            for i in range(len(c) - 1):
                a, b = c[i], c[i + 1]
                if a < len(ps) and b < len(ps):
                    cv2.line(f, ps[a], ps[b], (0, 200, 140), 1)

    # ──────── 本地摄像头线程（活动量） ────────
    def _local_w(self):
        while self.running:
            try:
                frame = self.local_cap.read()
                if frame is None: time.sleep(0.01); continue
                h, w = frame.shape[:2]
                r = self.pose_detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                with self.lock:
                    self._lfc += 1
                    if r.pose_landmarks:
                        self.person_detected_local = True
                        self._compute_motion(r.pose_landmarks)
                        self._draw_pose(frame, r.pose_landmarks, w, h)
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, f"MOTION: {self.motion_intensity:.1f}%",
                                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 229, 160), 1)
                        cv2.putText(frame, f"ACC: {self.motion_accumulator:.1f}",
                                    (w - 180, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        bw = int(w * min(self.motion_intensity, 100) / 100)
                        bc = ((0, 229, 160) if self.motion_intensity < 30 else
                              (0, 180, 120) if self.motion_intensity < 60 else (0, 100, 255))
                        cv2.rectangle(frame, (0, h - 4), (bw, h), bc, -1)
                    else:
                        self.person_detected_local = False; self.prev_pose_points = None
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, "NO PERSON", (10, 24),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
                    self._update_person(); self._update_fps(); self.local_frame_out = frame
            except: time.sleep(0.01)

    # ──────── IP 摄像头线程（情绪+属性+专注度） ────────
    def _ip_w(self):
        while self.running:
            try:
                frame = self.ip_cap.read()
                if frame is None: time.sleep(0.01); continue
                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                det = self.face_detection.process(rgb)
                has_f = det.detections is not None and len(det.detections) > 0
                mr = None
                if has_f:
                    mr = self.face_mesh.process(rgb)
                    has_m = mr.multi_face_landmarks is not None and len(mr.multi_face_landmarks) > 0
                else: has_m = False

                with self.lock:
                    self._ifc += 1
                    if has_m:
                        self.person_detected_ip = True
                        lm = mr.multi_face_landmarks[0]
                        crop = self._crop_oval(frame, lm)

                        # 困倦检测（所有后端通用）
                        pts = np.array([(p.x, p.y, p.z) for p in lm.landmark])
                        fh = np.linalg.norm(pts[10][:2] - pts[152][:2])
                        is_drowsy = False
                        if fh > 1e-6:
                            le = abs(pts[159][1] - pts[145][1]) / (abs(pts[33][0] - pts[133][0]) + 1e-8)
                            re = abs(pts[386][1] - pts[374][1]) / (abs(pts[362][0] - pts[263][0]) + 1e-8)
                            ear = (le + re) / 2; self.eye_openness = ear
                            mo = abs(pts[13][1] - pts[14][1]) / fh
                            if ear < 0.15 and mo > 0.04: is_drowsy = True

                        # 情绪（按选择的情绪后端）
                        self._run_emotion(crop, lm, is_drowsy)

                        # 属性（始终用 ONNX，不受情绪后端影响）
                        if self.agnet and crop is not None:
                            if self._frame_cnt % ONNX_ATTR_INTERVAL == 0:
                                attr = self.agnet.predict(crop)
                                if attr:
                                    self.face_attribute = attr
                                    self.attr_method = "onnx"

                        # 专注度
                        self._compute_focus(lm)

                        # 绘制
                        self._draw_face(frame, lm, w, h)
                        cv2.rectangle(frame, (0, 0), (w, 72), (0, 0, 0), -1)
                        cn, color = EMOTION_META.get(self.emotion, ('?', (150, 150, 150)))
                        mt = {"deepface": "[DF]", "onnx": "[ON]", "llm": "[LLM]", "rule": "[R]"}.get(
                            self.emotion_method, "[?]")
                        cv2.putText(frame, f"{mt} {cn} ({self.emotion_confidence:.0%})",
                                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                        fc = ((0, 229, 160) if self.focus_score > 60 else
                              (0, 180, 120) if self.focus_score > 30 else (0, 80, 255))
                        cv2.putText(frame, f"Focus: {self.focus_score:.0f}%",
                                    (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.45, fc, 1)
                        cv2.putText(frame, f"Blink: {self.blink_rate:.0f}/min",
                                    (w - 170, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        cv2.putText(frame, f"Eye: {self.eye_openness:.2f}",
                                    (w - 170, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        if self.face_attribute:
                            a_s = f"{self.face_attribute.get('age','?')}  {self.face_attribute.get('gender','?')}"
                            cv2.putText(frame, a_s, (10, 66),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1)
                        bw = int(w * min(self.focus_score, 100) / 100)
                        cv2.rectangle(frame, (0, h - 4), (bw, h), fc, -1)

                        now = time.time()
                        if now - self._dbg_t > 3.0:
                            self._dbg_t = now
                            t3 = sorted(self.emotion_scores.items(), key=lambda x: -x[1])[:3]
                            print(f"[DBG] {self.emotion}({self.emotion_confidence:.2f}) "
                                  f"emo:{self.emotion_method} attr:{self.attr_method} TOP3:{t3}")
                    else:
                        self.person_detected_ip = False
                        self.emotion = "neutral"
                        self.emotion_confidence = max(0, self.emotion_confidence - 0.02)
                        self.focus_score *= 0.98; self.face_attribute = None
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, "NO FACE", (10, 24),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
                    self._update_person(); self._update_fps(); self.ip_frame_out = frame
            except: time.sleep(0.01)

    # ──────── API 数据 ────────
    def get_status(self):
        with self.lock:
            r = {
                'person': {'detected': self.person_detected,
                           'local': self.person_detected_local,
                           'ip': self.person_detected_ip,
                           'status': self.person_status,
                           'uptime': round(time.time() - self.start_time, 0)},
                'emotion': {'current': self.emotion,
                            'cn': EMOTION_META.get(self.emotion, ('?',))[0],
                            'confidence': round(self.emotion_confidence, 2),
                            'method': self.emotion_method,
                            'scores': self.emotion_scores,
                            'history': list(self.emotion_history)[-30:]},
                'focus': {'score': round(self.focus_score, 1),
                          'history': list(self.focus_history)[-60:],
                          'blink_rate': round(self.blink_rate, 1),
                          'head_yaw': round(self.head_yaw, 3),
                          'head_pitch': round(self.head_pitch, 3),
                          'head_motion': round(self.head_motion_score, 4),
                          'eye_openness': round(self.eye_openness, 3)},
                'motion': {'intensity': round(self.motion_intensity, 1),
                           'history': list(self.motion_history)[-60:],
                           'accumulated': round(self.motion_accumulator, 2)},
                'attribute': {'method': self.attr_method},
                'system': {'local_fps': round(self.local_fps, 1),
                           'ip_fps': round(self.ip_fps, 1),
                           'backend': self.backend,
                           'emotion_method': self.emotion_method,
                           'attr_method': self.attr_method,
                           'deepface': self.df.ready,
                           'onnx_emotion': self.ferplus is not None,
                           'onnx_attr': self.agnet is not None,
                           'llm': self.llm is not None}}
            if self.face_attribute:
                r['attribute'].update(self.face_attribute)
            return r


processor = Processor()
processor.start()

@app.route('/')
def index():
    p = os.path.join(SCRIPT_DIR, 'camm.html')
    return send_file(p) if os.path.exists(p) else "<h1>camm.html not found</h1>"

def _stream(fa, label, dw=640, dh=360):
    while processor.running:
        with processor.lock:
            f = getattr(processor, fa, None)
        if f is not None:
            ok, j = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + j.tobytes() + b'\r\n')
        else:
            ph = np.zeros((dh, dw, 3), dtype=np.uint8)
            cv2.putText(ph, label, (dw // 2 - 120, dh // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 1)
            ok, j = cv2.imencode('.jpg', ph, [cv2.IMWRITE_JPEG_QUALITY, 50])
            if ok: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + j.tobytes() + b'\r\n')
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

@app.route('/api/set_backend', methods=['POST'])
def api_set_backend():
    d = request.get_json(force=True, silent=True) or {}
    b = d.get('backend', 'auto')
    if b not in ('deepface', 'onnx', 'rule', 'llm', 'auto'):
        return jsonify({'error': 'invalid'}), 400
    processor.set_backend(b)
    return jsonify({'backend': processor.backend, 'emotion_method': processor.emotion_method})

if __name__ == '__main__':
    print("=" * 60)
    print(f"  V4.1 | 情绪后端: {processor.backend}")
    print(f"  DeepFace: {'YES' if processor.df.ready else 'NO'}")
    print(f"  ONNX 情绪: {'YES' if processor.ferplus else 'NO'}")
    print(f"  ONNX 属性: {'YES' if processor.agnet else 'NO'} (始终运行)")
    print(f"  LLM: {'YES' if processor.llm else 'NO'}")
    print(f"  http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
