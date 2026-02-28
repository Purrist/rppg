import cv2
import mediapipe as mp
import threading
import time
from flask import Flask, Response, render_template_string

app = Flask(__name__)

# --- HTML 模板 (与之前相同) ---
html_page = """
<!DOCTYPE html>
<html>
<head>
    <title>Real-time Pose Estimation</title>
    <style>
        * { margin: 0; padding: 0; }
        body, html { width: 100%; height: 100%; background-color: #000; overflow: hidden; }
        img { width: 100vw; height: 100vh; object-fit: cover; display: block; }
    </style>
</head>
<body>
    <img src="{{ url_for('video_feed') }}">
</body>
</html>
"""

# --- MediaPipe 初始化 ---
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

class VideoCamera:
    def __init__(self):
        # 尝试索引 1，不行试 0
        self.video = cv2.VideoCapture(1)
        if not self.video.isOpened():
            self.video = cv2.VideoCapture(0)
            if not self.video.isOpened():
                print("错误：未找到可用摄像头。请检查摄像头连接或索引。")
                self.is_running = False
                self.frame = None
                return
        
        # 设定分辨率和帧率，以平衡清晰度和流畅度
        # MediaPipe 在较低分辨率下运行更快
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # 降低分辨率以提升处理速度
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480) # 降低分辨率以提升处理速度
        self.video.set(cv2.CAP_PROP_FPS, 30) # 尝试设定帧率

        print(f"摄像头初始化成功，当前分辨率: {self.video.get(cv2.CAP_PROP_FRAME_WIDTH)}x{self.video.get(cv2.CAP_PROP_FRAME_HEIGHT)}")

        self.success, self.frame = self.video.read()
        self.is_running = True
        
        # MediaPipe Pose 模型，参数优化
        # min_detection_confidence: 最小检测置信度
        # min_tracking_confidence: 最小追踪置信度
        # model_complexity: 0 (light) -> 2 (heavy)，0最快，2最准
        self.pose = mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0 # 关键！选择轻量级模型以保证实时性
        )
        self.results = None # 存储姿态检测结果

        # 启动后台线程读取画面和处理姿态
        self.thread = threading.Thread(target=self._update, args=())
        self.thread.daemon = True
        self.thread.start()

    def _update(self):
        while self.is_running:
            success, frame = self.video.read()
            if success:
                self.success = success
                # 图像翻转 (可选，取决于摄像头方向)
                # frame = cv2.flip(frame, 1) 

                # MediaPipe 处理需要 RGB 格式
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 处理姿态
                self.results = self.pose.process(frame_rgb)

                # 将处理结果绘制回 BGR 帧，用于显示
                if self.results.pose_landmarks:
                    # 绘制所有骨骼
                    mp_drawing.draw_landmarks(
                        frame,
                        self.results.pose_landmarks,
                        mp_pose.POSE_CONNECTIONS,
                        landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
                    )

                    # 重点标记双脚 (用红色圆点)
                    # 左右脚踝对应的landmark索引
                    left_ankle_idx = mp_pose.PoseLandmark.LEFT_ANKLE.value
                    right_ankle_idx = mp_pose.PoseLandmark.RIGHT_ANKLE.value
                    
                    landmarks = self.results.pose_landmarks.landmark
                    h, w, c = frame.shape

                    if landmarks[left_ankle_idx].visibility > 0.5: # 确保可见度高
                        lx, ly = int(landmarks[left_ankle_idx].x * w), int(landmarks[left_ankle_idx].y * h)
                        cv2.circle(frame, (lx, ly), 10, (0, 0, 255), -1) # 红色实心圆

                    if landmarks[right_ankle_idx].visibility > 0.5: # 确保可见度高
                        rx, ry = int(landmarks[right_ankle_idx].x * w), int(landmarks[right_ankle_idx].y * h)
                        cv2.circle(frame, (rx, ry), 10, (0, 0, 255), -1) # 红色实心圆

                self.frame = frame # 更新为处理后的帧
            else:
                self.success = False
            time.sleep(0.01) # 稍微睡眠防止CPU空转

    def get_jpg_frame(self):
        if not self.success or self.frame is None:
            return None
        
        # 编码为 JPEG (降低质量以提升传输速度)
        ret, buffer = cv2.imencode('.jpg', self.frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buffer.tobytes()

    def __del__(self):
        self.is_running = False
        if self.video and self.video.isOpened():
            self.video.release()
        if self.pose:
            self.pose.close() # 释放MediaPipe资源

# 初始化全局摄像头对象
cam = VideoCamera()

def generate_frames():
    while True:
        frame_bytes = cam.get_jpg_frame()
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.03) # 控制网页端的最高发送频率约为 30FPS

@app.route('/')
def index():
    return render_template_string(html_page)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), 
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)