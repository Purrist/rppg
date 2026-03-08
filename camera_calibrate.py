# -*- coding: utf-8 -*-
"""
地面投影交互系统 V13
点击终端链接自动打开全屏Kiosk模式
"""

import cv2
import mediapipe as mp
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify
import threading
import time
import json
import os
import subprocess
import sys
import platform

app = Flask(__name__)

CONFIG_FILE = "projection_config.json"

# ============================================================================
# 自动打开浏览器的函数
# ============================================================================
def open_admin_browser():
    """打开Admin页面（普通浏览器）"""
    time.sleep(1.5)
    url = "http://127.0.0.1:5000/admin"
    
    if platform.system() == 'Windows':
        # Windows: 使用start命令打开默认浏览器
        os.system(f'start "" "{url}"')
    elif platform.system() == 'Darwin':
        # macOS
        os.system(f'open "{url}"')
    else:
        # Linux
        os.system(f'xdg-open "{url}"')
    
    print(f"✓ Admin页面已打开: {url}")

def open_projection_kiosk():
    """打开Projection页面（Kiosk全屏模式）"""
    time.sleep(2)
    url = "http://127.0.0.1:5000/projection"
    
    if platform.system() == 'Windows':
        # Windows: 优先使用Edge Kiosk模式
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        
        edge_found = False
        for edge_path in edge_paths:
            if os.path.exists(edge_path):
                cmd = f'"{edge_path}" --kiosk --edge-kiosk-type=fullscreen {url}'
                subprocess.Popen(cmd, shell=True)
                print(f"✓ Projection已打开 (Edge Kiosk全屏): {url}")
                edge_found = True
                break
        
        if not edge_found:
            # 尝试Chrome Kiosk模式
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
            
            for chrome_path in chrome_paths:
                if os.path.exists(chrome_path):
                    cmd = f'"{chrome_path}" --kiosk {url}'
                    subprocess.Popen(cmd, shell=True)
                    print(f"✓ Projection已打开 (Chrome Kiosk全屏): {url}")
                    return
            
            # 都没有，用默认浏览器
            os.system(f'start "" "{url}"')
            print(f"✓ Projection已打开 (默认浏览器): {url}")
    
    elif platform.system() == 'Darwin':
        # macOS
        os.system(f'open "{url}"')
        print(f"✓ Projection已打开: {url}")
    else:
        # Linux
        os.system(f'xdg-open "{url}"')
        print(f"✓ Projection已打开: {url}")

# ============================================================================
# 平滑滤波器
# ============================================================================
class SmoothFilter:
    def __init__(self, alpha=0.5, threshold=30):
        self.alpha = alpha
        self.threshold = threshold
        self.value = None
    
    def update(self, new_value):
        if self.value is None:
            self.value = new_value
            return new_value
        diff = abs(new_value - self.value)
        alpha = 0.8 if diff > self.threshold else self.alpha
        self.value = alpha * new_value + (1 - alpha) * self.value
        return self.value

class PositionSmoother:
    def __init__(self):
        self.x_filter = SmoothFilter(alpha=0.4, threshold=25)
        self.y_filter = SmoothFilter(alpha=0.4, threshold=25)
        self.last_x = None
        self.last_y = None
        self.last_time = 0
    
    def update(self, x, y, detected):
        if detected:
            smooth_x = self.x_filter.update(x)
            smooth_y = self.y_filter.update(y)
            self.last_x = smooth_x
            self.last_y = smooth_y
            self.last_time = time.time()
            return int(smooth_x), int(smooth_y), True
        elif self.last_x is not None and time.time() - self.last_time < 0.3:
            return int(self.last_x), int(self.last_y), True
        return x, y, False

# ============================================================================
# 全局状态
# ============================================================================
state = {
    "corners": [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]],
    "zones": [
        {"id": 1, "name": "1", "type": "rect", "points": [[50, 80], [180, 80], [180, 280], [50, 280]], "color": "#33B555"},
        {"id": 2, "name": "2", "type": "rect", "points": [[230, 80], [410, 80], [410, 280], [230, 280]], "color": "#FF7222"},
        {"id": 3, "name": "3", "type": "rect", "points": [[460, 80], [590, 80], [590, 280], [460, 280]], "color": "#2196F3"}
    ],
    "feet_x": 320,
    "feet_y": 180,
    "feet_detected": False,
    "active_zones": [],
    "matrix": None,
    "zone_id_counter": 4,
    "admin_bg": "#ffffff",
    "projection_bg": "#000000"
}

ZONE_COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", 
               "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B",
               "#4CAF50", "#3F51B5"]

def save_config_to_file():
    config = {
        "corners": state["corners"],
        "zones": state["zones"],
        "zone_id_counter": state["zone_id_counter"],
        "admin_bg": state["admin_bg"],
        "projection_bg": state["projection_bg"]
    }
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except:
        return False

def load_config_from_file():
    global state
    if not os.path.exists(CONFIG_FILE):
        return False
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if "corners" in config: state["corners"] = config["corners"]
        if "zones" in config: state["zones"] = config["zones"]
        if "zone_id_counter" in config: state["zone_id_counter"] = config["zone_id_counter"]
        if "admin_bg" in config: state["admin_bg"] = config["admin_bg"]
        if "projection_bg" in config: state["projection_bg"] = config["projection_bg"]
        return True
    except:
        return False

load_config_from_file()

