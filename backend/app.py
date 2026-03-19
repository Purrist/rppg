# -*- coding: utf-8 -*-
"""
AI具身智能认知训练系统 - 主程序 v2.1
模块化架构
"""

import os
import sys
import time
import threading
import socket

from flask import Flask, Response, request, jsonify, send_from_directory
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

TABLET_VIDEO_URL = "http://192.168.3.94:8080/video"
PROJECTION_CAMERA_SOURCE = 1

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
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    engineio_logger=False,
    logger=False
)

# ============================================================================
# 导入模块
# ============================================================================
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 核心模块
from core import SystemStateManager, ask_akon, think, should_think, get_agent_state, ActionExecutor

# 游戏系统
from games import GameManager, GAME_REGISTRY, GAME_CONFIGS

# 感知模块
from perception import PerceptionManager, init_screen_processor, draw_detection_info

# ============================================================================
# 初始化
# ============================================================================
# 投影摄像头处理器
screen_proc = init_screen_processor(camera_source=PROJECTION_CAMERA_SOURCE, socketio=socketio)

# 游戏管理器
game_manager = GameManager(socketio)
for game_id, game_class in GAME_REGISTRY.items():
    config = GAME_CONFIGS.get(game_id)
    game_manager.register(game_id, game_class, config)
print(f"[游戏系统] 已注册游戏: {list(GAME_REGISTRY.keys())}")

# 感知管理器
perception_manager = PerceptionManager()

# ⭐ 设置感知管理器引用到游戏管理器
game_manager.set_perception_manager(perception_manager)

# 状态管理器（世界模型）
state_manager = SystemStateManager(socketio)

# 行动执行器
action_executor = ActionExecutor(socketio, state_manager)

# 用户状态
user_state = {
    "emotion": {"primary": "neutral"},
    "heart_rate": {"bpm": None},
    "environment": {"person_present": False},
    "body_state": {"posture": "unknown"},
    "eye_state": {"attention_score": 0},
    "overall": {"fatigue_level": 0, "state_summary": "normal"},
}

# 感知处理线程
perception_frame = None
perception_frame_lock = threading.Lock()
_last_perception_time = 0
PERCEPTION_INTERVAL = 0.5  # 500ms处理一次感知，平衡性能和实时性

def perception_worker():
    """感知处理线程 - 优化版"""
    import urllib.request
    
    global perception_frame, user_state, _last_perception_time
    tablet_url = TABLET_VIDEO_URL
    
    print(f"[感知线程] 启动，连接: {tablet_url}")
    
    while True:
        try:
            stream = urllib.request.urlopen(tablet_url, timeout=5)
            bytes_data = bytes()
            
            while True:
                bytes_data += stream.read(4096)  # 增加读取大小
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')
                
                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        now = time.time()
                        
                        # ⭐ 视频帧始终更新（用于显示）
                        with perception_frame_lock:
                            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                            perception_frame = jpeg.tobytes()
                        
                        # ⭐ 感知处理按频率限制
                        if now - _last_perception_time >= PERCEPTION_INTERVAL:
                            _last_perception_time = now
                            user_state = perception_manager.process_frame(frame, "tablet")
                            state_manager.update_world(user_state)
                
        except Exception as e:
            print(f"[感知线程] 错误: {e}")
            time.sleep(1)

# ============================================================================
# Agent循环 - 降低频率
# ============================================================================
def agent_loop():
    """Agent持续运行循环 - 降低频率"""
    print("[Agent循环] 启动")
    
    while True:
        try:
            world_state = state_manager.get_world_state()
            
            if should_think(world_state):
                print(f"[Agent循环] 触发思考")
                decision = think(world_state, state_manager)
                
                if decision.get("need_action"):
                    action_executor.execute(decision)
            
            time.sleep(1.0)  # ⭐ 降低到1秒检查一次
            
        except Exception as e:
            print(f"[Agent循环] 错误: {e}")
            time.sleep(2)

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
    def gen_tablet_video():
        global perception_frame
        
        while True:
            with perception_frame_lock:
                frame = perception_frame
            
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + b'' + b'\r\n')
            
            time.sleep(0.03)
    
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
    return jsonify({
        "state": {
            "mode": "game" if game_manager.is_game_active() else "normal",
            "current_page": state_manager.get_current_page(),
            "game": {
                "active": game_manager.is_game_active(),
                "name": game_manager.get_current_game_id(),
                "status": game_manager.get_game_status(),
                "score": game_manager.get_game_state().get("score", 0) if game_manager.get_game_state() else 0,
                "timer": game_manager.get_game_state().get("timer", 0) if game_manager.get_game_state() else 0,
            }
        }
    })

