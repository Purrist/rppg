import cv2
import mediapipe as mp
import threading
import time
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify

app = Flask(__name__)

# --- 全局状态配置 ---
# 存储透视变换的4个顶点和3个交互区域（基于变换后 800x600 的虚拟画布）
state = {
    "corners": [], # 存储原始画面中的4个顶点坐标 (x, y)
    "zones": [
        {"id": 1, "x": 100, "y": 200, "w": 150, "h": 150},
        {"id": 2, "x": 325, "y": 200, "w": 150, "h": 150},
        {"id": 3, "x": 550, "y": 200, "w": 150, "h": 150}
    ],
    "warped_size": (800, 600), # 投影变换后的标准尺寸
    "cam_width": 640,
    "cam_height": 480
}

# --- HTML 测试与校准面板 ---
html_page = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>投影区域校准与测试系统</title>
    <style>
        body { font-family: sans-serif; background: #1a1a1a; color: white; display: flex; margin: 0; height: 100vh; }
        .video-container { flex: 2; padding: 20px; display: flex; flex-direction: column; align-items: center; }
        .control-panel { flex: 1; background: #2a2a2a; padding: 20px; overflow-y: auto; }
        img { max-width: 100%; border: 2px solid #555; cursor: crosshair; }
        .btn { padding: 10px 15px; background: #FF7222; color: white; border: none; cursor: pointer; border-radius: 5px; margin-bottom: 10px; font-weight: bold;}
        .btn-danger { background: #FB4422; }
        .zone-card { background: #333; padding: 10px; margin-bottom: 15px; border-radius: 5px; }
        .zone-card input { width: 60px; margin-right: 10px; background: #444; color: white; border: 1px solid #666; }
        h3 { margin-top: 0; color: #FFD111; }
    </style>
</head>
<body>
    <div class="video-container">
        <h2 style="color: #33B555;">实时识别与校准画面</h2>
        <img id="videoFeed" src="/video_feed" onclick="handleImageClick(event)">
        <p>提示：在画面上依次点击 4 个点（左上、右上、右下、左下）来框定投影区域。</p>
    </div>
    
    <div class="control-panel">
        <h3>📍 投影区域顶点</h3>
        <button class="btn btn-danger" onclick="clearCorners()">清除重置顶点</button>
        <p id="corner-status">当前已设置: 0 / 4 点</p>

        <h3>🎛️ 交互区域配置 (虚拟画布 800x600)</h3>
        <div id="zones-container"></div>
        <button class="btn" onclick="saveZones()">更新区域配置</button>
    </div>

    <script>
        // 初始化区域输入框
        let zones = [];
        
        function fetchConfig() {
            fetch('/api/config').then(r => r.json()).then(data => {
                document.getElementById('corner-status').innerText = `当前已设置: ${data.corners.length} / 4 点`;
                zones = data.zones;
                renderZones();
            });
        }

        function renderZones() {
            const container = document.getElementById('zones-container');
            container.innerHTML = '';
            zones.forEach((z, index) => {
                container.innerHTML += `
                    <div class="zone-card">
                        <strong>区域 ${z.id}</strong><br>
                        X: <input type="number" id="z${index}_x" value="${z.x}">
                        Y: <input type="number" id="z${index}_y" value="${z.y}"><br>
                        宽: <input type="number" id="z${index}_w" value="${z.w}">
                        高: <input type="number" id="z${index}_h" value="${z.h}">
                    </div>
                `;
            });
        }

        function saveZones() {
            const newZones = zones.map((z, index) => ({
                id: z.id,
                x: parseInt(document.getElementById(`z${index}_x`).value),
                y: parseInt(document.getElementById(`z${index}_y`).value),
                w: parseInt(document.getElementById(`z${index}_w`).value),
                h: parseInt(document.getElementById(`z${index}_h`).value)
            }));
            fetch('/api/zones', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({zones: newZones})
            }).then(() => alert('区域配置已更新！'));
        }

        function handleImageClick(event) {
            const rect = event.target.getBoundingClientRect();
            // 计算归一化坐标 (0.0 ~ 1.0)
            const normX = (event.clientX - rect.left) / rect.width;
            const normY = (event.clientY - rect.top) / rect.height;
            
            fetch('/api/click', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ nx: normX, ny: normY })
            }).then(() => fetchConfig());
        }

        function clearCorners() {
            fetch('/api/clear_corners', { method: 'POST' }).then(() => fetchConfig());
        }

        // 定期刷新状态
        setInterval(fetchConfig, 2000);
        fetchConfig();
    </script>
</body>
</html>
"""

# --- 核心处理逻辑 ---
mp_pose = mp.solutions.pose

class VideoCamera:
    def __init__(self):
        self.video = cv2.VideoCapture(1)
        if not self.video.isOpened():
            self.video = cv2.VideoCapture(0)
            
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.video.set(cv2.CAP_PROP_FPS, 30)

        # 记录实际分辨率用于坐标映射
        state["cam_width"] = self.video.get(cv2.CAP_PROP_FRAME_WIDTH)
        state["cam_height"] = self.video.get(cv2.CAP_PROP_FRAME_HEIGHT)

        self.success, self.frame = self.video.read()
        self.is_running = True
        
        # 姿态检测模型 (选择 model_complexity=0 保证实时性)
        self.pose = mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0 
        )

        self.thread = threading.Thread(target=self._update, args=())
        self.thread.daemon = True
        self.thread.start()

    def _update(self):
        while self.is_running:
            success, raw_frame = self.video.read()
            if success:
                # 图像处理前可以进行翻转 (如需要解决镜像问题)
                # raw_frame = cv2.flip(raw_frame, 1)
                
                display_frame = raw_frame.copy()
                frame_rgb = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB)
                results = self.pose.process(frame_rgb)

                foot_coords = [] # 存储检测到的脚部像素坐标

                if results.pose_landmarks:
                    h, w, c = raw_frame.shape
                    landmarks = results.pose_landmarks.landmark
                    
                    # 提取左右脚尖和脚踝
                    target_idx = [
                        mp_pose.PoseLandmark.LEFT_FOOT_INDEX.value,
                        mp_pose.PoseLandmark.RIGHT_FOOT_INDEX.value,
                        mp_pose.PoseLandmark.LEFT_ANKLE.value,
                        mp_pose.PoseLandmark.RIGHT_ANKLE.value
                    ]
                    
                    for idx in target_idx:
                        lm = landmarks[idx]
                        if lm.visibility > 0.6:
                            cx, cy = int(lm.x * w), int(lm.y * h)
                            foot_coords.append((cx, cy))
                            cv2.circle(display_frame, (cx, cy), 5, (0, 255, 255), -1)

                # 判断逻辑：寻找最下方的脚点 (Y 坐标最大)
                main_foot = None
                if foot_coords:
                    main_foot = max(foot_coords, key=lambda p: p[1])
                    cv2.circle(display_frame, main_foot, 10, (0, 0, 255), 2) # 重点标记

                # 透视变换与区域判断逻辑
                status_text = "Status: Not in zone"
                status_color = (0, 0, 255) # 红色

                if len(state["corners"]) == 4:
                    pts_src = np.array(state["corners"], dtype="float32")
                    ww, wh = state["warped_size"]
                    pts_dst = np.array([[0, 0], [ww, 0], [ww, wh], [0, wh]], dtype="float32")
                    
                    # 获取透视变换矩阵
                    matrix = cv2.getPerspectiveTransform(pts_src, pts_dst)

                    # 在原图上画出透视框
                    cv2.polylines(display_frame, [np.int32(pts_src)], True, (0, 255, 0), 2)

                    # 创建一个黑色背景用于绘制 warped 画中画 (PiP)
                    warped_pip = np.zeros((wh, ww, 3), dtype=np.uint8)

                    # 如果检测到脚，将其坐标变换到虚拟空间
                    if main_foot:
                        pt = np.array([[[main_foot[0], main_foot[1]]]], dtype="float32")
                        warped_pt = cv2.perspectiveTransform(pt, matrix)[0][0]
                        wx, wy = int(warped_pt[0]), int(warped_pt[1])
                        
                        # 在虚拟空间中绘制脚部位置
                        cv2.circle(warped_pip, (wx, wy), 15, (0, 0, 255), -1)

                        # 碰撞检测：检查是否在3个区域内
                        for z in state["zones"]:
                            if z["x"] <= wx <= z["x"] + z["w"] and z["y"] <= wy <= z["y"] + z["h"]:
                                status_text = f"Status: In Zone {z['id']}"
                                status_color = (0, 255, 0) # 绿色
                                break

                    # 在虚拟空间中绘制3个交互区域
                    for z in state["zones"]:
                        cv2.rectangle(warped_pip, (z["x"], z["y"]), (z["x"]+z["w"], z["y"]+z["h"]), (255, 114, 34), 2)
                        cv2.putText(warped_pip, f"Z{z['id']}", (z["x"]+5, z["y"]+30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 114, 34), 2)

                    # 将 PiP 缩小并叠加到左上角进行监控
                    pip_h, pip_w = int(wh/3), int(ww/3)
                    pip_resized = cv2.resize(warped_pip, (pip_w, pip_h))
                    display_frame[10:10+pip_h, 10:10+pip_w] = pip_resized
                    cv2.rectangle(display_frame, (10, 10), (10+pip_w, 10+pip_h), (255, 255, 255), 1)

                else:
                    # 绘制正在收集的顶点
                    for pt in state["corners"]:
                        cv2.circle(display_frame, pt, 5, (255, 0, 0), -1)
                    cv2.putText(display_frame, f"Set {len(state['corners'])}/4 Corners", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)

                # 将最终状态绘制在主画面正下方
                cv2.putText(display_frame, status_text, (20, int(state["cam_height"]) - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 3)

                self.success = True
                self.frame = display_frame
            time.sleep(0.01)

    def get_jpg_frame(self):
        if not self.success or self.frame is None:
            return None
        ret, buffer = cv2.imencode('.jpg', self.frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buffer.tobytes()

cam = VideoCamera()

def generate_frames():
    while True:
        frame_bytes = cam.get_jpg_frame()
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.03)

# --- 路由配置 ---
@app.route('/')
def index():
    return render_template_string(html_page)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(state)

@app.route('/api/zones', methods=['POST'])
def update_zones():
    data = request.json
    state["zones"] = data.get("zones", state["zones"])
    return jsonify({"status": "success"})

@app.route('/api/click', methods=['POST'])
def handle_click():
    if len(state["corners"]) < 4:
        data = request.json
        nx, ny = data['nx'], data['ny']
        # 将网页传来的归一化坐标转换为实际像素坐标
        cx = int(nx * state["cam_width"])
        cy = int(ny * state["cam_height"])
        state["corners"].append((cx, cy))
    return jsonify({"status": "success", "corners": state["corners"]})

@app.route('/api/clear_corners', methods=['POST'])
def clear_corners():
    state["corners"] = []
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)