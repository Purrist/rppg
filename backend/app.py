import cv2
import numpy as np
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
import sys
import time

from tablet_processor import TabletProcessor
from screen_processor import ScreenProcessor
from state_manager import StateManager

app = Flask(__name__)
CORS(app)

tablet_processor = None
screen_processor = None
state_manager = None

def get_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

@app.route('/tablet_video_feed')
def tablet_video_feed():
    def generate():
        while True:
            frame = tablet_processor.get_frame()
            if frame is not None:
                _, jpeg = cv2.imencode('.jpg', frame)
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
            else:
                time.sleep(0.01)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/screen_video_feed')
def screen_video_feed():
    def generate():
        while True:
            frame = screen_processor.get_frame()
            if frame is not None:
                _, jpeg = cv2.imencode('.jpg', frame)
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
            else:
                time.sleep(0.01)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/physiological_state')
def get_physiological_state():
    return jsonify(tablet_processor.get_state())

@app.route('/api/screen_state')
def get_screen_state():
    return jsonify(screen_processor.get_state())

@app.route('/api/interaction_state')
def get_interaction_state():
    # 返回脚踩踏状态数据
    return jsonify({
        "person_detected": screen_processor.hand_detected,
        "body_position": {"x": 0.5, "y": 0.5},
        "gesture": "none",
        "gesture_confidence": 0.0,
        "interaction_target": screen_processor.selected_region or "none",
        "activity_level": "medium",
        "foot_detected": screen_processor.hand_detected,
        "foot_position": {"x": 0.5, "y": 0.8}
    })

@app.route('/api/fused_state')
def get_fused_state():
    return jsonify(state_manager.get_fused_state())

@app.route('/api/start_training', methods=['POST'])
def start_training():
    data = request.get_json() or {}
    mode = data.get('mode', 'memory_game')
    difficulty = data.get('difficulty', 'medium')
    
    result = state_manager.start_training(mode, difficulty)
    return jsonify(result)

@app.route('/api/stop_training', methods=['POST'])
def stop_training():
    result = state_manager.stop_training()
    return jsonify(result)

@app.route('/api/training_status')
def get_training_status():
    return jsonify(state_manager.get_training_status())

@app.route('/api/update_score', methods=['POST'])
def update_score():
    data = request.get_json() or {}
    correct = data.get('correct', True)
    
    state_manager.update_score(correct)
    return jsonify({"status": "success"})

@app.route('/api/training_history')
def get_training_history():
    limit = request.args.get('limit', 10, type=int)
    history = state_manager.get_training_history(limit)
    return jsonify({"sessions": history})

@app.route('/api/health')
def health_check():
    return jsonify({
        "status": "running",
        "tablet_camera": tablet_processor is not None,
        "screen_camera": screen_processor is not None,
        "state_manager": state_manager is not None
    })

def main():
    global tablet_processor, screen_processor, state_manager
    
    tablet_camera_url = 0
    screen_camera_url = 0
    
    if len(sys.argv) > 1:
        tablet_camera_url = sys.argv[1]
        print(f"使用手机摄像头作为平板摄像头: {tablet_camera_url}")
    else:
        print("错误: 必须提供平板摄像头URL")
        print("提示: 请运行 start_system.bat 并输入正确的手机摄像头URL")
        sys.exit(1)
    
    if len(sys.argv) > 2:
        screen_camera_url = sys.argv[2]
        print(f"使用手机摄像头作为屏幕摄像头: {screen_camera_url}")
    else:
        print("错误: 必须提供屏幕摄像头URL")
        print("提示: 请运行 start_system.bat 并输入正确的手机摄像头URL")
        sys.exit(1)
    
    try:
        state_manager = StateManager()
        print("[系统] 状态管理器已初始化")
        
        tablet_processor = TabletProcessor(tablet_camera_url)
        tablet_processor.start()
        print("[系统] 平板摄像头已启动")
        
        screen_processor = ScreenProcessor(screen_camera_url)
        screen_processor.start()
        print("[系统] 屏幕摄像头已启动")
        
        print("\n" + "="*60)
        print("双摄像头感知系统启动成功！")
        print("="*60)
        
        local_ip = get_ip()
        print(f"\n📡 局域网访问地址:")
        print(f"   平板控制界面: http://{local_ip}:3000/tablet")
        print(f"   投影训练界面: http://{local_ip}:3000/training")
        print(f"\n⚙️  后端 API 地址:")
        print(f"   http://{local_ip}:8080")
        print(f"\n📹 视频流:")
        print(f"   平板摄像头: http://{local_ip}:8080/tablet_video_feed")
        print(f"   屏幕摄像头: http://{local_ip}:8080/screen_video_feed")
        print(f"\n📊 API 接口:")
        print(f"   生理状态: http://{local_ip}:8080/api/physiological_state")
        print(f"   屏幕状态: http://{local_ip}:8080/api/screen_state")
        print(f"   融合状态: http://{local_ip}:8080/api/fused_state")
        print("="*60 + "\n")
        
        app.run(host="0.0.0.0", port=8080, debug=False)
        
    except KeyboardInterrupt:
        print("\n[系统] 正在关闭...")
    except Exception as e:
        print(f"\n[系统] 错误: {e}")
        print("\n请检查:")
        print("1. 平板摄像头 URL 是否正确")
        print("2. 平板和电脑是否在同一 Wi-Fi 网络")
        print("3. 平板上的摄像头应用是否已启动")
        print("4. 屏幕摄像头 URL 是否正确")
    finally:
        if tablet_processor:
            tablet_processor.stop()
        if screen_processor:
            screen_processor.stop()
        print("[系统] 已关闭")

if __name__ == "__main__":
    main()
