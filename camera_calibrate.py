# -*- coding: utf-8 -*-
"""
地面投影交互系统 - 稳定版
功能：
1. Admin页面：摄像头画面 + 骨骼识别 + 拖动顶点校准
2. Projection页面：绿色圆点显示脚的位置（用于地面投影）
"""

import cv2
import mediapipe as mp
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify
import threading
import time
import queue

app = Flask(__name__)

# ============================================================================
# 全局状态
# ============================================================================
state = {
    "corners": [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]],  # 四边形顶点
    "feet_x": 640,        # 脚的X坐标（投影坐标系）
    "feet_y": 360,        # 脚的Y坐标（投影坐标系）
    "feet_detected": False,
    "matrix": None,
    "frame_count": 0
}

# ============================================================================
# 摄像头和检测处理器（单线程处理，避免竞争）
# ============================================================================
class Processor:
    def __init__(self):
        # 摄像头
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 减少缓冲，提高实时性
        
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"摄像头: {self.frame_w}x{self.frame_h}")
        
        # MediaPipe Pose
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0  # 轻量模型，更快
        )
        
        # 输出帧
        self.raw_frame = None      # 原始画面（带骨骼）
        self.corrected_frame = None  # 矫正后画面
        
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
    
    def _loop(self):
        """主处理循环"""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # 镜像
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            
            # MediaPipe检测
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb)
            
            feet_detected = False
            feet_x, feet_y = 320, 180  # 默认中心
            
            if results.pose_landmarks:
                # 绘制骨骼
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
                    mp.solutions.drawing_styles.get_default_pose_landmarks_style()
                )
                
                lm = results.pose_landmarks.landmark
                left_ankle = lm[27]   # 左脚踝
                right_ankle = lm[28]  # 右脚踝
                
                # 两只脚踝都可见
                if left_ankle.visibility > 0.5 and right_ankle.visibility > 0.5:
                    # 脚踝像素坐标
                    l_pt = (int(left_ankle.x * w), int(left_ankle.y * h))
                    r_pt = (int(right_ankle.x * w), int(right_ankle.y * h))
                    
                    # 高亮双脚
                    cv2.circle(frame, l_pt, 15, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 15, (0, 255, 0), -1)
                    cv2.line(frame, l_pt, r_pt, (0, 255, 255), 3)
                    
                    # 双脚中心
                    center = ((l_pt[0] + r_pt[0]) // 2, (l_pt[1] + r_pt[1]) // 2)
                    cv2.circle(frame, center, 10, (255, 0, 255), -1)
                    
                    # 透视变换到投影坐标
                    if state["matrix"] is not None:
                        try:
                            src_pt = np.array([[[center[0], center[1]]]], dtype=np.float32)
                            dst_pt = cv2.perspectiveTransform(src_pt, state["matrix"])[0][0]
                            feet_x, feet_y = int(dst_pt[0]), int(dst_pt[1])
                            feet_detected = True
                        except:
                            pass
            
            # 更新状态
            state["feet_x"] = feet_x
            state["feet_y"] = feet_y
            state["feet_detected"] = feet_detected
            state["frame_count"] += 1
            
            # 绘制校准框
            pts = np.array([[int(c[0]*w), int(c[1]*h)] for c in state["corners"]], np.int32)
            cv2.polylines(frame, [pts], True, (255, 0, 0), 2)
            for i, c in enumerate(state["corners"]):
                x, y = int(c[0]*w), int(c[1]*h)
                cv2.circle(frame, (x, y), 10, (255, 0, 0), -1)
                cv2.putText(frame, str(i+1), (x-6, y+4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
            
            # 生成矫正后画面
            corrected = None
            if state["matrix"] is not None:
                try:
                    corrected = cv2.warpPerspective(frame, state["matrix"], (640, 360))
                except:
                    corrected = np.zeros((360, 640, 3), dtype=np.uint8)
                    corrected[:] = 255
            else:
                corrected = np.zeros((360, 640, 3), dtype=np.uint8)
                corrected[:] = 255
            
            # 保存帧
            self.raw_frame = frame
            self.corrected_frame = corrected
            
            time.sleep(0.01)  # 控制CPU占用
    
    def get_raw_jpeg(self):
        if self.raw_frame is None:
            return None
        _, buf = cv2.imencode('.jpg', self.raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def get_corrected_jpeg(self):
        if self.corrected_frame is None:
            return None
        _, buf = cv2.imencode('.jpg', self.corrected_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def update_matrix(self):
        """更新透视变换矩阵"""
        if self.raw_frame is None:
            return
        h, w = self.raw_frame.shape[:2]
        src = np.array([[c[0]*w, c[1]*h] for c in state["corners"]], dtype=np.float32)
        dst = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], dtype=np.float32)
        state["matrix"] = cv2.getPerspectiveTransform(src, dst)
        print("透视矩阵已更新")

# 创建处理器
processor = Processor()

# 延迟初始化矩阵
def delayed_init():
    time.sleep(2)
    processor.update_matrix()
threading.Thread(target=delayed_init, daemon=True).start()

# ============================================================================
# HTML模板
# ============================================================================

# Admin页面 - 白底
HTML_ADMIN = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Admin - 校准管理</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #fff;
            color: #333;
            font-family: 'Microsoft YaHei', sans-serif;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }
        h1 { margin-bottom: 10px; font-size: 24px; }
        .hint { color: #666; margin-bottom: 15px; }
        .container { position: relative; margin-bottom: 20px; }
        #video { border: 2px solid #333; display: block; }
        #canvas { position: absolute; top: 0; left: 0; cursor: crosshair; }
        .label { color: #666; margin: 10px 0; font-size: 14px; }
        #corrected { border: 2px solid #33B555; display: block; }
        .status {
            margin-top: 15px;
            padding: 10px 20px;
            background: #f5f5f5;
            border-radius: 8px;
            font-size: 14px;
        }
        .status span { font-weight: bold; }
        .detected { color: #33B555; }
        .not-detected { color: #ff6b6b; }
    </style>
</head>
<body>
    <h1>摄像头校准管理</h1>
    <p class="hint">拖动蓝色圆点调整四边形，框选地面投影区域</p>
    
    <div class="container">
        <img id="video" src="/video_feed">
        <canvas id="canvas"></canvas>
    </div>
    
    <p class="label">↓ 矫正后的16:9画面 ↓</p>
    <img id="corrected" src="/corrected_feed">
    
    <div class="status">
        脚部检测: <span id="feet-status" class="not-detected">未检测到</span>
    </div>

    <script>
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        
        let corners = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]];
        let dragging = -1;
        let mouseDown = false;

        function init() {
            fetch('/api/corners').then(r => r.json()).then(d => {
                corners = d.corners || corners;
            });
            resize();
            requestAnimationFrame(draw);
            setInterval(updateStatus, 500);
        }

        function resize() {
            canvas.width = video.clientWidth;
            canvas.height = video.clientHeight;
        }
        video.onload = resize;
        window.onresize = resize;
        setTimeout(resize, 500);

        function draw() {
            if (canvas.width === 0) {
                requestAnimationFrame(draw);
                return;
            }
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const w = canvas.width, h = canvas.height;

            // 画四边形
            ctx.strokeStyle = '#0066cc';
            ctx.lineWidth = 3;
            ctx.beginPath();
            corners.forEach((p, i) => {
                const x = p[0] * w, y = p[1] * h;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.closePath();
            ctx.stroke();
            ctx.fillStyle = 'rgba(0, 102, 204, 0.1)';
            ctx.fill();

            // 画顶点
            corners.forEach((p, i) => {
                const x = p[0] * w, y = p[1] * h;
                ctx.beginPath();
                ctx.arc(x, y, 14, 0, Math.PI * 2);
                ctx.fillStyle = '#0066cc';
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2;
                ctx.stroke();
                
                ctx.fillStyle = '#fff';
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
                if (d < 0.06) {
                    dragging = i;
                    mouseDown = true;
                    break;
                }
            }
        };

        canvas.onmousemove = (e) => {
            if (!mouseDown || dragging < 0) return;
            const pos = getPos(e);
            corners[dragging] = [
                Math.max(0.02, Math.min(0.98, pos.x)),
                Math.max(0.02, Math.min(0.98, pos.y))
            ];
        };

        canvas.onmouseup = () => {
            if (mouseDown) save();
            mouseDown = false;
            dragging = -1;
        };

        canvas.onmouseleave = () => {
            if (mouseDown) save();
            mouseDown = false;
            dragging = -1;
        };

        function save() {
            fetch('/api/corners', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({corners: corners})
            });
        }

        function updateStatus() {
            fetch('/api/status').then(r => r.json()).then(d => {
                const el = document.getElementById('feet-status');
                if (d.feet_detected) {
                    el.textContent = '已检测';
                    el.className = 'detected';
                } else {
                    el.textContent = '未检测到';
                    el.className = 'not-detected';
                }
            });
        }

        setTimeout(init, 1000);
    </script>
</body>
</html>
"""

# Projection页面 - 白底，用于地面投影
HTML_PROJECTION = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Projection - 地面投影</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #fff;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            position: relative;
        }
        #foot-point {
            width: 120px;
            height: 120px;
            background: radial-gradient(circle, #33B555 0%, #228B22 100%);
            border-radius: 50%;
            position: absolute;
            transform: translate(-50%, -50%);
            box-shadow: 0 0 40px rgba(51, 181, 85, 0.6);
            display: none;
            z-index: 100;
        }
        #foot-point::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 40px;
            height: 40px;
            background: rgba(255, 255, 255, 0.5);
            border-radius: 50%;
        }
        #debug {
            position: absolute;
            bottom: 20px;
            left: 20px;
            font-family: monospace;
            font-size: 14px;
            color: #999;
        }
    </style>
</head>
<body>
    <div id="foot-point"></div>
    <div id="debug"></div>

    <script>
        const footPoint = document.getElementById('foot-point');
        const debug = document.getElementById('debug');
        const projW = 640;
        const projH = 360;

        function update() {
            fetch('/api/status')
                .then(r => r.json())
                .then(d => {
                    if (d.feet_detected) {
                        footPoint.style.display = 'block';
                        // 将投影坐标映射到屏幕百分比
                        footPoint.style.left = (d.feet_x / projW * 100) + '%';
                        footPoint.style.top = (d.feet_y / projH * 100) + '%';
                        debug.textContent = `位置: (${d.feet_x}, ${d.feet_y})`;
                    } else {
                        footPoint.style.display = 'none';
                        debug.textContent = '未检测到脚';
                    }
                })
                .catch(err => {
                    console.error(err);
                });
        }

        setInterval(update, 50);  // 20FPS
        update();
    </script>
</body>
</html>
"""

# ============================================================================
# Flask路由
# ============================================================================

@app.route('/')
@app.route('/admin')
def admin():
    return render_template_string(HTML_ADMIN)

@app.route('/projection')
def projection():
    return render_template_string(HTML_PROJECTION)

@app.route('/video_feed')
def video_feed():
    def gen():
        while True:
            jpeg = processor.get_raw_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/corrected_feed')
def corrected_feed():
    def gen():
        while True:
            jpeg = processor.get_corrected_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/corners', methods=['GET', 'POST'])
def api_corners():
    if request.method == 'POST':
        data = request.json
        state["corners"] = data.get("corners", state["corners"])
        processor.update_matrix()
        return jsonify({"ok": True})
    return jsonify({"corners": state["corners"]})

@app.route('/api/status')
def api_status():
    return jsonify({
        "feet_detected": state["feet_detected"],
        "feet_x": state["feet_x"],
        "feet_y": state["feet_y"]
    })

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    print("=" * 50)
    print("地面投影交互系统")
    print("=" * 50)
    print("Admin页面:  http://127.0.0.1:5000/admin")
    print("投影页面:  http://127.0.0.1:5000/projection")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
