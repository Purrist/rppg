import cv2
import base64
import time
import threading
import numpy as np
from deepface import DeepFace

class EmotionProcessor:
    def __init__(self, video_url):
        self.cap = cv2.VideoCapture(video_url)
        # 缓冲设为 1，确保平板端看到的是“实时”画面
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.raw_frame = None
        self.latest_result = {"emotion": "initializing", "confidence": 0, "region": None}
        self.running = True

        # 线程 1：疯狂拉流（高频）
        threading.Thread(target=self._capture_loop, daemon=True).start()
        # 线程 2：识别情绪（低频，按你要求的 0.8s 步长）
        threading.Thread(target=self._analysis_loop, daemon=True).start()

    def _capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.raw_frame = frame
            else:
                time.sleep(0.01)

    def _analysis_loop(self):
        while self.running:
            if self.raw_frame is not None:
                try:
                    # 使用 opencv 作为 backend 是识别最快的方式
                    results = DeepFace.analyze(
                        self.raw_frame, 
                        actions=['emotion'], 
                        enforce_detection=False,
                        detector_backend='opencv', 
                        silent=True
                    )
                    if results:
                        res = results[0]
                        self.latest_result = {
                            "emotion": res['dominant_emotion'],
                            "confidence": round(res['emotion'][res['dominant_emotion']], 1),
                            "region": res['region']
                        }
                except Exception:
                    pass
            time.sleep(0.8) # 识别频率：0.8秒一次

    def get_ui_frame(self):
        """将最新的帧和识别结果合成为一张 Base64 图片"""
        if self.raw_frame is None: return None
        
        frame = self.raw_frame.copy()
        res = self.latest_result
        
        # 绘制逻辑：如果识别到人脸，画科技感边框
        if res.get("region"):
            r = res["region"]
            x, y, w, h = r['x'], r['y'], r['w'], r['h']
            color = (0, 255, 127) # 青色
            
            # 绘制四角 L 型框
            l = 25
            cv2.line(frame, (x, y), (x + l, y), color, 2)
            cv2.line(frame, (x, y), (x, y + l), color, 2)
            cv2.line(frame, (x+w, y), (x+w-l, y), color, 2)
            cv2.line(frame, (x+w, y), (x+w, y+l), color, 2)
            cv2.line(frame, (x, y+h), (x+l, y+h), color, 2)
            cv2.line(frame, (x, y+h), (x, y+h-l), color, 2)
            cv2.line(frame, (x+w, y+h), (x+w-l, y+h), color, 2)
            cv2.line(frame, (x+w, y+h), (x+w, y+h-l), color, 2)

            # 写文字
            label = f"{res['emotion'].upper()} {res['confidence']}%"
            cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 压缩并编码，质量 75 保证流畅度
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return {
            "image": base64.b64encode(buffer).decode('utf-8'),
            "emotion": res["emotion"],
            "confidence": res["confidence"]
        }

    def stop(self):
        self.running = False
        self.cap.release()