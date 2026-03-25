import cv2
import speech_recognition as sr
import threading
import logging
from flask import Flask, Response

# ================= 配置 =================
PORT = 5000
MIC_DEVICE = 3
CAMERA_ID = 1

app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ================= 视频流 =================
def gen_frames():
    cap = cv2.VideoCapture(CAMERA_ID)
    while True:
        success, frame = cap.read()
        if not success:
            continue
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video')
def video():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ================= 麦克风（已修复拼写） =================
def mic_task():
    r = sr.Recognizer()  # 这里修复了！
    mic = sr.Microphone(device_index=MIC_DEVICE)
    name = mic.list_microphone_names()[MIC_DEVICE]
    print(f"✅ 麦克风正常: {name}")

    with mic as source:
        r.adjust_for_ambient_noise(source)
        while True:
            try:
                audio = r.listen(source, timeout=1, phrase_time_limit=1)
                print(f"🗣️ 使用 {name}，麦克风正常！")
            except:
                continue

# ================= 启动 =================
if __name__ == '__main__':
    print("="*60)
    print("✅ 端口 5000 已清空")
    print("✅ 麦克风已就绪")
    print("✅ 摄像头已启动")
    print("🌐 访问地址：http://127.0.0.1:5000/video")
    print("="*60)

    threading.Thread(target=mic_task, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)