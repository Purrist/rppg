import cv2
import base64
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 这里 0 通常是内置摄像头，1 通常是外接 USB 摄像头
# 如果看不到画面，请尝试将 0 改为 1 或 2
camera_index = 1 
cap = cv2.VideoCapture(camera_index)

def generate_frames():
    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            # 缩放一下，保证预览流畅
            frame = cv2.resize(frame, (640, 480))
            # 编码为 base64
            _, buffer = cv2.imencode('.jpg', frame)
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            socketio.emit('test_stream', {'image': jpg_as_text})
            socketio.sleep(0.03) # 约 30 帧

@socketio.on('connect')
def handle_connect():
    print("前端已连接")
    socketio.start_background_task(generate_frames)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8888)