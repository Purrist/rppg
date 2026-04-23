import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torchvision import transforms
from PIL import Image
import mediapipe as mp
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import traceback
import os

# ===================== 环境配置 =====================
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ===================== 简单 CNN 模型定义 =====================

class SimpleEmotionCNN(nn.Module):
    """轻量级情绪识别CNN - 不需要预训练权重"""
    def __init__(self, num_classes=7):
        super(SimpleEmotionCNN, self).__init__()
        # 卷积层
        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, stride=1, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1)
        
        # 池化和激活
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.5)
        self.batch_norm1 = nn.BatchNorm2d(32)
        self.batch_norm2 = nn.BatchNorm2d(64)
        self.batch_norm3 = nn.BatchNorm2d(128)
        
        # 全连接层
        self.fc1 = nn.Linear(128 * 28 * 28, 256)
        self.fc2 = nn.Linear(256, 128)
        self.fc3 = nn.Linear(128, num_classes)
    
    def forward(self, x):
        # 第1组卷积
        x = self.conv1(x)
        x = self.batch_norm1(x)
        x = F.relu(x)
        x = self.pool(x)
        x = self.dropout(x)
        
        # 第2组卷积
        x = self.conv2(x)
        x = self.batch_norm2(x)
        x = F.relu(x)
        x = self.pool(x)
        x = self.dropout(x)
        
        # 第3组卷积
        x = self.conv3(x)
        x = self.batch_norm3(x)
        x = F.relu(x)
        x = self.pool(x)
        x = self.dropout(x)
        
        # 展平
        x = x.view(x.size(0), -1)
        
        # 全连接层
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = F.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.fc3(x)
        
        return x


# ===================== 情绪识别核心模块 =====================

