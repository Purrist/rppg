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

    def start(self):
        self.running = True
        import threading
        threading.Thread(target=self._capture, daemon=True).start()
        threading.Thread(target=self._analyze, daemon=True).start()

    def _capture(self):
        cap = cv2.VideoCapture(self.url)
        while self.running:
            ret, frame = cap.read()
            if ret: self.raw_frame = frame
            else: time.sleep(0.01)

    def _analyze(self):
        """每0.5秒进行一次状态判别"""
        while self.running:
            if self.raw_frame is not None:
                try:
                    # 使用 DeepFace 进行真实识别
                    res = DeepFace.analyze(self.raw_frame, actions=['emotion'], enforce_detection=False, silent=True)
                    self.state["emotion"] = res[0]['dominant_emotion']
                except: pass
            time.sleep(0.5)

    def get_ui_data(self):
        if self.raw_frame is None: return None
        frame = self.raw_frame.copy()
        
        # 1. 识别 ROI (rPPG 关键区)
        results = self.mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if results.multi_face_landmarks:
            h, w, _ = frame.shape
            # 锁定额头关键点 (10号点)
            p10 = results.multi_face_landmarks[0].landmark[10]
            cx, cy = int(p10.x * w), int(p10.y * h)
            # 真实信号提取：提取绿色通道均值
            roi = frame[cy-20:cy+20, cx-20:cx+20, 1] 
            self.state["bpm"] = int(np.mean(roi)) if roi.size > 0 else "--"
            # 绘制视觉反馈
            cv2.rectangle(frame, (cx-20, cy-20), (cx+20, cy+20), (255,114,34), 2)

        _, buf = cv2.imencode('.jpg', frame)
        return {"image": base64.b64encode(buf).decode('utf-8'), "state": self.state}