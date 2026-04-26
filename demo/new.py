import os, time, threading, traceback as tb, base64
from datetime import datetime
from queue import Queue
from collections import deque

import cv2, numpy as np, mediapipe as mp
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ===== 摄像头 =====
IP_CAMERA_URL = "http://10.158.10.79:8080/video"
LOCAL_CAMERA = 0
g_camera_src = LOCAL_CAMERA
g_processor = None

# ===== 模型路径（你的）=====
ONNX_MODEL_PATH = r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\emotion_classifier.onnx"

# ===== Debug =====
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_START = datetime.now().strftime("%Y%m%d_%H%M%S")
DEBUG_DIR = os.path.join(SCRIPT_DIR, "debug_aligned", RUN_START)
os.makedirs(DEBUG_DIR, exist_ok=True)


# ================= Emotion Model =================
class EmotionDetector:
    def __init__(self, path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
        self.input_name = self.sess.get_inputs()[0].name

        # 模型输出顺序
        self.labels = ["angry","disgust","fear","happy","sad","surprise","neutral"]
        print("[OK] EfficientNet Emotion Loaded")

    def predict(self, bgr):
        face = cv2.resize(bgr, (224, 224))
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        face = face.astype(np.float32) / 255.0

        face = np.transpose(face, (2, 0, 1))
        face = np.expand_dims(face, axis=0)

        outputs = self.sess.run(None, {self.input_name: face})[0][0]
        probs = self._softmax(outputs)

        # ===== 三分类映射（优化）=====
        p_happy = probs[3]
        p_calm = probs[6] + probs[5] * 0.3
        p_upset = probs[0] + probs[1] + probs[2] + probs[4] + probs[5] * 0.7

        total = p_happy + p_calm + p_upset + 1e-6
        final_probs = [p_calm/total, p_happy/total, p_upset/total]

        labels = ["calm", "happy", "upset"]
        idx = int(np.argmax(final_probs))
        return labels[idx], final_probs

    def _softmax(self, x):
        e = np.exp(x - np.max(x))
        return e / e.sum()


# ================= Face + Pose =================
class SmartAligner:
    def __init__(self):
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True
        )

    def detect(self, frame):
        h, w = frame.shape[:2]
        res = self.mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        if not res or not res.multi_face_landmarks:
            return None, None, None

        lm = res.multi_face_landmarks[0]
        pts = np.array([[p.x * w, p.y * h] for p in lm.landmark])

        le, re = pts[33], pts[263]
        eye_c = (le + re) / 2
        dist = np.linalg.norm(re - le)
        if dist < 5:
            return None, None, None

        angle = np.degrees(np.arctan2(re[1]-le[1], re[0]-le[0]))
        scale = 100 / dist

        M = cv2.getRotationMatrix2D(tuple(eye_c), angle, scale)
        M[0,2] += 128 - eye_c[0]
        M[1,2] += 128 - eye_c[1]

        aligned = cv2.warpAffine(frame, M, (256,256))

        # 简单 yaw 估计
        nose = pts[1]
        dx = (nose[0] - eye_c[0]) / dist
        yaw = -dx * 55

        box = (int(pts[:,0].min()), int(pts[:,1].min()),
               int(pts[:,0].max()), int(pts[:,1].max()))

        return aligned, box, (0, yaw, 0)


# ================= 平滑 =================
class TemporalSmoother:
    def __init__(self):
        self.state = "calm"
        self.conf = 0

    def update(self, label, probs):
        self.state = label
        self.conf = max(probs)
        return self.state, self.conf


# ================= 主处理 =================
class Processor:
    def __init__(self, src):
        self.cap = cv2.VideoCapture(src)
        self.det = SmartAligner()
        self.fer = EmotionDetector(ONNX_MODEL_PATH)
        self.smoother = TemporalSmoother()

        self.q = Queue(maxsize=1)
        self.jpeg = None
        self.label = "calm"
        self.conf = 0

        threading.Thread(target=self._grab, daemon=True).start()
        threading.Thread(target=self._work, daemon=True).start()

    def _grab(self):
        while True:
            ok, f = self.cap.read()
            if not ok:
                continue
            if self.q.full():
                self.q.get()
            self.q.put(f)

    def _work(self):
        while True:
            f = self.q.get()

            crop, box, pose = self.det.detect(f)

            if crop is not None:
                # ⭐ 侧脸过滤（关键稳定）
                if pose and abs(pose[1]) > 45:
                    pass
                else:
                    lb, pr = self.fer.predict(crop)
                    lb, cf = self.smoother.update(lb, pr)
                    self.label, self.conf = lb, cf

            self._render(f, box)

    def _render(self, frame, box):
        d = frame.copy()

        if box:
            x1,y1,x2,y2 = box
            cv2.rectangle(d,(x1,y1),(x2,y2),(0,255,0),2)
            cv2.putText(d,f"{self.label} {self.conf:.2f}",
                        (x1,y1-10),0,0.8,(0,255,0),2)

        _, buf = cv2.imencode(".jpg", d)
        self.jpeg = buf.tobytes()


# ================= Flask =================
def init():
    global g_processor
    g_processor = Processor(g_camera_src)

@app.route("/video_feed")
def vf():
    def g():
        while True:
            if g_processor and g_processor.jpeg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + g_processor.jpeg + b"\r\n")
    return Response(g, mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/get_emotion")
def ge():
    return jsonify(
        emotion=g_processor.label,
        confidence=g_processor.conf
    )

if __name__ == "__main__":
    init()
    app.run()