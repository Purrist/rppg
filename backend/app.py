# -*- coding: utf-8 -*-
"""
AI具身智能认知训练系统 - 主程序 v3.0
基于SystemCore的统一架构
"""

import os
import sys
import time
import threading
import socket

# 抑制TensorFlow等库的警告信息
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

from flask import Flask, Response, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import cv2

# 抑制OpenCV警告
import logging
logging.getLogger('cv2').setLevel(logging.ERROR)

import numpy as np

# ============================================================================# 配置# ============================================================================

def check_port(port):
    """检查端口是否被占用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()
    return result == 0

def find_available_port(start_port=5000, max_attempts=10):
    """查找可用端口"""
    port = start_port
    attempts = 0
    while attempts < max_attempts:
        if not check_port(port):
            return port
        print(f"[端口检查] 端口 {port} 已被占用，尝试下一个端口...")
        port += 1
        attempts += 1
    return None

LOCAL_IP = "192.168.3.91"
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    LOCAL_IP = s.getsockname()[0]
    s.close()
except:
    pass

TABLET_VIDEO_URL = "http://10.158.6.244:8080/video"
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

# 检查并选择可用端口
DEFAULT_PORT = 5000
PORT = find_available_port(DEFAULT_PORT)
if not PORT:
    print("[端口检查] 无法找到可用端口，使用默认端口")
    PORT = DEFAULT_PORT
else:
    print(f"[端口检查] 使用端口: {PORT}")

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

# ⭐ 系统核心（唯一数据中心）- 最先初始化
from core import SystemCore, init_system_core, get_system_core

# AI Agent模块
from core.core_agent import ask_akon, think, should_think, get_agent_state
from core.core_tools import ActionExecutor

# 游戏系统
from games import GameManager, GAME_REGISTRY, GAME_CONFIGS

# 感知模块
from perception import PerceptionManager, init_screen_processor, get_screen_processor, draw_detection_info

# ============================================================================
# 初始化
# ============================================================================
# ⭐ 1. 初始化系统核心（必须在其他模块之前）
system_core = init_system_core(socketio)

# 2. 投影摄像头处理器
screen_proc = init_screen_processor(camera_source=PROJECTION_CAMERA_SOURCE, socketio=socketio)

# 3. 游戏管理器（传入system_core用于状态同步）
game_manager = GameManager(socketio, system_core)
for game_id, game_class in GAME_REGISTRY.items():
    config = GAME_CONFIGS.get(game_id)
    game_manager.register(game_id, game_class, config)
#print(f"[游戏系统] 已注册游戏: {list(GAME_REGISTRY.keys())}")

# 4. 感知管理器
perception_manager = PerceptionManager()

# 5. 行动执行器（使用SystemCore作为状态源）
action_executor = ActionExecutor(socketio, system_core)

# 6. 语音管理器（后端语音处理）- 使用 sherpa-onnx
# ⭐ 首先尝试下载模型
import os
import subprocess
models_dir = os.path.join(os.path.dirname(__file__), "core", "models")
if not os.path.exists(models_dir) or not os.listdir(models_dir):
    try:
        # 运行下载脚本
        download_script = os.path.join(os.path.dirname(__file__), "core", "download_models.py")
        subprocess.run([sys.executable, download_script], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        voice_manager = None
    else:
        try:
            from core.voice_manager_sherpa import init_voice_manager, get_voice_manager
            voice_manager = init_voice_manager(socketio, system_core)
            
            # ⭐ 设置语音识别回调 - 识别到用户语音后自动发送给AI
            voice_manager.set_speech_recognized_callback(lambda text: handle_voice_command(text))
            
            # ⭐ 启动语音监听（后端持续监听麦克风）
            voice_manager.start_listening()
        except Exception as e:
            voice_manager = None
else:
    try:
        from core.voice_manager_sherpa import init_voice_manager, get_voice_manager
        voice_manager = init_voice_manager(socketio, system_core)
        
        # ⭐ 设置语音识别回调 - 识别到用户语音后自动发送给AI
        voice_manager.set_speech_recognized_callback(lambda text: handle_voice_command(text))
        
        # ⭐ 启动语音监听（后端持续监听麦克风）
        voice_manager.start_listening()
    except Exception as e:
        voice_manager = None

# 7. 训练分析器
from core.training_analytics import init_training_analytics, get_training_analytics
# ⭐ 使用绝对路径确保文件保存到正确位置
core_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core")
training_analytics = init_training_analytics(data_dir=core_data_dir)
#print(f"[训练系统] 训练分析器已初始化，数据目录: {core_data_dir}")

# 语音命令处理函数
def handle_voice_command(text: str):
    """处理语音命令 - 将用户语音发送给AI Agent"""
    print(f"[语音命令] 收到: {text}")

    try:
        # 获取当前系统上下文
        context = system_core.get_state()
        
        # 调用AI Agent
        response, action = ask_akon(text, context)
        
        print(f"[语音命令] AI回复: {response}")
        
        # 通知前端显示AI回复（会触发打字机效果）
        socketio.emit('voice_llm_response', {
            'text': response
        })
        
        # 处理页面跳转
        if action and action.get('type') == 'navigate':
            socketio.emit('navigate_to', {'page': action.get('page')})
        
    except Exception as e:
        print(f"[语音命令] 处理错误: {e}")
        import traceback
        traceback.print_exc()

# 用户状态（保留用于兼容）
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
    """感知处理线程 - 带指数退避重连机制和本地摄像头切换"""
    import urllib.request
    
    global perception_frame, user_state, _last_perception_time
    tablet_url = TABLET_VIDEO_URL
    
    #print(f"[感知线程] 启动，连接: {tablet_url}")
    
    # ⭐ 指数退避重连参数
    retry_delay = 1
    max_retry_delay = 30
    consecutive_errors = 0
    
    # 本地摄像头切换参数
    use_local_camera = False
    local_camera_cap = None
    
    while True:
        try:
            if not use_local_camera:
                # 尝试连接网络摄像头
                stream = urllib.request.urlopen(tablet_url, timeout=5)
                bytes_data = bytes()
                
                # 连接成功，重置重连参数
                if consecutive_errors > 0:
                    print(f"[感知线程] 连接恢复")
                    retry_delay = 1
                    consecutive_errors = 0
                
                # 重置本地摄像头状态
                if local_camera_cap:
                    local_camera_cap.release()
                    local_camera_cap = None
                    print("[感知线程] 切换回网络摄像头")
                
                while True:
                    bytes_data += stream.read(4096)
                    a = bytes_data.find(b'\xff\xd8')
                    b = bytes_data.find(b'\xff\xd9')
                    
                    if a != -1 and b != -1:
                        jpg = bytes_data[a:b+2]
                        bytes_data = bytes_data[b+2:]
                        
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        
                        if frame is None or frame.size == 0:
                            continue
                        
                        now = time.time()
                        
                        # 视频帧始终更新（用于显示）
                        with perception_frame_lock:
                            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                            perception_frame = jpeg.tobytes()
                        
                        # 感知处理按频率限制
                        if now - _last_perception_time >= PERCEPTION_INTERVAL:
                            _last_perception_time = now
                            user_state = perception_manager.process_frame(frame, "tablet")
                            
                            # 更新SystemCore的感知数据
                            system_core.update_perception({
                                'personDetected': user_state.get('environment', {}).get('person_present', False),
                                'personCount': user_state.get('environment', {}).get('person_count', 0),
                                'faceCount': user_state.get('environment', {}).get('person_count', 0),
                                'bodyDetected': user_state.get('body_state', {}).get('posture') != 'unknown',
                                'emotion': user_state.get('emotion', {}).get('primary', 'neutral'),
                                'attention': user_state.get('eye_state', {}).get('attention_score', 0),
                                'fatigue': user_state.get('overall', {}).get('fatigue_level', 0),
                                'activity': user_state.get('body_state', {}).get('posture', 'unknown'),
                            })
            else:
                # 使用本地摄像头
                if not local_camera_cap:
                    local_camera_cap = cv2.VideoCapture(0)
                    if local_camera_cap.isOpened():
                        print("[感知线程] 切换到本地摄像头 (ID: 0)")
                    else:
                        print("[感知线程] 本地摄像头打开失败，尝试重新连接网络摄像头")
                        use_local_camera = False
                        local_camera_cap = None
                        continue
                
                ret, frame = local_camera_cap.read()
                if not ret or frame is None or frame.size == 0:
                    # 本地摄像头读取失败，尝试重新连接网络摄像头
                    if local_camera_cap:
                        local_camera_cap.release()
                        local_camera_cap = None
                    use_local_camera = False
                    print("[感知线程] 本地摄像头读取失败，尝试重新连接网络摄像头")
                    continue
                
                now = time.time()
                
                # 视频帧始终更新（用于显示）
                with perception_frame_lock:
                    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    perception_frame = jpeg.tobytes()
                
                # 感知处理按频率限制
                if now - _last_perception_time >= PERCEPTION_INTERVAL:
                    _last_perception_time = now
                    
                    # 获取屏幕处理器的脚部检测状态
                    feet_detected = False
                    try:
                        screen_proc = get_screen_processor()
                        if screen_proc:
                            status = screen_proc.get_status()
                            feet_detected = status.get('feet_detected', False)
                    except Exception:
                        pass
                    
                    user_state = perception_manager.process_frame(frame, "tablet", feet_detected=feet_detected)
                    
                    # 更新SystemCore的感知数据
                    system_core.update_perception({
                        'personDetected': user_state.get('environment', {}).get('person_present', False),
                        'personCount': user_state.get('environment', {}).get('person_count', 0),
                        'faceCount': user_state.get('environment', {}).get('person_count', 0),
                        'bodyDetected': user_state.get('body_state', {}).get('posture') != 'unknown',
                        'emotion': user_state.get('emotion', {}).get('primary', 'neutral'),
                        'attention': user_state.get('eye_state', {}).get('attention_score', 0),
                        'fatigue': user_state.get('overall', {}).get('fatigue_level', 0),
                        'activity': user_state.get('body_state', {}).get('posture', 'unknown'),
                    })
                
                # 本地摄像头模式下，短暂休眠以控制帧率
                time.sleep(0.033)  # 约30fps
                
        except Exception as e:
            consecutive_errors += 1
            print(f"[感知线程] 错误 ({consecutive_errors}): {e}")
            
            # 当连续错误次数达到阈值时，切换到本地摄像头
            if consecutive_errors >= 5 and not use_local_camera:
                print("[感知线程] 网络摄像头连接失败，切换到本地摄像头")
                use_local_camera = True
                if local_camera_cap:
                    local_camera_cap.release()
                    local_camera_cap = None
            else:
                print(f"[感知线程] {retry_delay}秒后重连...")
                time.sleep(retry_delay)
                # 指数退避，但不超过最大值
                retry_delay = min(retry_delay * 2, max_retry_delay)

# ============================================================================
# Agent循环 - 降低频率
# ============================================================================
def agent_loop():
    """Agent持续运行循环 - 降低频率"""
    print("[Agent循环] 启动")
    
    while True:
        try:
            # ⭐ 基础模式下不运行Agent循环
            if system_core.is_basic_mode():
                time.sleep(2.0)
                continue
            
            world_state = system_core.get_state()
            
            if should_think(world_state):
                print(f"[Agent循环] 触发思考")
                decision = think(world_state, system_core)
                
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

# ⭐ 新的系统状态API - 从SystemCore获取
@app.route('/api/system/state')
def api_system_state():
    """获取系统全局状态"""
    return jsonify(system_core.get_state())

@app.route('/api/health')
def api_health():
    return jsonify(perception_manager.get_summary())

@app.route('/api/user_state')
def api_user_state():
    """获取用户感知状态 - 返回前端期望的格式"""
    # 从perception_manager获取最新状态
    pm_state = perception_manager.get_state()
    
    # 转换为前端期望的格式
    formatted_state = {
        "person_detected": pm_state.get("environment", {}).get("person_present", False),
        "face_detected": pm_state.get("environment", {}).get("face_detected", False),
        "body_detected": pm_state.get("body_state", {}).get("posture") != "unknown",
        "face_count": pm_state.get("environment", {}).get("person_count", 0),
        "physical_load": {
            "value": pm_state.get("overall", {}).get("fatigue_level", 0),
            "heart_rate": pm_state.get("heart_rate", {}).get("bpm"),
            "movement_intensity": pm_state.get("body_state", {}).get("activity_level", 0),
            "fall_detected": False  # 暂时不支持摔倒检测
        },
        "cognitive_load": {
            "value": 1 - pm_state.get("eye_state", {}).get("attention_score", 0.5),  # 注意力低则认知负荷高
            "error_rate": 0,  # 暂时不支持错误率检测
            "attention_stability": pm_state.get("eye_state", {}).get("attention_score", 0.5)
        },
        "engagement": {
            "value": pm_state.get("overall", {}).get("engagement_level", 0.5),
            "emotion_positive": 0.5 if pm_state.get("emotion", {}).get("primary") == "neutral" else (0.8 if pm_state.get("emotion", {}).get("primary") in ["happy", "excited"] else 0.2),
            "initiative_level": pm_state.get("body_state", {}).get("activity_level", 0)
        },
        "emotion": {
            "primary": pm_state.get("emotion", {}).get("primary", "neutral")
        },
        "posture": {
            "type": pm_state.get("body_state", {}).get("posture", "unknown"),
            "stability": 1.0 if pm_state.get("body_state", {}).get("posture") != "unknown" else 0
        },
        "activity": {
            "level": pm_state.get("body_state", {}).get("activity_level", 0)
        },
        "environment": {
            "light_level": pm_state.get("environment", {}).get("light_level", "normal")
        },
        "overall": {
            "state_summary": pm_state.get("overall", {}).get("state_summary", "normal")
        }
    }
    
    return jsonify(formatted_state)

@app.route('/api/world_state')
def api_world_state():
    return jsonify(system_core.get_state())

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

# ============================================================================
# 阿康对话 API
# ============================================================================
@app.route('/api/akon/chat', methods=['POST'])
def api_akon_chat():
    data = request.json
    user_input = data.get('message', '')
    
    if not user_input:
        return jsonify({"error": "请输入内容"}), 400
    
    system_core.set_user_speaking(True)
    
    # ⭐ 从SystemCore获取当前状态
    core_state = system_core.get_state()
    akon_state = {
        "current_page": core_state.get('currentPage', '/'),
        "game_active": system_core.is_game_active(),
        "game_name": core_state.get('game', {}).get('currentGame'),
        "game_score": core_state.get('gameRuntime', {}).get('score', 0),
        "ai_mode": core_state.get('aiMode', 'basic')
    }
    
    response, action = ask_akon(user_input, akon_state)
    
    system_core.set_user_speaking(False)
    
    return jsonify({"response": response, "action": action})


# ⭐ 训练统计 API
@app.route('/api/training/stats', methods=['GET'])
def api_training_stats():
    """获取训练统计数据"""
    analytics = get_training_analytics()
    
    return jsonify({
        "daily": analytics.get_daily_stats(),
        "weekly": analytics.get_weekly_stats(),
        "monthly": analytics.get_monthly_stats(),
        "trend": analytics.get_accuracy_trend(days=7)
    })


@app.route('/api/training/history', methods=['GET'])
def api_training_history():
    """获取训练历史记录"""
    analytics = get_training_analytics()

    # 返回最近10次训练记录
    sessions = analytics.sessions[-10:] if analytics.sessions else []

    return jsonify({
        "sessions": [
            {
                "session_id": s.session_id,
                "start_time": s.start_time,
                "game_type": s.game_type,
                "module": s.module,
                "final_score": s.final_score,
                "final_accuracy": round(s.final_accuracy * 100, 1),
                "total_trials": s.total_trials,
                "correct_trials": s.correct_trials,
                "avg_reaction_time_ms": round(s.avg_reaction_time_ms, 0),
                "difficulty_range": f"{s.min_difficulty}-{s.max_difficulty}",
                "duration": analytics._calc_duration(s)
            }
            for s in reversed(sessions)
        ]
    })


@app.route('/api/training/delete', methods=['POST'])
def api_training_delete():
    """删除训练记录"""
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({"success": False, "message": "缺少session_id参数"}), 400
    
    # 使用SystemCore的删除方法，同时删除summary和session文件
    success = system_core.delete_training_record(session_id)
    
    if success:
        return jsonify({"success": True, "message": "删除成功"})
    else:
        return jsonify({"success": False, "message": "删除失败"}), 500

# ============================================================================
# Socket事件 - 游戏控制
# ============================================================================
@socketio.on('game_control')
def handle_game_control(data):
    action = data.get('action')
    game_id = data.get('game', 'whack_a_mole')
    
    print(f"[游戏控制] action={action}, game={game_id}")
    
    if action == 'ready':
        # ⭐ 在准备游戏时，传递游戏参数
        game_params = {}
        # 从SystemCore获取确认时间
        dwell_time = data.get('dwell_time') or data.get('dwellTime') or system_core.get_dwell_time() or 2000
        game_params['dwell_time'] = dwell_time
        print(f"[游戏控制] {game_id} 确认时间: {dwell_time}ms")
        
        # ⭐ 更新SystemCore状态
        system_core.set_current_game(game_id)
        system_core.set_game_status('READY')
        system_core.reset_game_runtime()
        
        game_manager.set_ready(game_id, game_params=game_params)
        
        # ⭐ 发送导航指令让平板跳转到训练页面
        socketio.emit('navigate_to', {"page": "/training"})
        print(f"[游戏控制] 发送导航指令: /training")
    
    elif action == 'start':
        # ⭐ 更新SystemCore状态
        system_core.set_game_status('PLAYING')
        game_manager.start_game()
    
    elif action == 'pause':
        current_status = system_core.get_game_status()
        new_status = 'PAUSED' if current_status == 'PLAYING' else 'PLAYING'
        system_core.set_game_status(new_status)
        game_manager.toggle_pause()
    
    elif action == 'stop':
        system_core.set_game_status('IDLE')
        system_core.set_current_game(None)
        game_manager.stop_game()
        socketio.emit('navigate_to', {"page": "/learning"})
    
    elif action == 'timeout_stop':
        print("[游戏控制] 超时停止")
        system_core.set_game_status('IDLE')
        system_core.set_current_game(None)
        game_manager.stop_game()
        socketio.emit('navigate_to', {"page": "/learning"})
    
    elif action == 'restart':
        # ⭐ 重新开始游戏 - 直接回到READY状态，不经过IDLE
        restart_game_id = data.get('game') or system_core.get_current_game() or 'whack_a_mole'
        restart_dwell_time = data.get('dwell_time') or data.get('dwellTime') or system_core.get_dwell_time() or 2000
        
        print(f"[游戏控制] 重新开始游戏: {restart_game_id}, 确认时间: {restart_dwell_time}ms")
        
        # 停止当前游戏但不发送IDLE状态（避免前端跳转）
        if game_manager._current_game:
            game_manager._current_game.stop()
        
        # 直接设置为READY状态
        game_params = {'dwell_time': restart_dwell_time}
        system_core.set_current_game(restart_game_id)
        system_core.set_game_status('READY')
        system_core.reset_game_runtime()
        
        game_manager.set_ready(restart_game_id, game_params=game_params)
    
    elif action == 'update_params':
        # ⭐ 更新游戏参数（如确认时间）
        dwell_time = data.get('dwell_time')
        if dwell_time:
            system_core.set_dwell_time(dwell_time)
            if game_manager.get_current_game():
                game_manager.get_current_game().update_params({'dwell_time': dwell_time})
                print(f"[游戏控制] 更新确认时间: {dwell_time}ms")
    
    elif action == 'switch_module':
        # ⭐ 切换游戏模块
        module = data.get('module')
        if module:
            system_core.set_game_module(module)
            if game_manager.get_current_game():
                game_manager.get_current_game().update_params({'module': module})
                print(f"[游戏控制] 切换模块: {module}")

@socketio.on('game_action')
def handle_game_action(data):
    """处理游戏内动作"""
    action = data.get('action')
    zone = data.get('zone', -1)
    zone_id = data.get('zone_id', -1)
    success = data.get('success', False)
    
    # 优先使用 zone_id
    actual_zone = zone_id if zone_id > 0 else zone
    
    game_manager.handle_action(action, {
        "zone": actual_zone,
        "zone_id": zone_id,
        "success": success
    })

@socketio.on('game_hit')
def handle_game_hit(data):
    """兼容旧接口"""
    hole = data.get('hole', -1)
    hit = data.get('hit', False)
    game_manager.handle_action("hit", {"zone": hole, "success": hit})

# ============================================================================
# ⭐ Socket事件 - 系统状态控制（前端操作后端状态）
# ============================================================================
@socketio.on('set_ai_mode')
def handle_set_ai_mode(data):
    """设置AI模式 - 基础模式/智伴模式"""
    # ⭐ 数据验证
    if not isinstance(data, dict):
        print(f"[Socket] set_ai_mode: 无效数据类型")
        return
    
    mode = data.get('mode')
    if mode in ['basic', 'companion']:
        system_core.set_ai_mode(mode)
    else:
        print(f"[Socket] set_ai_mode: 无效模式 {mode}")

@socketio.on('toggle_companion')
def handle_toggle_companion(data):
    """切换智伴系统开关"""
    if not isinstance(data, dict):
        return
    
    enabled = data.get('enabled', False)
    mode = 'companion' if enabled else 'basic'
    system_core.set_ai_mode(mode)
    print(f"[系统] 智伴系统: {'开启' if enabled else '关闭'}")

@socketio.on('set_page')
def handle_set_page(data):
    """设置当前页面"""
    if not isinstance(data, dict):
        return
    
    page = data.get('page')
    # ⭐ 验证页面格式（必须以/开头）
    if page and isinstance(page, str) and page.startswith('/'):
        system_core.set_page(page)
    else:
        print(f"[Socket] set_page: 无效页面 {page}")

@socketio.on('set_dwell_time')
def handle_set_dwell_time(data):
    """设置确认时间"""
    if not isinstance(data, dict):
        return
    
    dwell_time = data.get('dwellTime') or data.get('dwell_time')
    # ⭐ 验证确认时间范围（500ms - 10000ms）
    if dwell_time and isinstance(dwell_time, (int, float)):
        dwell_time = int(dwell_time)
        if 500 <= dwell_time <= 10000:
            system_core.set_dwell_time(dwell_time)
            # 同时更新游戏参数
            if game_manager.get_current_game():
                game_manager.get_current_game().update_params({'dwell_time': dwell_time})
        else:
            print(f"[Socket] set_dwell_time: 确认时间超出范围 {dwell_time}")
    else:
        print(f"[Socket] set_dwell_time: 无效确认时间 {dwell_time}")

@socketio.on('set_voice_setting')
def handle_set_voice_setting(data):
    """设置语音功能"""
    if not isinstance(data, dict):
        return
    
    voice_type = data.get('type')
    enabled = data.get('enabled')
    
    if voice_type in ['wakeup', 'speaking'] and isinstance(enabled, bool):
        # 更新系统设置
        with system_core._lock:
            if voice_type == 'wakeup':
                system_core._state['settings']['voiceWakeup'] = enabled
            elif voice_type == 'speaking':
                system_core._state['settings']['voiceSpeaking'] = enabled
        
        # 保存配置
        system_core._save_config()
        # 广播状态更新
        system_core._broadcast()
        
        print(f"[Socket] 语音设置更新: {voice_type} = {enabled}")
    else:
        print(f"[Socket] set_voice_setting: 无效参数 type={voice_type}, enabled={enabled}")

@socketio.on('get_system_state')
def handle_get_system_state():
    """获取完整系统状态"""
    socketio.emit('system_state', system_core.get_state())

@socketio.on('get_state')
def handle_get_state(data=None):
    """获取状态（兼容旧接口）"""
    if data and data.get('client') == 'tablet' and data.get('first_connect'):
        if not system_core.is_game_active():
            socketio.emit('navigate_to', {"page": "/"})
    
    # ⭐ 发送 system_state
    socketio.emit('system_state', system_core.get_state())

@socketio.on('start_voice_input')
def handle_start_voice_input():
    """开始语音输入（点击按钮触发，不播放回应语）"""
    print("[语音] 前端请求开始语音输入（按钮点击）")
    # 通知语音管理器开始录音，跳过回应语
    if voice_manager:
        voice_manager.start_voice_input()

@socketio.on('get_tts_config')
def handle_get_tts_config():
    """获取TTS配置"""
    if voice_manager:
        config = voice_manager.get_tts_config()
        socketio.emit('tts_config', config)
        print("[TTS] 发送TTS配置到前端")

@socketio.on('set_tts_sid')
def handle_set_tts_sid(sid):
    """设置TTS音色ID"""
    if voice_manager:
        success = voice_manager.set_tts_sid(sid)
        print(f"[TTS] 设置音色ID: {sid}, 成功: {success}")

@socketio.on('set_tts_speed')
def handle_set_tts_speed(speed):
    """设置TTS语速"""
    if voice_manager:
        success = voice_manager.set_tts_speed(speed)
        print(f"[TTS] 设置语速: {speed}, 成功: {success}")

@socketio.on('set_tts_volume')
def handle_set_tts_volume(volume):
    """设置TTS音量"""
    if voice_manager:
        success = voice_manager.set_tts_volume(volume)
        print(f"[TTS] 设置音量: {volume}, 成功: {success}")

@socketio.on('set_tts_engine')
def handle_set_tts_engine(data):
    """设置TTS引擎 (vits 或 pytts)"""
    if not isinstance(data, dict):
        return
    
    engine = data.get('engine')
    if engine in ['vits', 'pytts']:
        # 更新VoiceManager
        if voice_manager:
            success = voice_manager.set_tts_engine(engine)
            print(f"[TTS] 设置引擎: {engine}, 成功: {success}")
        
        # 更新SystemCore
        system_core.set_tts_engine(engine)
    else:
        print(f"[TTS] 无效的引擎类型: {engine}")

@socketio.on('speak_text')
def handle_speak_text(data):
    """语音播报文本（前端打字完成后调用）"""
    text = data.get('text', '')
    source = data.get('source', 'text')
    
    if text and voice_manager:
        print(f"[语音播报] 来源: {source}, 文本: {text[:30]}...")
        voice_manager._speak(text)

# ============================================================================
# Socket事件 - 导航
# ============================================================================
@socketio.on('navigate')
def handle_navigate(data):
    page = data.get('page')
    source = data.get('source')
    print(f"[导航] page={page}, source={source}")
    
    if system_core.is_game_active():
        emit('navigate_error', {"message": "请先退出当前游戏"})
        return
    
    system_core.set_page(page)
    socketio.emit('navigate_to', {"page": page})

# ============================================================================
# 游戏状态同步 - 从GameManager到SystemCore
# ============================================================================
def sync_game_state():
    """同步游戏状态到SystemCore"""
    if game_manager.get_current_game():
        game = game_manager.get_current_game()
        state = game.get_state()
        
        # ⭐ 同步游戏状态（关键！确保SystemCore知道状态变化）
        current_status = state.get('status')
        if current_status:
            system_core_status = system_core.get_game_status()
            if system_core_status != current_status:
                print(f'[sync_game_state] 状态同步: {system_core_status} -> {current_status}')
                system_core.set_game_status(current_status)
        
        # 更新SystemCore的游戏运行时数据
        if game_manager.is_game_active():
            # ⭐ 准确率已经是 0-1 的小数，转换为整数百分比（0.89 -> 89）
            raw_accuracy = state.get('stats', {}).get('accuracy', 0)
            accuracy_percent = round(raw_accuracy * 100) if raw_accuracy <= 1 else round(raw_accuracy)
            system_core.update_game_runtime({
                'score': state.get('score', 0),
                'timer': state.get('timer', 60),
                'accuracy': accuracy_percent,
            })

# ============================================================================
# 后台任务
# ============================================================================
def main_worker():
    """游戏主循环 - 30fps"""
    while True:
        game_manager.update()
        
        # ⭐ 同步游戏状态到SystemCore
        sync_game_state()
        
        socketio.sleep(0.033)  # 33ms = 30fps

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    threading.Thread(target=main_worker, daemon=True).start()
    threading.Thread(target=perception_worker, daemon=True).start()
    threading.Thread(target=agent_loop, daemon=True).start()
"""    
    print("=" * 60)
    print("AI具身智能认知训练系统 - EAOS v3.0")
    print("============================================================")
    print()
    print(f"本机IP:     http://{LOCAL_IP}:{PORT}")
    print(f"平板访问:   http://{LOCAL_IP}:3000")
    print(f"投影页面:   http://{LOCAL_IP}:3000/projection")
    print(f"开发后台:   http://{LOCAL_IP}:3000/developer")
    print()
    print("已注册游戏:")
    
    for game_id in GAME_REGISTRY:
        print(f"  - {game_id}")
    print()
    
    print("系统模式:")
    
    mode = system_core.get_ai_mode()
    if mode == 'companion':
        print("  🟢 智伴模式 - AI主动感知和交互")
    else:
        print("  ⚪ 基础模式 - 预设程序运行")
    print()
    
    print("模块结构:")
    print("  core/       - SystemCore（统一状态管理）")
    print("  games/      - 游戏系统")
    print("  perception/ - 感知系统")
    print("============================================================")
    print()
"""
socketio.run(app, host='0.0.0.0', port=PORT, debug=False)