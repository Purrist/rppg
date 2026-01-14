from flask import Flask, Response
from flask_cors import CORS
import cv2

app = Flask(__name__)
CORS(app) # 允许 Nuxt 跨域访问

class VideoCamera:
    def __init__(self):
        self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    def __del__(self):
        self.video.release()
    def get_frame(self):
        success, frame = self.video.read()
        if not success: return None
        # 这里以后可以添加 Mediapipe 处理
        _, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()

camera = VideoCamera()

def gen(camera):
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen(camera), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/health')
def health():
    return {"status": "ok"}