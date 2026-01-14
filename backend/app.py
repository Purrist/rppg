import cv2
import numpy as np
from flask import Flask, Response, jsonify
from flask_cors import CORS
from scipy.signal import butter, filtfilt, detrend

# 医疗声明：本原型仅用于学术交互设计研究，不作为医疗诊断依据。
try:
    import mediapipe.python.solutions.face_mesh as mp_face_mesh
except:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh

app = Flask(__name__)
CORS(app)

# 信号缓冲区
FS = 30
BUFFER_SIZE = 150
raw_signals = []      # 原始绿色通道均值
filtered_signals = [] # 滤波后的波形（用于可视化）
current_bpm = "--"

face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)

def butter_bandpass(data, lowcut=0.75, highcut=3.0, fs=30, order=2):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return filtfilt(b, a, data)

class ResearchProcessor:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    def get_frame(self):
        global current_bpm, filtered_signals
        success, frame = self.cap.read()
        if not success: return None

        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = face_mesh.process(rgb)

        # 信号分析仪表盘
        dashboard = np.zeros((h, 300, 3), dtype=np.uint8) 

        if res.multi_face_landmarks:
            landmarks = res.multi_face_landmarks[0].landmark
            # 动态ROI选取：额头(10), 左脸颊(234), 右脸颊(454)
            rois = [10, 234, 454]
            current_g_pool = []

            for i, idx in enumerate(rois):
                cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
                # 动态ROI范围
                r = 15
                if 0 < cy-r < h and 0 < cx-r < w:
                    roi_zone = frame[cy-r:cy+r, cx-r:cx+r]
                    current_g_pool.append(np.mean(roi_zone[:,:,1]))
                    # 光谱成像叠加
                    cv2.circle(frame, (cx, cy), r, (0, 255, 0), -1)

            if current_g_pool:
                # 空间均值融合 + 全局归一化（抗光照波动核心）
                avg_g = np.mean(current_g_pool)
                global_g = np.mean(frame[:,:,1]) + 1e-6
                raw_signals.append(avg_g / global_g)

                if len(raw_signals) > BUFFER_SIZE: raw_signals.pop(0)

                if len(raw_signals) == BUFFER_SIZE:
                    try:
                        # 信号处理链路可视化
                        processed = detrend(np.array(raw_signals))
                        y = butter_bandpass(processed)
                        filtered_signals = y.tolist()
                        
                        # 频率计算
                        fft = np.abs(np.fft.rfft(y))
                        freqs = np.fft.rfftfreq(BUFFER_SIZE, 1/FS)
                        current_bpm = int(freqs[np.argmax(fft[1:])+1] * 60)
                    except: pass

        # 绘制实时波形图（这就是你要的可视化）
        if len(filtered_signals) > 2:
            pts = np.column_stack((
                np.linspace(10, 290, len(filtered_signals)), 
                150 - np.array(filtered_signals) * 1000
            )).astype(np.int32)
            cv2.polylines(dashboard, [pts], False, (0, 255, 0), 2)
            cv2.putText(dashboard, "BVP Signal Trace", (10, 30), 0, 0.5, (0,255,0), 1)

        # 拼接主画面和仪表盘
        combined = np.hstack((frame, dashboard))
        _, jpeg = cv2.imencode('.jpg', combined)
        return jpeg.tobytes()

ap = ResearchProcessor()

@app.route('/video_feed')
def video_feed():
    return Response((b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + ap.get_frame() + b'\r\n\r\n' for _ in iter(int, 1)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_metrics')
def get_metrics():
    return jsonify({"bpm": current_bpm})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)