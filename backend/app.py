import sys, time, threading
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from tablet_processor import TabletProcessor
from screen_processor import ScreenProcessor
from games import WhackAMole
from akon_agent import ask_akon

app = Flask(__name__)
CORS(app)
# 使用 threading 模式并限制发送队列大小
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10**6)

processor = TabletProcessor(sys.argv[1] if len(sys.argv) > 1 else "http://192.168.137.97:8080/video")
screen_proc = ScreenProcessor(sys.argv[2] if len(sys.argv) > 2 else "http://192.168.137.113:8080/video")
current_game = WhackAMole(socketio)

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message', '')
    
    response, action_name, action_params = ask_akon(user_input)
    
    return jsonify({
        'response': response,
        'action': {
            'name': action_name,
            'params': action_params
        }
    })
    
@socketio.on('game_control')
def handle_game_control(data):
    action = data.get('action')
    if action == 'ready': current_game.set_ready()
    elif action == 'start': current_game.start_game()
    elif action == 'pause': current_game.toggle_pause()
    elif action == 'stop': current_game.stop()

def main_worker():
    last_emit_time = 0
    while True:
        now = time.time()
        t_data = processor.get_ui_data()
        s_data = screen_proc.get_latest() # 假设该方法获取最新帧并清空缓存
        
        # 1. 处理游戏逻辑判定 (不受帧率限制)
        if s_data and current_game.status != "PAUSED":
            interact = s_data['interact']
            if current_game.status == "READY" and interact["progress"][1] >= 100:
                current_game.start_game()
            elif current_game.status == "PLAYING" and interact["hit_index"] != -1:
                current_game.handle_hit(interact["hit_index"])
        
        current_game.update(t_data['state'] if t_data else None)

        # 2. 限制视频流推送频率 (Max 25fps) 解决堆积延迟
        if now - last_emit_time > 0.04:
            if s_data:
                socketio.emit('screen_stream', {'image': s_data['image'], 'interact': s_data['interact']}, room=None)
            if t_data:
                socketio.emit('tablet_stream', {'image': t_data['image'], 'state': t_data['state']}, room=None)
            last_emit_time = now
        
        socketio.sleep(0.01)

if __name__ == '__main__':
    processor.start()
    threading.Thread(target=main_worker, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)