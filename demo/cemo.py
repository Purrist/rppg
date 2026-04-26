import cv2
import numpy as np
import sys
import traceback
import os
import threading
import time
from queue import Queue
from collections import deque
import mediapipe as mp

# ===================== FER+ ONNX 模型 =====================

class FerPlusDetector:
    def __init__(self, model_path):
        """加载 FER+ ONNX 模型"""
        try:
            self.net = cv2.dnn.readNetFromONNX(model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.labels = ['neutral', 'happiness', 'surprise', 'sadness', 'anger', 'disgust', 'fear', 'contempt']
            print(f"✓ FER+ 模型加载成功: {os.path.basename(model_path)}")
        except Exception as e:
            print(f"❌ FER+ 模型加载失败: {e}")
            raise

    def predict(self, face_bgr):
        """
        输入: 已裁剪的人脸 (任意大小)
        输出: (label, confidence)
        """
        try:
            # 转灰度 + resize 到 64x64 (FER+ 要求)
            gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (64, 64))
            
            # 转 blob
            blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
            self.net.setInput(blob)
            scores = self.net.forward()[0]
            
            # softmax
            probs = self._softmax(scores)
            
            # 激进 neutral 惩罚 (如 emo.py)
            probs[0] *= 0.6
            probs[1] *= 0.85
            probs[3] *= 1.15
            probs[4] *= 0.85
            probs = probs / probs.sum()
            
            cls = int(np.argmax(probs))
            return self.labels[cls], float(probs[cls])
        except Exception as e:
            print(f"FER+ 推理错误: {e}")
            return "neutral", 0.0

    @staticmethod
    def _softmax(x):
        e = np.exp(x - np.max(x))
        return e / e.sum()


# ===================== 人脸检测 (Haar Cascade) =====================

class FaceDetector:
    """同 emo.py 的人脸检测器"""
    def __init__(self):
        data_dir = cv2.data.haarcascades
        self.frontal = cv2.CascadeClassifier(
            data_dir + "haarcascade_frontalface_default.xml")
        self.frontal_alt2 = cv2.CascadeClassifier(
            data_dir + "haarcascade_frontalface_alt2.xml")
        self.profile = cv2.CascadeClassifier(
            data_dir + "haarcascade_profileface.xml")
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._last_rotate_time = 0

    def detect(self, frame, no_face_count=0):
        """检测人脸"""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = self.clahe.apply(gray)

        boxes = []

        # 正脸检测
        for cascade in [self.frontal_alt2, self.frontal]:
            if cascade.empty():
                continue
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(50, 50))
            for (x, y, bw, bh) in faces:
                boxes.append((x, y, x + bw, y + bh))

        if boxes:
            return self._nms(boxes)

        # 侧脸检测
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

        # 旋转检测 (节流)
        if no_face_count >= 1 and (time.time() - self._last_rotate_time > 0.3):
            self._last_rotate_time = time.time()
            boxes = self._rotate_detect(gray, w, h)

        return self._nms(boxes)

    def _rotate_detect(self, gray, w, h):
        """旋转角度的人脸检测"""
        scale = min(1.0, 480.0 / w)
        sw, sh = int(w * scale), int(h * scale)
        small = cv2.resize(gray, (sw, sh))

        boxes = []
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

        return boxes

    @staticmethod
    def _nms(boxes, iou_thresh=0.35):
        """非极大值抑制"""
        if not boxes:
            return []
        boxes = list(boxes)
        boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
        keep = []
        while boxes:
            best = boxes.pop(0)
            keep.append(best)
            boxes = [b for b in boxes if FaceDetector._iou(best, b) < iou_thresh]
        return keep

    @staticmethod
    def _iou(a, b):
        x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
        x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = ((a[2] - a[0]) * (a[3] - a[1])
                 + (b[2] - b[0]) * (b[3] - b[1]) - inter)
        return inter / (union + 1e-6)


# ===================== 头部姿态估计 (MediaPipe) =====================

