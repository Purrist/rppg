# -*- coding: utf-8 -*-
"""
Flask主应用 - 整合状态管理、游戏控制、Socket通信
"""
import sys, time, threading, socket, os, json
from flask import Flask, request, jsonify, Response
from flask_socketio import SocketIO
from flask_cors import CORS

# 本地模块
from tablet_processor import TabletProcessor
from screen_processor import init_screen_processor, get_screen_processor, state
from games import WhackAMole
from akon_agent import ask_akon

# ============================================================================
# 获取本机IP
# ============================================================================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

# ============================================================================
# 配置文件
# ============================================================================
CONFIG_FILE = "projection_config.json"

def load_config_on_startup():
    """启动时加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if "corners" in config:
                state["corners"] = config["corners"]
            if "zones" in config:
                state["zones"] = config["zones"]
            if "zone_id_counter" in config:
                state["zone_id_counter"] = config["zone_id_counter"]
            print(f"✓ 配置已加载: {CONFIG_FILE}")
            return True
        except:
            pass
    return False

# ============================================================================
# Flask 应用初始化
# ============================================================================
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10**6)

# ============================================================================
# 系统状态管理
# ============================================================================
system_state = {
    "current_page": "/",
    "mode": "normal",
    "game": {
        "active": False,
        "name": None,
        "status": "IDLE",
        "score": 0,
        "timer": 60
    },
    "user": {
        "detected": False,
        "x": 320,
        "y": 180
    }
}

user_preferences = {
    "pages": {},
    "games": {},
    "music": {}
}

# ============================================================================
# 摄像头处理器初始化
# ============================================================================
tablet_cam_url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.3.94:8080/video"
processor = TabletProcessor(tablet_cam_url)

try:
    screen_cam_source = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1
except:
    screen_cam_source = 1
screen_proc = init_screen_processor(screen_cam_source, socketio)

# 启动时加载配置
load_config_on_startup()

# 延迟更新矩阵
def delayed_update_matrix():
    time.sleep(2)
    screen_proc.update_matrix()
    print("✓ 透视矩阵已更新")

threading.Thread(target=delayed_update_matrix, daemon=True).start()

whack_a_mole = WhackAMole(socketio)

# ============================================================================
# API路由 - 视频流
# ============================================================================
@app.route('/video_feed')
def video_feed():
    def gen():
        while True:
            jpeg = screen_proc.get_raw_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.02)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/corrected_feed')
def corrected_feed():
    def gen():
        while True:
            jpeg = screen_proc.get_corrected_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.02)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/tablet_video_feed')
def tablet_video_feed():
    """平板摄像头视频流"""
    def gen():
        while True:
            jpeg = processor.get_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ============================================================================
# API路由 - 配置管理
# ============================================================================
@app.route('/api/config')
def api_config():
    return jsonify({
        "corners": state["corners"],
        "zones": state["zones"],
        "zone_id_counter": state["zone_id_counter"],
        "admin_bg": state["admin_bg"],
        "projection_bg": state["projection_bg"]
    })

@app.route('/api/corners', methods=['POST'])
def api_corners():
    state["corners"] = request.json.get("corners", state["corners"])
    screen_proc.update_matrix()
    return jsonify({"ok": True})

@app.route('/api/zones', methods=['POST'])
def api_zones():
    data = request.json
    state["zones"] = data.get("zones", state["zones"])
    if "zone_id_counter" in data:
        state["zone_id_counter"] = data["zone_id_counter"]
    return jsonify({"ok": True})

@app.route('/api/settings', methods=['POST'])
def api_settings():
    data = request.json
    if "admin_bg" in data:
        state["admin_bg"] = data["admin_bg"]
    if "projection_bg" in data:
        state["projection_bg"] = data["projection_bg"]
    return jsonify({"ok": True})

@app.route('/api/save_all', methods=['POST'])
def api_save_all():
    ok = screen_proc.save_config()
    return jsonify({"ok": ok, "msg": "配置已保存" if ok else "保存失败"})

@app.route('/api/load_all', methods=['POST'])
def api_load_all():
    if screen_proc.load_config():
        screen_proc.update_matrix()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "加载失败"})

@app.route('/api/status')
def api_status():
    return jsonify({
        "feet_detected": state["feet_detected"],
        "feet_x": state["feet_x"],
        "feet_y": state["feet_y"],
        "active_zones": state["active_zones"]
    })

@app.route('/api/system/state')
def api_system_state():
    return jsonify({
        "state": system_state,
        "preferences": user_preferences
    })

@app.route('/api/health')
def api_health():
    """获取健康数据"""
    health_data = processor.get_health_data()
    return jsonify(health_data)

# ============================================================================
# Socket事件 - 导航控制
# ============================================================================
@socketio.on('navigate')
def handle_navigate(data):
    page = data.get('page')
    source = data.get('source', 'user')
    
    if system_state["game"]["active"]:
        socketio.emit('navigate_error', {
            "error": "game_active",
            "message": "请先退出当前游戏"
        })
        return
    
    system_state["current_page"] = page
    user_preferences["pages"][page] = user_preferences["pages"].get(page, 0) + 1
    socketio.emit('navigate_to', {"page": page})

@socketio.on('request_nav')
def handle_request_nav(data):
    handle_navigate(data)

# ============================================================================
# Socket事件 - 游戏控制
# ============================================================================
@socketio.on('game_control')
def handle_game_control(data):
    global system_state
    action = data.get('action')
    game_name = data.get('game', 'whack_a_mole')
    
    print(f"[游戏控制] action={action}, game={game_name}")
    
    if action == 'ready':
        system_state["game"]["active"] = True
        system_state["game"]["name"] = game_name
        system_state["game"]["status"] = "READY"
        system_state["mode"] = "game"
        whack_a_mole.set_ready()
        
    elif action == 'start':
        system_state["game"]["status"] = "PLAYING"
        whack_a_mole.start_game()
        
    elif action == 'pause':
        whack_a_mole.toggle_pause()
        system_state["game"]["status"] = whack_a_mole.status
        
    elif action == 'stop':
        system_state["game"]["active"] = False
        system_state["game"]["name"] = None
        system_state["game"]["status"] = "IDLE"
        system_state["mode"] = "normal"
        whack_a_mole.stop()
    
    socketio.emit('system_state', {"state": system_state})

@socketio.on('game_hit')
def handle_game_hit(data):
    hole = data.get('hole', -1)
    hit = data.get('hit', False)
    whack_a_mole.handle_hit(hole, hit)

# ============================================================================
# Socket事件 - 用户交互
# ============================================================================
@socketio.on('user_interaction')
def handle_user_interaction(data):
    interaction_type = data.get('type')
    interaction_data = data.get('data', {})
    print(f"[用户交互] type={interaction_type}, data={interaction_data}")

# ============================================================================
# Socket事件 - 校准
# ============================================================================
@socketio.on('update_calibration_point')
def handle_update_point(data):
    index = data.get('index')
    x = data.get('x')
    y = data.get('y')
    if 0 <= index < 4:
        state["corners"][index] = [x, y]
        screen_proc.update_matrix()

@socketio.on('save_calibration')
def handle_save_calibration():
    screen_proc.save_config()

@socketio.on('reset_calibration')
def handle_reset_calibration():
    state["corners"] = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]]
    screen_proc.update_matrix()

# ============================================================================
# API - 阿康对话
# ============================================================================
@app.route('/api/akon/chat', methods=['POST'])
def akon_chat():
    data = request.json
    user_message = data.get('message', '')
    sid = data.get('sid')
    
    response_text, action_name, action_params = ask_akon(user_message)
    
    if action_name == "navigate_to" and action_params:
        target_page = action_params[0]
        if not system_state["game"]["active"]:
            system_state["current_page"] = target_page
            socketio.emit('navigate_to', {"page": target_page})
    
    result = {
        'reply': response_text,
        'action': {'name': action_name, 'params': action_params}
    }
    
    if sid:
        socketio.emit('akon_response', result, to=sid)
    
    return jsonify({'status': 'success'})

# ============================================================================
# 后台任务
# ============================================================================
def main_worker():
    last_emit_time = 0
    while True:
        now = time.time()
        
        t_data = processor.get_ui_data()
        whack_a_mole.update(t_data['state'] if t_data else None)
        
        if system_state["game"]["active"]:
            system_state["game"]["score"] = whack_a_mole.score
            system_state["game"]["timer"] = whack_a_mole.timer
        
        if now - last_emit_time > 0.05:
            raw_jpeg = screen_proc.get_raw_jpeg()
            if raw_jpeg:
                socketio.emit('screen_stream', {
                    'image': raw_jpeg.hex(),
                    'status': screen_proc.get_status(),
                    'config': screen_proc.get_config()
                })
            
            if t_data:
                socketio.emit('tablet_stream', {'image': t_data['image'], 'state': t_data['state']})
            
            last_emit_time = now
        
        socketio.sleep(0.01)

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    processor.start()
    threading.Thread(target=main_worker, daemon=True).start()
    
    print("=" * 60)
    print("AI具身智能认知训练系统")
    print("=" * 60)
    print()
    print(f"本机IP:     http://{LOCAL_IP}:5000")
    print(f"Flask API:  http://127.0.0.1:5000")
    print()
    print(f"平板访问:   http://{LOCAL_IP}:3000")
    print(f"投影页面:   http://{LOCAL_IP}:3000/projection")
    print(f"开发后台:   http://{LOCAL_IP}:3000/developer")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
