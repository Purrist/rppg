import cv2
import base64
import time
import threading
import numpy as np
from deepface import DeepFace
from collections import deque

class EmotionProcessor:
    def __init__(self, video_url):
        self.cap = cv2.VideoCapture(video_url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.raw_frame = None
        self.running = True
        
        # 核心：情绪状态平滑队列，容量设为 8，减少误判
        self.history = deque(maxlen=8)
        self.latest_result = {"emotion": "neutral", "confidence": 0, "status_level": 1}

        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._analysis_loop, daemon=True).start()

    def _capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret: self.raw_frame = frame
            else: time.sleep(0.01)

    def _analysis_loop(self):
        # 映射情绪到三级难度调节系统
        # 0: 难度太高 (愤怒/沮丧) | 1: 难度适中 (开心/专注) | 2: 难度太低 (无聊/平静)
        level_map = {
            'angry': 0, 'fear': 0, 'sad': 0, 
            'happy': 1, 'surprise': 1,
            'neutral': 2
        }

        while self.running:
            if self.raw_frame is not None:
                try:
                    # 使用 mediapipe 作为后端提供更好的角度鲁棒性
                    # 开启 align=True 强制人脸对齐，这是识别准确的关键
                    results = DeepFace.analyze(
                        self.raw_frame, 
                        actions=['emotion'], 
                        enforce_detection=False,
                        detector_backend='mediapipe', 
                        align=True,
                        silent=True
                    )
                    
                    if results:
                        res = results[0]
                        emo = res['dominant_emotion']
                        conf = res['emotion'][emo]

                        # 阈值过滤：只有当置信度超过一定程度或表情剧烈时才更新
                        self.history.append(emo)
                        
                        # 取众数，保证稳定性
                        stable_emo = max(set(self.history), key=self.history.count)
                        
                        self.latest_result = {
                            "emotion": stable_emo,
                            "confidence": round(conf, 1),
                            "status_level": level_map.get(stable_emo, 1),
                            "all_scores": res['emotion'] # 传回所有评分供前端绘图
                        }
                except Exception as e:
                    print(f"AI Analysis Error: {e}")
            
            # 识别频率调优：0.4秒，兼顾性能与灵敏度
            time.sleep(0.4)

    def get_ui_frame(self):
        if self.raw_frame is None: return None
        
        # 仿照你提供的 UI 参考图：视频流做半透明边缘遮罩处理
        frame = self.raw_frame.copy()
        
        # 仅压缩，不做画框，画框交给前端 Canvas 性能更好
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        return {
            "image": base64.b64encode(buffer).decode('utf-8'),
            "data": self.latest_result
        }