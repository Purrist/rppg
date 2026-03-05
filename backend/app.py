import sys, time, threading
from flask import Flask, request, jsonify, Response
from flask_socketio import SocketIO
from flask_cors import CORS
from tablet_processor import TabletProcessor
from screen_processor import init_screen_processor, get_screen_processor, state, ZONE_COLORS
from games import WhackAMole
from akon_agent import ask_akon

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10**6)

# --- 全局系统状态 ---
system_state = {
    "current_page": "/",
}

# --- 1. 平板端摄像头（状态感知） ---
processor = TabletProcessor(sys.argv[1] if len(sys.argv) > 1 else "http://192.168.3.94:8080/video")

# --- 2. 投影端摄像头（交互识别） ---
try:
    raw_arg = sys.argv[2] if len(sys.argv) > 2 else "1"
    screen_cam_source = int(raw_arg) if str(raw_arg).isdigit() else raw_arg
except:
    screen_cam_source = 1

# 初始化屏幕处理器
screen_proc = init_screen_processor(screen_cam_source, socketio)
current_game = WhackAMole(socketio)

# ============================================================================
# 视频流路由
# ============================================================================
@app.route('/video_feed')
def video_feed():
    """原始摄像头画面流"""
    def gen():
        while True:
            jpeg = screen_proc.get_raw_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.02)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/corrected_feed')
def corrected_feed():
    """校正后画面流"""
    def gen():
        while True:
            jpeg = screen_proc.get_corrected_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.02)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ============================================================================
# API路由 - 配置管理
# ============================================================================
@app.route('/api/config')
def api_config():
    """获取所有配置"""
    return jsonify({
        "corners": state["corners"],
        "zones": state["zones"],
        "zone_id_counter": state["zone_id_counter"],
        "admin_bg": state["admin_bg"],
        "projection_bg": state["projection_bg"]
    })

@app.route('/api/corners', methods=['POST'])
def api_corners():
    """保存校准顶点"""
    state["corners"] = request.json.get("corners", state["corners"])
    screen_proc.update_matrix()
    return jsonify({"ok": True})

@app.route('/api/zones', methods=['POST'])
def api_zones():
    """保存区域配置"""
    data = request.json
    state["zones"] = data.get("zones", state["zones"])
    if "zone_id_counter" in data:
        state["zone_id_counter"] = data["zone_id_counter"]
    return jsonify({"ok": True})

@app.route('/api/settings', methods=['POST'])
def api_settings():
    """保存背景颜色设置"""
    data = request.json
    if "admin_bg" in data:
        state["admin_bg"] = data["admin_bg"]
    if "projection_bg" in data:
        state["projection_bg"] = data["projection_bg"]
    return jsonify({"ok": True})

@app.route('/api/save_all', methods=['POST'])
def api_save_all():
    """保存所有配置到文件"""
    ok = screen_proc.save_config()
    return jsonify({"ok": ok, "msg": "配置已保存" if ok else "保存失败"})

@app.route('/api/load_all', methods=['POST'])
def api_load_all():
    """从文件加载配置"""
    if screen_proc.load_config():
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "加载失败"})

@app.route('/api/status')
def api_status():
    """获取实时状态"""
    return jsonify({
        "feet_detected": state["feet_detected"],
        "feet_x": state["feet_x"],
        "feet_y": state["feet_y"],
        "active_zones": state["active_zones"]
    })

# ============================================================================
# Socket 交互逻辑
# ============================================================================
@socketio.on('request_nav')
def handle_nav(data):
    """处理导航请求"""
    target_page = data.get('page')
    if target_page:
        system_state["current_page"] = target_page
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
    # 更新corners
    if 0 <= index < 4:
        state["corners"][index] = [x, y]
        screen_proc.update_matrix()

@socketio.on('update_hole')
def handle_update_hole(data):
    """更新地鼠洞区域"""
    index = data.get('index')
    points = data.get('points')
    if 0 <= index < len(state["zones"]):
        state["zones"][index]["points"] = points

@socketio.on('save_calibration')
def handle_save_calibration():
    """保存校准配置"""
    screen_proc.save_config()

@socketio.on('reset_calibration')
def handle_reset_calibration():
    """重置校准"""
    state["corners"] = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]]
    screen_proc.update_matrix()

def main_worker():
    """中心化逻辑处理与状态广播线程"""
    last_emit_time = 0
    while True:
        now = time.time()
        t_data = processor.get_ui_data()
        
        # 获取屏幕处理器状态
        status = screen_proc.get_status()
        
        # 游戏逻辑判定
        if status["feet_detected"] and current_game.status != "PAUSED":
            active_zones = status["active_zones"]
            if current_game.status == "READY" and len(active_zones) > 0:
                # 进入区域开始游戏
                current_game.start_game()
            elif current_game.status == "PLAYING" and len(active_zones) > 0:
                # 命中判定
                zone_id = active_zones[0]
                zone_index = next((i for i, z in enumerate(state["zones"]) if z["id"] == zone_id), -1)
                if zone_index >= 0:
                    current_game.handle_hit(zone_index)
        
        current_game.update(t_data['state'] if t_data else None)

        # 定时广播
        if now - last_emit_time > 0.05:
            game_state = {
                "status": current_game.status,
                "score": current_game.score,
                "timer": current_game.timer,
                "current_mole": current_game.current_mole
            }
            socketio.emit('game_update', game_state)
            
            # 推送视频流与感知结果
            raw_jpeg = screen_proc.get_raw_jpeg()
            corrected_jpeg = screen_proc.get_corrected_jpeg()
            
            if raw_jpeg:
                socketio.emit('screen_stream', {
                    'image': raw_jpeg.hex(),
                    'status': status,
                    'config': screen_proc.get_config()
                })
            
            if t_data:
                socketio.emit('tablet_stream', {'image': t_data['image'], 'state': t_data['state']})
            
            last_emit_time = now
        
        socketio.sleep(0.01)

# --- HTTP API 接口 ---

@app.route('/api/akon/chat', methods=['POST'])
def akon_chat():
    """处理阿康对话"""
    data = request.json
    user_message = data.get('message', '')
    sid = data.get('sid')
    
    response_text, action_name, action_params = ask_akon(user_message)
    
    if action_name == "navigate_to" and action_params:
        target_page = action_params[0]
        system_state["current_page"] = target_page
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
    threading.Thread(target=main_worker, daemon=True).start()
    
    print("=" * 50)
    print("地面投影交互系统")
    print("=" * 50)
    print()
    print("Flask API:  http://127.0.0.1:5000")
    print("Admin:      http://127.0.0.1:3000/developer")
    print("投影:       http://127.0.0.1:3000/projection")
    print()
    print("API端点:")
    print("  - http://127.0.0.1:5000/api/config")
    print("  - http://127.0.0.1:5000/api/status")
    print("  - http://127.0.0.1:5000/video_feed")
    print("  - http://127.0.0.1:5000/corrected_feed")
    print("=" * 50)
    
    # Flask 运行在端口 5000
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
