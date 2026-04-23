import cv2
import time
import threading
import numpy as np
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ======================
# 摄像头配置
# ======================
IP_CAMERA_URL = "http://10.158.10.79:8080/video"
LOCAL_CAMERA = 0
g_camera_src = LOCAL_CAMERA
g_processor = None

ONNX_MODEL_PATH = r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\emotion-ferplus-8.onnx"

FER_LABELS = ['neutral', 'happiness', 'surprise', 'sadness',
              'anger', 'disgust', 'fear', 'contempt']

EMOJI_MAP = {
    'neutral': '😐', 'happiness': '😊', 'surprise': '😲',
    'sadness': '😢', 'anger': '😠', 'disgust': '🤢',
    'fear': '😨', 'contempt': '🤨', '未检测到人脸': '❓'
}
LABEL_ZH = {
    'neutral': '平静', 'happiness': '高兴', 'surprise': '惊讶',
    'sadness': '悲伤', 'anger': '愤怒', 'disgust': '厌恶',
    'fear': '恐惧', 'contempt': '轻蔑', '未检测到人脸': '未检测到人脸'
}


# ======================
# FER+ 推理（无 CLAHE + 直接输出 + 激进 neutral 惩罚）
# ======================
class FerPlusDetector:

    def __init__(self, model_path):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def predict(self, face_bgr):
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (64, 64))
        blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
        self.net.setInput(blob)
        scores = self.net.forward()[0]

        probs = self._softmax(scores)

        probs[0] *= 0.6
        probs[1] *= 0.85
        probs[3] *= 1.15
        probs[4] *= 0.85
        probs = probs / probs.sum()

        sorted_idx = np.argsort(probs)[::-1]
        if sorted_idx[0] == 0:
            gap = probs[0] - probs[sorted_idx[1]]
            if gap < 0.12:
                probs[0] *= 0.05
                probs = probs / probs.sum()

        cls = int(np.argmax(probs))
        return FER_LABELS[cls], float(probs[cls])

    @staticmethod
    def _softmax(x):
        e = np.exp(x - np.max(x))
        return e / e.sum()


