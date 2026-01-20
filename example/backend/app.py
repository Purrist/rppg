import sys
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from processor import EmotionProcessor

app = Flask(__name__)
CORS(app)
# 设置 async_mode 为 eventlet 提升并发性能
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 获取命令行参数中的 IP Webcam 地址
VIDEO_URL = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.137.97:8080/video"

processor = EmotionProcessor(VIDEO_URL)

def stream_worker():
    """持续推送画面线程"""
    while True:
        data = processor.get_ui_frame()
        if data:
            socketio.emit('video_frame', data)
        socketio.sleep(0.03) # 约 30fps 的推送速度

@socketio.on('connect')
def handle_connect():
    print("Client connected")

if __name__ == "__main__":
    socketio.start_background_task(stream_worker)
    socketio.run(app, host="0.0.0.0", port=8081)