class MultiPoseEmotionDetector:
    def __init__(self, model_path=None):
        """初始化多视角情绪检测器"""
        try:
            print("📍 初始化 MediaPipe 人脸检测器...")
            # 使用MediaPipe进行多视角人脸检测（支持侧脸/低头）
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(
                model_selection=1,  # 1=full range model，支持远距离和侧脸
                min_detection_confidence=0.5
            )
            print("✓ MediaPipe 人脸检测器初始化成功")
            
            # 情绪分类模型
            print("📍 初始化情绪分类模型...")
            self.emotion_model = self._load_emotion_model(model_path)
            self.emotions = ['angry', 'disgust', 'fear', 'happy', 'neutral', 'sad', 'surprise']
            print("✓ 情绪分类模型初始化成功")
            
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            traceback.print_exc()
            raise
        
    def _load_emotion_model(self, model_path):
        """加载情绪分类模型 - 无需预训练权重"""
        try:
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            print(f"   使用设备: {device}")
            
            # 创建模型
            print(f"   创建 SimpleEmotionCNN 模型...")
            model = SimpleEmotionCNN(num_classes=7)
            
            # 尝试加载自定义模型
            if model_path:
                try:
                    print(f"   加载自定义模型: {model_path}")
                    state_dict = torch.load(model_path, map_location=device)
                    model.load_state_dict(state_dict)
                    print(f"   ✓ 自定义模型加载成功")
                except Exception as e:
                    print(f"   ⚠ 自定义模型加载失败: {e}")
                    print(f"   💡 使用随机初始化的模型")
            else:
                print(f"   💡 使用随机初始化的模型（建议用自己的数据训练）")
                print(f"   📝 模型参数数: {sum(p.numel() for p in model.parameters()):,}")
            
            model.to(device)
            model.eval()
            return model
            
        except Exception as e:
            print(f"   ❌ 模型加载失败: {e}")
            traceback.print_exc()
            raise
    
    def detect_faces(self, image):
        """多视角人脸检测"""
        try:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_image)
            
            faces = []
            if results.detections:
                h, w, _ = image.shape
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    x1 = int(bbox.xmin * w)
                    y1 = int(bbox.ymin * h)
                    x2 = int((bbox.xmin + bbox.width) * w)
                    y2 = int((bbox.ymin + bbox.height) * h)
                    
                    # 确保坐标有效
                    x1, x2 = max(0, x1), min(w, x2)
                    y1, y2 = max(0, y1), min(h, y2)
                    
                    # 添加边距
                    margin = int((x2 - x1) * 0.1)
                    x1 = max(0, x1 - margin)
                    x2 = min(w, x2 + margin)
                    y1 = max(0, y1 - margin)
                    y2 = min(h, y2 + margin)
                    
                    faces.append({
                        'bbox': (x1, y1, x2, y2),
                        'confidence': float(detection.score[0])
                    })
            return faces
        except Exception as e:
            print(f"检测失败: {e}")
            return []
    
    def recognize_emotion(self, image, face_bbox):
        """识别单个人脸的情绪（支持侧脸和低头）"""
        try:
            x1, y1, x2, y2 = face_bbox
            face_roi = image[y1:y2, x1:x2]
            
            if face_roi.size == 0 or face_roi.shape[0] < 32 or face_roi.shape[1] < 32:
                return None
            
            # 预处理
            face_pil = Image.fromarray(cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB))
            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                   std=[0.229, 0.224, 0.225])
            ])
            
            face_tensor = transform(face_pil).unsqueeze(0)
            face_tensor = face_tensor.to(self.device)
            
            # 推理
            with torch.no_grad():
                output = self.emotion_model(face_tensor)
                probabilities = torch.softmax(output, dim=1)
                emotion_idx = torch.argmax(probabilities, dim=1).item()
                confidence = probabilities[0, emotion_idx].item()
            
            return {
                'emotion': self.emotions[emotion_idx],
                'confidence': float(confidence),
                'all_emotions': {self.emotions[i]: float(probabilities[0, i].item()) 
                               for i in range(7)}
            }
        except Exception as e:
            print(f"情绪识别错误: {e}")
            return None
    
    def process_frame(self, frame):
        """处理一帧视频"""
        try:
            faces = self.detect_faces(frame)
            results = []
            
            for face in faces:
                emotion_result = self.recognize_emotion(frame, face['bbox'])
                if emotion_result:
                    results.append({
                        'bbox': face['bbox'],
                        'face_confidence': face['confidence'],
                        **emotion_result
                    })
            
            return results
        except Exception as e:
            print(f"处理帧失败: {e}")
            return []


# ===================== Flask Web应用 =====================

