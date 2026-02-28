# -*- coding: utf-8 -*-
"""
地面投影交互系统 - 基础版
功能：显示摄像头画面 + 拖动四边形顶点 + 显示矫正后的16:9画面
"""

import cv2
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify
import threading
import time

app = Flask(__name__)

# 全局状态
state = {
    # 四边形顶点（归一化坐标 0-1）
    "corners": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
    # 透视变换矩阵
    "matrix": None
}

# 摄像头
cap = None
frame = None
lock = threading.Lock()

def camera_loop():
    """摄像头采集线程"""
    global frame, cap
    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    cap.set(3, 640)
    cap.set(4, 480)
    
    while True:
        ret, f = cap.read()
        if ret:
            f = cv2.flip(f, 1)  # 镜像
            with lock:
                frame = f.copy()
        time.sleep(0.01)

threading.Thread(target=camera_loop, daemon=True).start()

# HTML页面
HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>摄像头校准</title>
    <style>
        body {
            margin: 0;
            padding: 20px;
            background: #1a1a1a;
            color: #fff;
            font-family: sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }
        h1 { margin-bottom: 20px; }
        .video-container {
            position: relative;
            margin-bottom: 20px;
        }
        #video {
            border: 2px solid #333;
        }
        #canvas {
            position: absolute;
            top: 0;
            left: 0;
            cursor: crosshair;
        }
        .hint {
            color: #888;
            margin-bottom: 10px;
            font-size: 14px;
        }
        #corrected {
            border: 2px solid #33B555;
        }
        .label {
            margin: 10px 0;
            font-size: 14px;
            color: #aaa;
        }
    </style>
</head>
<body>
    <h1>摄像头校准</h1>
    <p class="hint">拖动青色圆点调整四边形，框选需要矫正的区域</p>
    
    <div class="video-container">
        <img id="video" src="/video_feed">
        <canvas id="canvas"></canvas>
    </div>
    
    <p class="label">↓ 矫正后的16:9画面 ↓</p>
    <img id="corrected" src="/corrected_feed">

    <script>
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        
        let corners = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]];
        let dragging = -1;
        let isDown = false;

        function init() {
            fetch('/api/corners').then(r => r.json()).then(d => {
                corners = d.corners;
            });
            resize();
            requestAnimationFrame(draw);
        }

        function resize() {
            canvas.width = video.clientWidth;
            canvas.height = video.clientHeight;
        }
        video.onload = resize;
        window.onresize = resize;
        setTimeout(resize, 500);

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const w = canvas.width, h = canvas.height;

            // 画四边形
            ctx.strokeStyle = '#00e5ff';
            ctx.lineWidth = 3;
            ctx.beginPath();
            corners.forEach((p, i) => {
                const x = p[0] * w, y = p[1] * h;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.closePath();
            ctx.stroke();

            // 填充半透明
            ctx.fillStyle = 'rgba(0, 229, 255, 0.1)';
            ctx.fill();

            // 画顶点
            corners.forEach((p, i) => {
                const x = p[0] * w, y = p[1] * h;
                ctx.beginPath();
                ctx.arc(x, y, 12, 0, Math.PI * 2);
                ctx.fillStyle = '#00e5ff';
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2;
                ctx.stroke();
                
                // 编号
                ctx.fillStyle = '#000';
                ctx.font = 'bold 12px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(i + 1, x, y);
            });

            requestAnimationFrame(draw);
        }

        function getPos(e) {
            const rect = canvas.getBoundingClientRect();
            return {
                x: (e.clientX - rect.left) / canvas.width,
                y: (e.clientY - rect.top) / canvas.height
            };
        }

        canvas.onmousedown = (e) => {
            const pos = getPos(e);
            for (let i = 0; i < corners.length; i++) {
                const d = Math.hypot(corners[i][0] - pos.x, corners[i][1] - pos.y);
                if (d < 0.05) {
                    dragging = i;
                    isDown = true;
                    break;
                }
            }
        };

        canvas.onmousemove = (e) => {
            if (!isDown || dragging < 0) return;
            const pos = getPos(e);
            corners[dragging] = [
                Math.max(0, Math.min(1, pos.x)),
                Math.max(0, Math.min(1, pos.y))
            ];
        };

        canvas.onmouseup = () => {
            if (isDown) {
                save();
            }
            isDown = false;
            dragging = -1;
        };

        canvas.onmouseleave = () => {
            isDown = false;
            dragging = -1;
        };

        function save() {
            fetch('/api/corners', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({corners: corners})
            });
        }

        setTimeout(init, 1000);
    </script>
</body>
</html>
"""

@app.route('/')
@app.route('/admin')
def admin():
    return render_template_string(HTML)

@app.route('/video_feed')
def video_feed():
    def gen():
        while True:
            with lock:
                if frame is not None:
                    # 绘制顶点
                    f = frame.copy()
                    h, w = f.shape[:2]
                    pts = np.array([[int(c[0]*w), int(c[1]*h)] for c in state["corners"]], np.int32)
                    cv2.polylines(f, [pts], True, (0, 229, 255), 2)
                    for i, c in enumerate(state["corners"]):
                        x, y = int(c[0]*w), int(c[1]*h)
                        cv2.circle(f, (x, y), 8, (0, 229, 255), -1)
                        cv2.putText(f, str(i+1), (x-5, y+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)
                    _, buf = cv2.imencode('.jpg', f)
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/corrected_feed')
def corrected_feed():
    def gen():
        while True:
            with lock:
                if frame is not None and state["matrix"] is not None:
                    try:
                        # 透视变换到16:9 (640x360)
                        corrected = cv2.warpPerspective(frame, state["matrix"], (640, 360))
                        _, buf = cv2.imencode('.jpg', corrected)
                        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
                    except:
                        pass
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/corners', methods=['GET', 'POST'])
def api_corners():
    if request.method == 'POST':
        data = request.json
        state["corners"] = data["corners"]
        # 更新透视变换矩阵
        update_matrix()
        return jsonify({"ok": True})
    return jsonify({"corners": state["corners"]})

def update_matrix():
    """计算透视变换矩阵"""
    global frame
    if frame is None:
        return
    h, w = frame.shape[:2]
    src = np.array([[c[0]*w, c[1]*h] for c in state["corners"]], dtype=np.float32)
    dst = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], dtype=np.float32)
    state["matrix"] = cv2.getPerspectiveTransform(src, dst)
    print("透视矩阵已更新")

# 延迟初始化矩阵
def delayed_init():
    time.sleep(2)
    update_matrix()
threading.Thread(target=delayed_init, daemon=True).start()

if __name__ == '__main__':
    print("=" * 50)
    print("访问: http://127.0.0.1:5000/admin")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
