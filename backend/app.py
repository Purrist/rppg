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
import cv2
import numpy as np

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

# ============================================================================
# 解析命令行参数
# ============================================================================
# args[0]: 平板视频地址 (如 http://192.168.3.94:8080/video)
# args[1]: 投影摄像头源 (如 1)
TABLET_VIDEO_URL = "http://192.168.3.94:8080/video"  # 默认值
PROJECTION_CAMERA_SOURCE = 1  # 默认值

if len(sys.argv) >= 2:
    TABLET_VIDEO_URL = sys.argv[1]
    print(f"[配置] 平板视频地址: {TABLET_VIDEO_URL}")
if len(sys.argv) >= 3:
    try:
        PROJECTION_CAMERA_SOURCE = int(sys.argv[2])
    except:
        pass
    print(f"[配置] 投影摄像头源: {PROJECTION_CAMERA_SOURCE}")

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
from akon_agent import ask_akon
from rppg_processor import RPPGProcessor

# ============================================================================
# 初始化
# ============================================================================
screen_proc = init_screen_processor(camera_source=PROJECTION_CAMERA_SOURCE, socketio=socketio)
whack_a_mole = WhackAMole(socketio)
rppg_processor = RPPGProcessor(fps=30)

# rPPG 状态
rppg_status = {
    "bpm": None,
    "emotion": None,
    "confidence": 0
}

# rPPG处理线程
rppg_frame = None
rppg_frame_lock = threading.Lock()

def rppg_worker():
    """rPPG处理线程：独立处理心率检测"""
    import urllib.request
    
    global rppg_frame, rppg_status
    tablet_url = TABLET_VIDEO_URL
    
    print(f"[rPPG线程] 启动，连接: {tablet_url}")
    
    while True:
        try:
            stream = urllib.request.urlopen(tablet_url, timeout=5)
            bytes_data = bytes()
            
            while True:
                bytes_data += stream.read(1024)
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')
                
                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        # 处理rPPG
                        bpm, conf, face, roi = rppg_processor.process_frame(frame)
                        
                        # 更新状态
                        if bpm and conf > 2.0:
                            rppg_status["bpm"] = round(bpm, 1)
                            rppg_status["confidence"] = round(conf, 2)
                        
                        # 绘制结果
                        if face:
                            x, y, w, h = face
                            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        
                        if roi:
                            rx, ry, rw, rh = roi
                            cv2.rectangle(frame, (rx, ry), (rx+rw, ry+rh), (255, 0, 0), 2)
                        
                        if rppg_status["bpm"]:
                            cv2.putText(frame, f"BPM: {rppg_status['bpm']}", (10, 30),
                                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        
                        # 更新共享帧
                        with rppg_frame_lock:
                            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            rppg_frame = jpeg.tobytes()
                        
        except Exception as e:
            print(f"[rPPG线程] 错误: {e}")
            time.sleep(1)

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
    """平板摄像头视频流（从共享帧读取，流畅不卡顿）"""
    def gen_tablet_video():
        global rppg_frame
        
        while True:
            with rppg_frame_lock:
                frame = rppg_frame
            
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                # 等待帧
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')
            
            time.sleep(0.03)  # ~30fps
    
    return Response(gen_tablet_video(), mimetype='multipart/x-mixed-replace; boundary=frame')

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
    return jsonify(rppg_status)

# ============================================================================
# 阿康对话 API
# ============================================================================
@app.route('/api/akon/chat', methods=['POST'])
def api_akon_chat():
    """阿康对话接口"""
    data = request.json
    user_input = data.get('message', '')
    
    if not user_input:
        return jsonify({"error": "请输入内容"}), 400
    
    # 构建系统状态
    akon_state = {
        "current_page": system_state.get("current_page", "/"),
        "game_active": system_state["game"]["active"],
        "game_name": system_state["game"]["name"],
        "game_score": system_state["game"]["score"]
    }
    
    # 调用阿康
    response, action = ask_akon(user_input, akon_state)
    
    result = {
        "response": response,
        "action": action
    }
    
    # 如果有导航动作，执行导航
    if action and action.get("action") == "navigate":
        page = action.get("page", "/")
        if not system_state["game"]["active"]:
            system_state["current_page"] = page
            socketio.emit('navigate_to', {"page": page})
    
    return jsonify(result)

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
    # 启动后台任务
    threading.Thread(target=main_worker, daemon=True).start()
    
    # 启动rPPG处理线程
    threading.Thread(target=rppg_worker, daemon=True).start()
    
    print("=" * 60)
    print("AI具身智能认知训练系统")
    print("=" * 60)
    print()
    print(f"本机IP:     http://{LOCAL_IP}:5000")
    print(f"Flask API:  http://127.0.0.1:5000")
    print()
    print(f"平板视频:   {TABLET_VIDEO_URL}")
    print(f"投影摄像头: {PROJECTION_CAMERA_SOURCE}")
    print()
    print(f"平板访问:   http://{LOCAL_IP}:3000")
    print(f"投影页面:   http://{LOCAL_IP}:3000/projection")
    print(f"开发后台:   http://{LOCAL_IP}:3000/developer")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
