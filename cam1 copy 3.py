import cv2
import mediapipe as mp
import threading
import time
import numpy as np
import math
from flask import Flask, Response, render_template_string, request, jsonify

app = Flask(__name__)

# --- 全局状态 ---
state = {
    # 1. 投影外框（原始画面中的梯形顶点，归一化坐标）
    "corners": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
    # 2. 交互子区域（800x600 虚拟平面中的位置和宽高）
    "zones": [
        {"id": 1, "x": 50,  "y": 200, "w": 180, "h": 200},
        {"id": 2, "x": 310, "y": 200, "w": 180, "h": 200},
        {"id": 3, "x": 570, "y": 200, "w": 180, "h": 200}
    ],
    "warped_size": (800, 600),
    "max_foot_dist": 150, # 双脚最大允许间距（像素）
    "current_status": "未触发",
    "active_zone": None
}

# --- HTML 交互控制台 ---
html_page = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>高级投影标定系统 V3.0</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #1a1a1a; color: #fff; margin: 0; display: flex; flex-direction: column; height: 100vh; }
        .header { background: #333; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #FF7222; }
        .main { flex: 1; display: flex; overflow: hidden; }
        .view-section { flex: 2; position: relative; background: #000; display: flex; align-items: center; justify-content: center; border-right: 1px solid #444; }
        .control-section { flex: 1; padding: 20px; background: #252525; overflow-y: auto; }
        
        #raw-canvas { position: absolute; cursor: crosshair; }
        #video-feed { max-width: 100%; max-height: 100%; opacity: 0.6; }
        
        .zone-config { background: #333; border-radius: 8px; padding: 15px; margin-bottom: 15px; border-left: 4px solid #FF7222; }
        .zone-config h4 { margin: 0 0 10px 0; color: #FF7222; }
        .slider-group { margin-bottom: 8px; }
        .slider-group label { display: inline-block; width: 60px; font-size: 12px; }
        input[type=range] { width: 150px; vertical-align: middle; }
        
        .status-badge { font-size: 24px; padding: 10px 20px; border-radius: 5px; background: #444; border: 2px solid #666; }
        .triggered { background: #1b5e20; border-color: #4caf50; color: #fff; }
    </style>
</head>
<body>
    <div class="header">
        <h2>交互区域定义与标定</h2>
        <div id="status-display" class="status-badge">未检测到目标</div>
    </div>
    
    <div class="main">
        <div class="view-section">
            <img id="video-feed" src="/video_feed">
            <canvas id="raw-canvas"></canvas>
        </div>
        
        <div class="control-section">
            <h3>1. 调整投影边界 (蓝色点)</h3>
            <p style="font-size: 12px; color: #aaa;">在左侧画面拖动蓝色圆点，使其对准投影仪投射在地面的四个角。</p>
            
            <hr style="border:0; border-top:1px solid #444; margin:20px 0;">
            
            <h3>2. 调整交互子区域 (橙色框)</h3>
            <div id="zone-editors"></div>
            
            <button style="width:100%; padding:15px; background:#FF7222; border:none; color:white; font-weight:bold; cursor:pointer; margin-top:20px;" onclick="saveConfig()">保存标定数据</button>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('raw-canvas');
        const ctx = canvas.getContext('2d');
        const img = document.getElementById('video-feed');
        let config = { corners: [], zones: [] };
        let activeCorner = null;

        function init() {
            canvas.width = img.clientWidth;
            canvas.height = img.clientHeight;
            fetch('/api/config').then(r => r.json()).then(data => {
                config = data;
                renderZoneEditors();
                draw();
            });
        }

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const w = canvas.width, h = canvas.height;

            // 绘制投影边界
            ctx.strokeStyle = '#00e5ff'; ctx.lineWidth = 3;
            ctx.beginPath();
            config.corners.forEach((p, i) => {
                if(i==0) ctx.moveTo(p[0]*w, p[1]*h); else ctx.lineTo(p[0]*w, p[1]*h);
            });
            ctx.closePath(); ctx.stroke();
            
            config.corners.forEach((p, i) => {
                ctx.fillStyle = '#00e5ff'; ctx.beginPath();
                ctx.arc(p[0]*w, p[1]*h, 10, 0, Math.PI*2); ctx.fill();
                ctx.fillStyle = "#000"; ctx.fillText(i, p[0]*w-3, p[1]*h+3);
            });

            // 获取实时状态
            fetch('/api/status').then(r => r.json()).then(data => {
                const badge = document.getElementById('status-display');
                badge.innerText = data.status;
                if(data.status.includes("区域")) badge.className = "status-badge triggered";
                else badge.className = "status-badge";
            });

            requestAnimationFrame(draw);
        }

        // 顶点拖拽逻辑
        canvas.onmousedown = (e) => {
            const rect = canvas.getBoundingClientRect();
            const mx = (e.clientX - rect.left) / canvas.width;
            const my = (e.clientY - rect.top) / canvas.height;
            config.corners.forEach((p, i) => {
                if(Math.hypot(p[0]-mx, p[1]-my) < 0.04) activeCorner = i;
            });
        };
        canvas.onmousemove = (e) => {
            if(activeCorner === null) return;
            const rect = canvas.getBoundingClientRect();
            config.corners[activeCorner] = [
                (e.clientX - rect.left) / canvas.width,
                (e.clientY - rect.top) / canvas.height
            ];
        };
        canvas.onmouseup = () => { activeCorner = null; saveConfig(); };

        function renderZoneEditors() {
            const container = document.getElementById('zone-editors');
            container.innerHTML = config.zones.map((z, i) => `
                <div class="zone-config">
                    <h4>区域 ${z.id}</h4>
                    <div class="slider-group"><label>X位置:</label><input type="range" min="0" max="800" value="${z.x}" oninput="updateZone(${i},'x',this.value)"></div>
                    <div class="slider-group"><label>Y位置:</label><input type="range" min="0" max="600" value="${z.y}" oninput="updateZone(${i},'y',this.value)"></div>
                    <div class="slider-group"><label>宽度:</label><input type="range" min="10" max="400" value="${z.w}" oninput="updateZone(${i},'w',this.value)"></div>
                    <div class="slider-group"><label>高度:</label><input type="range" min="10" max="400" value="${z.h}" oninput="updateZone(${i},'h',this.value)"></div>
                </div>
            `).join('');
        }

        function updateZone(idx, prop, val) {
            config.zones[idx][prop] = parseInt(val);
            saveConfig();
        }

        function saveConfig() {
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });
        }

        setTimeout(init, 1000);
    </script>
</body>
</html>
"""

# --- 后端处理逻辑 ---
mp_pose = mp.solutions.pose

class InteractionManager:
    def __init__(self):
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened(): self.cap = cv2.VideoCapture(0)
        self.pose = mp_pose.Pose(min_detection_confidence=0.5, model_complexity=0)
        self.lock = threading.Lock()
        self.frame = None
        self.is_running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret: continue
            
            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb_frame)
            
            temp_status = "未检测到双脚"
            
            if results.pose_landmarks:
                lm = results.pose_landmarks.landmark
                # 获取脚踝点 (27: 左脚踝, 28: 右脚踝)
                if lm[27].visibility > 0.5 and lm[28].visibility > 0.5:
                    l_ankle = (int(lm[27].x * w), int(lm[27].y * h))
                    r_ankle = (int(lm[28].x * w), int(lm[28].y * h))
                    
                    # 进行透视变换映射
                    pts_src = np.array([[p[0]*w, p[1]*h] for p in state["corners"]], dtype="float32")
                    pts_dst = np.array([[0,0], [800,0], [800,600], [0,600]], dtype="float32")
                    
                    try:
                        matrix = cv2.getPerspectiveTransform(pts_src, pts_dst)
                        # 转换双脚坐标到 800x600 的上帝视角
                        feet_raw = np.array([[l_ankle], [r_ankle]], dtype="float32")
                        warped = cv2.perspectiveTransform(feet_raw, matrix)
                        f1, f2 = warped[0][0], warped[1][0]
                        
                        # 计算双脚间距
                        dist = math.hypot(f1[0]-f2[0], f1[1]-f2[1])
                        
                        if dist < state["max_foot_dist"]:
                            found = False
                            for z in state["zones"]:
                                # 检查双脚是否都在当前矩形内
                                in_l = z["x"] < f1[0] < z["x"]+z["w"] and z["y"] < f1[1] < z["y"]+z["h"]
                                in_r = z["x"] < f2[0] < z["x"]+z["w"] and z["y"] < f2[1] < z["y"]+z["h"]
                                
                                if in_l and in_r:
                                    temp_status = f"✅ 触发区域 {z['id']}"
                                    found = True
                                    break
                            if not found: temp_status = "目标在投影区，未进入按键"
                        else:
                            temp_status = "请双脚靠拢以触发"
                            
                        # 在原图画出检测点
                        cv2.circle(frame, l_ankle, 8, (0,255,0), -1)
                        cv2.circle(frame, r_ankle, 8, (0,0,255), -1)
                    except:
                        temp_status = "校准区域无效"

            state["current_status"] = temp_status
            
            # 画出投影边界预览
            pts_poly = np.array([[p[0]*w, p[1]*h] for p in state["corners"]], np.int32)
            cv2.polylines(frame, [pts_poly], True, (255, 229, 0), 2)
            
            with self.lock:
                self.frame = frame
            time.sleep(0.01)

    def get_frame(self):
        with self.lock:
            if self.frame is None: return None
            _, buf = cv2.imencode('.jpg', self.frame)
            return buf.tobytes()

manager = InteractionManager()

# --- Flask 路由 ---
@app.route('/')
def index(): return render_template_string(html_page)

@app.route('/video_feed')
def video_feed():
    def gen():
        while True:
            f = manager.get_frame()
            if f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f + b'\r\n')
            time.sleep(0.04)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    global state
    if request.method == 'POST':
        data = request.json
        state["corners"] = data.get("corners", state["corners"])
        state["zones"] = data.get("zones", state["zones"])
        return jsonify({"msg": "ok"})
    return jsonify(state)

@app.route('/api/status')
def get_status(): return jsonify({"status": state["current_status"]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)