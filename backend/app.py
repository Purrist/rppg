import os
import sys
import time
import threading
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from tablet_processor import TabletProcessor
from screen_processor import ScreenProcessor

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
        
SCREEN_URL = sys.argv[2] if len(sys.argv) > 2 else "http://192.168.137.113:8080/video"
screen_proc = ScreenProcessor(SCREEN_URL)

@socketio.on('start_game')
def on_start(data):
    # 当平板点击开始，广播给投影端
    socketio.emit('game_command', {'action': 'start'})

@socketio.on('game_event')
def on_event(data):
    # 处理暂停、重开逻辑
    socketio.emit('game_command', data)

def screen_worker():
    print(f"🎮 投影识别线程启动: {SCREEN_URL}")
    while True:
        res = screen_proc.get_interaction()
        if res:
            # 发送给平板（显示进度）和投影端（显示动画）
            socketio.emit('interaction_update', res)
        time.sleep(0.05)

if __name__ == '__main__':
    # 1. 启动平板处理器（内部开启 _capture 和 _analyze 线程）
    # 负责面部情绪、rPPG心率等监测
    processor.start()
    
    # 2. 启动平板视频流推送线程 (stream_worker)
    # 将处理后的画面和生理数据发往前端
    t_tablet = threading.Thread(target=stream_worker, daemon=True)
    t_tablet.start()
    
    # 3. 启动投影识别线程 (screen_worker)
    # 负责手机摄像头流的手势/进度判定
    t_screen = threading.Thread(target=screen_worker, daemon=True)
    t_screen.start()
    
    print("=" * 50)
    print(f"✅ 系统核心已启动")
    print(f"🔗 平板流源: {VIDEO_URL}")
    print(f"🔗 投影流源: {SCREEN_URL}")
    print(f"🌍 服务运行在: http://localhost:8080")
    print("=" * 50)

    # 4. 启动 SocketIO 主服务
    # 注意：debug=False 是为了防止在 VSCode 中因热重载导致线程重复启动
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)