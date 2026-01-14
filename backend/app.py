from flask import Flask, Response
from flask_cors import CORS
import cv2

app = Flask(__name__)
CORS(app) # 必须开启，否则 Nuxt 前端无法跨端口读取视频流

# 摄像头管理类
class VideoCamera:
    def __init__(self):
        # 0 通常是电脑自带摄像头
        self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW) 
    
    def __del__(self):
        self.video.release()

    def get_frame(self):
        success, frame = self.video.read()
        if not success:
            return None
        # 这里预留：未来可以在这里添加 rPPG 脸部识别算法
        _, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()

gen_camera = VideoCamera()

def frame_generator():
    while True:
        frame = gen_camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/')
def index():
    return {"status": "running", "api_endpoints": ["/video_feed", "/health"]}

@app.route('/health')
def health():
    return {"status": "ok"}

@app.route('/video_feed')
def video_feed():
    return Response(frame_generator(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')