class HeadPoseEstimator:
    """用 MediaPipe FaceMesh 估计头部姿态"""
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        print("✓ MediaPipe FaceMesh 初始化成功")
    
    def estimate(self, frame):
        """
        估计头部姿态
        返回: (pitch, yaw, roll, pose_label)
        """
        try:
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self.face_mesh.process(rgb)
            
            if not result.multi_face_landmarks:
                return 0, 0, 0, "未检测"
            
            lm = result.multi_face_landmarks[0].landmark
            
            # 6 个关键点 (同 test.py)
            face_3d = np.array([
                [0.0,  0.0,  0.0],    # 鼻尖 (1)
                [-2.2, 1.7, -0.5],    # 左眼外角 (33)
                [2.2,  1.7, -0.5],    # 右眼外角 (263)
                [-1.5, -1.0, -0.5],   # 左嘴角 (61)
                [1.5, -1.0, -0.5],    # 右嘴角 (291)
                [0.0, -3.3, -1.0]     # 下巴 (152)
            ], dtype=np.float64)
            
            lm_indices = [1, 33, 263, 61, 291, 152]
            face_2d = np.array([
                [lm[idx].x * w, lm[idx].y * h] for idx in lm_indices
            ], dtype=np.float64)
            
            # 相机矩阵
            focal_length = w
            cam_matrix = np.array([
                [focal_length, 0, w / 2],
                [0, focal_length, h / 2],
                [0, 0, 1]
            ], dtype=np.float64)
            dist_coeffs = np.zeros((4, 1))
            
            # solvePnP
            success, rvec, tvec = cv2.solvePnP(
                face_3d, face_2d, cam_matrix, dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            
            if not success:
                return 0, 0, 0, "计算失败"
            
            # 转欧拉角
            rmat, _ = cv2.Rodrigues(rvec)
            yaw = np.arctan2(rmat[1][0], rmat[0][0]) * 180 / np.pi
            pitch = np.arctan2(-rmat[2][0], np.sqrt(rmat[2][1]**2 + rmat[2][2]**2)) * 180 / np.pi
            roll = np.arctan2(rmat[2][1], rmat[2][2]) * 180 / np.pi
            
            # 标准化
            def norm(a):
                while a > 180: a -= 360
                while a < -180: a += 360
                return a
            
            pitch = norm(pitch)
            yaw = norm(yaw)
            roll = norm(roll)
            
            # 判断姿态
            if abs(yaw) > 25:
                pose = "侧脸右" if yaw > 0 else "侧脸左"
            elif pitch > 20:
                pose = "抬头"
            elif pitch < -20:
                pose = "低头"
            else:
                pose = "正脸"
            
            return pitch, yaw, roll, pose
            
        except Exception as e:
            print(f"头部姿态估计失败: {e}")
            return 0, 0, 0, "错误"


# ===================== 视频处理器 =====================

class VideoProcessor:
    def __init__(self, src, fer_detector, face_detector, pose_estimator):
        self.src = src
        self.fer = fer_detector
        self.face_det = face_detector
        self.pose_est = pose_estimator
        
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not self.cap.isOpened():
            print(f"❌ 摄像头打开失败: {src}")
            self.running = False
            return
        
        print(f"✓ 摄像头已打开: {src}")
        
        self.frame_queue = Queue(maxsize=2)
        self.lock = threading.Lock()
        self.jpeg = None
        
        self.emotion = "neutral"
        self.confidence = 0.0
        self.face_box = None
        self.pose = "未检测"
        self.pitch = 0.0
        self.yaw = 0.0
        self.roll = 0.0
        
        self._stab_emotion = "neutral"
        self._stab_conf = 0.0
        self._stab_cnt = 0
        self._MIN_STABLE = 2
        self._no_face_count = 0
        
        self.running = True
        
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._process_loop, daemon=True).start()
    
    def _capture_loop(self):
        """采集线程"""
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
                    print("⚠️ 重新连接摄像头...")
                    self.cap = cv2.VideoCapture(self.src)
                    time.sleep(0.5)
                else:
                    time.sleep(0.5)
                continue
            
            retry_timer = 0
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except:
                    pass
            self.frame_queue.put(frame)
            time.sleep(0.01)
    
    def _process_loop(self):
        """处理线程"""
        frame_counter = 0
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=0.5)
            except:
                continue
            
            frame_counter += 1
            h, w = frame.shape[:2]
            
            # 检测人脸
            faces = self.face_det.detect(frame, self._no_face_count)
            
            if len(faces) == 0:
                self._no_face_count += 1
                self._stab_cnt = 0
                self._stab_emotion = "neutral"
                self._stab_conf = 0.0
                with self.lock:
                    self.face_box = None
                    self.emotion = "未检测"
                    self.confidence = 0.0
                    self.pose = "未检测"
            else:
                self._no_face_count = 0
                
                # 最大的人脸
                best = max(faces, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
                x1, y1, x2, y2 = best
                
                # 添加 padding
                bw, bh = x2 - x1, y2 - y1
                pad = int(max(bw, bh) * 0.3)
                cx1 = max(0, x1 - pad)
                cy1 = max(0, y1 - pad)
                cx2 = min(w, x2 + pad)
                cy2 = min(h, y2 + pad)
                
                crop = frame[cy1:cy2, cx1:cx2]
                
                if crop.size > 0:
                    # FER+ 推理
                    label, conf = self.fer.predict(crop)
                    
                    # 稳定性检查 (同 emo.py)
                    if label == self._stab_emotion:
                        self._stab_cnt += 1
                        self._stab_conf = 0.5 * conf + 0.5 * self._stab_conf
                    else:
                        self._stab_emotion = label
                        self._stab_conf = conf
                        self._stab_cnt = 1
                    
                    # 头部姿态
                    pitch, yaw, roll, pose = self.pose_est.estimate(frame)
                    
                    with self.lock:
                        if self._stab_cnt >= self._MIN_STABLE:
                            self.emotion = self._stab_emotion
                            self.confidence = self._stab_conf
                        else:
                            self.emotion = label
                            self.confidence = conf
                        
                        self.face_box = (cx1, cy1, cx2, cy2)
                        self.pitch = pitch
                        self.yaw = yaw
                        self.roll = roll
                        self.pose = pose
            
            self._render(frame)
    
    def _render(self, frame):
        """渲染"""
        try:
            d = frame.copy()
            with self.lock:
                if self.face_box:
                    x1, y1, x2, y2 = self.face_box
                    cv2.rectangle(d, (x1, y1), (x2, y2), (0, 200, 255), 2)
                    
                    emoji_map = {
                        'neutral': '😐', 'happiness': '😊', 'surprise': '😲',
                        'sadness': '😢', 'anger': '😠', 'disgust': '🤢',
                        'fear': '😨', 'contempt': '🤨'
                    }
                    emoji = emoji_map.get(self.emotion, '🤔')
                    
                    text = f"{emoji} {self.emotion.upper()} ({self.confidence:.0%}) | {self.pose}"
                    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                    cv2.rectangle(d, (x1, y1 - th - 8), (x1 + tw + 4, y1), (0, 200, 255), -1)
                    cv2.putText(d, text, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                    
                    # 角度
                    angle_text = f"P:{self.pitch:.0f}° Y:{self.yaw:.0f}° R:{self.roll:.0f}°"
                    cv2.putText(d, angle_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            ok, buf = cv2.imencode('.jpg', d, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                with self.lock:
                    self.jpeg = buf.tobytes()
        except Exception as e:
            print(f"渲染错误: {e}")
    
    def stop(self):
        self.running = False
        self.cap.release()


# ===================== Flask 应用 =====================

from flask import Flask, Response, jsonify
from flask_cors import CORS

g_processor = None

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    @app.route('/')
    def index():
        return get_html_content()
    
    @app.route('/video_feed')
    def video_feed():
        def gen():
            while True:
                if g_processor and g_processor.jpeg:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n"
                           + g_processor.jpeg + b"\r\n")
                time.sleep(0.033)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")
    
    @app.route('/get_emotion')
    def get_emotion():
        if g_processor:
            with g_processor.lock:
                return jsonify(
                    emotion=g_processor.emotion,
                    confidence=g_processor.confidence,
                    pose=g_processor.pose,
                    pitch=g_processor.pitch,
                    yaw=g_processor.yaw,
                    roll=g_processor.roll
                )
        return jsonify(emotion="neutral", confidence=0.0, pose="未检测", pitch=0, yaw=0, roll=0)
    
    return app


def get_html_content():
    return '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🎭 情绪 + 头部姿态识别</title>
        <style>
            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #fff;
                text-align: center;
                margin: 0;
                padding: 20px;
                font-family: 'Segoe UI', sans-serif;
                min-height: 100vh;
            }
            .container {
                max-width: 1000px;
                margin: 0 auto;
                background: rgba(0, 0, 0, 0.7);
                border-radius: 15px;
                padding: 30px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }
            h1 { font-size: 2.5em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); }
            .subtitle { font-size: 1.1em; color: #aaa; margin-bottom: 30px; }
            #video-box {
                background: #000;
                border: 3px solid #667eea;
                border-radius: 10px;
                overflow: hidden;
                margin-bottom: 20px;
                max-width: 900px;
                margin-left: auto;
                margin-right: auto;
            }
            img { width: 100%; display: block; }
            .info-panel {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }
            .info-box {
                background: rgba(255, 255, 255, 0.1);
                padding: 20px;
                border-radius: 10px;
                border: 1px solid #667eea;
            }
            .info-box h3 { margin-top: 0; color: #58a6ff; }
            .emotion-display { font-size: 2em; font-weight: bold; margin: 10px 0; }
            .emoji { font-size: 3em; }
            .pose-display { font-size: 1.8em; color: #58a6ff; margin: 10px 0; }
            .angle-display { font-size: 1em; color: #aaa; margin-top: 10px; }
            .conf { color: #aaa; font-size: 0.8em; }
            @media (max-width: 768px) {
                .info-panel { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎭 情绪 + 头部姿态识别</h1>
            <p class="subtitle">基于 FER+ 和 MediaPipe</p>
            
            <div id="video-box">
                <img id="stream" src="/video_feed" alt="摄像头">
            </div>
            
            <div class="info-panel">
                <div class="info-box">
                    <h3>😊 情绪识别</h3>
                    <div class="emotion-display">
                        <span class="emoji">😐</span><br>
                        <span id="emotion-label">加载中...</span>
                        <div class="conf">置信度: <span id="emotion-conf">-- %</span></div>
                    </div>
                </div>
                
                <div class="info-box">
                    <h3>🎯 头部姿态</h3>
                    <div class="pose-display">
                        <span id="pose-label">未检测</span>
                    </div>
                    <div class="angle-display">
                        Pitch: <span id="pitch">0</span>°<br>
                        Yaw: <span id="yaw">0</span>°<br>
                        Roll: <span id="roll">0</span>°
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            const EMOJI = {
                'neutral': '😐', 'happiness': '😊', 'surprise': '😲',
                'sadness': '😢', 'anger': '😠', 'disgust': '🤢',
                'fear': '😨', 'contempt': '🤨', '未检测': '❓'
            };
            
            const POSE_EMOJI = {
                '正脸': '📍', '低头': '⬇️', '抬头': '⬆️',
                '侧脸左': '⬅️', '侧脸右': '➡️', '未检测': '❓'
            };
            
            setInterval(() => {
                fetch('/get_emotion')
                    .then(r => r.json())
                    .then(d => {
                        const emoji = EMOJI[d.emotion] || '🤔';
                        const pct = (d.confidence * 100).toFixed(1);
                        const pose_emoji = POSE_EMOJI[d.pose] || '❓';
                        
                        document.getElementById('emotion-label').textContent = d.emotion.toUpperCase();
                        document.getElementById('emotion-conf').textContent = pct;
                        document.querySelector('.emotion-display .emoji').textContent = emoji;
                        
                        document.getElementById('pose-label').innerHTML = `${pose_emoji} ${d.pose}`;
                        document.getElementById('pitch').textContent = d.pitch.toFixed(1);
                        document.getElementById('yaw').textContent = d.yaw.toFixed(1);
                        document.getElementById('roll').textContent = d.roll.toFixed(1);
                    })
                    .catch(() => {});
            }, 300);
        </script>
    </body>
    </html>
    '''


# ===================== 主程序 =====================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, required=True, help='FER+ ONNX 模型路径')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--camera', type=int, default=0)
    
    args = parser.parse_args()
    
    if not os.path.exists(args.model):
        print(f"❌ 模型文件不存在: {args.model}")
        print("\n使用方法:")
        print(f"python emotion_recognition.py --model <FER+模型路径>")
        print("\n例如:")
        print(f"python emotion_recognition.py --model emotion-ferplus-8.onnx")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("🎭 情绪 + 头部姿态识别系统")
    print("=" * 60 + "\n")
    
    try:
        print("📌 第1步: 加载 FER+ 模型...")
        fer = FerPlusDetector(args.model)
        
        print("📌 第2步: 初始化人脸检测...")
        face_det = FaceDetector()
        
        print("📌 第3步: 初始化头部姿态估计...")
        pose_est = HeadPoseEstimator()
        
        print("📌 第4步: 启动视频处理...")
        g_processor = VideoProcessor(args.camera, fer, face_det, pose_est)
        
        print("📌 第5步: 创建 Flask 应用...")
        app = create_app()
        
        print("\n" + "=" * 60)
        print("✅ 系统启动成功!")
        print("=" * 60)
        print(f"🌐 访问: http://localhost:{args.port}")
        print(f"📸 摄像头: {args.camera}")
        print(f"📦 模型: {os.path.basename(args.model)}")
        print("=" * 60)
        print("⏸️  按 Ctrl+C 停止\n")
        
        app.run(host='0.0.0.0', port=args.port, debug=False, use_reloader=False, threaded=True)
        
    except KeyboardInterrupt:
        print("\n\n❌ 已停止")
        if g_processor:
            g_processor.stop()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        sys.exit(1)