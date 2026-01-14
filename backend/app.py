import cv2
import numpy as np
from flask import Flask, Response, jsonify
from flask_cors import CORS
from scipy.signal import butter, filtfilt, detrend

# 强制路径导入，解决常见的 MediaPipe 属性错误
try:
    import mediapipe.python.solutions.face_mesh as mp_face_mesh
except:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh

app = Flask(__name__)
CORS(app)

# 核心算法参数
FS = 30           # 采样率
BUFFER_SIZE = 150 # 5秒数据窗口
signal_data = []
current_bpm = "--"

# 初始化人脸网格
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

def process_bpm(data):
    if len(data) < BUFFER_SIZE: return None
    # 1. 去趋势 & 归一化
    norm_data = detrend(np.array(data))
    norm_data = (norm_data - np.mean(norm_data)) / (np.std(norm_data) + 1e-6)
    # 2. 带通滤波 (0.75Hz - 3Hz 对应 45-180 BPM)
    nyq = 0.5 * FS
    b, a = butter(2, [0.75 / nyq, 3.0 / nyq], btype='band')
    filtered = filtfilt(b, a, norm_data)
    # 3. FFT 频率提取
    fft = np.abs(np.fft.rfft(filtered))
    freqs = np.fft.rfftfreq(BUFFER_SIZE, 1/FS)
    return int(freqs[np.argmax(fft[1:]) + 1] * 60)

class RppgEngine:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    def get_frame(self):
        global current_bpm
        success, frame = self.cap.read()
        
        # 核心修复：严禁空包进入 MediaPipe
        if not success or frame is None: return None

        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        try:
            results = face_mesh.process(rgb)
        except:
            return None

        # 准备叠加层 (光谱可视化)
        overlay = frame.copy()

        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            # 选取三个关键区域：额头(10), 左脸颊(234), 右脸颊(454)
            roi_points = [10, 234, 454]
            g_vals = []

            for idx in roi_points:
                cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
                r = 15
                if 0 < cy-r < h and 0 < cx-r < w:
                    roi = frame[cy-r:cy+r, cx-r:cx+r]
                    # 空间平均值提取
                    g_vals.append(np.mean(roi[:, :, 1]))
                    # 绘制光谱叠加效果 (增强绿色)
                    overlay[cy-r:cy+r, cx-r:cx+r, 1] = cv2.add(overlay[cy-r:cy+r, cx-r:cx+r, 1], 60)
                    cv2.rectangle(overlay, (cx-r, cy-r), (cx+r, cy+r), (0, 255, 0), 1)

            if g_vals:
                # 环境光补偿：局部均值 / 全局均值
                global_g = np.mean(frame[:, :, 1]) + 1e-6
                signal_data.append(np.mean(g_vals) / global_g)
                
                if len(signal_data) > BUFFER_SIZE: signal_data.pop(0)
                if len(signal_data) == BUFFER_SIZE:
                    bpm_res = process_bpm(signal_data)
                    if bpm_res: current_bpm = bpm_res

        # 合并图像：原始画面 + 30%光谱叠加
        final_frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
        _, jpeg = cv2.imencode('.jpg', final_frame)
        return jpeg.tobytes()

engine = RppgEngine()

@app.route('/video_feed')
def video_feed():
    def gen():
        while True:
            f = engine.get_frame()
            if f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f + b'\r\n\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/bpm_data')
def bpm_data():
    return jsonify({"bpm": current_bpm})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)