import os, sys, traceback as tb
from queue import Queue
import cv2, time, threading
import numpy as np
import mediapipe as mp
from flask import Flask, jsonify, Response

app = Flask(__name__)

LOCAL_CAMERA = 0
g_camera_src = LOCAL_CAMERA
g_processor = None


class Processor:
    def __init__(self, src):
        self.src = src
        # 关键：DirectShow 后端 + 缓冲区设为1，降低延迟
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            print(f"[ERR] 摄像头打开失败: {src}")
            self.running = False
            return

        print(f"[OK] 摄像头: {src}")

        # MediaPipe FaceMesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # 🔥 关键：预热！在循环外完成 TFLite 初始化，避免阻塞
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        _ = self.face_mesh.process(cv2.cvtColor(dummy, cv2.COLOR_BGR2RGB))
        print("[OK] MediaPipe 预热完成")

        # 6点 3D 面部模型（单位：厘米，相对比例正确即可）
        self.face_3d = np.array([
            [0.0,  0.0,  0.0],    # 鼻尖 1
            [-2.2, 1.7, -0.5],    # 左眼外角 33
            [2.2,  1.7, -0.5],    # 右眼外角 263
            [-1.5, -1.0, -0.5],   # 左嘴角 61
            [1.5, -1.0, -0.5],    # 右嘴角 291
            [0.0, -3.3, -1.0]     # 下巴 152
        ], dtype=np.float64)
        self.lm_indices = [1, 33, 263, 61, 291, 152]

        # 多线程架构
        self.frame_queue = Queue(maxsize=3)
        self.lock = threading.Lock()
        self.jpeg = None
        self.running = True

        self.pitch = 0.0
        self.yaw = 0.0
        self.roll = 0.0

        threading.Thread(target=self._grab, daemon=True).start()
        threading.Thread(target=self._work, daemon=True).start()

    def _grab(self):
        """采集线程：只读帧，入队"""
        rt = 0
        while self.running:
            ok, f = self.cap.read()
            if not ok:
                self.cap.release()
                now = time.time()
                if rt == 0:
                    rt = now
                elif now - rt >= 3:
                    rt = 0
                    self.cap = cv2.VideoCapture(self.src, cv2.CAP_DSHOW)
                    time.sleep(0.5)
                else:
                    time.sleep(0.5)
                continue
            rt = 0
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except Exception:
                    pass
            self.frame_queue.put(f)
            time.sleep(0.01)

    def _get_head_pose(self, face_landmarks, w, h):
        """solvePnP 解算头部姿态"""
        face_2d = []
        for idx in self.lm_indices:
            lm = face_landmarks.landmark[idx]
            face_2d.append([lm.x * w, lm.y * h])
        face_2d = np.array(face_2d, dtype=np.float64)

        focal_length = w
        cam_matrix = np.array([
            [focal_length, 0, w / 2],
            [0, focal_length, h / 2],
            [0, 0, 1]
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1))

        success, rvec, tvec = cv2.solvePnP(
            self.face_3d, face_2d, cam_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )
        if not success:
            return None, None, None

        rmat, _ = cv2.Rodrigues(rvec)
        yaw = np.arctan2(rmat[1][0], rmat[0][0]) * 180 / np.pi
        pitch = np.arctan2(-rmat[2][0], np.sqrt(rmat[2][1]**2 + rmat[2][2]**2)) * 180 / np.pi
        roll = np.arctan2(rmat[2][1], rmat[2][2]) * 180 / np.pi

        def norm(a):
            while a > 180:
                a -= 360
            while a < -180:
                a += 360
            return a

        return norm(pitch), norm(yaw), norm(roll)

    def _work(self):
        """推理线程：每2帧做一次头部姿态，渲染后编码为 JPEG"""
        frame_counter = 0
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=0.1)
            except Exception:
                continue

            frame_counter += 1
            h, w = frame.shape[:2]

            # 每2帧推理一次，节流
            if frame_counter % 2 == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self.face_mesh.process(rgb)

                if result.multi_face_landmarks:
                    p, y, r = self._get_head_pose(result.multi_face_landmarks[0], w, h)
                    if p is not None:
                        with self.lock:
                            self.pitch, self.yaw, self.roll = p, y, r

            # 读取当前姿态（带锁）
            with self.lock:
                p, y, r = self.pitch, self.yaw, self.roll

            # 渲染到画面
            d = frame.copy()
            text = f"Pitch:{p:.0f}  Yaw:{y:.0f}  Roll:{r:.0f}"
            cv2.putText(d, text, (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

            # 画一个参考坐标轴（可选，直观显示朝向）
            # 这里简化为文字，避免遮挡

            ok, buf = cv2.imencode(".jpg", d, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                with self.lock:
                    self.jpeg = buf.tobytes()

    def stop(self):
        self.running = False
        self.cap.release()


def init():
    global g_processor
    if g_processor:
        g_processor.stop()
        time.sleep(0.3)
    g_processor = Processor(g_camera_src)


@app.route("/video_feed")
def video_feed():
    def gen():
        while True:
            if g_processor and g_processor.jpeg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + g_processor.jpeg + b"\r\n")
            time.sleep(0.033)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/get_pose")
def get_pose():
    if g_processor:
        with g_processor.lock:
            return jsonify(
                pitch=g_processor.pitch,
                yaw=g_processor.yaw,
                roll=g_processor.roll
            )
    return jsonify(pitch=0, yaw=0, roll=0)


@app.route("/")
def index():
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>头部姿态估计</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9;
               text-align: center; margin: 0; padding: 30px; }
        h1 { color: #58a6ff; margin-bottom: 20px; }
        #box { display: inline-block; border: 2px solid #30363d; border-radius: 12px;
               overflow: hidden; background: #161b22; }
        img { display: block; width: 640px; height: 480px; object-fit: cover; }
        #info { margin-top: 20px; font-size: 1.6em; font-family: monospace; }
        .tag { color: #8b949e; }
        .val { color: #3fb950; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🎯 头部姿态估计（Web 版）</h1>
    <div id="box">
        <img src="/video_feed" alt="video stream">
    </div>
    <div id="info">
        <span class="tag">Pitch:</span> <span class="val" id="p">--</span>° &nbsp;&nbsp;
        <span class="tag">Yaw:</span>   <span class="val" id="y">--</span>° &nbsp;&nbsp;
        <span class="tag">Roll:</span>  <span class="val" id="r">--</span>°
    </div>
    <script>
        async function poll() {
            try {
                const res = await fetch('/get_pose');
                const d = await res.json();
                document.getElementById('p').textContent = d.pitch.toFixed(1);
                document.getElementById('y').textContent = d.yaw.toFixed(1);
                document.getElementById('r').textContent = d.roll.toFixed(1);
            } catch(e) {}
            setTimeout(poll, 80);
        }
        poll();
    </script>
</body>
</html>"""


if __name__ == "__main__":
    print("=" * 50)
    print("  头部姿态估计 —— Web 流式版本")
    print("  ❌ 无 cv2.imshow  |  ✅ 浏览器查看")
    print("=" * 50)
    try:
        init()
        print("[RUN] 打开浏览器访问: http://127.0.0.1:5000")
        app.run(host="127.0.0.1", port=5000,
                debug=False, use_reloader=False, threaded=True)
    except Exception:
        tb.print_exc()