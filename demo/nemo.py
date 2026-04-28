"""
nemo.py — MediaPipe对齐 + FER+推理 + 时间平滑（工程级方案）
✅ L1: 双眼水平对齐
✅ L2: 标准化裁剪(64x64)
✅ L3: 滑动窗口时间平滑
✅ 架构重构: Frame Queue + 推理节流
"""
import sys, os, traceback as tb
from queue import Queue
from collections import deque
import cv2, time, threading
import numpy as np
import mediapipe as mp
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

IP_CAMERA_URL = "http://10.215.158.45:8080/video"
LOCAL_CAMERA = 0
g_camera_src = LOCAL_CAMERA
g_processor = None

MODEL_PATH = r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\emotion-ferplus-8.onnx"
LABELS = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def softmax(x):
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-10)


# ========== 人脸对齐（L1） ==========
class FaceAligner:
    """用MediaPipe做双眼水平对齐"""
    def __init__(self):
        print("[INIT] MediaPipe FaceMesh (align)...")
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5)
        print("[OK] FaceMesh")

    def align(self, frame):
        """
        输入: 原图
        输出: (aligned_face_64x64, box) 或 (None, None)
        """
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            res = self.mesh.process(rgb)
        except Exception:
            return None, None

        if not res.multi_face_landmarks:
            return None, None

        lm = res.multi_face_landmarks[0].landmark
        
        # 双眼关键点
        left_eye = np.array([lm[33].x * w, lm[33].y * h])
        right_eye = np.array([lm[263].x * w, lm[263].y * h])
        
        # 计算角度：让双眼水平
        dy = right_eye[1] - left_eye[1]
        dx = right_eye[0] - left_eye[0]
        angle = np.degrees(np.arctan2(dy, dx))
        
        # 人脸中心（双眼中间）
        eye_center = ((left_eye[0] + right_eye[0]) / 2, (left_eye[1] + right_eye[1]) / 2)
        
        # 计算人脸尺寸
        xs = [p.x * w for p in lm]
        ys = [p.y * h for p in lm]
        bx1, by1 = min(xs), min(ys)
        bx2, by2 = max(xs), max(ys)
        bw, bh = bx2 - bx1, by2 - by1
        
        # 旋转矩阵
        rot_mat = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
        
        # 旋转整张图
        rotated = cv2.warpAffine(frame, rot_mat, (w, h), borderValue=(0, 0, 0))
        
        # 从旋转图裁剪人脸（加30% padding）
        pad = int(max(bw, bh) * 0.3)
        cx1 = max(0, int(bx1 - pad))
        cy1 = max(0, int(by1 - pad))
        cx2 = min(w, int(bx2 + pad))
        cy2 = min(h, int(by2 + pad))
        
        crop = rotated[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None, None
        
        # 标准化到64x64（FER+输入要求）
        aligned = cv2.resize(crop, (64, 64))
        
        return aligned, (int(bx1), int(by1), int(bx2), int(by2))


# ========== FER+推理 ==========
class EmotionDetector:
    def __init__(self, model_path):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.labels = LABELS
        print(f"[OK] FER+: {os.path.basename(model_path)}")

    def predict(self, aligned_bgr):
        """aligned_bgr: 已对齐的64x64人脸"""
        try:
            gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)
            blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
            self.net.setInput(blob)
            scores = self.net.forward()[0]
            probs = softmax(scores)
            cls = int(np.argmax(probs))
            return self.labels[cls], float(probs[cls])
        except Exception as e:
            print(f"[ERR] predict: {e}")
            return "neutral", 0.0


# ========== 时间平滑（L3） ==========
class EmotionSmoother:
    def __init__(self, window_size=10):
        self.window = deque(maxlen=window_size)
        
    def update(self, label, conf):
        self.window.append((label, conf))
        if not self.window:
            return "neutral", 0.0
        
        # majority vote（计票）
        counts = {}
        for lbl, _ in self.window:
            counts[lbl] = counts.get(lbl, 0) + 1
        
        # 选得票最多的
        sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
        best_label = sorted_counts[0][0]
        
        # 对这个标签求平均置信度
        best_confs = [c for l, c in self.window if l == best_label]
        avg_conf = np.mean(best_confs)
        
        return best_label, float(avg_conf)


