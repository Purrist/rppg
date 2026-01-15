import cv2
import numpy as np
from flask import Flask, Response, jsonify
from flask_cors import CORS
from scipy.signal import butter, filtfilt, detrend

try:
    import mediapipe.python.solutions.face_mesh as mp_face_mesh
except:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh

app = Flask(__name__)
CORS(app)

FS = 30
BUFFER_SIZE = 150
raw_signals = []
filtered_signals = []
current_bpm = "--"

face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)

def butter_bandpass(data, lowcut=0.75, highcut=3.0, fs=30, order=2):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return filtfilt(b, a, data)

class ResearchProcessor:
    def __init__(self, camera_source=0):
        self.cap = None
        self.camera_source = camera_source
        self.connect_camera()

    def connect_camera(self):
        if self.cap is not None:
            self.cap.release()
        
        if isinstance(self.camera_source, str):
            print(f"正在连接网络摄像头: {self.camera_source}")
            self.cap = cv2.VideoCapture(self.camera_source)
        else:
            print(f"正在连接本地摄像头: {self.camera_source}")
            self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
        
        if not self.cap.isOpened():
            raise Exception(f"无法打开摄像头: {self.camera_source}")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("摄像头连接成功！")

    def get_frame(self):
        global current_bpm, filtered_signals
        success, frame = self.cap.read()
        if not success: return None

        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = face_mesh.process(rgb)

        dashboard = np.zeros((h, 300, 3), dtype=np.uint8)

        if res.multi_face_landmarks:
            landmarks = res.multi_face_landmarks[0].landmark
            rois = [10, 234, 454]
            current_g_pool = []

            for i, idx in enumerate(rois):
                cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
                r = 15
                if 0 < cy-r < h and 0 < cx-r < w:
                    roi_zone = frame[cy-r:cy+r, cx-r:cx+r]
                    current_g_pool.append(np.mean(roi_zone[:,:,1]))
                    cv2.circle(frame, (cx, cy), r, (0, 255, 0), -1)

            if current_g_pool:
                avg_g = np.mean(current_g_pool)
                global_g = np.mean(frame[:,:,1]) + 1e-6
                raw_signals.append(avg_g / global_g)

                if len(raw_signals) > BUFFER_SIZE: raw_signals.pop(0)

                if len(raw_signals) == BUFFER_SIZE:
                    try:
                        processed = detrend(np.array(raw_signals))
                        y = butter_bandpass(processed)
                        filtered_signals = y.tolist()
                        
                        fft = np.abs(np.fft.rfft(y))
                        freqs = np.fft.rfftfreq(BUFFER_SIZE, 1/FS)
                        current_bpm = int(freqs[np.argmax(fft[1:])+1] * 60)
                    except: pass

        if len(filtered_signals) > 2:
            pts = np.column_stack((
                np.linspace(10, 290, len(filtered_signals)), 
                150 - np.array(filtered_signals) * 1000
            )).astype(np.int32)
            cv2.polylines(dashboard, [pts], False, (0, 255, 0), 2)
            cv2.putText(dashboard, "BVP Signal Trace", (10, 30), 0, 0.5, (0,255,0), 1)

        combined = np.hstack((frame, dashboard))
        _, jpeg = cv2.imencode('.jpg', combined)
        return jpeg.tobytes()

ap = None

@app.route('/video_feed')
def video_feed():
    return Response((b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + ap.get_frame() + b'\r\n\r\n' for _ in iter(int, 1)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_metrics')
def get_metrics():
    return jsonify({"bpm": current_bpm})

if __name__ == "__main__":
    import sys
    
    camera_source = 0
    
    if len(sys.argv) > 1:
        camera_source = sys.argv[1]
        print(f"使用网络摄像头: {camera_source}")
    else:
        print("使用本地摄像头: 0")
        print("提示: 使用网络摄像头请运行: python app.py <RTSP_URL>")
    
    ap = ResearchProcessor(camera_source)
    app.run(host="0.0.0.0", port=8080)
