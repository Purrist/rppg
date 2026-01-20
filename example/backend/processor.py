import cv2
import base64
import time
import threading
from deepface import DeepFace

class EmotionProcessor:
    def __init__(self, video_url):
        self.cap = cv2.VideoCapture(video_url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.raw_frame = None
        self.latest_result = {"emotion": "neutral", "confidence": 0, "region": None}
        self.running = True

        threading.Thread(target=self._capture_loop, daemon=True).start()
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
                    # 优化点：使用 mediapipe 代替 opencv，能极大地提高侧脸识别率
                    results = DeepFace.analyze(
                        self.raw_frame, 
                        actions=['emotion'], 
                        enforce_detection=False,
                        detector_backend='mediapipe', # 改为 mediapipe
                        silent=True
                    )
                    if results:
                        res = results[0]
                        self.latest_result = {
                            "emotion": res['dominant_emotion'],
                            "confidence": int(res['emotion'][res['dominant_emotion']]),
                            "region": res['region']
                        }
                except Exception:
                    pass
            time.sleep(0.6) # 稍微加快一点频率

    def get_ui_frame(self):
        if self.raw_frame is None: return None
        
        frame = self.raw_frame.copy()
        res = self.latest_result
        
        if res.get("region"):
            r = res["region"]
            x, y, w, h = r['x'], r['y'], r['w'], r['h']
            # 使用主题色 FF7222 (BGR: 34, 114, 255)
            color = (34, 114, 255) 
            
            # 画一个圆角的矩形框（简化版）
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 3)

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return {
            "image": base64.b64encode(buffer).decode('utf-8'),
            "emotion": res["emotion"],
            "confidence": res["confidence"]
        }

    def stop(self):
        self.running = False
        self.cap.release()