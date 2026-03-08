# -*- coding: utf-8 -*-
"""
AI具身智能认知训练系统 - 主程序
"""

import os
import sys
import time
import json
import threading
import socket
from datetime import datetime

from flask import Flask, render_template, Response, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ============================================================================
# 配置
# ============================================================================
LOCAL_IP = "192.168.3.91"
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    LOCAL_IP = s.getsockname()[0]
    s.close()
except:
    pass

app = Flask(__name__, static_folder='../frontend/.output/public', static_url_path='')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============================================================================
# 系统状态
# ============================================================================
system_state = {
    "mode": "normal",
    "current_page": "/",
    "game": {
        "active": False,
        "name": None,
        "status": "IDLE",
        "score": 0,
        "timer": 60
    }
}

# ============================================================================
# 导入模块
# ============================================================================
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screen_processor import init_screen_processor, get_screen_processor, state
from games import WhackAMole

# ============================================================================
# 初始化
# ============================================================================
screen_proc = init_screen_processor(camera_source=1, socketio=socketio)
whack_a_mole = WhackAMole(socketio)

# ============================================================================
# 静态文件
# ============================================================================
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory(app.static_folder, path)
    except:
        return send_from_directory(app.static_folder, 'index.html')

# ============================================================================
# 视频流
# ============================================================================
def gen_video(processor, is_corrected=False):
    while True:
        frame = processor.get_corrected_jpeg() if is_corrected else processor.get_raw_jpeg()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.03)

@app.route('/video_feed')
def video_feed():
    return Response(gen_video(screen_proc), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/corrected_feed')
def corrected_feed():
    return Response(gen_video(screen_proc, True), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/tablet_video_feed')
def tablet_video_feed():
    return Response(b'', mimetype='multipart/x-mixed-replace; boundary=frame')

# ============================================================================
# API
# ============================================================================
@app.route('/api/status')
def api_status():
    return jsonify(screen_proc.get_status())

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.json
        if 'corners' in data:
            screen_proc.update_corners(data['corners'])
        return jsonify({"ok": True})
    return jsonify(screen_proc.get_config())

@app.route('/api/corners', methods=['POST'])
def api_corners():
    data = request.json
    screen_proc.update_corners(data['corners'])
    return jsonify({"ok": True})

@app.route('/api/save_all', methods=['POST'])
def api_save_all():
    ok = screen_proc.save_config()
    return jsonify({"ok": ok, "msg": "配置已保存" if ok else "保存失败"})

@app.route('/api/load_all', methods=['POST'])
def api_load_all():
    ok = screen_proc.load_config()
    return jsonify({"ok": ok})

@app.route('/api/system/state')
def api_system_state():
    return jsonify({"state": system_state})

@app.route('/api/health')
def api_health():
    return jsonify({"bpm": None, "emotion": None})

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
    
    elif action == 'restart':
        # 先停止（不发送状态）
        system_state["game"]["active"] = False
        system_state["game"]["name"] = None
        system_state["game"]["status"] = "IDLE"
        system_state["mode"] = "normal"
        whack_a_mole.status = "IDLE"
        whack_a_mole.current_mole = -1
        print("[打地鼠] 重新开始：停止游戏")
        
        # 立即重新开始
        system_state["game"]["active"] = True
        system_state["game"]["name"] = game_name
        system_state["game"]["status"] = "READY"
        system_state["mode"] = "game"
        whack_a_mole.set_ready()
        print("[打地鼠] 重新开始：进入准备状态")
        return  # 不发送 system_state
    
    socketio.emit('system_state', {"state": system_state})

@socketio.on('game_hit')
def handle_game_hit(data):
    hole = data.get('hole', -1)
    hit = data.get('hit', False)
    whack_a_mole.handle_hit(hole, hit)

# ============================================================================
# Socket事件 - 导航
# ============================================================================
@socketio.on('navigate')
def handle_navigate(data):
    page = data.get('page')
    source = data.get('source')
    print(f"[导航] page={page}, source={source}")
    
    if system_state["game"]["active"]:
        emit('navigate_error', {"message": "请先退出当前游戏"})
        return
    
    system_state["current_page"] = page
    socketio.emit('navigate_to', {"page": page})

# ============================================================================
# Socket事件 - 获取状态
# ============================================================================
@socketio.on('get_state')
def handle_get_state(data=None):
    """客户端请求获取当前状态"""
    # 如果是平板客户端首次连接，检查是否需要导航到首页
    if data and data.get('client') == 'tablet' and data.get('first_connect'):
        if not system_state["game"]["active"]:
            socketio.emit('navigate_to', {"page": "/"})
    
    socketio.emit('system_state', {"state": system_state})

# ============================================================================
# 后台任务
# ============================================================================
def main_worker():
    while True:
        t_data = None  # processor.get_ui_data() if processor else None
        whack_a_mole.update(t_data['state'] if t_data else None)
        
        if system_state["game"]["active"]:
            system_state["game"]["score"] = whack_a_mole.score
            system_state["game"]["timer"] = whack_a_mole.timer
            system_state["game"]["status"] = whack_a_mole.status
        
        socketio.sleep(0.05)

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
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
