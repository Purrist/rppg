import cv2
import base64
import time
import threading
import numpy as np
import mediapipe as mp
from flask import Flask, request, jsonify
from deepface import DeepFace

app = Flask(__name__)

# ======================
# 摄像头配置
# ======================
IP_CAMERA_URL = "http://10.215.158.45:8080/video"
LOCAL_CAMERA = 0
g_camera_src = IP_CAMERA_URL
g_processor = None


# ======================
# 极速情绪检测器（MediaPipe检测 + DeepFace分类）
# ======================
class EmotionDetector:
    def __init__(self):
        # 用 MediaPipe 做人脸检测（CPU上极速，约 5ms）
        self.face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.5
        )

    def detect_emotions(self, frame):
        # 1. MediaPipe 极速定位人脸
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = frame.shape
        results = self.face_detector.process(rgb_frame)
        
        if not results.detections:
            return []

        formatted = []
        for detection in results.detections:
            bbox = detection.location_data.relative_bounding_box
            x_min = int(bbox.xmin * w)
            y_min = int(bbox.ymin * h)
            box_w = int(bbox.width * w)
            box_h = int(bbox.height * h)

            # 上下左右各扩 15% 边界，防止切得太死影响情绪判断
            pad_w = int(box_w * 0.15)
            pad_h = int(box_h * 0.15)
            x1 = max(0, x_min - pad_w)
            y1 = max(0, y_min - pad_h)
            x2 = min(w, x_min + box_w + 2 * pad_w)
            y2 = min(h, y_min + box_h + 2 * pad_h)

            # 2. 抠出纯净的人脸区域（去除背景干扰，提升准确度）
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            # 3. DeepFace 仅做情绪分类（关键：跳过内部检测，极速）
            try:
                emo_result = DeepFace.analyze(
                    img_path=face_crop,
                    actions=["emotion"],
                    enforce_detection=False,  # 核心：跳过耗时的 RetinaFace 检测
                    silent=True,
                    anti_spoofing=False,
                )
                
                # DeepFace 返回格式兼容处理
                emo_data = emo_result[0]["emotion"] if isinstance(emo_result, list) else emo_result["emotion"]
                
                # 百分制转 0~1 浮点数
                normalized_emotions = {k: v / 100.0 for k, v in emo_data.items()}
                
                formatted.append({
                    "box": [x1, y1, x2 - x1, y2 - y1],
                    "emotions": normalized_emotions,
                })
            except Exception as e:
                pass # 抠图太小等偶发错误直接跳过，避免卡线程

        return formatted