# ========== 主处理器（架构重构） ==========
class Processor:
    def __init__(self, src):
        self.src = src
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not self.cap.isOpened():
            print(f"[ERR] cam: {src}")
            self.running = False
            return
        
        print(f"[OK] cam: {src}")
        self.aligner = FaceAligner()
        self.emotion = EmotionDetector(MODEL_PATH)
        self.smoother = EmotionSmoother(window_size=10)
        
        # 架构：Queue + 锁
        self.frame_queue = Queue(maxsize=3)
        self.lock = threading.Lock()
        self.jpeg = None
        self.box = None
        self.label = "neutral"
        self.conf = 0.0
        self.running = True
        
        # 启动线程
        threading.Thread(target=self._grab, daemon=True).start()
        threading.Thread(target=self._work, daemon=True).start()

    def _grab(self):
        """采集线程：只负责拿帧，不做推理"""
        rt = 0
        while self.running:
            ok, f = self.cap.read()
            if not ok:
                self.cap.release()
                now = time.time()
                if rt == 0: rt = now
                elif now - rt >= 3:
                    rt = 0
                    self.src = (LOCAL_CAMERA if self.src == IP_CAMERA_URL
                                else IP_CAMERA_URL)
                    self.cap = cv2.VideoCapture(self.src)
                    time.sleep(0.5)
                else:
                    time.sleep(0.5)
                continue
            rt = 0
            
            # 入队，满了就丢旧帧
            if self.frame_queue.full():
                try: self.frame_queue.get_nowait()
                except: pass
            self.frame_queue.put(f)
            time.sleep(0.01)

    def _work(self):
        """推理线程：从队列拿帧，每3帧推理一次"""
        frame_counter = 0
        last_render = None
        
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=0.1)
            except:
                continue
                
            frame_counter += 1
            
            # 每3帧推理一次，节流！
            should_infer = (frame_counter % 3 == 0)
            
            aligned = None
            box = None
            
            if should_infer:
                aligned, box = self.aligner.align(frame)
            
            with self.lock:
                if aligned is not None:
                    label, conf = self.emotion.predict(aligned)
                    self.label, self.conf = self.smoother.update(label, conf)
                    self.box = box
                last_render = frame
            
            if last_render is not None:
                self._render(last_render)

    def _render(self, frame):
        try:
            d = frame.copy()
            if self.box:
                x1, y1, x2, y2 = self.box
                cv2.rectangle(d, (x1, y1), (x2, y2), (0, 200, 255), 2)
                txt = f"{self.label} ({self.conf:.0%})"
                tw, th = cv2.getTextSize(
                    txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                cv2.rectangle(d, (x1, y1 - th - 8),
                            (x1 + tw + 4, y1), (0, 200, 255), -1)
                cv2.putText(d, txt, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (255, 255, 255), 2)
            ok, buf = cv2.imencode(".jpg", d, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                self.jpeg = buf.tobytes()
        except Exception as e:
            print(f"[ERR] render: {e}")

    def stop(self):
        self.running = False
        self.cap.release()


def init():
    global g_processor
    if g_processor:
        g_processor.stop()
        time.sleep(0.3)
    g_processor = Processor(g_camera_src)


@app.route("/switch_camera", methods=["POST"])
def switch_cam():
    global g_camera_src
    d = request.get_json() or {}
    c = d.get("cam", "")
    if c == "ip":
        g_camera_src = IP_CAMERA_URL
    elif c == "local":
        g_camera_src = LOCAL_CAMERA
    else:
        return jsonify(code=400, msg="invalid")
    init()
    return jsonify(code=200, msg="switched")


@app.route("/video_feed")
def video_feed():
    def gen():
        while True:
            if g_processor and g_processor.jpeg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + g_processor.jpeg + b"\r\n")
            time.sleep(0.033)
    return Response(gen(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/get_emotion")
def get_emotion():
    if g_processor:
        return jsonify(emotion=g_processor.label,
                       confidence=g_processor.conf)
    return jsonify(emotion="neutral", confidence=0)


@app.route("/")
def index():
    html_path = os.path.join(SCRIPT_DIR, "nemo.html")
    if os.path.exists(html_path):
        return open(html_path, encoding="utf-8").read()
    return "<h1>nemo.html not found</h1>"


if __name__ == "__main__":
    try:
        init()
        print("[RUN] http://127.0.0.1:5000")
        app.run(host="127.0.0.1", port=5000,
                debug=False, use_reloader=False)
    except Exception as e:
        print("=" * 50)
        tb.print_exc()
        print("=" * 50)