@app.route('/api/health')
def api_health():
    return jsonify(perception_manager.get_summary())

@app.route('/api/user_state')
def api_user_state():
    """获取用户状态（感知信息）"""
    return jsonify(perception_manager.get_state())

@app.route('/api/world_state')
def api_world_state():
    return jsonify(state_manager.get_world_state())

@app.route('/api/agent_state')
def api_agent_state():
    return jsonify(get_agent_state())

@app.route('/api/games')
def api_games():
    """获取游戏列表"""
    return jsonify(game_manager.get_game_list())

@app.route('/api/games/<game_id>/config')
def api_game_config(game_id):
    """获取游戏配置"""
    config = game_manager.get_game_config(game_id)
    if config:
        return jsonify(config)
    return jsonify({"error": "游戏不存在"}), 404

# ==================== 难度调整 API ====================
@app.route('/api/difficulty')
def api_difficulty():
    """获取当前难度参数"""
    return jsonify({
        "level": game_manager.get_difficulty_level(),
        "params": game_manager.get_difficulty_params(),
        "adjuster_state": game_manager.get_difficulty_adjuster_state(),
    })

@app.route('/api/difficulty/levels')
def api_difficulty_levels():
    """获取所有难度等级"""
    return jsonify(game_manager.difficulty_adjuster.get_all_levels())

@app.route('/api/difficulty/set', methods=['POST'])
def api_set_difficulty():
    """手动设置难度等级"""
    data = request.get_json()
    level = data.get('level', 5)
    result = game_manager.set_difficulty_level(level)
    return jsonify(result)

@app.route('/api/difficulty/adjustment')
def api_difficulty_adjustment():
    """获取难度调整建议"""
    return jsonify(perception_manager.get_difficulty_adjustment())

# ============================================================================
# 阿康对话 API
# ============================================================================
@app.route('/api/akon/chat', methods=['POST'])
def api_akon_chat():
    data = request.json
    user_input = data.get('message', '')
    
    if not user_input:
        return jsonify({"error": "请输入内容"}), 400
    
    state_manager.set_user_speaking(True, user_input)
    
    akon_state = {
        "current_page": state_manager.get_current_page(),
        "game_active": game_manager.is_game_active(),
        "game_name": game_manager.get_current_game_id(),
        "game_score": game_manager.get_game_state().get("score", 0) if game_manager.get_game_state() else 0
    }
    
    response, action = ask_akon(user_input, akon_state)
    state_manager.set_user_speaking(False)
    
    result = {"response": response, "action": action}
    
    if action:
        action_type = action.get("type", "none")
        
        if action_type == "navigate_and_recommend":
            page = action.get("page", "/")
            content = action.get("content", {})
            if not game_manager.is_game_active():
                state_manager.navigate_to(page)
                socketio.emit('navigate_to', {"page": page})
            if content:
                socketio.emit('akon_recommend', {
                    "type": content.get("type"),
                    "items": content.get("items", [])
                })
        
        elif action_type == "navigate":
            page = action.get("page", "/")
            if not game_manager.is_game_active():
                state_manager.navigate_to(page)
                socketio.emit('navigate_to', {"page": page})
        
        elif action_type == "play":
            content = action.get("content", {})
            socketio.emit('akon_play', {
                "type": content.get("type"),
                "items": content.get("items", [])
            })
        
        elif action_type == "game":
            game_name = action.get("game_name", "whack_a_mole")
            socketio.emit('akon_start_game', {"game": game_name})
    
    return jsonify(result)

