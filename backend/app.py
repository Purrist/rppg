import sys, time, threading
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from tablet_processor import TabletProcessor
from screen_processor import ScreenProcessor
from games import WhackAMole # 导入游戏类

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 初始化处理器
processor = TabletProcessor(sys.argv[1] if len(sys.argv) > 1 else "http://192.168.137.97:8080/video")
screen_proc = ScreenProcessor(sys.argv[2] if len(sys.argv) > 2 else "http://192.168.137.113:8080/video")

# 实例化游戏（后续可以根据前端指令切换不同的游戏实例）
current_game = WhackAMole(socketio)

def main_worker():
    """统一的后台处理线程"""
    while True:
        # 1. 处理平板数据推送
        t_data = processor.get_ui_data()
        if t_data:
            socketio.emit('tablet_stream', {'image': t_data['image'], 'state': t_data['state']})

        # 2. 处理投影识别与游戏逻辑
        s_img, interact = screen_proc.get_debug_frame()
        if s_img:
            socketio.emit('screen_stream', {'image': s_img, 'interact': interact})
            # 如果判定击中，交给游戏类处理
            if interact["hit_index"] != -1:
                current_game.handle_hit(interact["hit_index"])

        # 3. 驱动游戏内部逻辑更新
        current_game.update()
        
        time.sleep(0.04)

@socketio.on('start_game')
def handle_start():
    current_game.start()

@socketio.on('game_event')
def handle_event(data):
    if data['action'] == 'pause':
        current_game.playing = not current_game.playing

if __name__ == '__main__':
    processor.start()
    threading.Thread(target=main_worker, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)