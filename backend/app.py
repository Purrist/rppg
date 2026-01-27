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
    """统一的后台处理线程：负责高效分发"""
    while True:
        # 1. 平板端数据 (生理信号/情绪)
        # 获取最新的缓存数据，不阻塞主循环
        t_data = processor.get_ui_data()
        if t_data:
            # 移除 buffer=False，直接发送
            socketio.emit('tablet_stream', {
                'image': t_data['image'], 
                'state': t_data['state']
            })

        # 2. 投影交互数据 (交互识别)
        s_data = screen_proc.get_latest()
        if s_data:
            # 移除 buffer=False，直接发送
            socketio.emit('screen_stream', {
                'image': s_data['image'], 
                'interact': s_data['interact']
            })
            
            # 游戏逻辑处理：如果击中，立即更新得分
            if s_data['interact']["hit_index"] != -1:
                current_game.handle_hit(s_data['interact']["hit_index"])
            
            # 驱动游戏逻辑（倒计时、地鼠位置刷新等）
            current_game.update()
        
        # 维持 100Hz 的检查频率，同时释放 CPU 给 eventlet 协程
        socketio.sleep(0.01)

if __name__ == '__main__':
    processor.start()
    threading.Thread(target=main_worker, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)