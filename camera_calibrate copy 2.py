# -*- coding: utf-8 -*-
"""
地面投影交互系统 - 完整版V2
功能：
1. Admin页面：摄像头画面 + 骨骼识别 + 校准 + 可添加/删除区域
2. Projection页面：绿色圆点 + 区域状态显示
3. 支持1-12个区域，形状可选：矩形/三角形/圆形/自由四边形
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
    # 校准四边形顶点（归一化坐标 0-1）
    "corners": [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]],
    
    # 识别区域列表（投影坐标系 640x360）
    # type: rect(矩形), triangle(三角形), circle(圆形), quad(自由四边形)
    "zones": [
        {"id": 1, "type": "rect", "points": [[50, 80], [180, 80], [180, 280], [50, 280]], "color": "#33B555"},
        {"id": 2, "type": "rect", "points": [[230, 80], [410, 80], [410, 280], [230, 280]], "color": "#FF7222"},
        {"id": 3, "type": "rect", "points": [[460, 80], [590, 80], [590, 280], [460, 280]], "color": "#2196F3"}
    ],
    
    # 脚部位置（投影坐标系）
    "feet_x": 320,
    "feet_y": 180,
    "feet_detected": False,
    "active_zone": None,
    
    # 透视变换矩阵
    "matrix": None,
    
    # 区域ID计数器
    "zone_id_counter": 4
}

# 预设颜色
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
            
            # 判断在哪个区域
            active_zone = None
            if feet_detected:
                for zone in state["zones"]:
                    if self._point_in_zone(feet_x, feet_y, zone):
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
            
            # 在矫正画面上绘制所有区域
            for zone in state["zones"]:
                self._draw_zone(corrected, zone, state["active_zone"] == zone["id"])
            
            # 绘制脚部位置
            if feet_detected:
                cv2.circle(corrected, (feet_x, feet_y), 20, (0, 200, 0), -1)
            
            self.raw_frame = frame
            self.corrected_frame = corrected
            
            time.sleep(0.01)
    
    def _point_in_zone(self, x, y, zone):
        """判断点是否在区域内"""
        zone_type = zone.get("type", "rect")
        
        if zone_type == "circle":
            # 圆形：计算到圆心距离
            cx, cy, r = zone["center"][0], zone["center"][1], zone["radius"]
            return (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2
        else:
            # 多边形（矩形、三角形、自由四边形）
            pts = np.array(zone["points"], dtype=np.int32)
            return cv2.pointPolygonTest(pts, (x, y), False) >= 0
    
    def _draw_zone(self, img, zone, is_active):
        """绘制区域"""
        zone_type = zone.get("type", "rect")
        hex_color = zone["color"].lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        bgr = (rgb[2], rgb[1], rgb[0])
        
        if zone_type == "circle":
            cx, cy = zone["center"]
            r = zone["radius"]
            cv2.circle(img, (cx, cy), r, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.circle(overlay, (cx, cy), r, bgr, -1)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            # 标签
            cv2.putText(img, f"区域{zone['id']}", (cx-25, cy), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, bgr, 2)
        else:
            pts = np.array(zone["points"], dtype=np.int32)
            cv2.polylines(img, [pts], True, bgr, 3)
            if is_active:
                overlay = img.copy()
                cv2.fillPoly(overlay, [pts], bgr)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            # 标签
            cx = int(np.mean([p[0] for p in zone["points"]]))
            cy = int(np.mean([p[1] for p in zone["points"]]))
            cv2.putText(img, f"区域{zone['id']}", (cx-25, cy), 
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
            padding: 15px;
        }
        h1 { margin-bottom: 8px; font-size: 20px; }
        .hint { color: #666; margin-bottom: 12px; font-size: 13px; }
        
        .main-content {
            display: flex;
            gap: 15px;
            align-items: flex-start;
        }
        
        .video-section {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        
        .container { position: relative; margin-bottom: 12px; }
        #video { border: 2px solid #333; display: block; max-width: 500px; }
        #canvas { position: absolute; top: 0; left: 0; cursor: crosshair; }
        .label { color: #666; margin: 6px 0; font-size: 12px; }
        #corrected { border: 2px solid #33B555; display: block; max-width: 500px; }
        
        .corrected-container { position: relative; }
        #corrected-canvas { position: absolute; top: 0; left: 0; cursor: crosshair; }
        
        .status {
            margin-top: 8px;
            padding: 6px 12px;
            background: #f0f0f0;
            border-radius: 4px;
            font-size: 12px;
        }
        .detected { color: #33B555; font-weight: bold; }
        .not-detected { color: #ff6b6b; }
        
        /* 区域控制面板 */
        .zone-panel {
            background: #f8f8f8;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 12px;
            min-width: 220px;
            max-height: 600px;
            overflow-y: auto;
        }
        .zone-panel h3 {
            margin-bottom: 10px;
            font-size: 14px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 6px;
        }
        
        /* 添加区域按钮组 */
        .add-zone-section {
            margin-bottom: 12px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }
        .add-zone-section p {
            font-size: 12px;
            color: #666;
            margin-bottom: 6px;
        }
        .shape-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }
        .shape-btn {
            padding: 8px;
            border: 1px solid #ccc;
            border-radius: 4px;
            background: #fff;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }
        .shape-btn:hover {
            background: #e8f5e9;
            border-color: #33B555;
        }
        
        /* 区域列表 */
        .zone-list {
            max-height: 350px;
            overflow-y: auto;
        }
        
        .zone-item {
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 6px;
            margin-bottom: 8px;
            overflow: hidden;
        }
        .zone-header {
            padding: 8px 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            background: #fafafa;
        }
        .zone-title { font-weight: bold; font-size: 13px; display: flex; align-items: center; }
        .zone-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
        }
        .zone-type { font-size: 11px; color: #888; margin-left: 6px; }
        
        .zone-body {
            padding: 8px 10px;
            border-top: 1px solid #eee;
            display: none;
        }
        .zone-item.active .zone-body { display: block; }
        
        .btn-group { display: flex; gap: 6px; margin-top: 6px; }
        .btn {
            flex: 1;
            padding: 6px 10px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            font-weight: bold;
        }
        .btn-edit { background: #FF7222; color: #fff; }
        .btn-edit:hover { background: #e65c00; }
        .btn-confirm { background: #33B555; color: #fff; }
        .btn-confirm:hover { background: #2a9245; }
        .btn-delete { background: #f44336; color: #fff; }
        .btn-delete:hover { background: #d32f2f; }
        
        .zone-item.editing {
            border-color: #FF7222;
            box-shadow: 0 0 6px rgba(255, 114, 34, 0.3);
        }
        
        .zone-info {
            font-size: 11px;
            color: #888;
            margin-bottom: 4px;
        }
    </style>
</head>
<body>
    <h1>摄像头校准管理</h1>
    <p class="hint">上方：拖动蓝色顶点校准画面 | 下方：点击区域按钮编辑识别区域（最多12个）</p>
    
    <div class="main-content">
        <div class="video-section">
            <div class="container">
                <img id="video" src="/video_feed">
                <canvas id="canvas"></canvas>
            </div>
            
            <p class="label">↓ 矫正后的16:9画面（可编辑区域） ↓</p>
            <div class="corrected-container">
                <img id="corrected" src="/corrected_feed">
                <canvas id="corrected-canvas"></canvas>
            </div>
            
            <div class="status">
                脚部: <span id="feet-status" class="not-detected">未检测到</span> | 
                区域: <span id="zone-status">未进入</span>
            </div>
        </div>
        
        <div class="zone-panel">
            <h3>识别区域设置</h3>
            
            <!-- 添加区域 -->
            <div class="add-zone-section">
                <p>添加新区域（当前 <span id="zone-count">3</span>/12 个）：</p>
                <div class="shape-buttons">
                    <button class="shape-btn" onclick="addZone('rect')">▢ 矩形</button>
                    <button class="shape-btn" onclick="addZone('triangle')">△ 三角形</button>
                    <button class="shape-btn" onclick="addZone('circle')">○ 圆形</button>
                    <button class="shape-btn" onclick="addZone('quad')">◇ 自由四边形</button>
                </div>
            </div>
            
            <!-- 区域列表 -->
            <div class="zone-list" id="zone-list"></div>
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
        let zones = [];
        let zoneIdCounter = 4;
        
        let draggingCorner = -1;
        let draggingZone = -1;
        let draggingPoint = -1;
        let editingZone = null;
        let mouseDown = false;

        const COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", 
                        "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B",
                        "#4CAF50", "#3F51B5"];

        // ========== 初始化 ==========
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
            // 上方校准框
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
            
            // 下方区域
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
                    // 绘制圆心控制点
                    ctx.beginPath();
                    ctx.arc(cx, cy, 8, 0, Math.PI * 2);
                    ctx.fillStyle = '#fff';
                    ctx.fill();
                    ctx.strokeStyle = zone.color;
                    ctx.lineWidth = 2;
                    ctx.stroke();
                    
                    // 绘制半径控制点
                    ctx.beginPath();
                    ctx.arc(cx + r, cy, 8, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();
                }
            } else {
                // 多边形
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
                    
                    // 绘制顶点
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
            
            if (zone.type === 'circle') {
                // 检查是否点击圆心或半径控制点
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
            const pos = getPosCorrected(e);
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

        // ========== 区域管理 ==========
        function addZone(type) {
            if (zones.length >= 12) {
                alert('最多只能添加12个区域！');
                return;
            }
            
            const id = zoneIdCounter++;
            const color = COLORS[(id - 1) % COLORS.length];
            let newZone;
            
            // 在随机位置创建区域
            const baseX = 100 + Math.random() * 400;
            const baseY = 100 + Math.random() * 150;
            
            switch(type) {
                case 'rect':
                    newZone = {
                        id: id,
                        type: 'rect',
                        points: [[baseX, baseY], [baseX+100, baseY], [baseX+100, baseY+100], [baseX, baseY+100]],
                        color: color
                    };
                    break;
                case 'triangle':
                    newZone = {
                        id: id,
                        type: 'triangle',
                        points: [[baseX+50, baseY], [baseX+100, baseY+100], [baseX, baseY+100]],
                        color: color
                    };
                    break;
                case 'circle':
                    newZone = {
                        id: id,
                        type: 'circle',
                        center: [baseX+50, baseY+50],
                        radius: 50,
                        color: color
                    };
                    break;
                case 'quad':
                    newZone = {
                        id: id,
                        type: 'quad',
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
        
        function renderZoneList() {
            const container = document.getElementById('zone-list');
            document.getElementById('zone-count').textContent = zones.length;
            
            const typeNames = {
                'rect': '矩形',
                'triangle': '三角形',
                'circle': '圆形',
                'quad': '自由四边形'
            };
            
            container.innerHTML = zones.map(zone => `
                <div class="zone-item" id="zone-item-${zone.id}">
                    <div class="zone-header" onclick="toggleZone(${zone.id})">
                        <span class="zone-title">
                            <span class="zone-dot" style="background:${zone.color}"></span>
                            区域${zone.id}
                            <span class="zone-type">(${typeNames[zone.type]})</span>
                        </span>
                        <span>▼</span>
                    </div>
                    <div class="zone-body">
                        <p class="zone-info">点击编辑后，在下方画面拖动控制点调整</p>
                        <div class="btn-group">
                            <button class="btn btn-edit" onclick="startEditZone(${zone.id})">编辑</button>
                            <button class="btn btn-confirm" onclick="confirmZone(${zone.id})">确定</button>
                        </div>
                        <div class="btn-group" style="margin-top:6px;">
                            <button class="btn btn-delete" onclick="deleteZone(${zone.id})">删除区域</button>
                        </div>
                    </div>
                </div>
            `).join('');
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
                body: JSON.stringify({zones: zones, zone_id_counter: zoneIdCounter})
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
        
        /* 顶部状态文字 - 缩小 */
        #status-text {
            position: absolute;
            top: 3%;
            left: 50%;
            transform: translateX(-50%);
            font-size: 4vw;
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
            width: 100px;
            height: 100px;
            background: radial-gradient(circle, #33B555 0%, #228B22 100%);
            border-radius: 50%;
            position: absolute;
            transform: translate(-50%, -50%);
            box-shadow: 0 0 30px rgba(51, 181, 85, 0.5);
            display: none;
            z-index: 50;
        }
        #foot-point::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 30px;
            height: 30px;
            background: rgba(255, 255, 255, 0.5);
            border-radius: 50%;
        }
        
        /* 区域边框 */
        .zone-border {
            position: absolute;
            border: 3px solid;
            pointer-events: none;
            border-radius: 6px;
        }
        .zone-border.active {
            border-width: 5px;
            box-shadow: 0 0 15px currentColor;
        }
        
        /* 圆形区域 */
        .zone-circle {
            position: absolute;
            border: 3px solid;
            border-radius: 50%;
            pointer-events: none;
        }
        .zone-circle.active {
            border-width: 5px;
            box-shadow: 0 0 15px currentColor;
        }
        
        .zone-label {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 1.5vw;
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
                let div;
                
                if (zone.type === 'circle') {
                    const cx = zone.center[0], cy = zone.center[1], r = zone.radius;
                    div = document.createElement('div');
                    div.className = 'zone-circle' + (activeZone === zone.id ? ' active' : '');
                    div.style.left = ((cx - r) / projW * 100) + '%';
                    div.style.top = ((cy - r) / projH * 100) + '%';
                    div.style.width = (r * 2 / projW * 100) + '%';
                    div.style.height = (r * 2 / projH * 100) + '%';
                    div.style.borderColor = zone.color;
                    div.style.color = zone.color;
                } else {
                    const xs = zone.points.map(p => p[0]);
                    const ys = zone.points.map(p => p[1]);
                    const minX = Math.min(...xs), maxX = Math.max(...xs);
                    const minY = Math.min(...ys), maxY = Math.max(...ys);
                    
                    div = document.createElement('div');
                    div.className = 'zone-border' + (activeZone === zone.id ? ' active' : '');
                    div.style.left = (minX / projW * 100) + '%';
                    div.style.top = (minY / projH * 100) + '%';
                    div.style.width = ((maxX - minX) / projW * 100) + '%';
                    div.style.height = ((maxY - minY) / projH * 100) + '%';
                    div.style.borderColor = zone.color;
                    div.style.color = zone.color;
                }
                
                // 标签
                const label = document.createElement('div');
                label.className = 'zone-label';
                label.textContent = zone.id;
                label.style.color = zone.color;
                div.appendChild(label);
                
                zonesLayer.appendChild(div);
            });
        }

        function update() {
            fetch('/api/status')
                .then(r => r.json())
                .then(d => {
                    if (d.active_zone) {
                        statusText.textContent = '已进入区域' + d.active_zone;
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
        "active_zone": state["active_zone"]
    })

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    print("=" * 50)
    print("地面投影交互系统 V2")
    print("=" * 50)
    print("Admin页面:  http://127.0.0.1:5000/admin")
    print("投影页面:  http://127.0.0.1:5000/projection")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
