# -*- coding: utf-8 -*-
"""
地面投影交互系统 - 完整版
功能：
1. Admin页面：摄像头画面 + 骨骼识别 + 拖动顶点校准 + 三个可编辑区域
2. Projection页面：绿色圆点 + 区域状态显示
"""

import cv2
import mediapipe as mp
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify
import threading
import time

app = Flask(__name__)

# ============================================================================
# 全局状态
# ============================================================================
state = {
    # 校准四边形顶点（归一化坐标 0-1）
    "corners": [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]],
    
    # 三个识别区域（投影坐标系 640x360）
    "zones": [
        {"id": 1, "points": [[50, 100], [200, 100], [200, 300], [50, 300]], "color": "#33B555"},
        {"id": 2, "points": [[220, 100], [420, 100], [420, 300], [220, 300]], "color": "#FF7222"},
        {"id": 3, "points": [[440, 100], [590, 100], [590, 300], [440, 300]], "color": "#2196F3"}
    ],
    
    # 脚部位置（投影坐标系）
    "feet_x": 320,
    "feet_y": 180,
    "feet_detected": False,
    "active_zone": None,  # 当前所在区域
    
    # 透视变换矩阵
    "matrix": None
}

# ============================================================================
# 处理器
# ============================================================================
class Processor:
    def __init__(self):
        # 摄像头
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"摄像头: {self.frame_w}x{self.frame_h}")
        
        # MediaPipe
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0
        )
        
        self.raw_frame = None
        self.corrected_frame = None
        self.running = True
        
        threading.Thread(target=self._loop, daemon=True).start()
    
    def _loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # 上下翻转 + 镜像
            frame = cv2.flip(frame, 0)  # 上下翻转
            frame = cv2.flip(frame, 1)  # 左右镜像
            
            h, w = frame.shape[:2]
            
            # MediaPipe检测
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb)
            
            feet_detected = False
            feet_x, feet_y = 320, 180
            
            if results.pose_landmarks:
                # 绘制骨骼
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
                    mp.solutions.drawing_styles.get_default_pose_landmarks_style()
                )
                
                lm = results.pose_landmarks.landmark
                left_ankle = lm[27]
                right_ankle = lm[28]
                
                if left_ankle.visibility > 0.5 and right_ankle.visibility > 0.5:
                    l_pt = (int(left_ankle.x * w), int(left_ankle.y * h))
                    r_pt = (int(right_ankle.x * w), int(right_ankle.y * h))
                    
                    # 高亮双脚
                    cv2.circle(frame, l_pt, 15, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 15, (0, 255, 0), -1)
                    cv2.line(frame, l_pt, r_pt, (0, 255, 255), 3)
                    
                    center = ((l_pt[0] + r_pt[0]) // 2, (l_pt[1] + r_pt[1]) // 2)
                    cv2.circle(frame, center, 10, (255, 0, 255), -1)
                    
                    if state["matrix"] is not None:
                        try:
                            src_pt = np.array([[[center[0], center[1]]]], dtype=np.float32)
                            dst_pt = cv2.perspectiveTransform(src_pt, state["matrix"])[0][0]
                            feet_x, feet_y = int(dst_pt[0]), int(dst_pt[1])
                            feet_detected = True
                        except:
                            pass
            
            # 判断在哪个区域
            active_zone = None
            if feet_detected:
                for zone in state["zones"]:
                    pts = np.array(zone["points"], dtype=np.int32)
                    if cv2.pointPolygonTest(pts, (feet_x, feet_y), False) >= 0:
                        active_zone = zone["id"]
                        break
            
            state["feet_x"] = feet_x
            state["feet_y"] = feet_y
            state["feet_detected"] = feet_detected
            state["active_zone"] = active_zone
            
            # 绘制校准框
            pts = np.array([[int(c[0]*w), int(c[1]*h)] for c in state["corners"]], np.int32)
            cv2.polylines(frame, [pts], True, (255, 0, 0), 2)
            for i, c in enumerate(state["corners"]):
                x, y = int(c[0]*w), int(c[1]*h)
                cv2.circle(frame, (x, y), 10, (255, 0, 0), -1)
                cv2.putText(frame, str(i+1), (x-6, y+4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
            
            # 生成矫正后画面
            corrected = np.ones((360, 640, 3), dtype=np.uint8) * 255
            if state["matrix"] is not None:
                try:
                    corrected = cv2.warpPerspective(frame, state["matrix"], (640, 360))
                except:
                    pass
            
            # 在矫正画面上绘制三个区域
            for zone in state["zones"]:
                pts = np.array(zone["points"], dtype=np.int32)
                # 解析颜色
                hex_color = zone["color"].lstrip('#')
                rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                bgr = (rgb[2], rgb[1], rgb[0])
                
                # 绘制区域边框
                cv2.polylines(corrected, [pts], True, bgr, 3)
                
                # 如果是当前活动区域，填充半透明
                if state["active_zone"] == zone["id"]:
                    overlay = corrected.copy()
                    cv2.fillPoly(overlay, [pts], bgr)
                    cv2.addWeighted(overlay, 0.3, corrected, 0.7, 0, corrected)
                
                # 区域标签
                cx = int(np.mean([p[0] for p in zone["points"]]))
                cy = int(np.mean([p[1] for p in zone["points"]]))
                cv2.putText(corrected, f"区域{zone['id']}", (cx-30, cy), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, bgr, 2)
            
            # 绘制脚部位置
            if feet_detected:
                cv2.circle(corrected, (feet_x, feet_y), 20, (0, 200, 0), -1)
            
            self.raw_frame = frame
            self.corrected_frame = corrected
            
            time.sleep(0.01)
    
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
        if self.raw_frame is None:
            return
        h, w = self.raw_frame.shape[:2]
        src = np.array([[c[0]*w, c[1]*h] for c in state["corners"]], dtype=np.float32)
        dst = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], dtype=np.float32)
        state["matrix"] = cv2.getPerspectiveTransform(src, dst)
        print("透视矩阵已更新")

processor = Processor()

def delayed_init():
    time.sleep(2)
    processor.update_matrix()
threading.Thread(target=delayed_init, daemon=True).start()

# ============================================================================
# HTML模板
# ============================================================================

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
        }
        h1 { margin-bottom: 10px; font-size: 22px; }
        .hint { color: #666; margin-bottom: 15px; font-size: 14px; }
        
        .main-content {
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }
        
        .video-section {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        
        .container { position: relative; margin-bottom: 15px; }
        #video { border: 2px solid #333; display: block; }
        #canvas { position: absolute; top: 0; left: 0; cursor: crosshair; }
        .label { color: #666; margin: 8px 0; font-size: 13px; }
        #corrected { border: 2px solid #33B555; display: block; }
        
        .corrected-container { position: relative; }
        #corrected-canvas { position: absolute; top: 0; left: 0; cursor: crosshair; }
        
        .status {
            margin-top: 10px;
            padding: 8px 15px;
            background: #f0f0f0;
            border-radius: 6px;
            font-size: 13px;
        }
        .detected { color: #33B555; font-weight: bold; }
        .not-detected { color: #ff6b6b; }
        
        /* 区域控制面板 */
        .zone-panel {
            background: #f8f8f8;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            min-width: 200px;
        }
        .zone-panel h3 {
            margin-bottom: 15px;
            font-size: 16px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 8px;
        }
        
        .zone-item {
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 6px;
            margin-bottom: 10px;
            overflow: hidden;
        }
        .zone-header {
            padding: 10px 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }
        .zone-title { font-weight: bold; font-size: 14px; }
        .zone-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
        }
        
        .zone-body {
            padding: 10px 12px;
            border-top: 1px solid #eee;
            display: none;
        }
        .zone-item.active .zone-body { display: block; }
        
        .btn-group { display: flex; gap: 8px; }
        .btn {
            flex: 1;
            padding: 8px 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
        }
        .btn-edit { background: #FF7222; color: #fff; }
        .btn-edit:hover { background: #e65c00; }
        .btn-confirm { background: #33B555; color: #fff; }
        .btn-confirm:hover { background: #2a9245; }
        
        .zone-item.editing {
            border-color: #FF7222;
            box-shadow: 0 0 8px rgba(255, 114, 34, 0.3);
        }
    </style>
</head>
<body>
    <h1>摄像头校准管理</h1>
    <p class="hint">上方：拖动蓝色顶点校准画面 | 下方：点击区域按钮编辑三个识别区域</p>
    
    <div class="main-content">
        <div class="video-section">
            <div class="container">
                <img id="video" src="/video_feed">
                <canvas id="canvas"></canvas>
            </div>
            
            <p class="label">↓ 矫正后的16:9画面（可编辑三个区域） ↓</p>
            <div class="corrected-container">
                <img id="corrected" src="/corrected_feed">
                <canvas id="corrected-canvas"></canvas>
            </div>
            
            <div class="status">
                脚部检测: <span id="feet-status" class="not-detected">未检测到</span> | 
                当前区域: <span id="zone-status">未进入</span>
            </div>
        </div>
        
        <div class="zone-panel">
            <h3>识别区域设置</h3>
            
            <div class="zone-item" id="zone-item-1">
                <div class="zone-header" onclick="toggleZone(1)">
                    <span class="zone-title">
                        <span class="zone-dot" style="background:#33B555"></span>区域1
                    </span>
                    <span>▼</span>
                </div>
                <div class="zone-body">
                    <p style="font-size:12px;color:#666;margin-bottom:8px;">点击编辑后，在下方画面拖动顶点</p>
                    <div class="btn-group">
                        <button class="btn btn-edit" onclick="startEditZone(1)">编辑</button>
                        <button class="btn btn-confirm" onclick="confirmZone(1)">确定</button>
                    </div>
                </div>
            </div>
            
            <div class="zone-item" id="zone-item-2">
                <div class="zone-header" onclick="toggleZone(2)">
                    <span class="zone-title">
                        <span class="zone-dot" style="background:#FF7222"></span>区域2
                    </span>
                    <span>▼</span>
                </div>
                <div class="zone-body">
                    <p style="font-size:12px;color:#666;margin-bottom:8px;">点击编辑后，在下方画面拖动顶点</p>
                    <div class="btn-group">
                        <button class="btn btn-edit" onclick="startEditZone(2)">编辑</button>
                        <button class="btn btn-confirm" onclick="confirmZone(2)">确定</button>
                    </div>
                </div>
            </div>
            
            <div class="zone-item" id="zone-item-3">
                <div class="zone-header" onclick="toggleZone(3)">
                    <span class="zone-title">
                        <span class="zone-dot" style="background:#2196F3"></span>区域3
                    </span>
                    <span>▼</span>
                </div>
                <div class="zone-body">
                    <p style="font-size:12px;color:#666;margin-bottom:8px;">点击编辑后，在下方画面拖动顶点</p>
                    <div class="btn-group">
                        <button class="btn btn-edit" onclick="startEditZone(3)">编辑</button>
                        <button class="btn btn-confirm" onclick="confirmZone(3)">确定</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // ========== 全局变量 ==========
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        
        const correctedImg = document.getElementById('corrected');
        const correctedCanvas = document.getElementById('corrected-canvas');
        const correctedCtx = correctedCanvas.getContext('2d');
        
        let corners = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]];
        let zones = [
            {id:1, points:[[50,100],[200,100],[200,300],[50,300]], color:'#33B555'},
            {id:2, points:[[220,100],[420,100],[420,300],[220,300]], color:'#FF7222'},
            {id:3, points:[[440,100],[590,100],[590,300],[440,300]], color:'#2196F3'}
        ];
        
        let draggingCorner = -1;
        let draggingZone = -1;
        let draggingPoint = -1;
        let editingZone = null;
        let mouseDown = false;

        // ========== 初始化 ==========
        function init() {
            fetch('/api/config').then(r => r.json()).then(d => {
                if (d.corners) corners = d.corners;
                if (d.zones) zones = d.zones;
            });
            resize();
            requestAnimationFrame(draw);
            setInterval(updateStatus, 500);
        }

        function resize() {
            canvas.width = video.clientWidth;
            canvas.height = video.clientHeight;
            correctedCanvas.width = correctedImg.clientWidth;
            correctedCanvas.height = correctedImg.clientHeight;
        }
        video.onload = resize;
        correctedImg.onload = resize;
        window.onresize = resize;
        setTimeout(resize, 500);

        // ========== 绘制 ==========
        function draw() {
            // 绘制上方校准框
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const w = canvas.width, h = canvas.height;
            
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
            
            corners.forEach((p, i) => {
                const x = p[0] * w, y = p[1] * h;
                ctx.beginPath();
                ctx.arc(x, y, 12, 0, Math.PI * 2);
                ctx.fillStyle = '#0066cc';
                ctx.fill();
                ctx.fillStyle = '#fff';
                ctx.font = 'bold 11px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(i + 1, x, y);
            });
            
            // 绘制下方区域
            correctedCtx.clearRect(0, 0, correctedCanvas.width, correctedCanvas.height);
            const cw = correctedCanvas.width, ch = correctedCanvas.height;
            const scaleX = cw / 640, scaleY = ch / 360;
            
            zones.forEach(zone => {
                const isEditing = editingZone === zone.id;
                
                // 绘制区域
                correctedCtx.strokeStyle = zone.color;
                correctedCtx.lineWidth = isEditing ? 4 : 2;
                correctedCtx.beginPath();
                zone.points.forEach((p, i) => {
                    const x = p[0] * scaleX, y = p[1] * scaleY;
                    if (i === 0) correctedCtx.moveTo(x, y);
                    else correctedCtx.lineTo(x, y);
                });
                correctedCtx.closePath();
                correctedCtx.stroke();
                
                if (isEditing) {
                    correctedCtx.fillStyle = zone.color + '20';
                    correctedCtx.fill();
                }
                
                // 绘制顶点（仅编辑模式）
                if (isEditing) {
                    zone.points.forEach((p, i) => {
                        const x = p[0] * scaleX, y = p[1] * scaleY;
                        correctedCtx.beginPath();
                        correctedCtx.arc(x, y, 10, 0, Math.PI * 2);
                        correctedCtx.fillStyle = '#fff';
                        correctedCtx.fill();
                        correctedCtx.strokeStyle = zone.color;
                        correctedCtx.lineWidth = 3;
                        correctedCtx.stroke();
                        
                        correctedCtx.fillStyle = '#333';
                        correctedCtx.font = 'bold 10px Arial';
                        correctedCtx.textAlign = 'center';
                        correctedCtx.textBaseline = 'middle';
                        correctedCtx.fillText(i + 1, x, y);
                    });
                }
            });
            
            requestAnimationFrame(draw);
        }

        // ========== 上方校准框交互 ==========
        canvas.onmousedown = (e) => {
            const pos = getPos(e, canvas);
            for (let i = 0; i < corners.length; i++) {
                const d = Math.hypot(corners[i][0] - pos.x, corners[i][1] - pos.y);
                if (d < 0.05) {
                    draggingCorner = i;
                    mouseDown = true;
                    break;
                }
            }
        };
        
        canvas.onmousemove = (e) => {
            if (!mouseDown || draggingCorner < 0) return;
            const pos = getPos(e, canvas);
            corners[draggingCorner] = [
                Math.max(0.02, Math.min(0.98, pos.x)),
                Math.max(0.02, Math.min(0.98, pos.y))
            ];
        };
        
        canvas.onmouseup = () => {
            if (mouseDown && draggingCorner >= 0) saveCorners();
            mouseDown = false;
            draggingCorner = -1;
        };
        
        canvas.onmouseleave = () => {
            if (mouseDown && draggingCorner >= 0) saveCorners();
            mouseDown = false;
            draggingCorner = -1;
        };

        // ========== 下方区域交互 ==========
        correctedCanvas.onmousedown = (e) => {
            if (!editingZone) return;
            const pos = getPosCorrected(e);
            const zone = zones.find(z => z.id === editingZone);
            if (!zone) return;
            
            for (let i = 0; i < zone.points.length; i++) {
                const d = Math.hypot(zone.points[i][0] - pos.x, zone.points[i][1] - pos.y);
                if (d < 25) {
                    draggingZone = editingZone;
                    draggingPoint = i;
                    mouseDown = true;
                    break;
                }
            }
        };
        
        correctedCanvas.onmousemove = (e) => {
            if (!mouseDown || draggingZone < 0 || draggingPoint < 0) return;
            const pos = getPosCorrected(e);
            const zone = zones.find(z => z.id === draggingZone);
            if (zone) {
                zone.points[draggingPoint] = [
                    Math.max(10, Math.min(630, pos.x)),
                    Math.max(10, Math.min(350, pos.y))
                ];
            }
        };
        
        correctedCanvas.onmouseup = () => {
            mouseDown = false;
            draggingZone = -1;
            draggingPoint = -1;
        };
        
        correctedCanvas.onmouseleave = () => {
            mouseDown = false;
            draggingZone = -1;
            draggingPoint = -1;
        };

        // ========== 工具函数 ==========
        function getPos(e, c) {
            const rect = c.getBoundingClientRect();
            return {
                x: (e.clientX - rect.left) / c.width,
                y: (e.clientY - rect.top) / c.height
            };
        }
        
        function getPosCorrected(e) {
            const rect = correctedCanvas.getBoundingClientRect();
            return {
                x: (e.clientX - rect.left) / correctedCanvas.width * 640,
                y: (e.clientY - rect.top) / correctedCanvas.height * 360
            };
        }

        // ========== 区域编辑 ==========
        function toggleZone(id) {
            const item = document.getElementById('zone-item-' + id);
            document.querySelectorAll('.zone-item').forEach(el => {
                if (el.id !== 'zone-item-' + id) el.classList.remove('active');
            });
            item.classList.toggle('active');
        }
        
        function startEditZone(id) {
            editingZone = id;
            document.querySelectorAll('.zone-item').forEach(el => el.classList.remove('editing'));
            document.getElementById('zone-item-' + id).classList.add('editing');
        }
        
        function confirmZone(id) {
            editingZone = null;
            document.getElementById('zone-item-' + id).classList.remove('editing');
            saveZones();
        }

        // ========== 保存 ==========
        function saveCorners() {
            fetch('/api/corners', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({corners: corners})
            });
        }
        
        function saveZones() {
            fetch('/api/zones', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({zones: zones})
            });
        }

        // ========== 状态更新 ==========
        function updateStatus() {
            fetch('/api/status').then(r => r.json()).then(d => {
                const feetEl = document.getElementById('feet-status');
                const zoneEl = document.getElementById('zone-status');
                
                if (d.feet_detected) {
                    feetEl.textContent = '已检测';
                    feetEl.className = 'detected';
                } else {
                    feetEl.textContent = '未检测到';
                    feetEl.className = 'not-detected';
                }
                
                if (d.active_zone) {
                    zoneEl.textContent = '区域' + d.active_zone;
                    zoneEl.className = 'detected';
                } else {
                    zoneEl.textContent = '未进入';
                    zoneEl.className = 'not-detected';
                }
            });
        }

        setTimeout(init, 1000);
    </script>
</body>
</html>
"""

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
        
        /* 顶部状态文字 */
        #status-text {
            position: absolute;
            top: 5%;
            left: 50%;
            transform: translateX(-50%);
            font-size: 8vw;
            font-weight: bold;
            color: #333;
            z-index: 100;
            white-space: nowrap;
        }
        #status-text.in-zone {
            color: #33B555;
        }
        
        /* 脚部圆点 */
        #foot-point {
            width: 120px;
            height: 120px;
            background: radial-gradient(circle, #33B555 0%, #228B22 100%);
            border-radius: 50%;
            position: absolute;
            transform: translate(-50%, -50%);
            box-shadow: 0 0 40px rgba(51, 181, 85, 0.6);
            display: none;
            z-index: 50;
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
        
        /* 三个区域边框 */
        .zone-border {
            position: absolute;
            border: 4px solid;
            pointer-events: none;
            border-radius: 8px;
        }
        .zone-border.active {
            border-width: 6px;
            box-shadow: 0 0 20px currentColor;
        }
        .zone-label {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 2vw;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div id="status-text">未进入区域</div>
    <div id="foot-point"></div>
    <div id="zones-layer"></div>

    <script>
        const statusText = document.getElementById('status-text');
        const footPoint = document.getElementById('foot-point');
        const zonesLayer = document.getElementById('zones-layer');
        
        const projW = 640, projH = 360;
        let zones = [];
        let activeZone = null;

        function init() {
            fetch('/api/config').then(r => r.json()).then(d => {
                zones = d.zones || [];
                drawZones();
            });
            setInterval(update, 50);
            setInterval(loadConfig, 2000);
        }

        function drawZones() {
            zonesLayer.innerHTML = '';
            zones.forEach(zone => {
                const xs = zone.points.map(p => p[0]);
                const ys = zone.points.map(p => p[1]);
                const minX = Math.min(...xs), maxX = Math.max(...xs);
                const minY = Math.min(...ys), maxY = Math.max(...ys);
                
                const div = document.createElement('div');
                div.className = 'zone-border' + (activeZone === zone.id ? ' active' : '');
                div.style.left = (minX / projW * 100) + '%';
                div.style.top = (minY / projH * 100) + '%';
                div.style.width = ((maxX - minX) / projW * 100) + '%';
                div.style.height = ((maxY - minY) / projH * 100) + '%';
                div.style.borderColor = zone.color;
                div.style.color = zone.color;
                
                const label = document.createElement('div');
                label.className = 'zone-label';
                label.textContent = '区域' + zone.id;
                label.style.color = zone.color;
                div.appendChild(label);
                
                zonesLayer.appendChild(div);
            });
        }

        function update() {
            fetch('/api/status')
                .then(r => r.json())
                .then(d => {
                    // 更新状态文字
                    if (d.active_zone) {
                        statusText.textContent = '已进入区域' + d.active_zone;
                        statusText.className = 'in-zone';
                    } else {
                        statusText.textContent = '未进入区域';
                        statusText.className = '';
                    }
                    
                    // 更新脚部圆点
                    if (d.feet_detected) {
                        footPoint.style.display = 'block';
                        footPoint.style.left = (d.feet_x / projW * 100) + '%';
                        footPoint.style.top = (d.feet_y / projH * 100) + '%';
                    } else {
                        footPoint.style.display = 'none';
                    }
                    
                    // 更新区域高亮
                    if (d.active_zone !== activeZone) {
                        activeZone = d.active_zone;
                        drawZones();
                    }
                });
        }
        
        function loadConfig() {
            fetch('/api/config').then(r => r.json()).then(d => {
                zones = d.zones || [];
                drawZones();
            });
        }

        init();
    </script>
</body>
</html>
"""

# ============================================================================
# 路由
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

@app.route('/api/config')
def api_config():
    return jsonify({
        "corners": state["corners"],
        "zones": state["zones"]
    })

@app.route('/api/corners', methods=['POST'])
def api_corners():
    data = request.json
    state["corners"] = data.get("corners", state["corners"])
    processor.update_matrix()
    return jsonify({"ok": True})

@app.route('/api/zones', methods=['POST'])
def api_zones():
    data = request.json
    state["zones"] = data.get("zones", state["zones"])
    return jsonify({"ok": True})

@app.route('/api/status')
def api_status():
    return jsonify({
        "feet_detected": state["feet_detected"],
        "feet_x": state["feet_x"],
        "feet_y": state["feet_y"],
        "active_zone": state["active_zone"]
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