# ======================
# 摄像头 + 情绪处理器
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

        self.detector = EmotionDetector()

        self.frame_lock = threading.Lock()
        self.raw_frame = None
        self.faces = []
        self.emotions = {}
        
        # EMA 平滑算法（抗跳变）
        self.ema_alpha = 0.25    # 降到 0.25，进一步压制毛刺跳变
        self.smoothed_scores = {}

        self.running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._detect_thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._capture_thread.start()
        self._detect_thread.start()

    def _capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                print("⚠️ 摄像头断开，重连中...")
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(self.video_url)
                continue
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
                results = self.detector.detect_emotions(frame)
                self.faces = []

                if results:
                    results.sort(key=lambda r: r["box"][2] * r["box"][3], reverse=True)
                    best = results[0]
                    x, y, w, h = best["box"]
                    self.faces = [(x, y, w, h)]

                    emo_scores = best["emotions"]
                    
                    if not self.smoothed_scores:
                        self.smoothed_scores = emo_scores.copy()
                    else:
                        for k in emo_scores:
                            old_val = self.smoothed_scores.get(k, emo_scores[k])
                            self.smoothed_scores[k] = self.ema_alpha * emo_scores[k] + (1 - self.ema_alpha) * old_val
                    
                    top_emotion = max(self.smoothed_scores, key=self.smoothed_scores.get)
                    self.emotions = {
                        "emotion": top_emotion,
                        "confidence": self.smoothed_scores[top_emotion],
                    }
                else:
                    self.emotions = {"emotion": "未检测到人脸", "confidence": 0}
                    for k in self.smoothed_scores:
                        self.smoothed_scores[k] *= 0.7

            except Exception as e:
                print("❌ 检测出错:", e)

            # 因为单次分析已经从 500ms 降到 50ms，这里把等待降到 0.05，提升帧率
            time.sleep(0.05) 

    def get_ui_frame(self):
        with self.frame_lock:
            if self.raw_frame is None:
                return None
            frame = self.raw_frame.copy()

        for (x, y, w, h) in self.faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 255), 2)
            label = self.emotions.get("emotion", "")
            conf = self.emotions.get("confidence", 0)
            text = f"{label} ({conf:.0%})"
            cv2.rectangle(frame, (x, y - 30), (x + w, y), (0, 200, 255), -1)
            cv2.putText(frame, text, (x + 4, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return base64.b64encode(buffer).decode("utf-8")

    def stop(self):
        self.running = False
        self.cap.release()

    def wait_stopped(self):
        self._capture_thread.join(timeout=3)
        self._detect_thread.join(timeout=3)


# ======================
# 初始化与路由（保持不变）
# ======================
def init_processor():
    global g_processor
    if g_processor:
        g_processor.stop()
        g_processor.wait_stopped()
    g_processor = FaceProcessor(g_camera_src)

@app.route("/switch_camera", methods=["POST"])
def switch_camera():
    global g_camera_src
    data = request.get_json()
    cam_type = data.get("cam", "")
    if cam_type == "ip":
        g_camera_src = IP_CAMERA_URL
    elif cam_type == "local":
        g_camera_src = LOCAL_CAMERA
    else:
        return jsonify(code=400, msg="无效的摄像头类型")
    init_processor()
    return jsonify(code=200, msg=f"已切换到 {'IP摄像头' if cam_type == 'ip' else '本地摄像头'}")

@app.route("/get_frame")
def get_frame():
    if g_processor:
        frame_b64 = g_processor.get_ui_frame()
        if frame_b64:
            return frame_b64
    return ""

@app.route("/get_emotion")
def get_emotion():
    if g_processor:
        return jsonify(g_processor.emotions)
    return jsonify(emotion="未初始化", confidence=0)

# ======================
# 前端页面
# ======================
@app.route("/")
def index():
    return '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            body { background:#1a1a1a; color:#fff; text-align:center; margin:0; padding:20px; font-family:sans-serif; }
            button { padding:12px 24px; margin:10px; border:none; border-radius:8px; cursor:pointer; font-size:15px; transition:all 0.3s; }
            button:hover { transform:scale(1.05); }
            #btn-ip { background:#ff7222; color:#fff; }
            #btn-local { background:#22aaff; color:#fff; }
            button:disabled { opacity:0.4; cursor:not-allowed; transform:none; }
            img { max-width:800px; width:100%; border:3px solid #ff7222; border-radius:8px; }
            #emotion-display { margin-top:20px; font-size:28px; font-weight:bold; min-height:40px; }
            #toast { position:fixed; top:20px; right:20px; background:#333; color:#fff; padding:14px 24px; border-radius:8px; opacity:0; transition:opacity 0.3s; font-size:14px; pointer-events:none; }
            #toast.show { opacity:1; }
        </style>
    </head>
    <body>
        <h2>😊 实时情绪识别</h2>
        <div>
            <button id="btn-ip" onclick="switchCam('ip', this)">📡 IP摄像头</button>
            <button id="btn-local" onclick="switchCam('local', this)">💻 本地摄像头</button>
        </div>
        <br>
        <img id="live" src="" alt="等待画面...">
        <div id="emotion-display"></div>
        <div id="toast"></div>
        <script>
            const liveImg = document.getElementById("live");
            const emoDiv = document.getElementById("emotion-display");

            setInterval(() => {
                fetch("/get_frame")
                    .then(r => r.text())
                    .then(b64 => { if (b64) liveImg.src = "data:image/jpeg;base64," + b64; })
                    .catch(() => {});
            }, 200);

            setInterval(() => {
                fetch("/get_emotion")
                    .then(r => r.json())
                    .then(data => {
                        if (data.emotion && data.emotion !== "未初始化") {
                            const emojiMap = {
                                "happy": "😊", "surprise": "😲", "sad": "😢",
                                "angry": "😠", "fear": "😨", "disgust": "🤢",
                                "neutral": "😐", "未检测到人脸": "❓"
                            };
                            const emoji = emojiMap[data.emotion] || "🤔";
                            const pct = (data.confidence * 100).toFixed(0);
                            emoDiv.innerHTML = emoji + " " + data.emotion
                                + " <span style='color:#aaa;font-size:18px;'>(" + pct + "%)</span>";
                        }
                    })
                    .catch(() => {});
            }, 300);

            function switchCam(type, btn) {
                document.querySelectorAll("button").forEach(b => b.disabled = true);
                showToast("🔄 正在切换摄像头...");
                fetch("/switch_camera", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({cam: type})
                })
                .then(r => r.json())
                .then(data => {
                    showToast(data.code === 200 ? "✅ " + data.msg : "❌ 切换失败");
                })
                .catch(() => showToast("❌ 网络错误"))
                .finally(() => document.querySelectorAll("button").forEach(b => b.disabled = false));
            }

            function showToast(msg) {
                const t = document.getElementById("toast");
                t.textContent = msg; t.classList.add("show");
                clearTimeout(t._timer);
                t._timer = setTimeout(() => t.classList.remove("show"), 2500);
            }
        </script>
    </body>
    </html>
    '''

if __name__ == "__main__":
    init_processor()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