# ============================================================================
# Socket事件 - 游戏控制
# ============================================================================
@socketio.on('game_control')
def handle_game_control(data):
    action = data.get('action')
    game_id = data.get('game', 'whack_a_mole')
    
    print(f"[游戏控制] action={action}, game={game_id}")
    
    if action == 'ready':
        game_manager.set_ready(game_id)
    
    elif action == 'start':
        game_manager.start_game()
    
    elif action == 'pause':
        game_manager.toggle_pause()
    
    elif action == 'stop':
        game_manager.stop_game()
    
    elif action == 'timeout_stop':
        print("[游戏控制] 超时停止")
        game_manager.stop_game()
        socketio.emit('navigate_to', {"page": "/learning"})
    
    elif action == 'restart':
        # ⭐ 直接重启，进入 READY 状态
        game_manager.restart_game(game_id)
        # restart_game 会发送 system_state，其中 active=True（因为 READY 算激活）
        return
    
    socketio.emit('system_state', {
        "state": {
            "mode": "game" if game_manager.is_game_active() else "normal",
            "game": {
                "active": game_manager.is_game_active(),
                "name": game_manager.get_current_game_id(),
                "status": game_manager.get_game_status(),
                "score": game_manager.get_game_state().get("score", 0) if game_manager.get_game_state() else 0,
                "timer": game_manager.get_game_state().get("timer", 0) if game_manager.get_game_state() else 0,
            }
        }
    })

@socketio.on('game_action')
def handle_game_action(data):
    """处理游戏内动作"""
    action = data.get('action')
    zone = data.get('zone', -1)
    success = data.get('success', False)
    
    game_manager.handle_action(action, {"zone": zone, "success": success})

@socketio.on('game_hit')
def handle_game_hit(data):
    """兼容旧接口"""
    hole = data.get('hole', -1)
    hit = data.get('hit', False)
    game_manager.handle_action("hit", {"zone": hole, "success": hit})

# ============================================================================
# Socket事件 - 导航
# ============================================================================
@socketio.on('navigate')
def handle_navigate(data):
    page = data.get('page')
    source = data.get('source')
    print(f"[导航] page={page}, source={source}")
    
    if game_manager.is_game_active():
        emit('navigate_error', {"message": "请先退出当前游戏"})
        return
    
    state_manager.navigate_to(page)
    socketio.emit('navigate_to', {"page": page})

@socketio.on('get_state')
def handle_get_state(data=None):
    if data and data.get('client') == 'tablet' and data.get('first_connect'):
        if not game_manager.is_game_active():
            socketio.emit('navigate_to', {"page": "/"})
    
    # ⭐ 发送 system_state
    socketio.emit('system_state', {
        "state": {
            "mode": "game" if game_manager.is_game_active() else "normal",
            "game": {
                "active": game_manager.is_game_active(),
                "name": game_manager.get_current_game_id(),
                "status": game_manager.get_game_status(),
                "score": game_manager.get_game_state().get("score", 0) if game_manager.get_game_state() else 0,
                "timer": game_manager.get_game_state().get("timer", 0) if game_manager.get_game_state() else 0,
            }
        }
    })
    
    # ⭐ 如果游戏激活，也发送 game_update
    if game_manager.is_game_active() and game_manager.get_game_state():
        socketio.emit('game_update', {
            "game_id": game_manager.get_current_game_id(),
            **game_manager.get_game_state()
        })

# ============================================================================
# 后台任务
# ============================================================================
def main_worker():
    while True:
        game_manager.update()
        socketio.sleep(0.033)  # 33ms = 30fps

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    threading.Thread(target=main_worker, daemon=True).start()
    threading.Thread(target=perception_worker, daemon=True).start()
    threading.Thread(target=agent_loop, daemon=True).start()
    
    print("=" * 60)
    print("AI具身智能认知训练系统 - EAOS v2.1")
    print("=" * 60)
    print()
    print(f"本机IP:     http://{LOCAL_IP}:5000")
    print(f"平板访问:   http://{LOCAL_IP}:3000")
    print(f"投影页面:   http://{LOCAL_IP}:3000/projection")
    print(f"开发后台:   http://{LOCAL_IP}:3000/developer")
    print()
    print("已注册游戏:")
    for game_id in GAME_REGISTRY:
        print(f"  - {game_id}")
    print()
    print("模块结构:")
    print("  core/       - Agent、世界模型、工具")
    print("  games/      - 游戏系统（可扩展）")
    print("  perception/ - 感知系统")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
