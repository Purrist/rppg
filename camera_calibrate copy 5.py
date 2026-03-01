# -*- coding: utf-8 -*-
"""
地面投影交互系统 V5
修复：Projection页面SVG显示问题
"""

import cv2
import mediapipe as mp
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify
import threading
import time
import math

app = Flask(__name__)

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
    "zone_id_counter": 4
}

ZONE_COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", 
               "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B",
               "#4CAF50", "#3F51B5"]

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
        print(f"摄像头: {self.frame_w}x{self.frame_h}")
        
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
            
            frame = cv2.flip(frame, 0)
            frame = cv2.flip(frame, 1)
            
            h, w = frame.shape[:2]
            
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb)
            
            feet_detected = False
            feet_x, feet_y = 320, 180
            
            if results.pose_landmarks:
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
            
            active_zones = []
            if feet_detected:
                for zone in state["zones"]:
                    if self._point_in_zone(feet_x, feet_y, zone):
                        active_zones.append(zone["id"])
            
            state["feet_x"] = feet_x
            state["feet_y"] = feet_y
            state["feet_detected"] = feet_detected
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
            
            if feet_detected:
                cv2.circle(corrected, (feet_x, feet_y), 20, (0, 200, 0), -1)
            
            self.raw_frame = frame
            self.corrected_frame = corrected
            
            time.sleep(0.01)
    
    def _point_in_zone(self, x, y, zone):
        zone_type = zone.get("type", "rect")
        
        if zone_type == "circle":
            cx = int(zone["center"][0])
            cy = int(zone["center"][1])
            r = int(zone["radius"])
            return (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2
        else:
            pts = np.array(zone["points"], dtype=np.int32)
            return cv2.pointPolygonTest(pts, (x, y), False) >= 0
    
    def _draw_zone(self, img, zone, is_active):
        zone_type = zone.get("type", "rect")
        hex_color = zone["color"].lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        bgr = (rgb[2], rgb[1], rgb[0])
        
        if zone_type == "circle":
            cx = int(zone["center"][0])
            cy = int(zone["center"][1])
            r = int(zone["radius"])
            
            cv2.circle(img, (cx, cy), r, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.circle(overlay, (cx, cy), r, bgr, -1)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            cv2.putText(img, zone.get("name", str(zone["id"])), (cx-10, cy+5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)
        else:
            pts = np.array(zone["points"], dtype=np.int32)
            cv2.polylines(img, [pts], True, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.fillPoly(overlay, [pts], bgr)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            cx = int(np.mean([p[0] for p in zone["points"]]))
            cy = int(np.mean([p[1] for p in zone["points"]]))
            cv2.putText(img, zone.get("name", str(zone["id"])), (cx-10, cy+5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)
    
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
# HTML模板 - Admin页面
# ============================================================================
HTML_ADMIN = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - 校准管理</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #fff;
            color: #333;
            font-family: 'Microsoft YaHei', sans-serif;
            padding: 10px;
        }
        h1 { font-size: 16px; margin-bottom: 5px; }
        .hint { color: #666; font-size: 11px; margin-bottom: 8px; }
        
        .video-container {
            width: 640px;
            max-width: 100%;
            position: relative;
            background: #000;
            margin-bottom: 10px;
        }
        #video { display: block; width: 100%; }
        #canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; }
        
        .corrected-container {
            width: 640px;
            max-width: 100%;
            position: relative;
            background: #f5f5f5;
            border: 2px solid #33B555;
            margin-bottom: 10px;
        }
        #corrected { display: block; width: 100%; }
        #corrected-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; }
        
        .status-bar {
            width: 640px;
            max-width: 100%;
            background: #f0f0f0;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 12px;
            margin-bottom: 10px;
            display: flex;
            gap: 15px;
        }
        .detected { color: #33B555; font-weight: bold; }
        .not-detected { color: #ff6b6b; }
        
        .control-panel {
            width: 640px;
            max-width: 100%;
            background: #fafafa;
            border: 1px solid #ddd;
            border-radius: 6px;
            padding: 10px;
        }
        
        .section-title {
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 6px;
            padding-bottom: 4px;
            border-bottom: 1px solid #ddd;
        }
        
        .add-buttons {
            display: flex;
            gap: 5px;
            margin-bottom: 10px;
        }
        .add-btn {
            flex: 1;
            padding: 8px;
            border: 1px solid #ccc;
            border-radius: 4px;
            background: #fff;
            cursor: pointer;
            font-size: 12px;
        }
        .add-btn:hover { background: #e8f5e9; border-color: #33B555; }
        
        .zone-item {
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 5px;
        }
        .zone-header {
            padding: 6px 8px;
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: grab;
        }
        .drag-handle { color: #999; cursor: grab; font-size: 14px; }
        .zone-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            flex-shrink: 0;
        }
        .zone-name-input {
            border: none;
            background: transparent;
            font-size: 12px;
            font-weight: bold;
            width: 50px;
            padding: 2px;
        }
        .zone-name-input:focus {
            outline: none;
            background: #fffde7;
            border-radius: 2px;
        }
        .zone-type { font-size: 10px; color: #888; }
        .zone-actions {
            margin-left: auto;
            display: flex;
            gap: 4px;
        }
        .zone-btn {
            padding: 3px 8px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 10px;
        }
        .btn-edit { background: #FF7222; color: #fff; }
        .btn-confirm { background: #33B555; color: #fff; }
        .btn-delete { background: #f44336; color: #fff; }
        
        .zone-item.editing { border-color: #FF7222; box-shadow: 0 0 4px rgba(255,114,34,0.3); }
        .zone-item.dragging { opacity: 0.5; }
        
        .label { font-size: 11px; color: #666; margin: 5px 0; }
    </style>
</head>
<body>
    <h1>摄像头校准管理</h1>
    <p class="hint">上方：拖动蓝色顶点校准 | 中间：编辑区域 | 下方：拖动排序调整优先级</p>
    
    <div class="video-container">
        <img id="video" src="/video_feed">
        <canvas id="canvas"></canvas>
    </div>
    
    <p class="label">↓ 矫正后的16:9画面（点击编辑后拖动控制点） ↓</p>
    
    <div class="corrected-container">
        <img id="corrected" src="/corrected_feed">
        <canvas id="corrected-canvas"></canvas>
    </div>
    
    <div class="status-bar">
        <span>脚部: <span id="feet-status" class="not-detected">未检测到</span></span>
        <span>区域: <span id="zone-status">未进入</span></span>
    </div>
    
    <div class="control-panel">
        <div class="section-title">添加区域 (<span id="zone-count">3</span>/12)</div>
        <div class="add-buttons">
            <button class="add-btn" onclick="addZone('rect')">▢ 矩形</button>
            <button class="add-btn" onclick="addZone('triangle')">△ 三角形</button>
            <button class="add-btn" onclick="addZone('circle')">○ 圆形</button>
            <button class="add-btn" onclick="addZone('quad')">◇ 四边形</button>
        </div>
        
        <div class="section-title">区域列表（拖动排序，越靠前优先级越高）</div>
        <div class="zone-list" id="zone-list"></div>
    </div>

    <script>
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        
        const correctedImg = document.getElementById('corrected');
        const correctedCanvas = document.getElementById('corrected-canvas');
        const correctedCtx = correctedCanvas.getContext('2d');
        
        let corners = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]];
        let zones = [];
        let zoneIdCounter = 4;
        
        let draggingCorner = -1;
        let draggingZone = -1;
        let draggingPoint = -1;
        let editingZone = null;
        let mouseDown = false;
        let draggedZoneId = null;

        const COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", 
                        "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B",
                        "#4CAF50", "#3F51B5"];

        function init() {
            fetch('/api/config').then(r => r.json()).then(d => {
                if (d.corners) corners = d.corners;
                if (d.zones) zones = d.zones;
                if (d.zone_id_counter) zoneIdCounter = d.zone_id_counter;
                renderZoneList();
            });
            resize();
            requestAnimationFrame(draw);
            setInterval(updateStatus, 500);
        }

        function resize() {
            canvas.width = video.offsetWidth;
            canvas.height = video.offsetHeight;
            correctedCanvas.width = correctedImg.offsetWidth;
            correctedCanvas.height = correctedImg.offsetHeight;
        }
        video.onload = resize;
        correctedImg.onload = resize;
        window.onresize = resize;
        setTimeout(resize, 500);

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const w = canvas.width, h = canvas.height;
            
            ctx.strokeStyle = '#0066cc';
            ctx.lineWidth = 2;
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
                ctx.arc(x, y, 10, 0, Math.PI * 2);
                ctx.fillStyle = '#0066cc';
                ctx.fill();
                ctx.fillStyle = '#fff';
                ctx.font = 'bold 10px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(i + 1, x, y);
            });
            
            correctedCtx.clearRect(0, 0, correctedCanvas.width, correctedCanvas.height);
            const cw = correctedCanvas.width, ch = correctedCanvas.height;
            const scaleX = cw / 640, scaleY = ch / 360;
            
            zones.forEach(zone => {
                const isEditing = editingZone === zone.id;
                drawZone(correctedCtx, zone, scaleX, scaleY, isEditing);
            });
            
            requestAnimationFrame(draw);
        }
        
        function drawZone(ctx, zone, scaleX, scaleY, isEditing) {
            ctx.strokeStyle = zone.color;
            ctx.lineWidth = isEditing ? 3 : 2;
            
            if (zone.type === 'circle') {
                const cx = zone.center[0] * scaleX;
                const cy = zone.center[1] * scaleY;
                const r = zone.radius * Math.min(scaleX, scaleY);
                
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
                
                if (isEditing) {
                    ctx.beginPath();
                    ctx.arc(cx, cy, 8, 0, Math.PI * 2);
                    ctx.fillStyle = '#fff';
                    ctx.fill();
                    ctx.strokeStyle = zone.color;
                    ctx.lineWidth = 2;
                    ctx.stroke();
                    
                    ctx.beginPath();
                    ctx.arc(cx + r, cy, 8, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();
                }
            } else {
                ctx.beginPath();
                zone.points.forEach((p, i) => {
                    const x = p[0] * scaleX, y = p[1] * scaleY;
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                });
                ctx.closePath();
                ctx.stroke();
                
                if (isEditing) {
                    ctx.fillStyle = zone.color + '20';
                    ctx.fill();
                    
                    zone.points.forEach((p, i) => {
                        const x = p[0] * scaleX, y = p[1] * scaleY;
                        ctx.beginPath();
                        ctx.arc(x, y, 8, 0, Math.PI * 2);
                        ctx.fillStyle = '#fff';
                        ctx.fill();
                        ctx.strokeStyle = zone.color;
                        ctx.lineWidth = 2;
                        ctx.stroke();
                        
                        ctx.fillStyle = '#333';
                        ctx.font = 'bold 9px Arial';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';
                        ctx.fillText(i + 1, x, y);
                    });
                }
            }
        }

        canvas.onmousedown = (e) => {
            const rect = canvas.getBoundingClientRect();
            const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height };
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
            const rect = canvas.getBoundingClientRect();
            const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height };
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

        correctedCanvas.onmousedown = (e) => {
            if (!editingZone) return;
            const rect = correctedCanvas.getBoundingClientRect();
            const pos = {
                x: (e.clientX - rect.left) / rect.width * 640,
                y: (e.clientY - rect.top) / rect.height * 360
            };
            const zone = zones.find(z => z.id === editingZone);
            if (!zone) return;
            
            if (zone.type === 'circle') {
                const cx = zone.center[0], cy = zone.center[1], r = zone.radius;
                const dCenter = Math.hypot(pos.x - cx, pos.y - cy);
                const dRadius = Math.hypot(pos.x - (cx + r), pos.y - cy);
                
                if (dCenter < 20) {
                    draggingZone = editingZone;
                    draggingPoint = 'center';
                    mouseDown = true;
                } else if (dRadius < 20) {
                    draggingZone = editingZone;
                    draggingPoint = 'radius';
                    mouseDown = true;
                }
            } else {
                for (let i = 0; i < zone.points.length; i++) {
                    const d = Math.hypot(zone.points[i][0] - pos.x, zone.points[i][1] - pos.y);
                    if (d < 20) {
                        draggingZone = editingZone;
                        draggingPoint = i;
                        mouseDown = true;
                        break;
                    }
                }
            }
        };
        
        correctedCanvas.onmousemove = (e) => {
            if (!mouseDown || draggingZone < 0 || draggingPoint === -1) return;
            const rect = correctedCanvas.getBoundingClientRect();
            const pos = {
                x: (e.clientX - rect.left) / rect.width * 640,
                y: (e.clientY - rect.top) / rect.height * 360
            };
            const zone = zones.find(z => z.id === draggingZone);
            if (!zone) return;
            
            if (zone.type === 'circle') {
                if (draggingPoint === 'center') {
                    zone.center = [
                        Math.max(30, Math.min(610, pos.x)),
                        Math.max(30, Math.min(330, pos.y))
                    ];
                } else if (draggingPoint === 'radius') {
                    const cx = zone.center[0], cy = zone.center[1];
                    zone.radius = Math.max(20, Math.min(150, Math.hypot(pos.x - cx, pos.y - cy)));
                }
            } else {
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

        function addZone(type) {
            if (zones.length >= 12) {
                alert('最多只能添加12个区域！');
                return;
            }
            
            const id = zoneIdCounter++;
            const color = COLORS[(id - 1) % COLORS.length];
            const baseX = 100 + Math.random() * 400;
            const baseY = 100 + Math.random() * 150;
            let newZone;
            
            switch(type) {
                case 'rect':
                    newZone = {
                        id: id, name: String(id), type: 'rect',
                        points: [[baseX, baseY], [baseX+100, baseY], [baseX+100, baseY+100], [baseX, baseY+100]],
                        color: color
                    };
                    break;
                case 'triangle':
                    newZone = {
                        id: id, name: String(id), type: 'triangle',
                        points: [[baseX+50, baseY], [baseX+100, baseY+100], [baseX, baseY+100]],
                        color: color
                    };
                    break;
                case 'circle':
                    newZone = {
                        id: id, name: String(id), type: 'circle',
                        center: [baseX+50, baseY+50], radius: 50,
                        color: color
                    };
                    break;
                case 'quad':
                    newZone = {
                        id: id, name: String(id), type: 'quad',
                        points: [[baseX, baseY], [baseX+120, baseY+20], [baseX+100, baseY+100], [baseX+20, baseY+80]],
                        color: color
                    };
                    break;
            }
            
            zones.push(newZone);
            renderZoneList();
            saveZones();
        }
        
        function deleteZone(id) {
            if (zones.length <= 1) {
                alert('至少保留一个区域！');
                return;
            }
            zones = zones.filter(z => z.id !== id);
            if (editingZone === id) editingZone = null;
            renderZoneList();
            saveZones();
        }
        
        function startEdit(id) {
            editingZone = id;
            renderZoneList();
        }
        
        function confirmEdit(id) {
            editingZone = null;
            renderZoneList();
            saveZones();
        }
        
        function renameZone(id, name) {
            const zone = zones.find(z => z.id === id);
            if (zone) {
                zone.name = name.substring(0, 10);
                saveZones();
            }
        }
        
        function handleDragStart(e, id) {
            draggedZoneId = id;
            e.dataTransfer.effectAllowed = 'move';
            e.target.closest('.zone-item').classList.add('dragging');
        }
        
        function handleDragOver(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
        }
        
        function handleDrop(e, targetId) {
            e.preventDefault();
            if (draggedZoneId === null || draggedZoneId === targetId) return;
            
            const draggedIndex = zones.findIndex(z => z.id === draggedZoneId);
            const targetIndex = zones.findIndex(z => z.id === targetId);
            
            if (draggedIndex !== -1 && targetIndex !== -1) {
                const [removed] = zones.splice(draggedIndex, 1);
                zones.splice(targetIndex, 0, removed);
                renderZoneList();
                saveZones();
            }
        }
        
        function handleDragEnd(e) {
            document.querySelectorAll('.zone-item').forEach(el => el.classList.remove('dragging'));
            draggedZoneId = null;
        }
        
        function renderZoneList() {
            const container = document.getElementById('zone-list');
            document.getElementById('zone-count').textContent = zones.length;
            
            const typeNames = {'rect': '矩形', 'triangle': '三角形', 'circle': '圆形', 'quad': '四边形'};
            
            container.innerHTML = zones.map(zone => `
                <div class="zone-item ${editingZone === zone.id ? 'editing' : ''}" 
                     draggable="true"
                     ondragstart="handleDragStart(event, ${zone.id})"
                     ondragover="handleDragOver(event)"
                     ondrop="handleDrop(event, ${zone.id})"
                     ondragend="handleDragEnd(event)">
                    <div class="zone-header">
                        <span class="drag-handle">☰</span>
                        <span class="zone-dot" style="background:${zone.color}"></span>
                        <input class="zone-name-input" value="${zone.name}" 
                               onchange="renameZone(${zone.id}, this.value)"
                               onclick="event.stopPropagation()">
                        <span class="zone-type">(${typeNames[zone.type]})</span>
                        <div class="zone-actions">
                            ${editingZone === zone.id 
                                ? `<button class="zone-btn btn-confirm" onclick="confirmEdit(${zone.id})">确定</button>`
                                : `<button class="zone-btn btn-edit" onclick="startEdit(${zone.id})">编辑</button>`
                            }
                            <button class="zone-btn btn-delete" onclick="deleteZone(${zone.id})">删除</button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

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
                body: JSON.stringify({zones: zones, zone_id_counter: zoneIdCounter})
            });
        }

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
                
                if (d.active_zones && d.active_zones.length > 0) {
                    const names = d.active_zones.map(id => {
                        const z = zones.find(zone => zone.id === id);
                        return z ? z.name : id;
                    });
                    zoneEl.textContent = names.join(' - ');
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

# ============================================================================
# HTML模板 - Projection页面（使用Canvas绘制，与Admin完全一致）
# ============================================================================
HTML_PROJECTION = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Projection</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #fff;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            position: relative;
        }
        
        #status-text {
            position: absolute;
            top: 2%;
            left: 50%;
            transform: translateX(-50%);
            font-size: 2vw;
            font-weight: bold;
            color: #333;
            z-index: 100;
            white-space: nowrap;
        }
        #status-text.in-zone { color: #33B555; }
        
        #foot-point {
            width: 80px;
            height: 80px;
            background: radial-gradient(circle, #33B555 0%, #228B22 100%);
            border-radius: 50%;
            position: absolute;
            transform: translate(-50%, -50%);
            box-shadow: 0 0 25px rgba(51, 181, 85, 0.5);
            display: none;
            z-index: 50;
        }
        #foot-point::after {
            content: '';
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 25px; height: 25px;
            background: rgba(255, 255, 255, 0.5);
            border-radius: 50%;
        }
        
        /* Canvas铺满整个页面 */
        #zones-canvas {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
        }
    </style>
</head>
<body>
    <div id="status-text">未进入区域</div>
    <div id="foot-point"></div>
    <canvas id="zones-canvas"></canvas>

    <script>
        const statusText = document.getElementById('status-text');
        const footPoint = document.getElementById('foot-point');
        const zonesCanvas = document.getElementById('zones-canvas');
        const ctx = zonesCanvas.getContext('2d');
        
        const projW = 640, projH = 360;
        let zones = [];
        let activeZones = [];

        function init() {
            resize();
            fetch('/api/config').then(r => r.json()).then(d => {
                zones = d.zones || [];
                drawZones();
            });
            setInterval(update, 50);
            setInterval(loadConfig, 2000);
            window.addEventListener('resize', resize);
        }
        
        function resize() {
            zonesCanvas.width = window.innerWidth;
            zonesCanvas.height = window.innerHeight;
            drawZones();
        }

        function drawZones() {
            ctx.clearRect(0, 0, zonesCanvas.width, zonesCanvas.height);
            
            const scaleX = zonesCanvas.width / projW;
            const scaleY = zonesCanvas.height / projH;
            
            zones.forEach(zone => {
                const isActive = activeZones.includes(zone.id);
                drawZone(ctx, zone, scaleX, scaleY, isActive);
            });
        }
        
        function drawZone(ctx, zone, scaleX, scaleY, isActive) {
            ctx.strokeStyle = zone.color;
            ctx.lineWidth = isActive ? 5 : 3;
            
            if (zone.type === 'circle') {
                // 圆形
                const cx = zone.center[0] * scaleX;
                const cy = zone.center[1] * scaleY;
                const r = zone.radius * Math.min(scaleX, scaleY);
                
                // 填充
                if (isActive) {
                    ctx.fillStyle = zone.color + '40';
                    ctx.beginPath();
                    ctx.arc(cx, cy, r, 0, Math.PI * 2);
                    ctx.fill();
                }
                
                // 边框
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
                
                // 标签
                ctx.fillStyle = zone.color;
                ctx.font = 'bold ' + (16 * Math.min(scaleX, scaleY)) + 'px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(zone.name || zone.id, cx, cy);
                
            } else {
                // 多边形
                const points = zone.points.map(p => [p[0] * scaleX, p[1] * scaleY]);
                
                // 填充
                if (isActive) {
                    ctx.fillStyle = zone.color + '40';
                    ctx.beginPath();
                    points.forEach((p, i) => {
                        if (i === 0) ctx.moveTo(p[0], p[1]);
                        else ctx.lineTo(p[0], p[1]);
                    });
                    ctx.closePath();
                    ctx.fill();
                }
                
                // 边框
                ctx.beginPath();
                points.forEach((p, i) => {
                    if (i === 0) ctx.moveTo(p[0], p[1]);
                    else ctx.lineTo(p[0], p[1]);
                });
                ctx.closePath();
                ctx.stroke();
                
                // 标签
                const cx = points.reduce((s, p) => s + p[0], 0) / points.length;
                const cy = points.reduce((s, p) => s + p[1], 0) / points.length;
                ctx.fillStyle = zone.color;
                ctx.font = 'bold ' + (16 * Math.min(scaleX, scaleY)) + 'px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(zone.name || zone.id, cx, cy);
            }
        }

        function update() {
            fetch('/api/status')
                .then(r => r.json())
                .then(d => {
                    if (d.active_zones && d.active_zones.length > 0) {
                        const names = d.active_zones.map(id => {
                            const z = zones.find(zone => zone.id === id);
                            return z ? (z.name || z.id) : id;
                        });
                        statusText.textContent = '已进入 ' + names.join(' - ') + ' 区域';
                        statusText.className = 'in-zone';
                    } else {
                        statusText.textContent = '未进入区域';
                        statusText.className = '';
                    }
                    
                    if (d.feet_detected) {
                        footPoint.style.display = 'block';
                        footPoint.style.left = (d.feet_x / projW * 100) + '%';
                        footPoint.style.top = (d.feet_y / projH * 100) + '%';
                    } else {
                        footPoint.style.display = 'none';
                    }
                    
                    if (JSON.stringify(d.active_zones || []) !== JSON.stringify(activeZones)) {
                        activeZones = d.active_zones || [];
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
        "zones": state["zones"],
        "zone_id_counter": state["zone_id_counter"]
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
    if "zone_id_counter" in data:
        state["zone_id_counter"] = data["zone_id_counter"]
    return jsonify({"ok": True})

@app.route('/api/status')
def api_status():
    return jsonify({
        "feet_detected": state["feet_detected"],
        "feet_x": state["feet_x"],
        "feet_y": state["feet_y"],
        "active_zones": state["active_zones"]
    })

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    print("=" * 50)
    print("地面投影交互系统 V5")
    print("=" * 50)
    print("Admin:  http://127.0.0.1:5000/admin")
    print("投影:   http://127.0.0.1:5000/projection")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