# ======================
# 人脸检测（高质量 Haar + 人脸对齐 + CLAHE 增强）
# ======================
class FaceDetector:

    def __init__(self):
        data_dir = cv2.data.haarcascades
        self.frontal = cv2.CascadeClassifier(
            data_dir + "haarcascade_frontalface_default.xml")
        self.frontal_alt2 = cv2.CascadeClassifier(
            data_dir + "haarcascade_frontalface_alt2.xml")
        self.profile = cv2.CascadeClassifier(
            data_dir + "haarcascade_profileface.xml")
        self.eye_tree = cv2.CascadeClassifier(
            data_dir + "haarcascade_eye_tree_eyeglasses.xml")
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._last_rotate_time = 0

    def detect(self, frame, no_face_count=0):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = self.clahe.apply(gray)

        boxes = []

        for cascade in [self.frontal_alt2, self.frontal]:
            if cascade.empty():
                continue
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(50, 50))
            for (x, y, bw, bh) in faces:
                boxes.append((x, y, x + bw, y + bh))

        if boxes:
            return self._nms(boxes)

        if not self.profile.empty():
            for (x, y, bw, bh) in self.profile.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=3, minSize=(50, 50)):
                boxes.append((x, y, x + bw, y + bh))
            gray_flip = cv2.flip(gray, 1)
            for (x, y, bw, bh) in self.profile.detectMultiScale(
                    gray_flip, scaleFactor=1.1, minNeighbors=3, minSize=(50, 50)):
                boxes.append((w - x - bw, y, w - x, y + bh))

        if boxes:
            return self._nms(boxes)

        if no_face_count >= 1 and (time.time() - self._last_rotate_time > 0.3):
            self._last_rotate_time = time.time()
            boxes = self._rotate_detect(gray, w, h)

        return self._nms(boxes)

    def _rotate_detect(self, gray, w, h):
        # 缩小到 480px 做旋转检测，减少计算量
        scale = min(1.0, 480.0 / w)
        sw, sh = int(w * scale), int(h * scale)
        small = cv2.resize(gray, (sw, sh))

        boxes = []
        # ★ 降低阈值：旋转后图像有插值模糊，需要更宽松的参数
        # minNeighbors=2（允许一些误检，NMS 会清理）
        # minSize=(25,25)（缩小图里的最小尺寸）
        for angle in [-20, -15, -10, -5, 5, 10, 15, 20]:
            M = cv2.getRotationMatrix2D((sw / 2, sh / 2), angle, 1.0)
            rot = cv2.warpAffine(small, M, (sw, sh))
            M_inv = cv2.invertAffineTransform(M)

            for cascade in [self.frontal_alt2, self.frontal]:
                if cascade.empty():
                    continue
                faces = cascade.detectMultiScale(
                    rot, scaleFactor=1.08, minNeighbors=2, minSize=(25, 25))
                for (x, y, bw, bh) in faces:
                    pts = np.array([
                        [x, y], [x + bw, y],
                        [x, y + bh], [x + bw, y + bh]
                    ], dtype=np.float64)
                    pts = cv2.transform(
                        pts.reshape(1, -1, 2), M_inv).reshape(-1, 2) / scale
                    x1 = int(max(0, pts[:, 0].min()))
                    y1 = int(max(0, pts[:, 1].min()))
                    x2 = int(min(w, pts[:, 0].max()))
                    y2 = int(min(h, pts[:, 1].max()))
                    if (x2 - x1) > 30 and (y2 - y1) > 30:
                        boxes.append((x1, y1, x2, y2))

            # 侧面也要在旋转图里试
            if not self.profile.empty():
                faces = self.profile.detectMultiScale(
                    rot, scaleFactor=1.08, minNeighbors=2, minSize=(25, 25))
                for (x, y, bw, bh) in faces:
                    pts = np.array([
                        [x, y], [x + bw, y],
                        [x, y + bh], [x + bw, y + bh]
                    ], dtype=np.float64)
                    pts = cv2.transform(
                        pts.reshape(1, -1, 2), M_inv).reshape(-1, 2) / scale
                    x1 = int(max(0, pts[:, 0].min()))
                    y1 = int(max(0, pts[:, 1].min()))
                    x2 = int(min(w, pts[:, 0].max()))
                    y2 = int(min(h, pts[:, 1].max()))
                    if (x2 - x1) > 30 and (y2 - y1) > 30:
                        boxes.append((x1, y1, x2, y2))

        return boxes

    @staticmethod
    def _nms(boxes, iou_thresh=0.35):
        if not boxes:
            return []
        boxes = list(boxes)
        boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
        keep = []
        while boxes:
            best = boxes.pop(0)
            keep.append(best)
            boxes = [b for b in boxes
                     if FaceDetector._iou(best, b) < iou_thresh]
        return keep

    @staticmethod
    def _iou(a, b):
        x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
        x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = ((a[2] - a[0]) * (a[3] - a[1])
                 + (b[2] - b[0]) * (b[3] - b[1]) - inter)
        return inter / (union + 1e-6)


