import sys, time, threading
from flask import Flask, request, jsonify  # 补上了之前代码可能缺失的 request, jsonify
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

# --- 1. 平板端摄像头：维持现状，用于采集老人状态 ---
processor = TabletProcessor(sys.argv[1] if len(sys.argv) > 1 else "http://192.168.137.29:8080/video")

# --- 2. 外接摄像头 (camera1)：用于识别投影交互 ---
# 修改重点：如果你的 test_cam.py 运行结果显示 camera_index = 1 是外接摄像头，这里就填 1
# 同时也保留了从命令行参数 sys.argv[2] 传入的可能性
try:
    # 尝试将参数转为数字，如果失败（比如传入的是URL）则保持原样
    raw_arg = sys.argv[2] if len(sys.argv) > 2 else 1  # 默认值改为 1
    screen_cam_source = int(raw_arg) if str(raw_arg).isdigit() else raw_arg
except:
    screen_cam_source = 1

screen_proc = ScreenProcessor(screen_cam_source)
current_game = WhackAMole(socketio)

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
        s_data = screen_proc.get_latest() 
        
        # 1. 处理游戏逻辑判定
        if s_data and current_game.status != "PAUSED":
            interact = s_data['interact']
            # 根据逻辑：手放在圈内进度 100% 开始
            if current_game.status == "READY" and interact["progress"][1] >= 100:
                current_game.start_game()
            # 游戏中命中判断
            elif current_game.status == "PLAYING" and interact["hit_index"] != -1:
                current_game.handle_hit(interact["hit_index"])
        
        # 联动：将平板端采集到的健康数据传给游戏，用于自适应调节
        current_game.update(t_data['state'] if t_data else None)

        # 2. 限制视频流推送频率
        if now - last_emit_time > 0.04:
            if s_data:
                socketio.emit('screen_stream', {'image': s_data['image'], 'interact': s_data['interact']}, room=None)
            if t_data:
                socketio.emit('tablet_stream', {'image': t_data['image'], 'state': t_data['state']}, room=None)
            last_emit_time = now
        
        socketio.sleep(0.01)

@app.route('/api/akon/chat', methods=['POST'])
def akon_chat():
    """处理阿康的对话请求"""
    data = request.json
    user_message = data.get('message', '')
    sid = data.get('sid')
    
    response_text, action_name, action_params = ask_akon(user_message)
    
    result = {
        'reply': response_text,
        'action': {
            'name': action_name,
            'params': action_params
        }
    }
    
    if sid:
        socketio.emit('akon_response', result, to=sid)
    
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    processor.start()
    # 启动 ScreenProcessor 的读取线程（如果内部有读取循环）
    # 如果 screen_processor.py 没写线程启动，确保它在 __init__ 里已经 start 了
    threading.Thread(target=main_worker, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)