# ============================================================================
# 处理器
# ============================================================================
class Processor:
    def __init__(self):
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
            model_complexity=1,
            smooth_landmarks=True
        )
        
        self.raw_frame = None
        self.corrected_frame = None
        self.running = True
        self.position_smoother = PositionSmoother()
        
        threading.Thread(target=self._loop, daemon=True).start()
    
    def _loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            frame = cv2.flip(frame, 0)
            frame = cv2.flip(frame, 1)
            
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb)
            
            raw_feet_detected = False
            raw_feet_x, raw_feet_y = 320, 180
            
            if results.pose_landmarks:
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)
                
                lm = results.pose_landmarks.landmark
                left_ankle = lm[27]
                right_ankle = lm[28]
                
                if left_ankle.visibility > 0.5 and right_ankle.visibility > 0.5:
                    l_pt = (int(left_ankle.x * w), int(left_ankle.y * h))
                    r_pt = (int(right_ankle.x * w), int(right_ankle.y * h))
                    
                    cv2.circle(frame, l_pt, 15, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 15, (0, 255, 0), -1)
                    cv2.line(frame, l_pt, r_pt, (0, 255, 255), 3)
                    
                    center = ((l_pt[0] + r_pt[0]) // 2, (l_pt[1] + r_pt[1]) // 2)
                    cv2.circle(frame, center, 10, (255, 0, 255), -1)
                    
                    if state["matrix"] is not None:
                        try:
                            src_pt = np.array([[[center[0], center[1]]]], dtype=np.float32)
                            dst_pt = cv2.perspectiveTransform(src_pt, state["matrix"])[0][0]
                            raw_feet_x, raw_feet_y = int(dst_pt[0]), int(dst_pt[1])
                            raw_feet_detected = True
                        except:
                            pass
            
            smooth_x, smooth_y, smooth_detected = self.position_smoother.update(
                raw_feet_x, raw_feet_y, raw_feet_detected
            )
            
            active_zones = []
            if smooth_detected:
                for zone in state["zones"]:
                    if self._point_in_zone(smooth_x, smooth_y, zone):
                        active_zones.append(zone["id"])
            
            state["feet_x"] = smooth_x
            state["feet_y"] = smooth_y
            state["feet_detected"] = smooth_detected
            state["active_zones"] = active_zones
            
            pts = np.array([[int(c[0]*w), int(c[1]*h)] for c in state["corners"]], np.int32)
            cv2.polylines(frame, [pts], True, (255, 0, 0), 2)
            for i, c in enumerate(state["corners"]):
                x, y = int(c[0]*w), int(c[1]*h)
                cv2.circle(frame, (x, y), 10, (255, 0, 0), -1)
                cv2.putText(frame, str(i+1), (x-6, y+4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
            
            corrected = np.ones((360, 640, 3), dtype=np.uint8) * 255
            if state["matrix"] is not None:
                try:
                    corrected = cv2.warpPerspective(frame, state["matrix"], (640, 360))
                except:
                    pass
            
            for zone in state["zones"]:
                self._draw_zone(corrected, zone, zone["id"] in active_zones)
            
            if smooth_detected:
                cv2.circle(corrected, (smooth_x, smooth_y), 20, (0, 200, 0), -1)
            
            self.raw_frame = frame
            self.corrected_frame = corrected
            time.sleep(0.005)
    
    def _point_in_zone(self, x, y, zone):
        if zone.get("type") == "circle":
            cx, cy, r = int(zone["center"][0]), int(zone["center"][1]), int(zone["radius"])
            return (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2
        else:
            pts = np.array(zone["points"], dtype=np.int32)
            return cv2.pointPolygonTest(pts, (x, y), False) >= 0
    
    def _draw_zone(self, img, zone, is_active):
        hex_color = zone["color"].lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        bgr = (rgb[2], rgb[1], rgb[0])
        
        if zone.get("type") == "circle":
            cx, cy, r = int(zone["center"][0]), int(zone["center"][1]), int(zone["radius"])
            cv2.circle(img, (cx, cy), r, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.circle(overlay, (cx, cy), r, bgr, -1)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            cv2.putText(img, zone.get("name", str(zone["id"])), (cx-10, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)
        else:
            pts = np.array(zone["points"], dtype=np.int32)
            cv2.polylines(img, [pts], True, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.fillPoly(overlay, [pts], bgr)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            cx = int(np.mean([p[0] for p in zone["points"]]))
            cy = int(np.mean([p[1] for p in zone["points"]]))
            cv2.putText(img, zone.get("name", str(zone["id"])), (cx-10, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)
    
    def get_raw_jpeg(self):
        if self.raw_frame is None: return None
        _, buf = cv2.imencode('.jpg', self.raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def get_corrected_jpeg(self):
        if self.corrected_frame is None: return None
        _, buf = cv2.imencode('.jpg', self.corrected_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()
    
    def update_matrix(self):
        if self.raw_frame is None: return
        h, w = self.raw_frame.shape[:2]
        src = np.array([[c[0]*w, c[1]*h] for c in state["corners"]], dtype=np.float32)
        dst = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], dtype=np.float32)
        state["matrix"] = cv2.getPerspectiveTransform(src, dst)

processor = Processor()

def delayed_init():
    time.sleep(2)
    processor.update_matrix()
    print("✓ 透视矩阵已更新")

threading.Thread(target=delayed_init, daemon=True).start()

# ============================================================================
# HTML模板 - Admin
# ============================================================================
HTML_ADMIN = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Admin</title>
    <style>
        * { margin: 0; padding: 0; border: 0; box-sizing: border-box; }
        body { background: #fff; color: #333; font-family: sans-serif; padding: 10px; }
        h1 { font-size: 16px; margin-bottom: 8px; }
        
        .video-container { width: 640px; max-width: 100%; position: relative; background: #000; margin-bottom: 10px; }
        #video { display: block; width: 100%; }
        #canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; }
        
        .corrected-container { width: 640px; max-width: 100%; position: relative; background: #f5f5f5; border: 2px solid #33B555; margin-bottom: 10px; }
        #corrected { display: block; width: 100%; }
        #corrected-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: move; }
        
        .status-bar { width: 640px; max-width: 100%; background: #f0f0f0; padding: 6px 10px; border-radius: 4px; font-size: 12px; margin-bottom: 10px; display: flex; gap: 15px; }
        .detected { color: #33B555; font-weight: bold; }
        .not-detected { color: #ff6b6b; }
        
        .control-panel { width: 640px; max-width: 100%; background: #fafafa; border: 1px solid #ddd; border-radius: 6px; padding: 10px; }
        .section-title { font-size: 12px; font-weight: bold; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #ddd; }
        
        .settings-row { display: flex; gap: 20px; margin-bottom: 10px; padding: 8px; background: #fff; border-radius: 4px; }
        .setting-item { display: flex; align-items: center; gap: 8px; }
        .setting-item label { font-size: 12px; }
        .setting-item input[type="color"] { width: 40px; height: 30px; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; }
        
        .save-load-row { display: flex; gap: 10px; margin-bottom: 10px; }
        .save-btn { flex: 1; padding: 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: bold; color: #fff; }
        .btn-save-all { background: #4CAF50; }
        .btn-load-all { background: #2196F3; }
        
        .add-buttons { display: flex; gap: 5px; margin-bottom: 10px; }
        .add-btn { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 12px; }
        .add-btn:hover { background: #e8f5e9; }
        
        .zone-item { background: #fff; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 5px; }
        .zone-header { padding: 6px 8px; display: flex; align-items: center; gap: 6px; cursor: grab; }
        .drag-handle { color: #999; cursor: grab; }
        .zone-dot { width: 12px; height: 12px; border-radius: 50%; }
        .zone-name-input { border: none; background: transparent; font-size: 12px; font-weight: bold; width: 50px; }
        .zone-name-input:focus { outline: none; background: #fffde7; }
        .zone-type { font-size: 10px; color: #888; }
        .zone-actions { margin-left: auto; display: flex; gap: 4px; }
        .zone-btn { padding: 3px 8px; border: none; border-radius: 3px; cursor: pointer; font-size: 10px; color: #fff; }
        .btn-edit { background: #FF7222; }
        .btn-confirm { background: #33B555; }
        .btn-delete { background: #f44336; }
        .btn-copy { background: #2196F3; }
        .zone-item.editing { border-color: #FF7222; }
        .zone-item.dragging { opacity: 0.5; }
        
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 20px; border-radius: 4px; display: none; z-index: 1000; }
    </style>
</head>
<body>
    <h1>摄像头校准管理</h1>
    
    <div class="video-container">
        <img id="video" src="/video_feed">
        <canvas id="canvas"></canvas>
    </div>
    
    <p style="font-size:11px;color:#666;margin:5px 0;">↓ 矫正后的16:9画面 ↓</p>
    
    <div class="corrected-container">
        <img id="corrected" src="/corrected_feed">
        <canvas id="corrected-canvas"></canvas>
    </div>
    
    <div class="status-bar">
        <span>脚部: <span id="feet-status" class="not-detected">未检测到</span></span>
        <span>区域: <span id="zone-status">未进入</span></span>
    </div>
    
    <div class="control-panel">
        <div class="section-title">⚙️ 设置</div>
        <div class="settings-row">
            <div class="setting-item">
                <label>Admin背景:</label>
                <input type="color" id="admin-bg-input" value="#ffffff" onchange="updateAdminBg(this.value)">
            </div>
            <div class="setting-item">
                <label>Projection背景:</label>
                <input type="color" id="projection-bg-input" value="#000000" onchange="updateProjectionBg(this.value)">
            </div>
        </div>
        
        <div class="section-title">💾 配置保存/加载</div>
        <div class="save-load-row">
            <button class="save-btn btn-save-all" onclick="saveAllConfig()">保存全部</button>
            <button class="save-btn btn-load-all" onclick="loadAllConfig()">加载全部</button>
        </div>
        
        <div class="section-title">添加区域 (<span id="zone-count">3</span>/12)</div>
        <div class="add-buttons">
            <button class="add-btn" onclick="addZone('rect')">▢ 矩形</button>
            <button class="add-btn" onclick="addZone('triangle')">△ 三角形</button>
            <button class="add-btn" onclick="addZone('circle')">○ 圆形</button>
            <button class="add-btn" onclick="addZone('quad')">◇ 四边形</button>
        </div>
        
        <div class="section-title">区域列表</div>
        <div class="zone-list" id="zone-list"></div>
    </div>
    
    <div id="toast" class="toast"></div>

    <script>
        let corners = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]];
        let zones = [];
        let zoneIdCounter = 4;
        let adminBg = "#ffffff";
        let projectionBg = "#000000";
        let editingZone = null;
        let draggingCorner = -1;
        let mouseDown = false;
        let dragMode = null;
        let dragStartPos = null;
        let dragStartData = null;
        let draggedZoneId = null;

        const COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B", "#4CAF50", "#3F51B5"];
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const correctedImg = document.getElementById('corrected');
        const correctedCanvas = document.getElementById('corrected-canvas');
        const correctedCtx = correctedCanvas.getContext('2d');

        function showToast(msg) {
            document.getElementById('toast').textContent = msg;
            document.getElementById('toast').style.display = 'block';
            setTimeout(() => document.getElementById('toast').style.display = 'none', 2000);
        }

        function init() {
            fetch('/api/config').then(r => r.json()).then(d => {
                if (d.corners) corners = d.corners;
                if (d.zones) zones = d.zones;
                if (d.zone_id_counter) zoneIdCounter = d.zone_id_counter;
                if (d.admin_bg) { adminBg = d.admin_bg; document.getElementById('admin-bg-input').value = adminBg; document.body.style.backgroundColor = adminBg; }
                if (d.projection_bg) { projectionBg = d.projection_bg; document.getElementById('projection-bg-input').value = projectionBg; }
                renderZoneList();
            });
            resize();
            requestAnimationFrame(draw);
            setInterval(updateStatus, 300);
        }

        function resize() {
            canvas.width = video.offsetWidth; canvas.height = video.offsetHeight;
            correctedCanvas.width = correctedImg.offsetWidth; correctedCanvas.height = correctedImg.offsetHeight;
        }
        video.onload = resize; correctedImg.onload = resize; window.onresize = resize; setTimeout(resize, 500);

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const w = canvas.width, h = canvas.height;
            ctx.strokeStyle = '#0066cc'; ctx.lineWidth = 2;
            ctx.beginPath();
            corners.forEach((p, i) => { const x = p[0] * w, y = p[1] * h; i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
            ctx.closePath(); ctx.stroke(); ctx.fillStyle = 'rgba(0, 102, 204, 0.1)'; ctx.fill();
            corners.forEach((p, i) => {
                const x = p[0] * w, y = p[1] * h;
                ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fillStyle = '#0066cc'; ctx.fill();
                ctx.fillStyle = '#fff'; ctx.font = 'bold 10px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(i + 1, x, y);
            });
            
            correctedCtx.clearRect(0, 0, correctedCanvas.width, correctedCanvas.height);
            const scaleX = correctedCanvas.width / 640, scaleY = correctedCanvas.height / 360;
            zones.forEach(zone => drawZone(correctedCtx, zone, scaleX, scaleY, editingZone === zone.id));
            requestAnimationFrame(draw);
        }

        function drawZone(ctx, zone, scaleX, scaleY, isEditing) {
            ctx.strokeStyle = zone.color; ctx.lineWidth = isEditing ? 3 : 2;
            if (zone.type === 'circle') {
                const cx = zone.center[0] * scaleX, cy = zone.center[1] * scaleY, r = zone.radius * Math.min(scaleX, scaleY);
                ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
                if (isEditing) {
                    ctx.beginPath(); ctx.arc(cx, cy, 12, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill(); ctx.strokeStyle = zone.color; ctx.lineWidth = 3; ctx.stroke();
                    ctx.beginPath(); ctx.arc(cx + r, cy, 10, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill(); ctx.stroke();
                }
            } else {
                const points = zone.points.map(p => [p[0] * scaleX, p[1] * scaleY]);
                ctx.beginPath(); points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])); ctx.closePath(); ctx.stroke();
                if (isEditing) {
                    ctx.fillStyle = zone.color + '30'; ctx.fill();
                    if (zone.type === 'rect') { const centerX = (points[0][0] + points[2][0]) / 2, centerY = (points[0][1] + points[2][1]) / 2; ctx.beginPath(); ctx.arc(centerX, centerY, 15, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill(); ctx.strokeStyle = zone.color; ctx.lineWidth = 3; ctx.stroke(); }
                    ctx.strokeStyle = zone.color; ctx.lineWidth = 2;
                    points.forEach(p => { ctx.beginPath(); ctx.arc(p[0], p[1], 10, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill(); ctx.stroke(); });
                }
            }
        }

        canvas.onmousedown = (e) => { const rect = canvas.getBoundingClientRect(); const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }; for (let i = 0; i < corners.length; i++) { if (Math.hypot(corners[i][0] - pos.x, corners[i][1] - pos.y) < 0.05) { draggingCorner = i; mouseDown = true; break; } } };
        canvas.onmousemove = (e) => { if (!mouseDown || draggingCorner < 0) return; const rect = canvas.getBoundingClientRect(); const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }; corners[draggingCorner] = [Math.max(0.02, Math.min(0.98, pos.x)), Math.max(0.02, Math.min(0.98, pos.y))]; };
        canvas.onmouseup = () => { if (mouseDown && draggingCorner >= 0) saveCorners(); mouseDown = false; draggingCorner = -1; };
        canvas.onmouseleave = () => { if (mouseDown && draggingCorner >= 0) saveCorners(); mouseDown = false; draggingCorner = -1; };

        correctedCanvas.onmousedown = (e) => {
            if (!editingZone) return;
            const rect = correctedCanvas.getBoundingClientRect();
            const pos = { x: (e.clientX - rect.left) / rect.width * 640, y: (e.clientY - rect.top) / rect.height * 360 };
            const zone = zones.find(z => z.id === editingZone);
            if (!zone) return;
            dragStartPos = { x: pos.x, y: pos.y }; dragStartData = JSON.parse(JSON.stringify(zone)); mouseDown = true;
            if (zone.type === 'circle') {
                const dCenter = Math.hypot(pos.x - zone.center[0], pos.y - zone.center[1]);
                if (dCenter < 15) dragMode = 'move';
                else if (Math.abs(Math.hypot(pos.x - zone.center[0], pos.y - zone.center[1]) - zone.radius) < 15) dragMode = 'resize';
                else mouseDown = false;
            } else if (zone.type === 'rect') {
                const centerX = (zone.points[0][0] + zone.points[2][0]) / 2, centerY = (zone.points[0][1] + zone.points[2][1]) / 2;
                if (Math.hypot(pos.x - centerX, pos.y - centerY) < 20) dragMode = 'move';
                else { let found = -1; for (let i = 0; i < 4; i++) { if (Math.hypot(zone.points[i][0] - pos.x, zone.points[i][1] - pos.y) < 15) { found = i; break; } } if (found >= 0) dragMode = 'vertex-' + found; else mouseDown = false; }
            } else {
                let found = -1; for (let i = 0; i < zone.points.length; i++) { if (Math.hypot(zone.points[i][0] - pos.x, zone.points[i][1] - pos.y) < 15) { found = i; break; } } if (found >= 0) dragMode = 'point-' + found; else mouseDown = false;
            }
        };

        correctedCanvas.onmousemove = (e) => {
            if (!mouseDown || !editingZone || !dragMode) return;
            const rect = correctedCanvas.getBoundingClientRect();
            const pos = { x: (e.clientX - rect.left) / rect.width * 640, y: (e.clientY - rect.top) / rect.height * 360 };
            const zone = zones.find(z => z.id === editingZone); if (!zone) return;
            const dx = pos.x - dragStartPos.x, dy = pos.y - dragStartPos.y;
            if (zone.type === 'circle') {
                if (dragMode === 'move') { zone.center[0] = Math.max(30, Math.min(610, dragStartData.center[0] + dx)); zone.center[1] = Math.max(30, Math.min(330, dragStartData.center[1] + dy)); }
                else if (dragMode === 'resize') { zone.radius = Math.max(20, Math.min(150, Math.hypot(pos.x - zone.center[0], pos.y - zone.center[1]))); }
            } else if (zone.type === 'rect') {
                if (dragMode === 'move') { const w = dragStartData.points[2][0] - dragStartData.points[0][0], h = dragStartData.points[2][1] - dragStartData.points[0][1]; let newX = Math.max(10, Math.min(630 - w, dragStartData.points[0][0] + dx)), newY = Math.max(10, Math.min(350 - h, dragStartData.points[0][1] + dy)); zone.points = [[newX, newY], [newX + w, newY], [newX + w, newY + h], [newX, newY + h]]; }
                else if (dragMode.startsWith('vertex-')) { const idx = parseInt(dragMode.split('-')[1]); let newX = Math.max(10, Math.min(630, pos.x)), newY = Math.max(10, Math.min(350, pos.y)); if (idx === 0) { zone.points[0] = [newX, newY]; zone.points[1][1] = newY; zone.points[3][0] = newX; } else if (idx === 1) { zone.points[1] = [newX, newY]; zone.points[0][1] = newY; zone.points[2][0] = newX; } else if (idx === 2) { zone.points[2] = [newX, newY]; zone.points[1][0] = newX; zone.points[3][1] = newY; } else if (idx === 3) { zone.points[3] = [newX, newY]; zone.points[0][0] = newX; zone.points[2][1] = newY; } }
            } else { if (dragMode.startsWith('point-')) { const idx = parseInt(dragMode.split('-')[1]); zone.points[idx] = [Math.max(10, Math.min(630, pos.x)), Math.max(10, Math.min(350, pos.y))]; } }
        };

        correctedCanvas.onmouseup = () => { if (mouseDown) saveZones(); mouseDown = false; dragMode = null; };
        correctedCanvas.onmouseleave = () => { if (mouseDown) saveZones(); mouseDown = false; dragMode = null; };

        function addZone(type) {
            if (zones.length >= 12) { alert('最多12个区域'); return; }
            const id = zoneIdCounter++, color = COLORS[(id - 1) % COLORS.length], baseX = 100 + Math.random() * 400, baseY = 100 + Math.random() * 150;
            let newZone;
            if (type === 'rect') newZone = { id, name: String(id), type: 'rect', points: [[baseX, baseY], [baseX+100, baseY], [baseX+100, baseY+100], [baseX, baseY+100]], color };
            else if (type === 'triangle') newZone = { id, name: String(id), type: 'triangle', points: [[baseX+50, baseY], [baseX+100, baseY+100], [baseX, baseY+100]], color };
            else if (type === 'circle') newZone = { id, name: String(id), type: 'circle', center: [baseX+50, baseY+50], radius: 50, color };
            else newZone = { id, name: String(id), type: 'quad', points: [[baseX, baseY], [baseX+120, baseY+20], [baseX+100, baseY+100], [baseX+20, baseY+80]], color };
            zones.push(newZone); renderZoneList(); saveZones();
        }

        function copyZone(id) {
            if (zones.length >= 12) { alert('最多12个区域'); return; }
            const zone = zones.find(z => z.id === id); if (!zone) return;
            const newId = zoneIdCounter++, newZone = JSON.parse(JSON.stringify(zone));
            newZone.id = newId; newZone.name = String(newId); newZone.color = COLORS[(newId - 1) % COLORS.length];
            if (newZone.type === 'circle') { newZone.center[0] = Math.min(600, newZone.center[0] + 30); newZone.center[1] = Math.min(320, newZone.center[1] + 30); }
            else newZone.points = newZone.points.map(p => [Math.min(620, p[0] + 30), Math.min(340, p[1] + 30)]);
            zones.push(newZone); renderZoneList(); saveZones();
        }

        function deleteZone(id) { if (zones.length <= 1) { alert('至少保留1个区域'); return; } zones = zones.filter(z => z.id !== id); if (editingZone === id) editingZone = null; renderZoneList(); saveZones(); }
        function startEdit(id) { editingZone = id; renderZoneList(); }
        function confirmEdit(id) { editingZone = null; renderZoneList(); saveZones(); }
        function renameZone(id, name) { const zone = zones.find(z => z.id === id); if (zone) { zone.name = name.substring(0, 10); saveZones(); } }
        function handleDragStart(e, id) { draggedZoneId = id; e.dataTransfer.effectAllowed = 'move'; e.target.closest('.zone-item').classList.add('dragging'); }
        function handleDragOver(e) { e.preventDefault(); }
        function handleDrop(e, targetId) { e.preventDefault(); if (draggedZoneId === null || draggedZoneId === targetId) return; const draggedIndex = zones.findIndex(z => z.id === draggedZoneId), targetIndex = zones.findIndex(z => z.id === targetId); if (draggedIndex !== -1 && targetIndex !== -1) { const [removed] = zones.splice(draggedIndex, 1); zones.splice(targetIndex, 0, removed); renderZoneList(); saveZones(); } }
        function handleDragEnd(e) { document.querySelectorAll('.zone-item').forEach(el => el.classList.remove('dragging')); draggedZoneId = null; }

        function renderZoneList() {
            document.getElementById('zone-count').textContent = zones.length;
            const typeNames = { 'rect': '矩形', 'triangle': '三角形', 'circle': '圆形', 'quad': '四边形' };
            document.getElementById('zone-list').innerHTML = zones.map(zone => `
                <div class="zone-item ${editingZone === zone.id ? 'editing' : ''}" draggable="true" ondragstart="handleDragStart(event, ${zone.id})" ondragover="handleDragOver(event)" ondrop="handleDrop(event, ${zone.id})" ondragend="handleDragEnd(event)">
                    <div class="zone-header">
                        <span class="drag-handle">☰</span>
                        <span class="zone-dot" style="background:${zone.color}"></span>
                        <input class="zone-name-input" value="${zone.name}" onchange="renameZone(${zone.id}, this.value)" onclick="event.stopPropagation()">
                        <span class="zone-type">(${typeNames[zone.type]})</span>
                        <div class="zone-actions">
                            ${editingZone === zone.id ? `<button class="zone-btn btn-confirm" onclick="confirmEdit(${zone.id})">确定</button>` : `<button class="zone-btn btn-edit" onclick="startEdit(${zone.id})">编辑</button>`}
                            <button class="zone-btn btn-copy" onclick="copyZone(${zone.id})">复制</button>
                            <button class="zone-btn btn-delete" onclick="deleteZone(${zone.id})">删除</button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function updateAdminBg(c) { adminBg = c; document.body.style.backgroundColor = c; fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({admin_bg: adminBg, projection_bg: projectionBg}) }); }
        function updateProjectionBg(c) { projectionBg = c; fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({admin_bg: adminBg, projection_bg: projectionBg}) }); }
        function saveCorners() { fetch('/api/corners', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({corners}) }); }
        function saveZones() { fetch('/api/zones', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({zones, zone_id_counter: zoneIdCounter}) }); }
        function saveAllConfig() { fetch('/api/save_all', { method: 'POST' }).then(r => r.json()).then(d => showToast(d.msg || '保存成功')); }
        function loadAllConfig() { fetch('/api/load_all', { method: 'POST' }).then(r => r.json()).then(d => { if (d.ok) { fetch('/api/config').then(r => r.json()).then(c => { if (c.corners) corners = c.corners; if (c.zones) zones = c.zones; if (c.zone_id_counter) zoneIdCounter = c.zone_id_counter; if (c.admin_bg) { adminBg = c.admin_bg; document.body.style.backgroundColor = adminBg; document.getElementById('admin-bg-input').value = adminBg; } if (c.projection_bg) { projectionBg = c.projection_bg; document.getElementById('projection-bg-input').value = projectionBg; } renderZoneList(); showToast('配置已加载'); }); } else showToast(d.msg || '加载失败'); }); }

        function updateStatus() {
            fetch('/api/status').then(r => r.json()).then(d => {
                document.getElementById('feet-status').textContent = d.feet_detected ? '已检测' : '未检测到';
                document.getElementById('feet-status').className = d.feet_detected ? 'detected' : 'not-detected';
                if (d.active_zones && d.active_zones.length > 0) {
                    document.getElementById('zone-status').textContent = d.active_zones.map(id => { const z = zones.find(zone => zone.id === id); return z ? z.name : id; }).join(' - ');
                    document.getElementById('zone-status').className = 'detected';
                } else { document.getElementById('zone-status').textContent = '未进入'; document.getElementById('zone-status').className = 'not-detected'; }
            });
        }

        setTimeout(init, 1000);
    </script>
</body>
</html>
"""

# ============================================================================
# HTML模板 - Projection (纯黑背景)
# ============================================================================
HTML_PROJECTION = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Projection</title>
    <style>
        *, *::before, *::after { margin: 0 !important; padding: 0 !important; border: 0 !important; outline: 0 !important; box-sizing: border-box !important; }
        html { width: 100vw !important; height: 100vh !important; overflow: hidden !important; background: #000 !important; }
        body { width: 100vw !important; height: 100vh !important; overflow: hidden !important; position: fixed !important; top: 0 !important; left: 0 !important; background: #000 !important; }
        
        #status-text { position: absolute; top: 2%; left: 50%; transform: translateX(-50%); font-size: 2vw; font-weight: bold; color: #333; z-index: 100; white-space: nowrap; }
        #status-text.in-zone { color: #33B555; }
        
        #foot-point { width: 80px; height: 80px; background: radial-gradient(circle, #33B555 0%, #228B22 100%); border-radius: 50%; position: absolute; transform: translate(-50%, -50%); box-shadow: 0 0 25px rgba(51, 181, 85, 0.5); display: none; z-index: 50; }
        #foot-point::after { content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 25px; height: 25px; background: rgba(255, 255, 255, 0.5); border-radius: 50%; }
        
        #zones-canvas { position: absolute; top: 0; left: 0; width: 100vw; height: 100vh; pointer-events: none; }
        #loading-ring { position: absolute; width: 150px; height: 150px; transform: translate(-50%, -50%); display: none; z-index: 60; }
        #score-feedback { position: absolute; transform: translate(-50%, -50%); font-size: 4vw; font-weight: bold; display: none; z-index: 70; text-shadow: 0 0 30px currentColor; }
    </style>
</head>
<body>
    <div id="status-text">未进入区域</div>
    <div id="foot-point"></div>
    <canvas id="zones-canvas"></canvas>
    
    <svg id="loading-ring" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="none" stroke="#333" stroke-width="3" opacity="0.3"/>
        <circle id="progress-circle" cx="50" cy="50" r="45" fill="none" stroke="#33B555" stroke-width="6" stroke-linecap="round" stroke-dasharray="283" stroke-dashoffset="283" transform="rotate(-90 50 50)"/>
    </svg>
    
    <div id="score-feedback"></div>

    <script>
        const statusText = document.getElementById('status-text');
        const footPoint = document.getElementById('foot-point');
        const zonesCanvas = document.getElementById('zones-canvas');
        const ctx = zonesCanvas.getContext('2d');
        const loadingRing = document.getElementById('loading-ring');
        const progressCircle = document.getElementById('progress-circle');
        const scoreFeedback = document.getElementById('score-feedback');
        
        const projW = 640, projH = 360;
        let zones = [], activeZones = [], projectionBg = "#000000";
        let loadingZone = null, loadingProgress = 0, loadingStartTime = 0;
        const LOADING_DURATION = 3000;
        let canTriggerAgain = true;

        function init() { resize(); loadConfig(); setInterval(update, 30); setInterval(loadConfig, 2000); window.addEventListener('resize', resize); }
        function resize() { zonesCanvas.width = window.innerWidth; zonesCanvas.height = window.innerHeight; drawZones(); }
        function loadConfig() { fetch('/api/config').then(r => r.json()).then(d => { zones = d.zones || []; if (d.projection_bg) projectionBg = d.projection_bg; }); }

        function drawZones() {
            ctx.clearRect(0, 0, zonesCanvas.width, zonesCanvas.height);
            const scaleX = zonesCanvas.width / projW, scaleY = zonesCanvas.height / projH;
            zones.forEach(zone => drawZone(ctx, zone, scaleX, scaleY, activeZones.includes(zone.id)));
        }
        
        function drawZone(ctx, zone, scaleX, scaleY, isActive) {
            ctx.strokeStyle = zone.color; ctx.lineWidth = isActive ? 5 : 3;
            if (zone.type === 'circle') {
                const cx = zone.center[0] * scaleX, cy = zone.center[1] * scaleY, r = zone.radius * Math.min(scaleX, scaleY);
                if (isActive) { ctx.fillStyle = zone.color + '40'; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill(); }
                ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
                ctx.fillStyle = zone.color; ctx.font = 'bold ' + (20 * Math.min(scaleX, scaleY)) + 'px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(zone.name || zone.id, cx, cy);
            } else {
                const points = zone.points.map(p => [p[0] * scaleX, p[1] * scaleY]);
                if (isActive) { ctx.fillStyle = zone.color + '40'; ctx.beginPath(); points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])); ctx.closePath(); ctx.fill(); }
                ctx.beginPath(); points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])); ctx.closePath(); ctx.stroke();
                const cx = points.reduce((s, p) => s + p[0], 0) / points.length, cy = points.reduce((s, p) => s + p[1], 0) / points.length;
                ctx.fillStyle = zone.color; ctx.font = 'bold ' + (20 * Math.min(scaleX, scaleY)) + 'px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(zone.name || zone.id, cx, cy);
            }
        }

        function update() {
            fetch('/api/status').then(r => r.json()).then(d => {
                if (d.active_zones && d.active_zones.length > 0) {
                    statusText.textContent = '已进入 ' + d.active_zones.map(id => { const z = zones.find(zone => zone.id === id); return z ? (z.name || z.id) : id; }).join(' - ') + ' 区域';
                    statusText.className = 'in-zone';
                } else { statusText.textContent = '未进入区域'; statusText.className = ''; }
                
                if (d.feet_detected) { footPoint.style.display = 'block'; footPoint.style.left = (d.feet_x / projW * 100) + '%'; footPoint.style.top = (d.feet_y / projH * 100) + '%'; }
                else { footPoint.style.display = 'none'; }
                
                handleLoading(d.active_zones || [], d.feet_x, d.feet_y, d.feet_detected);
                if (JSON.stringify(d.active_zones || []) !== JSON.stringify(activeZones)) { activeZones = d.active_zones || []; drawZones(); }
            });
        }
        
        function handleLoading(currentZones, feetX, feetY, feetDetected) {
            if (!feetDetected) { resetLoading(); return; }
            if (currentZones.length > 0) {
                const zoneId = currentZones[0], zone = zones.find(z => z.id === zoneId);
                if (loadingZone !== zoneId) {
                    resetLoading(); loadingZone = zoneId; loadingStartTime = Date.now(); loadingProgress = 0; canTriggerAgain = true;
                    loadingRing.style.display = 'block'; loadingRing.style.left = (feetX / projW * 100) + '%'; loadingRing.style.top = (feetY / projH * 100) + '%';
                    if (zone) progressCircle.setAttribute('stroke', zone.color);
                }
                loadingRing.style.left = (feetX / projW * 100) + '%'; loadingRing.style.top = (feetY / projH * 100) + '%';
                loadingProgress = Math.min(100, ((Date.now() - loadingStartTime) / LOADING_DURATION) * 100);
                progressCircle.setAttribute('stroke-dashoffset', 283 - (283 * loadingProgress / 100));
                if (loadingProgress >= 100 && canTriggerAgain) { showFeedback(zoneId, feetX, feetY); canTriggerAgain = false; setTimeout(() => { if (loadingZone === zoneId) { loadingStartTime = Date.now(); loadingProgress = 0; canTriggerAgain = true; } }, 500); }
            } else { resetLoading(); }
        }
        
        function resetLoading() { if (loadingZone !== null) { loadingZone = null; loadingProgress = 0; loadingRing.style.display = 'none'; scoreFeedback.style.display = 'none'; canTriggerAgain = true; } }
        
        function showFeedback(zoneId, feetX, feetY) {
            const zone = zones.find(z => z.id === zoneId); if (!zone) return;
            const isCircle = zone.type === 'circle';
            progressCircle.setAttribute('stroke', isCircle ? '#33B555' : '#ff4444');
            scoreFeedback.textContent = isCircle ? '+5' : '-5';
            scoreFeedback.style.color = isCircle ? '#33B555' : '#ff4444';
            scoreFeedback.style.left = (feetX / projW * 100) + '%';
            scoreFeedback.style.top = ((feetY / projH * 100) - 12) + '%';
            scoreFeedback.style.display = 'block';
            setTimeout(() => { scoreFeedback.style.display = 'none'; }, 1000);
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
            if jpeg: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.02)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/corrected_feed')
def corrected_feed():
    def gen():
        while True:
            jpeg = processor.get_corrected_jpeg()
            if jpeg: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.02)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/config')
def api_config():
    return jsonify({"corners": state["corners"], "zones": state["zones"], "zone_id_counter": state["zone_id_counter"], "admin_bg": state["admin_bg"], "projection_bg": state["projection_bg"]})

@app.route('/api/corners', methods=['POST'])
def api_corners():
    state["corners"] = request.json.get("corners", state["corners"])
    processor.update_matrix()
    return jsonify({"ok": True})

@app.route('/api/zones', methods=['POST'])
def api_zones():
    data = request.json
    state["zones"] = data.get("zones", state["zones"])
    if "zone_id_counter" in data: state["zone_id_counter"] = data["zone_id_counter"]
    return jsonify({"ok": True})

@app.route('/api/settings', methods=['POST'])
def api_settings():
    data = request.json
    if "admin_bg" in data: state["admin_bg"] = data["admin_bg"]
    if "projection_bg" in data: state["projection_bg"] = data["projection_bg"]
    return jsonify({"ok": True})

@app.route('/api/save_all', methods=['POST'])
def api_save_all():
    return jsonify({"ok": save_config_to_file(), "msg": "配置已保存" if save_config_to_file() else "保存失败"})

@app.route('/api/load_all', methods=['POST'])
def api_load_all():
    if load_config_from_file():
        processor.update_matrix()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "加载失败"})

@app.route('/api/status')
def api_status():
    return jsonify({"feet_detected": state["feet_detected"], "feet_x": state["feet_x"], "feet_y": state["feet_y"], "active_zones": state["active_zones"]})

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    print("=" * 50)
    print("地面投影交互系统 V13")
    print("=" * 50)
    print()
    
    # 自动打开浏览器
    threading.Thread(target=open_admin_browser, daemon=True).start()
    threading.Thread(target=open_projection_kiosk, daemon=True).start()
    
    print("Admin:  http://127.0.0.1:5000/admin")
    print("投影:   http://127.0.0.1:5000/projection")
    print()
    print("提示: Admin页面将在默认浏览器打开")
    print("      Projection页面将以Kiosk全屏模式打开")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
