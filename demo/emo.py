import cv2
import numpy as np
import onnxruntime as ort
from deepface import DeepFace
from flask import Flask, render_template, Response, jsonify, request
from flask_cors import CORS
import threading
import queue
import time
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# ==================== 配置 ====================
DEFAULT_IP_CAMERA_URL = "http://10.215.158.45:8080/video"
ONNX_MODEL_PATH = r"C:\\Users\\purriste\\Desktop\\PYProject\\rppg\\backend\\core\\models\\emotion-ferplus-8.onnx"

# FER+ 情绪标签
EMOTION_LABELS = ['中性', '快乐', '惊讶', '悲伤', '愤怒', '厌恶', '恐惧', '蔑视']

# DeepFace 情绪映射
DEEPFACE_EMOTION_MAP = {
    'neutral': '中性',
    'happy': '快乐',
    'surprise': '惊讶',
    'sad': '悲伤',
    'angry': '愤怒',
    'disgust': '厌恶',
    'fear': '恐惧'
}

# ==================== 全局状态 ====================
class AppState:
    def __init__(self):
        self.current_camera = 0  # 0=系统摄像头, 1=IP摄像头
        self.current_method = "onnx"  # "onnx" 或 "deepface"
        self.running = True
        self.frame_queue = queue.Queue(maxsize=2)
        self.result_queue = queue.Queue(maxsize=2)
        self.lock = threading.Lock()
        
        # 视频捕获
        self.cap = None
        self.current_url = 0
        
        # ONNX 会话
        self.ort_session = None
        self._init_onnx()
        
        # 启动处理线程
        self.process_thread = threading.Thread(target=self._process_frames, daemon=True)
        self.process_thread.start()
        
        # 启动摄像头
        self._init_camera()
    
    def _init_onnx(self):
        """初始化ONNX运行时"""
        try:
            if os.path.exists(ONNX_MODEL_PATH):
                self.ort_session = ort.InferenceSession(ONNX_MODEL_PATH)
                logger.info("ONNX模型加载成功")
            else:
                logger.error(f"ONNX模型未找到: {ONNX_MODEL_PATH}")
        except Exception as e:
            logger.error(f"ONNX模型加载失败: {e}")
    
    def _init_camera(self):
        """初始化摄像头"""
        with self.lock:
            if self.cap is not None:
                self.cap.release()
            
            if self.current_camera == 0:
                self.current_url = 0
                self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            else:
                self.current_url = DEFAULT_IP_CAMERA_URL
                self.cap = cv2.VideoCapture(DEFAULT_IP_CAMERA_URL)
            
            if not self.cap.isOpened():
                logger.error(f"无法打开摄像头: {self.current_url}")
            else:
                logger.info(f"摄像头已启动: {self.current_url}")
    
    def switch_camera(self, camera_id):
        """切换摄像头"""
        with self.lock:
            if camera_id != self.current_camera:
                self.current_camera = camera_id
                self._init_camera()
                return True
            return False
    
    def switch_method(self, method):
        """切换识别方法"""
        with self.lock:
            if method in ["onnx", "deepface"]:
                self.current_method = method
                logger.info(f"切换到方法: {method}")
                return True
            return False
    
    def preprocess_for_onnx(self, face_img):
        """预处理图像用于ONNX模型"""
        # FER+ 模型输入: 1x1x64x64 (灰度图)
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (64, 64))
        normalized = resized.astype(np.float32) / 255.0
        # 标准化 (根据FER+训练时的预处理)
        normalized = (normalized - 0.5) / 0.5
        input_tensor = np.expand_dims(np.expand_dims(normalized, axis=0), axis=0)
        return input_tensor
    
    def detect_face(self, frame):
        """检测人脸"""
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(48, 48))
        return faces
    
    def predict_onnx(self, face_img):
        """使用ONNX模型预测情绪"""
        if self.ort_session is None:
            return None, 0
        
        try:
            input_tensor = self.preprocess_for_onnx(face_img)
            input_name = self.ort_session.get_inputs()[0].name
            outputs = self.ort_session.run(None, {input_name: input_tensor})
            
            # Softmax
            scores = outputs[0][0]
            exp_scores = np.exp(scores - np.max(scores))
            probs = exp_scores / np.sum(exp_scores)
            
            emotion_idx = np.argmax(probs)
            confidence = float(probs[emotion_idx])
            
            # 返回所有情绪概率
            all_probs = {EMOTION_LABELS[i]: float(probs[i]) for i in range(len(EMOTION_LABELS))}
            
            return EMOTION_LABELS[emotion_idx], confidence, all_probs
        except Exception as e:
            logger.error(f"ONNX预测错误: {e}")
            return None, 0, {}
    
    def predict_deepface(self, face_img):
        """使用DeepFace预测情绪"""
        try:
            result = DeepFace.analyze(
                face_img,
                actions=['emotion'],
                enforce_detection=False,
                detector_backend='opencv',
                silent=True
            )
            
            if isinstance(result, list):
                result = result[0]
            
            emotions = result['emotion']
            dominant = result['dominant_emotion']
            confidence = float(emotions[dominant]) / 100.0
            
            # 映射为中文
            all_probs = {}
            for eng, chi in DEEPFACE_EMOTION_MAP.items():
                all_probs[chi] = float(emotions.get(eng, 0)) / 100.0
            
            # 添加蔑视（DeepFace不支持）
            all_probs['蔑视'] = 0.0
            
            return DEEPFACE_EMOTION_MAP.get(dominant, dominant), confidence, all_probs
        except Exception as e:
            logger.error(f"DeepFace预测错误: {e}")
            return None, 0, {}
    
    def _process_frames(self):
        """后台处理线程"""
        while self.running:
            try:
                if self.cap is None or not self.cap.isOpened():
                    time.sleep(0.1)
                    continue
                
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                
                # 人脸检测
                faces = self.detect_face(frame)
                
                result = {
                    'faces': [],
                    'method': self.current_method,
                    'camera': self.current_camera
                }
                
                for (x, y, w, h) in faces:
                    face_roi = frame[y:y+h, x:x+w]
                    
                    if self.current_method == "onnx":
                        emotion, conf, probs = self.predict_onnx(face_roi)
                    else:
                        emotion, conf, probs = self.predict_deepface(face_roi)
                    
                    if emotion:
                        result['faces'].append({
                            'bbox': [int(x), int(y), int(w), int(h)],
                            'emotion': emotion,
                            'confidence': round(conf, 3),
                            'all_probs': {k: round(v, 3) for k, v in probs.items()}
                        })
                
                # 放入队列（丢弃旧帧）
                if self.result_queue.full():
                    try:
                        self.result_queue.get_nowait()
                    except:
                        pass
                self.result_queue.put(result)
                
            except Exception as e:
                logger.error(f"处理帧错误: {e}")
                time.sleep(0.1)
    
    def get_frame_with_overlay(self):
        """获取带叠加层的帧"""
        if self.cap is None or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        # 获取最新结果
        result = None
        try:
            result = self.result_queue.get_nowait()
        except:
            pass
        
        # 绘制人脸框和情绪
        if result and 'faces' in result:
            for face in result['faces']:
                x, y, w, h = face['bbox']
                emotion = face['emotion']
                conf = face['confidence']
                
                # 绘制矩形
                color = (0, 255, 0) if self.current_method == "onnx" else (255, 128, 0)
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                
                # 绘制标签背景
                label = f"{emotion} ({conf:.0%})"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(frame, (x, y-th-10), (x+tw, y), color, -1)
                cv2.putText(frame, label, (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        
        # 绘制状态信息
        method_text = "方法: ONNX-FER+" if self.current_method == "onnx" else "方法: DeepFace"
        cam_text = "摄像头: 系统摄像头" if self.current_camera == 0 else "摄像头: IP摄像头"
        cv2.putText(frame, method_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame, cam_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        return frame, result

# 全局状态实例
app_state = AppState()

# ==================== Flask 路由 ====================

@app.route('/')
def index():
    return render_template('emo.html')

@app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            frame_data = app_state.get_frame_with_overlay()
            if frame_data is None:
                time.sleep(0.05)
                continue
            
            frame, _ = frame_data
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                continue
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.03)  # ~30fps
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/switch_camera', methods=['POST'])
def switch_camera():
    data = request.get_json()
    camera_id = data.get('camera', 0)
    success = app_state.switch_camera(camera_id)
    return jsonify({'success': success, 'camera': camera_id})

@app.route('/api/switch_method', methods=['POST'])
def switch_method():
    data = request.get_json()
    method = data.get('method', 'onnx')
    success = app_state.switch_method(method)
    return jsonify({'success': success, 'method': method})

@app.route('/api/status')
def get_status():
    return jsonify({
        'camera': app_state.current_camera,
        'method': app_state.current_method,
        'camera_url': str(app_state.current_url)
    })

@app.route('/api/latest_result')
def latest_result():
    try:
        result = app_state.result_queue.get_nowait()
        return jsonify(result)
    except:
        return jsonify({'faces': [], 'method': app_state.current_method})

if __name__ == '__main__':
    print("=" * 50)
    print("情绪识别服务器启动中...")
    print(f"ONNX模型: {ONNX_MODEL_PATH}")
    print(f"IP摄像头: {DEFAULT_IP_CAMERA_URL}")
    print("访问地址: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)