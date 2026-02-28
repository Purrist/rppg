import cv2
import mediapipe as mp
import threading
import time
import numpy as np
import math
from flask import Flask, Response, render_template_string, request, jsonify

app = Flask(__name__)

# ============================================================================
# 全局状态管理
# ============================================================================
state = {
    # 整体投影区域 (4个顶点，归一化坐标 0.0-1.0)
    "main_area": [[0.1, 0.3], [0.9, 0.3], [0.9, 0.9], [0.1, 0.9]],
    
    # 三个识别区域 (每个4个顶点)
    "zones": [
        {"id": 1, "points": [[0.15, 0.5], [0.30, 0.5], [0.30, 0.85], [0.15, 0.85]], "color": "#33B555"},
        {"id": 2, "points": [[0.40, 0.5], [0.60, 0.5], [0.60, 0.85], [0.40, 0.85]], "color": "#FF7222"},
        {"id": 3, "points": [[0.70, 0.5], [0.85, 0.5], [0.85, 0.85], [0.70, 0.85]], "color": "#2AAADD"}
    ],
    
    # 系统配置
    "projection_size": (1920, 1080),  # 投影分辨率
    "max_foot_dist": 300,             # 双脚最大间距（像素）
    
    # 实时状态
    "status_text": "等待检测...",
    "feet_x": 960,
    "feet_y": 540,
    "feet_detected": False,
    "active_zone_id": None,
    
    # 透视变换矩阵
    "transform_matrix": None
}

