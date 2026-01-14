import cv2
import numpy as np
from flask import Flask, Response, jsonify
from flask_cors import CORS
from scipy.signal import butter, filtfilt

# 尝试极限导入
try:
    import mediapipe.python.solutions.face_mesh as mp_face_mesh
except:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh

app = Flask(__name__)
CORS(app)

# 全局变量
FS = 30
BUFFER_SIZE = 150
signal_data = []
current_bpm = "--"

# 强制初始化
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5
)

def bandpass_filter(data):
    if len(data) < 50: return np.array(data) - np.mean(data)
    nyq = 0.5 * FS
    low, high = 0.8 / nyq, 3.0 / nyq # 48-180次/分
    b, a = butter(2, [low, high], btype='band')
    return filtfilt(b, a, data)

class VideoProcessor:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    def get_frames(self):
        global current_bpm
        success, frame = self.cap.read()
        if not success: return None, None

        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb_frame)
        
        # 初始化波形图预览
        wave_view = np.zeros((h, w, 3), dtype=np.uint8)

        if results.multi_face_landmarks:
            # 10号点为额头
            land = results.multi_face_landmarks[0].landmark[10]
            cx, cy = int(land.x * w), int(land.y * h)
            rx, ry = 25, 15 # 采样区域半径
            
            if 0 < cy-ry < h and 0 < cx-rx < w:
                roi = frame[cy-ry:cy+ry, cx-rx:cx+rx]
                # 提取绿通道均值
                g_mean = np.mean(roi[:, :, 1])
                signal_data.append(g_mean)
                if len(signal_data) > BUFFER_SIZE: signal_data.pop(0)

                # 处理信号
                if len(signal_data) == BUFFER_SIZE:
                    y = bandpass_filter(signal_data)
                    # 估算
                    fft = np.abs(np.fft.rfft(y))
                    freqs = np.fft.rfftfreq(BUFFER_SIZE, 1/FS)
                    current_bpm = int(freqs[np.argmax(fft[1:])+1] * 60)
                    
                    # 绘制波形
                    pts = np.column_stack((np.linspace(0, w, len(y)), h/2 - y*30)).astype(np.int32)
                    cv2.polylines(wave_view, [pts], False, (0, 255, 0), 2)

                # 绘制UI
                cv2.rectangle(frame, (cx-rx, cy-ry), (cx+rx, cy+ry), (0, 255, 0), 2)

        _, img_raw = cv2.imencode('.jpg', frame)
        _, img_wave = cv2.imencode('.jpg', wave_view)
        return img_raw.tobytes(), img_wave.tobytes()

vp = VideoProcessor()

@app.route('/stream/<mode>')
def stream(mode):
    def generate():
        while True:
            raw, wave = vp.get_frames()
            data = raw if mode == 'raw' else wave
            if data:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + data + b'\r\n\r\n')
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/bpm')
def get_bpm():
    return jsonify({"bpm": current_bpm})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)