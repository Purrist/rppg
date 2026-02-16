import sys, time, threading
from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
from tablet_processor import TabletProcessor
from screen_processor import ScreenProcessor
from games import WhackAMole
from akon_agent import ask_akon

app = Flask(__name__)
CORS(app)
# 使用 threading 模式并限制发送队列大小，确保流传输流畅
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10**6)

# --- 全局系统状态 ---
system_state = {
    "current_page": "/",  # 追踪当前平板端应该显示的页面
}

# --- 1. 平板端摄像头（老人状态感知） ---
processor = TabletProcessor(sys.argv[1] if len(sys.argv) > 1 else "http://192.168.2.8:8080/video")

# --- 2. 投影端摄像头（交互识别） ---
try:
    raw_arg = sys.argv[2] if len(sys.argv) > 2 else "1"
    screen_cam_source = int(raw_arg) if str(raw_arg).isdigit() else raw_arg
except:
    screen_cam_source = 1

screen_proc = ScreenProcessor(screen_cam_source, socketio)
current_game = WhackAMole(socketio)

# --- Socket 交互逻辑 ---

@socketio.on('request_nav')
def handle_nav(data):
    """处理导航请求：点击行为转化为全局信号"""
    target_page = data.get('page')
    if target_page:
        system_state["current_page"] = target_page
        # 广播给所有客户端（平板/浏览器标签）进行同步跳转
        socketio.emit('navigate_to', {"page": target_page})

@socketio.on('game_control')
def handle_game_control(data):
    """处理游戏控制信号"""
    action = data.get('action')
    if action == 'ready': current_game.set_ready()
    elif action == 'start': current_game.start_game()
    elif action == 'pause': current_game.toggle_pause()
    elif action == 'stop': current_game.stop()

@socketio.on('update_calibration_point')
def handle_update_point(data):
    """更新校准点"""
    index = data.get('index')
    x = data.get('x')
    y = data.get('y')
    screen_proc.update_calibration_point(index, x, y)

@socketio.on('update_hole')
def handle_update_hole(data):
    """更新地鼠洞区域"""
    index = data.get('index')
    x1 = data.get('x1')
    x2 = data.get('x2')
    y1 = data.get('y1')
    y2 = data.get('y2')
    screen_proc.update_hole(index, x1, x2, y1, y2)

@socketio.on('save_calibration')
def handle_save_calibration():
    """保存校准配置"""
    screen_proc.save_config()

@socketio.on('reset_calibration')
def handle_reset_calibration():
    """重置校准"""
    screen_proc.reset_calibration()

def main_worker():
    """中心化逻辑处理与状态广播线程"""
    last_emit_time = 0
    while True:
        now = time.time()
        t_data = processor.get_ui_data()
        s_data = screen_proc.get_latest() 
        
        # 1. 游戏逻辑判定（由后端统一控制状态机）
        if s_data and current_game.status != "PAUSED":
            interact = s_data['interact']
            # READY 状态：中间白圈进度满 1s 开始
            if current_game.status == "READY" and interact["progress"][1] >= 100:
                current_game.start_game()
            # PLAYING 状态：命中判定
            elif current_game.status == "PLAYING" and interact["hit_index"] != -1:
                current_game.handle_hit(interact["hit_index"])
        
        # 传入生理状态数据，实现自适应难度调节
        current_game.update(t_data['state'] if t_data else None)

        # 2. 定时广播（中心化同步的关键）
        if now - last_emit_time > 0.05: # 约 20fps 同步率
            # 广播游戏核心状态，确保多页面完全同步
            game_state = {
                "status": current_game.status,
                "score": current_game.score,
                "timer": current_game.timer,
                "current_mole": current_game.current_mole
            }
            socketio.emit('game_update', game_state)
            
            # 推送视频流与感知结果
            if s_data:
                socketio.emit('screen_stream', {'image': s_data['image'], 'interact': s_data['interact'], 'calibration': s_data.get('calibration')})
            if t_data:
                socketio.emit('tablet_stream', {'image': t_data['image'], 'state': t_data['state']})
            
            last_emit_time = now
        
        socketio.sleep(0.01)

# --- HTTP API 接口 ---

@app.route('/api/akon/chat', methods=['POST'])
def akon_chat():
    """处理阿康对话及自主指令跳转"""
    data = request.json
    user_message = data.get('message', '')
    sid = data.get('sid')
    
    # 获取模型回复及动作提取
    response_text, action_name, action_params = ask_akon(user_message)
    
    # 自主跳转逻辑实现：如果模型决定去某个页面
    if action_name == "navigate_to" and action_params:
        target_page = action_params[0]
        system_state["current_page"] = target_page
        # 触发全局跳转信号
        socketio.emit('navigate_to', {"page": target_page})
    
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
    # 启动中心化逻辑处理线程
    threading.Thread(target=main_worker, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)