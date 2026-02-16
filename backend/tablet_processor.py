import cv2
import base64
import numpy as np
import time
from deepface import DeepFace
import mediapipe as mp

class TabletProcessor:
    def __init__(self, url):
        self.url = url
        self.running = False
        self.raw_frame = None
        self.mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=True)
        self.state = {"emotion": "neutral", "bpm": "--"}
        
        # rPPG 核心缓冲区
        self.buffer_size = 150
        self.data_buffer = []
        self.times = []

    def start(self):
        self.running = True
        import threading
        threading.Thread(target=self._capture, daemon=True).start()
        threading.Thread(target=self._analyze, daemon=True).start()

    def _capture(self):
        cap = cv2.VideoCapture(self.url)
        while self.running:
            ret, frame = cap.read()
            if ret:
                self.raw_frame = frame
            else:
                time.sleep(0.01)

    def _analyze(self):
        """降低检测频率至0.3s，防止DeepFace阻塞主进程导致卡顿"""
        while self.running:
            if self.raw_frame is not None:
                try:
                    # 关键：enforce_detection=False 避免没对准时报错死循环
                    res = DeepFace.analyze(self.raw_frame, actions=['emotion'], 
                                         enforce_detection=False, detector_backend='opencv', silent=True)
                    if res:
                        self.state["emotion"] = res[0]['dominant_emotion']
                except:
                    pass
            time.sleep(0.3)

    def get_ui_data(self):
        if self.raw_frame is None: return None
        frame = self.raw_frame.copy()
        
        # rPPG 实时提取逻辑
        results = self.mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if results.multi_face_landmarks:
            h, w, _ = frame.shape
            p10 = results.multi_face_landmarks[0].landmark[10] # 额头
            cx, cy = int(p10.x * w), int(p10.y * h)
            
            # 取得 ROI 区域
            roi = frame[max(0, cy-15):min(h, cy+15), max(0, cx-15):min(w, cx+15)]
            if roi.size > 0:
                green_val = np.mean(roi[:, :, 1])
                now = time.time()
                self.data_buffer.append(green_val)
                self.times.append(now)
                
                if len(self.data_buffer) > self.buffer_size:
                    self.data_buffer.pop(0)
                    self.times.pop(0)
                
                if len(self.data_buffer) >= self.buffer_size:
                    fps = len(self.times) / (self.times[-1] - self.times[0])
                    # 线性插值重采样
                    even_times = np.linspace(self.times[0], self.times[-1], len(self.times))
                    interp_data = np.interp(even_times, self.times, self.data_buffer)
                    # 归一化后 FFT
                    interp_data = (interp_data - np.mean(interp_data)) / np.std(interp_data)
                    fft = np.abs(np.fft.rfft(interp_data))
                    freqs = np.fft.rfftfreq(len(interp_data), 1.0/fps)
                    # 过滤 45-150 BPM 范围
                    valid = (freqs >= 0.75) & (freqs <= 2.5)
                    if np.any(valid):
                        self.state["bpm"] = int(freqs[valid][np.argmax(fft[valid])] * 60)

        _, buffer = cv2.imencode('.jpg', frame)
        return {
            "image": base64.b64encode(buffer).decode('utf-8'),
            "state": self.state
        }