# ======================
# 主处理器
# ★ 改动3：旋转检测节流（最多 0.3 秒一次，不会持续卡）
# ======================
class FaceProcessor:

    def __init__(self, video_url):
        self.video_url = video_url
        self.cap = cv2.VideoCapture(video_url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            print("❌ 摄像头打开失败:", video_url)
            self.running = False
            return

        self.face_detector = FaceDetector()
        self.fer = FerPlusDetector(ONNX_MODEL_PATH)

        self.frame_lock = threading.Lock()
        self.raw_frame = None
        self.annotated_jpeg = None

        self.box = None
        self.label = "未检测到人脸"
        self.conf = 0.0

        self._stab_cnt = 0
        self._stab_label = "未检测到人脸"
        self._stab_conf = 0.0
        self._MIN_STABLE = 2
        self._no_face_count = 0
        self._sleep_mode = False
        self._sleep_check_counter = 0
        self._just_woke = False

        self.running = True
        self._t_cap = threading.Thread(target=self._capture_loop, daemon=True)
        self._t_det = threading.Thread(target=self._detect_loop, daemon=True)
        self._t_cap.start()
        self._t_det.start()

    def _capture_loop(self):
        retry_timer = 0
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                self.cap.release()
                now = time.time()
                if retry_timer == 0:
                    retry_timer = now
                elif now - retry_timer >= 3:
                    retry_timer = 0
                    if self.video_url == IP_CAMERA_URL:
                        print("⚠️ IP摄像头连接失败，切换到本地摄像头")
                        self.video_url = LOCAL_CAMERA
                    else:
                        print("⚠️ 本地摄像头失败，尝试重连IP摄像头")
                        self.video_url = IP_CAMERA_URL
                    self.cap = cv2.VideoCapture(self.video_url)
                    time.sleep(0.5)
                    continue
                else:
                    time.sleep(0.5)
                    continue
            else:
                retry_timer = 0
            with self.frame_lock:
                self.raw_frame = frame
            time.sleep(0.01)

    def _detect_loop(self):
        while self.running:
            frame = None
            with self.frame_lock:
                if self.raw_frame is not None:
                    frame = self.raw_frame.copy()
            if frame is None:
                time.sleep(0.1)
                continue

            try:
                if self._sleep_mode:
                    self._sleep_check_counter += 1
                    if self._sleep_check_counter >= 5:
                        self._sleep_check_counter = 0
                        faces = self.face_detector.detect(frame, self._no_face_count)
                        if len(faces) > 0:
                            self._sleep_mode = False
                            self._just_woke = True
                            self._no_face_count = 0
                            print("☀️ 唤醒检测模式")
                            best = max(faces, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
                            x1, y1, x2, y2 = best
                            bw, bh = x2 - x1, y2 - y1
                            pad = int(max(bw, bh) * 0.3)
                            cx1 = max(0, x1 - pad)
                            cy1 = max(0, y1 - pad)
                            cx2 = min(frame.shape[1], x2 + pad)
                            cy2 = min(frame.shape[0], y2 + pad)
                            crop = frame[cy1:cy2, cx1:cx2]
                            if crop.size > 0:
                                label, conf = self.fer.predict(crop)
                                self.label = label
                                self.conf = conf
                                self.box = (cx1, cy1, cx2, cy2)
                            self._render(frame)
                            continue
                    time.sleep(0.2)
                    self._render(frame)
                    continue

                faces = self.face_detector.detect(frame, self._no_face_count)

                if len(faces) == 0:
                    self._no_face_count += 1
                    self._stab_cnt = 0
                    self._stab_label = "未检测到人脸"
                    self._stab_conf = 0.0
                    self.box = None
                    self.label = "未检测到人脸"
                    self.conf = 0.0
                    if self._no_face_count >= 5:
                        self._sleep_mode = True
                        print("😴 进入休眠模式")
                else:
                    if self._just_woke:
                        self._just_woke = False
                    if self._sleep_mode:
                        self._sleep_mode = False
                        self._just_woke = True
                        print("☀️ 唤醒检测模式")
                    self._no_face_count = 0

                    best = max(faces, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
                    x1, y1, x2, y2 = best

                    bw, bh = x2 - x1, y2 - y1
                    pad = int(max(bw, bh) * 0.3)
                    cx1 = max(0, x1 - pad)
                    cy1 = max(0, y1 - pad)
                    cx2 = min(frame.shape[1], x2 + pad)
                    cy2 = min(frame.shape[0], y2 + pad)

                    crop = frame[cy1:cy2, cx1:cx2]
                    if crop.size > 0:
                        label, conf = self.fer.predict(crop)

                        if label == self._stab_label:
                            self._stab_cnt += 1
                            self._stab_conf = 0.5 * conf + 0.5 * self._stab_conf
                        else:
                            self._stab_label = label
                            self._stab_conf = conf
                            self._stab_cnt = 1

                        if self._stab_cnt >= self._MIN_STABLE:
                            self.label = self._stab_label
                            self.conf = self._stab_conf

                        self.box = (cx1, cy1, cx2, cy2)

            except Exception as e:
                print("❌ 检测异常:", e)
                import traceback
                traceback.print_exc()

            self._render(frame)

    def _render(self, frame):
        draw = frame.copy()
        if self.box is not None:
            x1, y1, x2, y2 = self.box
            cv2.rectangle(draw, (x1, y1), (x2, y2), (0, 200, 255), 2)
            emoji = EMOJI_MAP.get(self.label, "")
            text = f"{emoji} {self.label} ({self.conf:.0%})"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(draw, (x1, y1 - th - 8), (x1 + tw + 4, y1),
                          (0, 200, 255), -1)
            cv2.putText(draw, text, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        ok, buf = cv2.imencode('.jpg', draw, [cv2.IMWRITE_JPEG_QUALITY, 75])
        self.annotated_jpeg = buf.tobytes() if ok else None

    def stop(self):
        self.running = False
        self.cap.release()

    def wait_stopped(self):
        self._t_cap.join(timeout=3)
        self._t_det.join(timeout=3)


def init_processor():
    global g_processor
    if g_processor:
        g_processor.stop()
        g_processor.wait_stopped()
    g_processor = FaceProcessor(g_camera_src)


# ======================
# 路由
# ======================
@app.route("/switch_camera", methods=["POST"])
def switch_camera():
    global g_camera_src
    data = request.get_json() or {}
    cam = data.get("cam", "")
    if cam == "ip":
        g_camera_src = IP_CAMERA_URL
    elif cam == "local":
        g_camera_src = LOCAL_CAMERA
    else:
        return jsonify(code=400, msg="无效的摄像头类型")
    init_processor()
    return jsonify(code=200, msg=f"已切换到 {'IP摄像头' if cam == 'ip' else '本地摄像头'}")


@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            if g_processor and g_processor.annotated_jpeg:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n"
                       + g_processor.annotated_jpeg + b"\r\n")
            time.sleep(0.033)
    return Response(generate(),
                   mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/get_emotion")
def get_emotion():
    if g_processor:
        return jsonify(emotion=g_processor.label, confidence=g_processor.conf)
    return jsonify(emotion="未初始化", confidence=0)


@app.route("/")
def index():
    return '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            body { background:#111; color:#fff; text-align:center; margin:0;
                   padding:20px; font-family:system-ui,sans-serif; }
            button { padding:10px 20px; margin:8px; border:none; border-radius:6px;
                     font-size:15px; cursor:pointer; }
            #btn-ip { background:#ff7a22; color:#fff; }
            #btn-local { background:#2299ff; color:#fff; }
            button:disabled { opacity:0.35; cursor:not-allowed; }
            #live { max-width:800px; width:100%; border:3px solid #ff7a22;
                    border-radius:8px; display:block; margin:12px auto 0; }
            #emotion-display { margin-top:18px; font-size:26px;
                               font-weight:bold; min-height:36px; }
            #toast { position:fixed; top:18px; right:18px; background:#333;
                     color:#fff; padding:12px 20px; border-radius:6px; opacity:0;
                     transition:opacity 0.25s; font-size:14px; pointer-events:none; }
            #toast.show { opacity:1; }
        </style>
    </head>
    <body>
        <h2>😊 实时情绪识别</h2>
        <div>
            <button id="btn-ip" onclick="switchCam('ip',this)">📡 IP摄像头</button>
            <button id="btn-local" onclick="switchCam('local',this)">💻 本地摄像头</button>
        </div>
        <img id="live" src="/video_feed" alt="等待画面...">
        <div id="emotion-display"></div>
        <div id="toast"></div>
        <script>
            const emoDiv = document.getElementById('emotion-display');
            const EMOJI = {
                'neutral':'😐','happiness':'😊','surprise':'😲','sadness':'😢',
                'anger':'😠','disgust':'🤢','fear':'😨','contempt':'🤨',
                '未检测到人脸':'❓'
            };
            const ZH = {
                'neutral':'平静','happiness':'高兴','surprise':'惊讶','sadness':'悲伤',
                'anger':'愤怒','disgust':'厌恶','fear':'恐惧','contempt':'轻蔑',
                '未检测到人脸':'未检测到人脸'
            };
            setInterval(() => {
                fetch('/get_emotion').then(r=>r.json()).then(d => {
                    if(d.emotion && d.emotion!=='未初始化'){
                        const pct=(d.confidence*100).toFixed(0);
                        emoDiv.innerHTML = (EMOJI[d.emotion]||'🤔')+' '
                            +(ZH[d.emotion]||d.emotion)
                            +' <span style="color:#aaa;font-size:18px;">('+pct+'%)</span>';
                    }
                }).catch(()=>{});
            }, 300);
            function switchCam(type){
                document.querySelectorAll('button').forEach(b=>b.disabled=true);
                showToast('🔄 切换中...');
                fetch('/switch_camera',{
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({cam:type})
                })
                .then(r=>r.json())
                .then(d=>showToast(d.code===200?'✅ '+d.msg:'❌ 失败'))
                .catch(()=>showToast('❌ 网络错误'))
                .finally(()=>document.querySelectorAll('button').forEach(b=>b.disabled=false));
            }
            function showToast(msg){
                const t=document.getElementById('toast');
                t.textContent=msg; t.classList.add('show');
                clearTimeout(t._timer);
                t._timer=setTimeout(()=>t.classList.remove('show'),2500);
            }
        </script>
    </body>
    </html>
    '''


if __name__ == "__main__":
    print("① 正在加载模型...")
    init_processor()
    print("② 启动完成 http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
