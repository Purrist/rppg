import sys, time, threading
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from tablet_processor import TabletProcessor
from screen_processor import ScreenProcessor
from games import WhackAMole

app = Flask(__name__)
CORS(app)
# 使用 threading 模式确保非阻塞通信
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 初始化状态感知处理器
processor = TabletProcessor(sys.argv[1] if len(sys.argv) > 1 else "http://192.168.137.97:8080/video")
screen_proc = ScreenProcessor(sys.argv[2] if len(sys.argv) > 2 else "http://192.168.137.113:8080/video")
current_game = WhackAMole(socketio)

@socketio.on('game_control')
def handle_game_control(data):
    """处理平板端发送的交互控制指令"""
    action = data.get('action')
    if action == 'ready':
        current_game.set_ready()
    elif action == 'stop':
        current_game.stop()
    elif action == 'pause':
        # 扩展逻辑：暂停当前状态切换
        pass

def main_worker():
    """核心分发线程：实现无感状态监测与实时同步"""
    while True:
        t_data = processor.get_ui_data()
        s_data = screen_proc.get_latest()
        
        health_state = t_data['state'] if t_data else None

        if s_data:
            interact = s_data['interact']
            # 逻辑判定：在 READY (白圈) 状态下，如果中间感应区进度满100，正式激活
            if current_game.status == "READY":
                if interact["progress"][1] >= 100:
                    current_game.start_game()
            
            # 运行中判定：如果击中地鼠，触发逻辑更新
            if current_game.status == "PLAYING":
                if interact["hit_index"] != -1:
                    current_game.handle_hit(interact["hit_index"])
            
            # 更新游戏逻辑（包含基于生理反馈的动态调节）
            current_game.update(health_state)
            
            # 推送投影端所需数据
            socketio.emit('screen_stream', {'image': s_data['image'], 'interact': interact})
        
        if t_data:
            # 推送平板端状态感知数据
            socketio.emit('tablet_stream', {'image': t_data['image'], 'state': t_data['state']})
            
        socketio.sleep(0.01) # 维持 100Hz 刷新，释放 CPU 资源

if __name__ == '__main__':
    processor.start()
    threading.Thread(target=main_worker, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)