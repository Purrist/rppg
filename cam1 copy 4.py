import cv2
import mediapipe as mp
import threading
import time
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify

app = Flask(__name__)

# --- 全局状态 ---
state = {
    # 1. 主投影区域 (摄像头坐标系下的4个点)
    "main_area": [[0.1, 0.3], [0.9, 0.3], [0.9, 0.9], [0.1, 0.9]],
    
    # 2. 三个识别区域 (投影坐标系 1920x1080 下的4个点)
    "zones": [
        {"id": 1, "points": [[300, 400], [600, 400], [600, 800], [300, 800]], "color": "#FF7222"},
        {"id": 2, "points": [[700, 400], [1000, 400], [1000, 800], [700, 800]], "color": "#2AAADD"},
        {"id": 3, "points": [[1100, 400], [1400, 400], [1400, 800], [1100, 800]], "color": "#FF69B4"}
    ],
    
    # 3. 透视变换矩阵 (从 main_area -> 1920x1080)
    "M": None,
    
    "status_text": "等待检测...",
    "active_zone_id": None
}

# --- HTML 模板 ---

# 1. 管理后台页面
html_admin = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>老年机器人交互系统 - 管理后台</title>
    <style>
        body { margin: 0; padding: 0; background: #fff; color: #000; font-family: 'Segoe UI', sans-serif; overflow: hidden; }
        .container { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; height: 100vh; gap: 10px; padding: 10px; box-sizing: border-box; }
        
        .panel { background: #fff; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; border: 1px solid #ddd; }
        .panel-header { background: #f0f0f0; padding: 10px 15px; font-weight: bold; border-bottom: 1px solid #ddd; }
        .panel-content { flex: 1; position: relative; }
        
        .video-container { width: 100%; height: 100%; position: relative; }
        .video { 
            width: 100%; 
            height: 100%; 
            object-fit: contain; /* 保持比例，完整显示 */
            display: block;
        }
        .canvas-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }
        .canvas-overlay.editable { pointer-events: auto; cursor: crosshair; }
        
        .status-box { position: absolute; top: 10px; left: 10px; background: rgba(255,255,255,0.8); padding: 8px 12px; border-radius: 4px; font-size: 14px; }
        .status-box span { color: #FF7222; font-weight: bold; }
        
        .zone-display { display: flex; justify-content: space-around; align-items: center; height: 100%; padding: 20px; }
        .zone-box { border: 3px solid; width: 120px; height: 180px; display: flex; justify-content: center; align-items: center; position: relative; background: #fff; }
        .zone-box.active { border-color: #FFD111; box-shadow: 0 0 20px #FFD111; }
        .foot-point { width: 40px; height: 40px; background: #33B555; border-radius: 50%; position: absolute; transform: translate(-50%, -50%); }
        .zone-label { position: absolute; top: -25px; left: 0; right: 0; text-align: center; font-size: 14px; font-weight: bold; }
        
        .controls { display: flex; flex-direction: column; gap: 10px; padding: 15px; }
        .control-row { display: flex; gap: 10px; }
        .btn { padding: 8px 15px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; transition: 0.2s; }
        .btn-edit { background: #FF7222; color: white; }
        .btn-save { background: #33B555; color: white; }
        .btn:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div class="container">
        <!-- 左上角：摄像头画面 + 骨骼识别 -->
        <div class="panel">
            <div class="panel-header">摄像头画面 (骨骼识别)</div>
            <div class="panel-content">
                <div class="video-container">
                    <img id="camera-video" class="video" src="/camera_feed">
                    <canvas id="camera-overlay" class="canvas-overlay"></canvas>
                </div>
            </div>
        </div>

        <!-- 右上角：三个区域显示 + 脚的位置 -->
        <div class="panel">
            <div class="panel-header">交互区域状态</div>
            <div class="panel-content">
                <div class="zone-display" id="zone-display">
                    <!-- 动态生成 -->
                </div>
            </div>
        </div>

        <!-- 左下角：校正后的画面 + 区域编辑 -->
        <div class="panel">
            <div class="panel-header">校正后画面 (区域编辑)</div>
            <div class="panel-content">
                <div class="video-container">
                    <img id="corrected-video" class="video" src="/corrected_feed">
                    <canvas id="corrected-overlay" class="canvas-overlay"></canvas>
                </div>
            </div>
        </div>

        <!-- 右下角：控制按钮 -->
        <div class="panel">
            <div class="panel-header">区域控制</div>
            <div class="panel-content">
                <div class="controls">
                    <div class="control-row">
                        <div>整体区域</div>
                        <button class="btn btn-edit" onclick="startEdit('main')">编辑</button>
                        <button class="btn btn-save" onclick="saveMainArea()">确定</button>
                    </div>
                    <div class="control-row">
                        <div>识别区域1</div>
                        <button class="btn btn-edit" onclick="startEdit(1)">编辑</button>
                        <button class="btn btn-save" onclick="saveZone(1)">确定</button>
                    </div>
                    <div class="control-row">
                        <div>识别区域2</div>
                        <button class="btn btn-edit" onclick="startEdit(2)">编辑</button>
                        <button class="btn btn-save" onclick="saveZone(2)">确定</button>
                    </div>
                    <div class="control-row">
                        <div>识别区域3</div>
                        <button class="btn btn-edit" onclick="startEdit(3)">编辑</button>
                        <button class="btn btn-save" onclick="saveZone(3)">确定</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const cameraVideo = document.getElementById('camera-video');
        const cameraCanvas = document.getElementById('camera-overlay');
        const correctedVideo = document.getElementById('corrected-video');
        const correctedCanvas = document.getElementById('corrected-overlay');
        const zoneDisplay = document.getElementById('zone-display');
        
        let config = { main_area: [], zones: [] };
        let editingType = null; // 'main', 1, 2, 3
        let draggingIdx = -1;
        
        // 初始化
        function init() {
            fetch('/api/config').then(r => r.json()).then(d => {
                config = d;
                adjustCanvases();
                renderZoneDisplay();
            });
            setInterval(updateStatus, 500);
        }

        // 调整Canvas尺寸
        function adjustCanvases() {
            [cameraCanvas, correctedCanvas].forEach(canvas => {
                const video = canvas.previousElementSibling;
                const rect = video.getBoundingClientRect();
                canvas.width = rect.width;
                canvas.height = rect.height;
                canvas.style.left = rect.left + 'px';
                canvas.style.top = rect.top + 'px';
            });
            drawCameraOverlay();
            drawCorrectedOverlay();
        }

        window.onresize = adjustCanvases;
        [cameraVideo, correctedVideo].forEach(v => v.onload = adjustCanvases);
        setTimeout(adjustCanvases, 500);

        // 绘制摄像头画面叠加层
        function drawCameraOverlay() {
            const ctx = cameraCanvas.getContext('2d');
            ctx.clearRect(0, 0, cameraCanvas.width, cameraCanvas.height);
            
            // 绘制主区域 (虚线)
            drawShape(ctx, config.main_area, '#00e5ff', editingType === 'main');
        }

        // 绘制校正后画面叠加层
        function drawCorrectedOverlay() {
            const ctx = correctedCanvas.getContext('2d');
            ctx.clearRect(0, 0, correctedCanvas.width, correctedCanvas.height);
            
            // 绘制三个区域 (虚线)
            config.zones.forEach(z => {
                drawShape(ctx, z.points, z.color, editingType === z.id);
            });
        }

        function drawShape(ctx, pts, color, isEdit) {
            if(pts.length !== 4) return;
            
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            
            ctx.beginPath();
            pts.forEach((p, i) => {
                const px = p[0] * ctx.canvas.width / 1920; // 基于1920x1080坐标系，映射到Canvas尺寸
                const py = p[1] * ctx.canvas.height / 1080;
                if(i===0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
            });
            ctx.closePath();
            ctx.stroke();
            ctx.setLineDash([]);

            // 绘制顶点 (仅在编辑模式下)
            if(isEdit) {
                pts.forEach((p, i) => {
                    const px = p[0] * ctx.canvas.width / 1920;
                    const py = p[1] * ctx.canvas.height / 1080;
                    ctx.beginPath();
                    ctx.arc(px, py, 10, 0, Math.PI*2);
                    ctx.fillStyle = '#fff';
                    ctx.fill();
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 3;
                    ctx.stroke();
                });
            }
        }

        // 交互逻辑
        function getMousePos(e, canvas) {
            const rect = canvas.getBoundingClientRect();
            return { x: (e.clientX - rect.left) / canvas.width, y: (e.clientY - rect.top) / canvas.height };
        }

        cameraCanvas.onmousedown = e => {
            if(editingType !== 'main') return;
            const pos = getMousePos(e, cameraCanvas);
            const pts = config.main_area;
            if(!pts) return;

            let minDist = 0.05;
            for(let i=0; i<pts.length; i++) {
                const d = Math.hypot(pts[i][0]-pos.x, pts[i][1]-pos.y);
                if(d < minDist) {
                    draggingIdx = i;
                    minDist = d;
                }
            }
        };

        correctedCanvas.onmousedown = e => {
            if(!editingType || editingType === 'main') return;
            const pos = getMousePos(e, correctedCanvas);
            const pts = config.zones.find(z => z.id === editingType)?.points;
            if(!pts) return;

            let minDist = 0.05;
            for(let i=0; i<pts.length; i++) {
                const d = Math.hypot(pts[i][0]-pos.x, pts[i][1]-pos.y);
                if(d < minDist) {
                    draggingIdx = i;
                    minDist = d;
                }
            }
        };

        [cameraCanvas, correctedCanvas].forEach(canvas => {
            canvas.onmousemove = e => {
                if(editingType === null || draggingIdx === -1) return;
                const pos = getMousePos(e, canvas);
                const pts = editingType === 'main' ? config.main_area : 
                           config.zones.find(z => z.id === editingType)?.points;
                if(pts) {
                    pts[draggingIdx] = [pos.x, pos.y];
                    if(editingType === 'main') drawCameraOverlay();
                    else drawCorrectedOverlay();
                }
            };
            
            canvas.onmouseup = () => draggingIdx = -1;
            canvas.onmouseleave = () => draggingIdx = -1;
        });

        function startEdit(type) {
            editingType = type;
            [cameraCanvas, correctedCanvas].forEach(c => c.classList.add('editable'));
        }

        function saveMainArea() {
            editingType = null;
            [cameraCanvas, correctedCanvas].forEach(c => c.classList.remove('editable'));
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({main_area: config.main_area})
            }).then(r => r.json()).then(d => console.log(d.msg));
        }

        function saveZone(id) {
            editingType = null;
            [cameraCanvas, correctedCanvas].forEach(c => c.classList.remove('editable'));
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({zones: config.zones})
            }).then(r => r.json()).then(d => console.log(d.msg));
        }

        function renderZoneDisplay() {
            zoneDisplay.innerHTML = config.zones.map(z => `
                <div class="zone-box" style="border-color: ${z.color}" id="zone-box-${z.id}">
                    <div class="zone-label">区域${z.id}</div>
                    <div class="foot-point" id="foot-point-${z.id}" style="display: none;"></div>
                </div>
            `).join('');
        }

        function updateStatus() {
            fetch('/api/status').then(r => r.json()).then(data => {
                // 更新状态文字
                document.querySelector('.panel-header').innerText = data.status_text;
                
                // 更新区域显示
                const activeId = data.active_zone_id;
                config.zones.forEach(z => {
                    const box = document.getElementById(`zone-box-${z.id}`);
                    const footPoint = document.getElementById(`foot-point-${z.id}`);
                    if(box) {
                        box.classList.toggle('active', z.id === activeId);
                        if(footPoint) {
                            footPoint.style.display = (z.id === activeId && data.feet_detected) ? 'block' : 'none';
                            if(z.id === activeId && data.feet_detected) {
                                footPoint.style.left = (data.feet_x / 1920 * 100) + '%';
                                footPoint.style.top = (data.feet_y / 1080 * 100) + '%';
                            }
                        }
                    }
                });
            });
        }

        init();
    </script>
</body>
</html>
"""

# 2. 投影端页面
html_projection = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>投影画面</title>
    <style>
        body { margin: 0; background: #fff; color: #000; overflow: hidden; font-family: 'Segoe UI', sans-serif; height: 100vh; display: flex; flex-direction: column; }
        
        #top-status { 
            width: 100%; text-align: center; padding-top: 5vh; 
            font-size: 10vw; font-weight: bold; 
            color: #000; z-index: 10; 
            text-shadow: 0 0 20px rgba(0,0,0,0.3);
        }
        
        /* 视频容器 */
        .video-container { position: relative; flex: 1; width: 100%; }
        #projection-video { 
            width: 100%; 
            height: 100%; 
            object-fit: contain; /* 保持比例，完整显示 */
            display: block;
        }
        
        /* 脚部光标 */
        #foot-cursor {
            width: 80px; height: 80px; background: #33B555; 
            border-radius: 50%; position: absolute;
            box-shadow: 0 0 30px #33B555; display: none;
            transform: translate(-50%, -50%);
            transition: left 0.1s, top 0.1s;
            z-index: 10;
        }
        
        /* 区域边框 */
        .zone-border {
            position: absolute; border: 4px solid rgba(0,0,0,0.3);
            pointer-events: none;
            transition: border-color 0.2s;
        }
        .zone-border.active { border-color: #FFD111; box-shadow: 0 0 20px #FFD111; }
    </style>
</head>
<body>
    <div id="top-status">准备就绪</div>
    <div class="video-container">
        <img id="projection-video" src="/projection_feed">
        <div id="foot-cursor"></div>
        <div id="zones-layer"></div>
    </div>

    <script>
        const video = document.getElementById('projection-video');
        const cursor = document.getElementById('foot-cursor');
        const zonesLayer = document.getElementById('zones-layer');
        
        const projW = 1920, projH = 1080;
        
        function init() {
            fetch('/api/config').then(r => r.json()).then(d => {
                config = d;
                adjustCanvasSize();
            });
            setInterval(update, 30);
        }

        function adjustCanvasSize() {
            const rect = video.getBoundingClientRect();
            zonesLayer.style.width = rect.width + 'px';
            zonesLayer.style.height = rect.height + 'px';
            zonesLayer.style.left = rect.left + 'px';
            zonesLayer.style.top = rect.top + 'px';
            drawZones();
        }

        window.onresize = adjustCanvasSize;
        video.onload = adjustCanvasSize;
        
        function drawZones() {
            zonesLayer.innerHTML = '';
            config.zones.forEach(z => {
                const div = document.createElement('div');
                div.className = 'zone-border' + (z.id === activeId ? ' active' : '');
                
                // 计算边界盒以便用CSS绘制
                const xs = z.points.map(p => p[0]);
                const ys = z.points.map(p => p[1]);
                const minX = Math.min(...xs), maxX = Math.max(...xs);
                const minY = Math.min(...ys), maxY = Math.max(...ys);
                
                div.style.left = (minX / projW * 100) + '%';
                div.style.top = (minY / projH * 100) + '%';
                div.style.width = ((maxX - minX) / projW * 100) + '%';
                div.style.height = ((maxY - minY) / projH * 100) + '%';
                div.style.borderColor = z.color;
                
                zonesLayer.appendChild(div);
            });
        }

        function update() {
            fetch('/api/projection_data')
                .then(r => r.json())
                .then(data => {
                    // 1. 更新状态文字
                    const txt = document.getElementById('top-status');
                    txt.innerText = data.status_text;
                    txt.style.color = data.active_zone_id ? '#FFD111' : '#000';

                    // 2. 更新脚部光标
                    if(data.feet_detected) {
                        cursor.style.display = 'block';
                        cursor.style.left = (data.feet_x / projW * 100) + '%';
                        cursor.style.top = (data.feet_y / projH * 100) + '%';
                    } else {
                        cursor.style.display = 'none';
                    }
                });
        }

        init();
    </script>
</body>
</html>
"""

# --- 后端处理 ---
mp_pose = mp.solutions.pose

class Processor:
    def __init__(self):
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened(): self.cap = cv2.VideoCapture(0)
        self.cap.set(3, 640)
        self.cap.set(4, 480)
        
        self.pose = mp_pose.Pose(
            min_detection_confidence=0.6, 
            min_tracking_confidence=0.6,
            model_complexity=1 
        )
        self.lock = threading.Lock()
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok: continue
            
            # 1. 镜像翻转
            frame = cv2.flip(frame, 1)
            
            h, w, _ = frame.shape
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = self.pose.process(frame_rgb)
            
            status = "未检测到目标"
            active_id = None
            feet_detected = False
            feet_x, feet_y = 0, 0

            if res.pose_landmarks:
                # 绘制骨骼
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, res.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    mp.solutions.drawing_styles.get_default_pose_landmarks_style()
                )
                
                lm = res.pose_landmarks.landmark
                l_ankle = lm[mp_pose.PoseLandmark.LEFT_ANKLE]
                r_ankle = lm[mp_pose.PoseLandmark.RIGHT_ANKLE]

                if l_ankle.visibility > 0.5 and r_ankle.visibility > 0.5:
                    l_pt = (int(l_ankle.x * w), int(l_ankle.y * h))
                    r_pt = (int(r_ankle.x * w), int(r_ankle.y * h))
                    
                    # 画面上高亮双脚
                    cv2.circle(frame, l_pt, 10, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 10, (0, 255, 0), -1)
                    
                    # --- 计算透视变换矩阵 ---
                    if state["M"] is not None:
                        # 变换双脚坐标到投影坐标系 (1920x1080)
                        feet_px = np.array([[[ (l_pt[0]+r_pt[0])/2, (l_pt[1]+r_pt[1])/2 ]]], dtype="float32")
                        mapped = cv2.perspectiveTransform(feet_px, state["M"])[0][0]
                        feet_x, feet_y = int(mapped[0]), int(mapped[1])
                        feet_detected = True
                        
                        # --- 区域检测逻辑 (在投影坐标系下) ---
                        center_pt = (feet_x, feet_y)
                        
                        found = False
                        for z in state["zones"]:
                            # 投影坐标系下的区域顶点
                            zone_pts = np.array(z["points"], dtype="int32")
                            
                            # 判断脚中心是否在区域内
                            if cv2.pointPolygonTest(zone_pts, center_pt, False) >= 0:
                                status = f"触发区域 {z['id']}"
                                active_id = z['id']
                                found = True
                                break
                        
                        if not found:
                            status = "移动中..."
                
                else:
                    status = "请完全进入画面"

            # --- 准备投影画面 ---
            proj_frame = None
            if state["M"] is not None:
                # 将原始画面变换到1920x1080
                proj_frame = cv2.warpPerspective(frame, state["M"], (1920, 1080))
            else:
                # 如果未校正，显示黑屏
                proj_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

            with self.lock:
                self.raw_frame = frame
                self.proj_frame = proj_frame
                state["status_text"] = status
                state["active_zone_id"] = active_id
                state["feet_detected"] = feet_detected
                state["feet_x"] = feet_x
                state["feet_y"] = feet_y

            time.sleep(0.01)

    def get_raw_frame(self):
        with self.lock:
            if self.raw_frame is None: return b''
            _, buf = cv2.imencode('.jpg', self.raw_frame)
            return buf.tobytes()

    def get_proj_frame(self):
        with self.lock:
            if self.proj_frame is None: return b''
            _, buf = cv2.imencode('.jpg', self.proj_frame)
            return buf.tobytes()

proc = Processor()

# --- 路由 ---
@app.route('/')
def index(): return render_template_string(html_admin)

@app.route('/admin')
def admin(): return render_template_string(html_admin)

@app.route('/projection')
def projection(): return render_template_string(html_projection)

@app.route('/camera_feed')
def camera_feed():
    def gen():
        while True:
            f = proc.get_raw_frame()
            if f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/corrected_feed')
def corrected_feed():
    def gen():
        while True:
            f = proc.get_proj_frame()
            if f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/projection_feed')
def projection_feed():
    def gen():
        while True:
            f = proc.get_proj_frame()
            if f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.json
        if 'main_area' in data:
            state['main_area'] = data['main_area']
            # 重新计算透视矩阵
            src_pts = np.array([[p[0]*640, p[1]*480] for p in state["main_area"]], dtype="float32")
            dst_pts = np.array([[0,0], [1920,0], [1920,1080], [0,1080]], dtype="float32")
            state['M'] = cv2.getPerspectiveTransform(src_pts, dst_pts)
        
        if 'zones' in data:
            state['zones'] = data['zones']
        
        return jsonify(msg="Saved")
    
    return jsonify(main_area=state['main_area'], zones=state['zones'])

@app.route('/api/status')
def api_status():
    return jsonify(status_text=state.get("status_text", ""))

@app.route('/api/projection_data')
def api_proj():
    return jsonify(
        status_text=state.get("status_text", ""),
        active_zone_id=state.get("active_zone_id"),
        feet_detected=state.get("feet_detected", False),
        feet_x=state.get("feet_x", 0),
        feet_y=state.get("feet_y", 0)
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