def create_app(detector):
    """创建Flask应用"""
    app = Flask(__name__)
    CORS(app)
    
    @app.route('/', methods=['GET'])
    def index():
        """返回HTML前端"""
        return get_html_content()
    
    @app.route('/api/health', methods=['GET'])
    def health():
        """健康检查"""
        return jsonify({'status': 'ok', 'message': '服务运行正常'})
    
    @app.route('/api/camera-info', methods=['GET'])
    def camera_info():
        """获取摄像头信息"""
        try:
            # 尝试打开摄像头 0
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                return jsonify({
                    'status': 'ok',
                    'camera_available': True,
                    'width': width,
                    'height': height,
                    'fps': fps
                })
            else:
                return jsonify({
                    'status': 'ok',
                    'camera_available': False,
                    'message': '摄像头不可用'
                })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'camera_available': False,
                'error': str(e)
            })
    
    @app.route('/detect', methods=['POST'])
    def detect_emotion():
        """处理上传的图像或视频帧"""
        try:
            data = request.json
            if not data:
                return jsonify({'success': False, 'error': '未提供数据'}), 400
            
            image_data = data.get('image', '')
            
            if not image_data:
                return jsonify({'success': False, 'error': '未提供图像数据'}), 400
            
            # 解码Base64图像
            try:
                if ',' in image_data:
                    img_bytes = base64.b64decode(image_data.split(',')[1])
                else:
                    img_bytes = base64.b64decode(image_data)
            except Exception as e:
                return jsonify({'success': False, 'error': f'图像解码失败: {str(e)}'}), 400
            
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return jsonify({'success': False, 'error': '图像解码失败'}), 400
            
            # 检测情绪
            results = detector.process_frame(frame)
            
            return jsonify({
                'success': True,
                'faces_detected': len(results),
                'emotions': results
            })
        except Exception as e:
            print(f"API错误: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    @app.route('/video', methods=['POST'])
    def detect_video():
        """处理视频流"""
        if 'video' not in request.files:
            return jsonify({'error': 'No video file'}), 400
        
        try:
            video_file = request.files['video']
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                video_path = tmp.name
                video_file.save(video_path)
            
            cap = cv2.VideoCapture(video_path)
            all_results = []
            frame_count = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 每5帧处理一次以加快速度
                if frame_count % 5 == 0:
                    results = detector.process_frame(frame)
                    all_results.append({
                        'frame': frame_count,
                        'detections': results
                    })
                
                frame_count += 1
            
            cap.release()
            os.remove(video_path)
            
            return jsonify({
                'success': True,
                'total_frames': frame_count,
                'results': all_results
            })
        except Exception as e:
            print(f"视频处理错误: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    return app


def get_html_content():
    """返回HTML前端内容"""
    return '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>多视角情绪识别系统</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                padding: 30px;
            }
            
            h1 {
                text-align: center;
                color: #333;
                margin-bottom: 10px;
                font-size: 2.5em;
            }
            
            .subtitle {
                text-align: center;
                color: #666;
                margin-bottom: 30px;
                font-size: 1.1em;
            }
            
            .content {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                margin-bottom: 30px;
            }
            
            .section {
                padding: 20px;
                border: 2px solid #eee;
                border-radius: 10px;
            }
            
            .section h2 {
                color: #667eea;
                margin-bottom: 15px;
                font-size: 1.3em;
            }
            
            #video, #canvas {
                width: 100%;
                border-radius: 10px;
                background: #000;
                max-height: 400px;
                display: block;
            }
            
            .controls {
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
                flex-wrap: wrap;
            }
            
            button {
                flex: 1;
                min-width: 120px;
                padding: 12px 20px;
                border: none;
                border-radius: 8px;
                background: #667eea;
                color: white;
                font-size: 1em;
                cursor: pointer;
                transition: all 0.3s ease;
                font-weight: bold;
            }
            
            button:hover {
                background: #764ba2;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            
            button:disabled {
                background: #ccc;
                cursor: not-allowed;
                transform: none;
            }
            
            .upload-section {
                border: 2px dashed #667eea;
                border-radius: 10px;
                padding: 30px;
                text-align: center;
                background: #f8f9ff;
            }
            
            .upload-section input[type="file"] {
                display: none;
            }
            
            .upload-label {
                display: inline-block;
                padding: 12px 25px;
                background: #667eea;
                color: white;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-weight: bold;
            }
            
            .upload-label:hover {
                background: #764ba2;
            }
            
            .results {
                background: #f8f9ff;
                border-radius: 10px;
                padding: 20px;
                border: 2px solid #eee;
            }
            
            .results h2 {
                color: #667eea;
                margin-bottom: 15px;
            }
            
            .emotion-item {
                background: white;
                padding: 15px;
                border-left: 4px solid #667eea;
                margin-bottom: 15px;
                border-radius: 5px;
            }
            
            .emotion-label {
                font-weight: bold;
                color: #333;
                margin-bottom: 8px;
                font-size: 1.1em;
            }
            
            .confidence-bar {
                width: 100%;
                height: 8px;
                background: #eee;
                border-radius: 4px;
                overflow: hidden;
                margin-top: 5px;
            }
            
            .confidence-fill {
                height: 100%;
                background: linear-gradient(90deg, #667eea, #764ba2);
                transition: width 0.3s ease;
            }
            
            .emotion-breakdown {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
                gap: 10px;
                margin-top: 10px;
            }
            
            .emotion-score {
                background: #f0f0f0;
                padding: 8px;
                border-radius: 5px;
                text-align: center;
                font-size: 0.85em;
            }
            
            .emotion-score .emotion-name {
                font-weight: bold;
                color: #333;
            }
            
            .emotion-score .score {
                color: #667eea;
                font-size: 1em;
                margin-top: 3px;
            }
            
            #imagePreview {
                max-height: 400px;
                border-radius: 10px;
            }
            
            .loading {
                text-align: center;
                color: #667eea;
                font-weight: bold;
            }
            
            .error {
                color: red;
                font-weight: bold;
            }
            
            .status-bar {
                background: #f0f0f0;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 15px;
                text-align: center;
                color: #666;
            }
            
            .info-box {
                background: #e3f2fd;
                border-left: 4px solid #2196F3;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 15px;
                font-size: 0.9em;
                color: #1565c0;
            }
            
            .debug-info {
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 10px;
                border-radius: 5px;
                margin-top: 10px;
                font-size: 0.85em;
                color: #856404;
                font-family: monospace;
            }
            
            @media (max-width: 768px) {
                .content {
                    grid-template-columns: 1fr;
                }
                
                h1 {
                    font-size: 1.8em;
                }
                
                .emotion-breakdown {
                    grid-template-columns: repeat(auto-fit, minmax(70px, 1fr));
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎭 多视角情绪识别系统</h1>
            <p class="subtitle">支持侧脸和低头等多种姿态下的实时情绪识别</p>
            
            <div class="info-box">
                ⚠️ 当前使用随机初始化模型。建议使用自己训练的模型以获得更好的识别效果。
                运行参数: <code>python emotion_recognition.py --model your_model.pth</code>
            </div>
            
            <div class="status-bar" id="statusBar">
                连接中... ⏳
            </div>
            
            <div class="content">
                <!-- 摄像头实时检测 -->
                <div class="section">
                    <h2>📹 实时摄像头</h2>
                    <div class="controls">
                        <button onclick="startCamera()" id="startBtn">启动摄像头</button>
                        <button onclick="stopCamera()" id="stopBtn" disabled>停止</button>
                        <button onclick="captureFrame()" id="captureBtn" disabled>截图检测</button>
                    </div>
                    <video id="video" autoplay muted playsinline style="width:100%; background:#000; border-radius:10px;"></video>
                    <canvas id="canvas" style="display:none;"></canvas>
                    <div class="debug-info" id="debugInfo">
                        摄像头状态: 未初始化
                    </div>
                </div>
                
                <!-- 图片上传检测 -->
                <div class="section">
                    <h2>🖼️ 图片检测</h2>
                    <div class="upload-section">
                        <label class="upload-label">
                            📁 选择图片
                            <input type="file" id="imageInput" accept="image/*">
                        </label>
                        <p style="color: #999; margin-top: 10px; font-size: 0.9em;">
                            支持JPG、PNG等常见格式
                        </p>
                    </div>
                    <img id="imagePreview" style="display:none; width:100%; margin-top:15px;">
                </div>
            </div>
            
            <!-- 检测结果 -->
            <div class="results">
                <h2>📊 检测结果</h2>
                <div id="results" style="color: #999; text-align: center; padding: 20px;">
                    等待检测...
                </div>
            </div>
        </div>

        <script>
            let video, canvas, ctx;
            let isRunning = false;
            let detectionInterval;
            const apiUrl = window.location.origin;
            
            function updateDebugInfo(message) {
                document.getElementById('debugInfo').innerText = message;
            }
            
            window.addEventListener('DOMContentLoaded', async () => {
                video = document.getElementById('video');
                canvas = document.getElementById('canvas');
                ctx = canvas.getContext('2d');
                
                document.getElementById('imageInput').addEventListener('change', handleImageUpload);
                
                // 检查服务器连接
                await checkServerConnection();
                
                // 检查摄像头可用性
                await checkCameraAvailability();
            });
            
            async function checkServerConnection() {
                try {
                    const response = await fetch(`${apiUrl}/api/health`);
                    if (response.ok) {
                        document.getElementById('statusBar').innerHTML = '✓ 服务连接成功';
                        document.getElementById('statusBar').style.background = '#d4edda';
                        document.getElementById('statusBar').style.color = '#155724';
                    }
                } catch (err) {
                    document.getElementById('statusBar').innerHTML = '❌ 无法连接到服务器';
                    document.getElementById('statusBar').style.background = '#f8d7da';
                    document.getElementById('statusBar').style.color = '#721c24';
                }
            }
            
            async function checkCameraAvailability() {
                try {
                    const response = await fetch(`${apiUrl}/api/camera-info`);
                    const data = await response.json();
                    
                    if (data.camera_available) {
                        updateDebugInfo(`✓ 摄像头可用 | ${data.width}x${data.height} @ ${data.fps.toFixed(1)}fps`);
                    } else {
                        updateDebugInfo('❌ 摄像头不可用');
                    }
                } catch (err) {
                    updateDebugInfo(`⚠️ 无法检查摄像头: ${err.message}`);
                }
            }
            
            async function startCamera() {
                try {
                    updateDebugInfo('📍 正在请求摄像头权限...');
                    
                    const stream = await navigator.mediaDevices.getUserMedia({
                        video: { 
                            width: { ideal: 1280 }, 
                            height: { ideal: 720 },
                            facingMode: 'user'
                        },
                        audio: false
                    });
                    
                    video.srcObject = stream;
                    
                    // 等待视频元数据加载
                    video.onloadedmetadata = () => {
                        updateDebugInfo(`✓ 摄像头已启动 | ${video.videoWidth}x${video.videoHeight}`);
                    };
                    
                    isRunning = true;
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = false;
                    document.getElementById('captureBtn').disabled = false;
                    
                    document.getElementById('results').innerHTML = '<p class="loading">📸 摄像头已启动，每500ms检测一次...</p>';
                    
                    detectionInterval = setInterval(detectFromCamera, 500);
                } catch (err) {
                    updateDebugInfo(`❌ 摄像头错误: ${err.message}`);
                    alert('❌ 无法访问摄像头：\\n' + err.message + '\\n\\n请检查：\\n1. 摄像头是否正确连接\\n2. 浏览器是否有摄像头权限\\n3. 其他应用是否占用摄像头');
                }
            }
            
            function stopCamera() {
                isRunning = false;
                clearInterval(detectionInterval);
                if (video.srcObject) {
                    video.srcObject.getTracks().forEach(track => track.stop());
                }
                document.getElementById('startBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('captureBtn').disabled = true;
                updateDebugInfo('⏹️ 摄像头已停止');
                document.getElementById('results').innerHTML = '<p style="color: #999; text-align: center;">摄像头已关闭</p>';
            }
            
            async function captureFrame() {
                if (!isRunning) {
                    alert('请先启动摄像头');
                    return;
                }
                
                try {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    
                    if (canvas.width === 0 || canvas.height === 0) {
                        alert('视频还未完全加载，请稍候...');
                        return;
                    }
                    
                    ctx.drawImage(video, 0, 0);
                    const imageData = canvas.toDataURL('image/jpeg', 0.8);
                    updateDebugInfo('📸 正在发送截图到服务器...');
                    await sendToBackend(imageData);
                } catch (err) {
                    updateDebugInfo(`❌ 截图错误: ${err.message}`);
                }
            }
            
            async function detectFromCamera() {
                if (!isRunning) return;
                
                try {
                    if (video.videoWidth === 0 || video.videoHeight === 0) {
                        return;
                    }
                    
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    ctx.drawImage(video, 0, 0);
                    
                    const imageData = canvas.toDataURL('image/jpeg', 0.8);
                    await sendToBackend(imageData);
                } catch (err) {
                    console.error('摄像头检测错误:', err);
                }
            }
            
            async function handleImageUpload(event) {
                const file = event.target.files[0];
                if (!file) return;
                
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const imageData = e.target.result;
                    document.getElementById('imagePreview').src = imageData;
                    document.getElementById('imagePreview').style.display = 'block';
                    
                    document.getElementById('results').innerHTML = '<p class="loading">⏳ 正在检测...</p>';
                    await sendToBackend(imageData);
                };
                reader.readAsDataURL(file);
            }
            
            async function sendToBackend(imageData) {
                try {
                    const response = await fetch(`${apiUrl}/detect`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ image: imageData })
                    });
                    
                    const result = await response.json();
                    displayResults(result);
                } catch (err) {
                    console.error('检测失败:', err);
                    document.getElementById('results').innerHTML = `<p class="error">❌ 检测失败: ${err.message}</p>`;
                }
            }
            
            function displayResults(result) {
                const resultsDiv = document.getElementById('results');
                
                if (!result.success) {
                    resultsDiv.innerHTML = `<p class="error">❌ 错误: ${result.error}</p>`;
                    return;
                }
                
                if (result.faces_detected === 0) {
                    resultsDiv.innerHTML = '<p style="color: #999; text-align: center;">⚠️ 未检测到人脸</p>';
                    return;
                }
                
                let html = `<p style="color: #333; margin-bottom: 15px; font-weight: bold;">✓ 检测到 ${result.faces_detected} 张脸</p>`;
                
                result.emotions.forEach((face, idx) => {
                    const topEmotions = Object.entries(face.all_emotions)
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 3);
                    
                    const emotionEmojis = {
                        'angry': '😠',
                        'disgust': '🤢',
                        'fear': '😨',
                        'happy': '😊',
                        'neutral': '😐',
                        'sad': '😢',
                        'surprise': '😲'
                    };
                    
                    const emoji = emotionEmojis[face.emotion] || '😊';
                    
                    html += `
                        <div class="emotion-item">
                            <div class="emotion-label">
                                ${emoji} 人脸 ${idx + 1}: ${face.emotion.toUpperCase()}
                            </div>
                            <div class="confidence-bar">
                                <div class="confidence-fill" style="width: ${face.confidence * 100}%"></div>
                            </div>
                            <p style="margin-top: 8px; color: #666; font-size: 0.9em;">
                                置信度: <strong>${(face.confidence * 100).toFixed(2)}%</strong>
                            </p>
                            <div class="emotion-breakdown">
                    `;
                    
                    topEmotions.forEach(([emotion, score]) => {
                        html += `
                            <div class="emotion-score">
                                <div class="emotion-name">${emotion}</div>
                                <div class="score">${(score * 100).toFixed(1)}%</div>
                            </div>
                        `;
                    });
                    
                    html += `
                            </div>
                        </div>
                    `;
                });
                
                resultsDiv.innerHTML = html;
            }
        </script>
    </body>
    </html>
    '''


# ===================== 主程序 =====================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='多视角情绪识别系统')
    parser.add_argument('--model', type=str, default=None, help='情绪分类模型路径')
    parser.add_argument('--port', type=int, default=5000, help='Web服务端口')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Web服务地址')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("🎭 多视角情绪识别系统 - 启动中...")
    print("=" * 60 + "\n")
    
    try:
        # 初始化检测器
        print("📌 第1步: 初始化检测器...")
        detector = MultiPoseEmotionDetector(model_path=args.model)
        print("✓ 检测器初始化完成\n")
        
        # 创建Flask应用
        print("📌 第2步: 创建Flask应用...")
        app = create_app(detector)
        print("✓ Flask应用创建完成\n")
        
        # 显示启动信息
        print("=" * 60)
        print("✅ 系统启动成功!")
        print("=" * 60)
        print(f"🌐 Web 地址: http://localhost:{args.port}")
        print(f"📝 服务器: {args.host}:{args.port}")
        print(f"💾 模型: {'自定义模型' if args.model else '随机初始化模型'}")
        print(f"🖥️  设备: {'CUDA (GPU)' if torch.cuda.is_available() else 'CPU'}")
        print("=" * 60)
        print("⏸️  按 Ctrl+C 停止服务\n")
        
        # 启动Flask应用
        app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
        
    except KeyboardInterrupt:
        print("\n\n❌ 服务已停止")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        traceback.print_exc()
        sys.exit(1)