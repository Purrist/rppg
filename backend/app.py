import os
import sys
import time
import threading
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from tablet_processor import TabletProcessor

app = Flask(__name__)
CORS(app)
# Windows + VSCode 调试环境下，threading 模式是最稳定的
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 获取命令行地址
VIDEO_URL = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.137.97:8080/video"
processor = TabletProcessor(VIDEO_URL)

def stream_worker():
    """彻底对齐：调用你写的 get_ui_data 方法"""
    print(f"🚀 推送线程已启动，目标源: {VIDEO_URL}")
    while True:
        try:
            # 调用你 TabletProcessor 里的 get_ui_data
            result = processor.get_ui_data()
            if result:
                # 这里的 result 包含你的 image (base64) 和 state (dict)
                socketio.emit('tablet_video_frame', {
                    'image': result['image'],
                    'data': result['state']
                })
        except Exception as e:
            print(f"推送循环崩溃: {e}")
        time.sleep(0.04) # 限制约 25FPS

if __name__ == '__main__':
    # 启动你写的 start() 以开启内部 _capture 和 _analyze 线程
    processor.start()
    
    # 启动 SocketIO 推送线程
    t = threading.Thread(target=stream_worker, daemon=True)
    t.start()
    
    print(f"✅ 服务运行在: http://localhost:8080")
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)