# ============================================================================
# HTML模板 - Admin管理端页面
# ============================================================================
html_admin = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>管理后台 - 地面投影交互系统</title>
    <style>
        * { box-sizing: border-box; }
        body { 
            margin: 0; padding: 0; 
            background: #1a1a1a; color: #fff; 
            display: flex; height: 100vh; 
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; 
            overflow: hidden;
        }
        
        /* 左侧视频区域 */
        .view-section { 
            flex: 1; 
            position: relative; 
            background: #000; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
        }
        #video-feed { 
            max-width: 100%; 
            max-height: 100%; 
            display: block;
        }
        #overlay-canvas { 
            position: absolute; 
            top: 0; left: 0; 
            width: 100%; height: 100%; 
            cursor: crosshair; 
        }
        
        /* 右侧控制面板 */
        .control-section { 
            width: 340px; 
            padding: 20px; 
            background: #252525; 
            overflow-y: auto; 
            border-left: 2px solid #333; 
        }
        
        /* 状态显示 */
        .status-panel { 
            background: linear-gradient(135deg, #1a1a2e, #16213e); 
            padding: 20px; 
            border-radius: 12px; 
            margin-bottom: 20px; 
            text-align: center;
            border: 1px solid #333;
        }
        .status-label { font-size: 12px; color: #888; margin-bottom: 8px; }
        .status-text { 
            font-size: 24px; 
            color: #FFD111; 
            font-weight: bold;
            text-shadow: 0 0 10px rgba(255, 209, 17, 0.3);
        }
        .status-text.triggered { 
            color: #33B555; 
            animation: pulse 1s infinite; 
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        
        /* 配置卡片 */
        .card { 
            background: #333; 
            border-radius: 10px; 
            margin-bottom: 15px; 
            overflow: hidden;
            border: 1px solid #444;
            transition: all 0.3s;
        }
        .card:hover { border-color: #555; }
        .card.editing { 
            border-color: #FF7222; 
            box-shadow: 0 0 15px rgba(255, 114, 34, 0.3); 
        }
        
        .card-header { 
            padding: 14px 16px; 
            background: #2a2a2a; 
            cursor: pointer; 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            border-bottom: 1px solid #444;
        }
        .card-title { 
            margin: 0; 
            font-size: 14px; 
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card-icon { font-size: 16px; }
        .card-badge { 
            font-size: 11px; 
            padding: 3px 8px; 
            border-radius: 4px; 
            background: #444;
        }
        
        .card-body { 
            padding: 16px; 
        }
        .card-hint { 
            font-size: 12px; 
            color: #aaa; 
            margin-bottom: 12px; 
            line-height: 1.5;
        }
        
        /* 按钮样式 */
        .btn-group { display: flex; gap: 10px; }
        .btn { 
            flex: 1;
            padding: 10px 16px; 
            border: none; 
            border-radius: 6px; 
            cursor: pointer; 
            font-size: 13px; 
            font-weight: 600;
            transition: all 0.2s;
        }
        .btn-edit { 
            background: linear-gradient(135deg, #FF7222, #ff8c42); 
            color: white; 
        }
        .btn-edit:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(255, 114, 34, 0.4); }
        .btn-save { 
            background: linear-gradient(135deg, #33B555, #4CAF50); 
            color: white; 
        }
        .btn-save:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(51, 181, 85, 0.4); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }
        
        /* 颜色指示器 */
        .color-dot { 
            display: inline-block; 
            width: 12px; height: 12px; 
            border-radius: 50%; 
            margin-right: 6px;
        }
        
        /* 使用说明 */
        .instructions {
            background: #2a2a2a;
            border-radius: 8px;
            padding: 12px;
            margin-top: 15px;
            font-size: 11px;
            color: #888;
            line-height: 1.6;
        }
        .instructions h4 { margin: 0 0 8px 0; color: #aaa; font-size: 12px; }
    </style>
</head>
<body>
    <div class="view-section">
        <img id="video-feed" src="/video_feed" alt="摄像头画面">
        <canvas id="overlay-canvas"></canvas>
    </div>
    
    <div class="control-section">
        <!-- 状态面板 -->
        <div class="status-panel">
            <div class="status-label">当前识别状态</div>
            <div id="status-display" class="status-text">初始化中...</div>
            <div style="margin-top: 10px; font-size: 12px; color: #666;">
                脚部检测: <span id="feet-status">未知</span>
            </div>
        </div>
        
        <!-- 整体投影区域 -->
        <div class="card" id="card-main">
            <div class="card-header">
                <span class="card-title">
                    <span class="card-icon">📐</span>
                    整体投影区域
                </span>
                <span class="card-badge" style="color: #00e5ff;">校准边界</span>
            </div>
            <div class="card-body">
                <p class="card-hint">
                    框选地面投影的四个角。此区域用于透视变换，将摄像头画面中的梯形校正为矩形，建立坐标映射关系。
                </p>
                <div class="btn-group">
                    <button class="btn btn-edit" onclick="startEdit('main')">编辑顶点</button>
                    <button class="btn btn-save" onclick="confirmEdit('main')">确定保存</button>
                </div>
            </div>
        </div>
        
        <!-- 识别区域容器 -->
        <div id="zones-container"></div>
        
        <!-- 使用说明 -->
        <div class="instructions">
            <h4>📖 使用说明</h4>
            1. 点击"编辑顶点"进入编辑模式<br>
            2. 在左侧画面上拖动顶点调整位置<br>
            3. 点击"确定保存"保存配置<br>
            4. 三个区域会显示在Projection页面
        </div>
    </div>

    <script>
        // ========== 全局变量 ==========
        const canvas = document.getElementById('overlay-canvas');
        const ctx = canvas.getContext('2d');
        const img = document.getElementById('video-feed');
        
        let config = { main_area: [], zones: [] };
        let editingType = null;      // 当前编辑类型: 'main' 或 zone id
        let draggingIdx = -1;        // 当前拖动的顶点索引
        let isMouseDown = false;
        
        // ========== 初始化 ==========
        function init() {
            // 调整Canvas尺寸
            resizeCanvas();
            
            // 获取配置
            fetch('/api/config')
                .then(r => r.json())
                .then(data => {
                    config = data;
                    renderZoneCards();
                });
            
            // 启动绘制循环
            requestAnimationFrame(draw);
            
            // 定时更新状态
            setInterval(updateStatus, 300);
        }
        
        function resizeCanvas() {
            const rect = img.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;
        }
        
        // 监听图片加载和窗口大小变化
        img.onload = resizeCanvas;
        window.onresize = resizeCanvas;
        setTimeout(resizeCanvas, 500);
        
        // ========== 绘制循环 ==========
        function draw() {
            if (canvas.width === 0 || canvas.height === 0) {
                requestAnimationFrame(draw);
                return;
            }
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // 绘制整体投影区域
            drawPolygon(config.main_area, '#00e5ff', editingType === 'main', true);
            
            // 绘制三个识别区域
            config.zones.forEach(zone => {
                drawPolygon(zone.points, zone.color, editingType === zone.id, false);
            });
            
            requestAnimationFrame(draw);
        }
        
        function drawPolygon(points, color, isEditing, isMain) {
            if (!points || points.length !== 4) return;
            
            const w = canvas.width;
            const h = canvas.height;
            
            // 绘制填充（仅主区域）
            if (isMain) {
                ctx.fillStyle = 'rgba(0, 229, 255, 0.1)';
                ctx.beginPath();
                points.forEach((p, i) => {
                    const px = p[0] * w, py = p[1] * h;
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                });
                ctx.closePath();
                ctx.fill();
            }
            
            // 绘制边框
            ctx.strokeStyle = color;
            ctx.lineWidth = isEditing ? 4 : 2;
            ctx.setLineDash(isEditing ? [] : [8, 4]);
            ctx.beginPath();
            points.forEach((p, i) => {
                const px = p[0] * w, py = p[1] * h;
                if (i === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
            });
            ctx.closePath();
            ctx.stroke();
            ctx.setLineDash([]);
            
            // 绘制顶点
            points.forEach((p, i) => {
                const px = p[0] * w, py = p[1] * h;
                const radius = isEditing ? 14 : 8;
                
                // 外圈
                ctx.beginPath();
                ctx.arc(px, py, radius, 0, Math.PI * 2);
                ctx.fillStyle = isEditing ? '#fff' : color;
                ctx.fill();
                
                // 内圈
                if (isEditing) {
                    ctx.beginPath();
                    ctx.arc(px, py, radius - 3, 0, Math.PI * 2);
                    ctx.fillStyle = color;
                    ctx.fill();
                }
                
                // 顶点编号
                if (isEditing) {
                    ctx.fillStyle = '#000';
                    ctx.font = 'bold 12px Arial';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(i + 1, px, py);
                }
            });
        }
        
        // ========== 鼠标交互 ==========
        function getMousePos(e) {
            const rect = canvas.getBoundingClientRect();
            return {
                x: (e.clientX - rect.left) / canvas.width,
                y: (e.clientY - rect.top) / canvas.height
            };
        }
        
        function getTargetPoints() {
            if (editingType === 'main') {
                return config.main_area;
            } else if (editingType && typeof editingType === 'number') {
                const zone = config.zones.find(z => z.id === editingType);
                return zone ? zone.points : null;
            }
            return null;
        }
        
        canvas.addEventListener('mousedown', (e) => {
            if (!editingType) return;
            
            const pos = getMousePos(e);
            const pts = getTargetPoints();
            if (!pts) return;
            
            // 查找最近的顶点
            let minDist = 0.06;  // 点击检测阈值
            for (let i = 0; i < pts.length; i++) {
                const d = Math.hypot(pts[i][0] - pos.x, pts[i][1] - pos.y);
                if (d < minDist) {
                    minDist = d;
                    draggingIdx = i;
                }
            }
            
            isMouseDown = true;
        });
        
        canvas.addEventListener('mousemove', (e) => {
            if (!editingType || draggingIdx === -1 || !isMouseDown) return;
            
            const pos = getMousePos(e);
            const pts = getTargetPoints();
            if (pts) {
                // 限制在 0-1 范围内
                pts[draggingIdx] = [
                    Math.max(0, Math.min(1, pos.x)),
                    Math.max(0, Math.min(1, pos.y))
                ];
            }
        });
        
        canvas.addEventListener('mouseup', () => {
            isMouseDown = false;
            draggingIdx = -1;
        });
        
        canvas.addEventListener('mouseleave', () => {
            isMouseDown = false;
            draggingIdx = -1;
        });
        
        // ========== 编辑控制 ==========
        function startEdit(type) {
            // 先保存之前的编辑
            if (editingType !== null) {
                saveConfig();
            }
            
            editingType = type;
            
            // 更新UI
            document.querySelectorAll('.card').forEach(c => c.classList.remove('editing'));
            const cardId = type === 'main' ? 'card-main' : `card-zone-${type}`;
            document.getElementById(cardId)?.classList.add('editing');
        }
        
        function confirmEdit(type) {
            editingType = null;
            saveConfig();
            
            // 更新UI
            document.querySelectorAll('.card').forEach(c => c.classList.remove('editing'));
        }
        
        function saveConfig() {
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
            .then(r => r.json())
            .then(data => console.log('配置已保存:', data.msg))
            .catch(err => console.error('保存失败:', err));
        }
        
        // ========== UI生成 ==========
        function renderZoneCards() {
            const container = document.getElementById('zones-container');
            container.innerHTML = config.zones.map(zone => `
                <div class="card" id="card-zone-${zone.id}">
                    <div class="card-header">
                        <span class="card-title">
                            <span class="color-dot" style="background: ${zone.color}"></span>
                            识别区域 ${zone.id}
                        </span>
                        <span class="card-badge" style="color: ${zone.color}">交互区域</span>
                    </div>
                    <div class="card-body">
                        <p class="card-hint">
                            定义第 ${zone.id} 个交互区域的四个角。支持不规则四边形，用于判断用户是否踩踏在此区域。
                        </p>
                        <div class="btn-group">
                            <button class="btn btn-edit" onclick="startEdit(${zone.id})">编辑顶点</button>
                            <button class="btn btn-save" onclick="confirmEdit(${zone.id})">确定保存</button>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        // ========== 状态更新 ==========
        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    const statusEl = document.getElementById('status-display');
                    const feetEl = document.getElementById('feet-status');
                    
                    statusEl.textContent = data.status_text;
                    statusEl.className = 'status-text' + (data.active_zone_id ? ' triggered' : '');
                    
                    feetEl.textContent = data.feet_detected ? '已检测' : '未检测到';
                    feetEl.style.color = data.feet_detected ? '#33B555' : '#ff6b6b';
                })
                .catch(err => console.error('状态更新失败:', err));
        }
        
        // 启动
        setTimeout(init, 1000);
    </script>
</body>
</html>
"""

# ============================================================================
# HTML模板 - Projection投影端页面
# ============================================================================
html_projection = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>投影画面 - 地面投影交互系统</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            background: #000; 
            color: #fff; 
            overflow: hidden; 
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; 
            height: 100vh; 
            width: 100vw;
        }
        
        /* 主容器 */
        .container {
            width: 100%;
            height: 100%;
            position: relative;
            display: flex;
            flex-direction: column;
        }
        
        /* 顶部状态文字 */
        #status-text {
            position: absolute;
            top: 5%;
            left: 50%;
            transform: translateX(-50%);
            font-size: 8vw;
            font-weight: bold;
            color: #fff;
            text-shadow: 0 0 30px rgba(255, 255, 255, 0.5);
            z-index: 100;
            white-space: nowrap;
            transition: all 0.3s;
        }
        #status-text.triggered {
            color: #FFD111;
            text-shadow: 0 0 40px rgba(255, 209, 17, 0.8);
        }
        
        /* 脚部位置圆点 */
        #foot-point {
            width: 100px;
            height: 100px;
            background: radial-gradient(circle, #33B555, #228B22);
            border-radius: 50%;
            position: absolute;
            box-shadow: 
                0 0 30px #33B555,
                0 0 60px rgba(51, 181, 85, 0.5),
                inset 0 0 20px rgba(255, 255, 255, 0.3);
            display: none;
            transform: translate(-50%, -50%);
            transition: left 0.15s ease-out, top 0.15s ease-out;
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
            background: rgba(255, 255, 255, 0.4);
            border-radius: 50%;
        }
        
        /* 区域边框 */
        .zone-border {
            position: absolute;
            border: 4px solid;
            pointer-events: none;
            transition: all 0.2s;
            border-radius: 8px;
        }
        .zone-border.active {
            border-width: 6px;
            box-shadow: 0 0 30px currentColor;
        }
        
        /* 区域标签 */
        .zone-label {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 3vw;
            font-weight: bold;
            text-shadow: 0 0 10px currentColor;
            opacity: 0.8;
        }
    </style>
</head>
<body>
    <div class="container">
        <div id="status-text">准备就绪</div>
        <div id="foot-point"></div>
        <div id="zones-layer"></div>
    </div>

    <script>
        // ========== 全局变量 ==========
        const statusText = document.getElementById('status-text');
        const footPoint = document.getElementById('foot-point');
        const zonesLayer = document.getElementById('zones-layer');
        
        const projW = 1920;  // 投影分辨率宽度
        const projH = 1080;  // 投影分辨率高度
        
        let config = { zones: [] };
        let activeZoneId = null;
        
        // ========== 初始化 ==========
        function init() {
            fetch('/api/config')
                .then(r => r.json())
                .then(data => {
                    config = data;
                    drawZones();
                });
            
            // 高频更新投影画面
            setInterval(update, 50);
            
            // 低频更新区域配置
            setInterval(updateConfig, 2000);
        }
        
        // ========== 绘制区域 ==========
        function drawZones() {
            zonesLayer.innerHTML = '';
            
            config.zones.forEach(zone => {
                // 计算边界框
                const xs = zone.points.map(p => p[0]);
                const ys = zone.points.map(p => p[1]);
                const minX = Math.min(...xs);
                const maxX = Math.max(...xs);
                const minY = Math.min(...ys);
                const maxY = Math.max(...ys);
                
                // 创建区域边框
                const div = document.createElement('div');
                div.className = 'zone-border' + (zone.id === activeZoneId ? ' active' : '');
                div.style.left = (minX / projW * 100) + '%';
                div.style.top = (minY / projH * 100) + '%';
                div.style.width = ((maxX - minX) / projW * 100) + '%';
                div.style.height = ((maxY - minY) / projH * 100) + '%';
                div.style.borderColor = zone.color;
                div.style.color = zone.color;
                
                // 添加标签
                const label = document.createElement('div');
                label.className = 'zone-label';
                label.textContent = '区域 ' + zone.id;
                label.style.color = zone.color;
                div.appendChild(label);
                
                zonesLayer.appendChild(div);
            });
        }
        
        // ========== 更新投影画面 ==========
        function update() {
            fetch('/api/projection_data')
                .then(r => r.json())
                .then(data => {
                    // 更新状态文字
                    statusText.textContent = data.status_text;
                    if (data.active_zone_id) {
                        statusText.classList.add('triggered');
                    } else {
                        statusText.classList.remove('triggered');
                    }
                    
                    // 更新脚部位置
                    if (data.feet_detected) {
                        footPoint.style.display = 'block';
                        footPoint.style.left = (data.feet_x / projW * 100) + '%';
                        footPoint.style.top = (data.feet_y / projH * 100) + '%';
                    } else {
                        footPoint.style.display = 'none';
                    }
                    
                    // 更新活动区域
                    if (data.active_zone_id !== activeZoneId) {
                        activeZoneId = data.active_zone_id;
                        drawZones();
                    }
                })
                .catch(err => console.error('更新失败:', err));
        }
        
        // ========== 更新配置 ==========
        function updateConfig() {
            fetch('/api/config')
                .then(r => r.json())
                .then(data => {
                    config = data;
                    drawZones();
                });
        }
        
        // 启动
        init();
    </script>
</body>
</html>
"""

# ============================================================================
# 核心处理类
# ============================================================================
mp_pose = mp.solutions.pose

class InteractionProcessor:
    """交互处理器：负责摄像头采集、姿态检测、区域判断"""
    
    def __init__(self):
        # 初始化摄像头
        self.cap = cv2.VideoCapture(1)  # 优先使用外置摄像头
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)  # 回退到默认摄像头
        
        # 设置摄像头参数
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # 获取实际分辨率
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"摄像头分辨率: {self.frame_w}x{self.frame_h}")
        
        # 初始化MediaPipe Pose
        self.pose = mp_pose.Pose(
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
            model_complexity=1,  # 0=轻量, 1=标准, 2=高精度
            enable_segmentation=False
        )
        
        # 线程控制
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        
        # 启动处理线程
        threading.Thread(target=self._process_loop, daemon=True).start()
        print("交互处理器已启动")
    
    def _process_loop(self):
        """主处理循环"""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # 镜像翻转（更直观的交互体验）
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            
            # 转换为RGB用于MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb_frame)
            
            # 初始化状态
            status_text = "等待进入投影区域"
            feet_detected = False
            feet_x, feet_y = state["projection_size"][0] // 2, state["projection_size"][1] // 2
            active_zone_id = None
            
            # 处理检测结果
            if results.pose_landmarks:
                # 绘制全身骨骼
                mp.solutions.drawing_utils.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    mp.solutions.drawing_styles.get_default_pose_landmarks_style()
                )
                
                landmarks = results.pose_landmarks.landmark
                
                # 获取脚踝位置 (27=左脚踝, 28=右脚踝)
                left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE]
                right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE]
                
                # 检查可见度
                if left_ankle.visibility > 0.5 and right_ankle.visibility > 0.5:
                    # 计算脚踝在画面中的像素坐标
                    l_pt = (int(left_ankle.x * w), int(left_ankle.y * h))
                    r_pt = (int(right_ankle.x * w), int(right_ankle.y * h))
                    
                    # 在画面上高亮双脚
                    cv2.circle(frame, l_pt, 12, (0, 255, 0), -1)
                    cv2.circle(frame, r_pt, 12, (0, 255, 0), -1)
                    cv2.line(frame, l_pt, r_pt, (0, 255, 255), 3)
                    
                    # 计算双脚中心点
                    feet_center = ((l_pt[0] + r_pt[0]) // 2, (l_pt[1] + r_pt[1]) // 2)
                    cv2.circle(frame, feet_center, 8, (255, 0, 255), -1)
                    
                    # 进行透视变换和区域检测
                    if state["transform_matrix"] is not None:
                        try:
                            # 将脚部中心点映射到投影坐标系
                            src_pt = np.array([[[feet_center[0], feet_center[1]]]], dtype=np.float32)
                            dst_pt = cv2.perspectiveTransform(src_pt, state["transform_matrix"])[0][0]
                            feet_x, feet_y = int(dst_pt[0]), int(dst_pt[1])
                            feet_detected = True
                            
                            # 计算双脚距离
                            foot_dist = math.hypot(l_pt[0] - r_pt[0], l_pt[1] - r_pt[1])
                            
                            if foot_dist < state["max_foot_dist"]:
                                # 检测是否在某个区域内
                                found = False
                                for zone in state["zones"]:
                                    # 将区域顶点转换为numpy数组
                                    zone_pts = np.array(zone["points"], dtype=np.int32)
                                    
                                    # 判断脚中心是否在区域内
                                    if cv2.pointPolygonTest(zone_pts, (feet_x, feet_y), False) >= 0:
                                        status_text = f"触发区域 {zone['id']}"
                                        active_zone_id = zone['id']
                                        found = True
                                        break
                                
                                if not found:
                                    status_text = "移动中..."
                            else:
                                status_text = "请双脚靠拢"
                                
                        except Exception as e:
                            print(f"透视变换错误: {e}")
                            status_text = "校准错误"
                    else:
                        status_text = "请先校准"
                else:
                    status_text = "请完全进入画面"
            
            # 绘制校准区域（在管理端显示）
            self._draw_calibration_overlay(frame, w, h)
            
            # 更新全局状态
            with self.lock:
                self.frame = frame.copy()
                state["status_text"] = status_text
                state["feet_x"] = feet_x
                state["feet_y"] = feet_y
                state["feet_detected"] = feet_detected
                state["active_zone_id"] = active_zone_id
            
            time.sleep(0.01)  # 控制处理频率
    
    def _draw_calibration_overlay(self, frame, w, h):
        """绘制校准区域叠加层"""
        # 绘制主区域
        main_pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in state["main_area"]], dtype=np.int32)
        cv2.polylines(frame, [main_pts], True, (0, 229, 255), 2)
        
        # 绘制三个识别区域
        for zone in state["zones"]:
            zone_pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in zone["points"]], dtype=np.int32)
            # 解析颜色
            hex_color = zone['color'].lstrip('#')
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            bgr = (rgb[2], rgb[1], rgb[0])
            cv2.polylines(frame, [zone_pts], True, bgr, 2)
    
    def get_frame(self):
        """获取当前帧（JPEG格式）"""
        with self.lock:
            if self.frame is None:
                return None
            _, buf = cv2.imencode('.jpg', self.frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return buf.tobytes()
    
    def stop(self):
        """停止处理"""
        self.running = False
        self.cap.release()
        self.pose.close()

# ============================================================================
# Flask路由
# ============================================================================

# 创建处理器实例
processor = InteractionProcessor()

@app.route('/')
def index():
    """默认路由：跳转到管理端"""
    return render_template_string(html_admin)

@app.route('/admin')
def admin():
    """管理端页面"""
    return render_template_string(html_admin)

@app.route('/projection')
def projection():
    """投影端页面"""
    return render_template_string(html_projection)

@app.route('/video_feed')
def video_feed():
    """视频流接口"""
    def generate():
        while True:
            frame = processor.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.03)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """配置接口"""
    if request.method == 'POST':
        data = request.json
        
        # 更新主区域
        if 'main_area' in data:
            state["main_area"] = data["main_area"]
            # 重新计算透视变换矩阵
            _update_transform_matrix()
        
        # 更新识别区域
        if 'zones' in data:
            state["zones"] = data["zones"]
        
        return jsonify({"msg": "配置已保存"})
    
    return jsonify({
        "main_area": state["main_area"],
        "zones": state["zones"]
    })

@app.route('/api/status')
def get_status():
    """状态接口"""
    return jsonify({
        "status_text": state["status_text"],
        "feet_detected": state["feet_detected"],
        "active_zone_id": state["active_zone_id"]
    })

@app.route('/api/projection_data')
def get_projection_data():
    """投影数据接口（聚合接口，减少请求次数）"""
    return jsonify({
        "status_text": state["status_text"],
        "feet_x": state["feet_x"],
        "feet_y": state["feet_y"],
        "feet_detected": state["feet_detected"],
        "active_zone_id": state["active_zone_id"]
    })

def _update_transform_matrix():
    """更新透视变换矩阵"""
    try:
        # 源点（摄像头坐标系）
        src_pts = np.array([
            [p[0] * processor.frame_w, p[1] * processor.frame_h] 
            for p in state["main_area"]
        ], dtype=np.float32)
        
        # 目标点（投影坐标系）
        proj_w, proj_h = state["projection_size"]
        dst_pts = np.array([
            [0, 0], [proj_w, 0], [proj_w, proj_h], [0, proj_h]
        ], dtype=np.float32)
        
        # 计算透视变换矩阵
        state["transform_matrix"] = cv2.getPerspectiveTransform(src_pts, dst_pts)
        print("透视变换矩阵已更新")
    except Exception as e:
        print(f"计算透视变换矩阵失败: {e}")
        state["transform_matrix"] = None

# ============================================================================
# 主程序入口
# ============================================================================
if __name__ == '__main__':
    print("=" * 60)
    print("老年机器人地面投影交互系统")
    print("=" * 60)
    print()
    print("使用说明:")
    print("  1. 访问管理端: http://localhost:5000/admin")
    print("  2. 访问投影端: http://localhost:5000/projection")
    print("  3. 在管理端拖动顶点进行校准")
    print("  4. 投影端会显示三个交互区域和脚部位置")
    print()
    print("按 Ctrl+C 停止程序")
    print("=" * 60)
    
    # 初始化透视变换矩阵
    _update_transform_matrix()
    
    # 启动Flask服务
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
