import cv2
import mediapipe as mp
import time
import base64
import threading

class ScreenProcessor:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # 最小化缓冲区
        
        self.mp_hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5, # 适当降低阈值提高响应
            min_tracking_confidence=0.5
        )
        
        # 预设三个地鼠洞识别区域 (保持归一化坐标不变，样式不改)
        self.holes = [
            {"id": 0, "rect": (0.05, 0.32, 0.35, 0.85)},
            {"id": 1, "rect": (0.37, 0.63, 0.35, 0.85)},
            {"id": 2, "rect": (0.68, 0.95, 0.35, 0.85)}
        ]
        
        self.hover_start = [0, 0, 0]
        self.progress = [0, 0, 0]
        self.raw_frame = None
        self.processed_data = {"image": "", "interact": {"progress": [0,0,0], "hit_index": -1}}
        self.running = True
        
        # 开启独立采集线程
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        """异步处理线程：确保识别不阻塞采集"""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.mp_hands.process(rgb_frame)
            
            active_index = -1
            if results.multi_hand_landmarks:
                # 获取食指指尖 (8号点)
                index_finger = results.multi_hand_landmarks[0].landmark[8]
                ix, iy = index_finger.x, index_finger.y
                
                for i, hole in enumerate(self.holes):
                    r = hole["rect"]
                    if r[0] < ix < r[1] and r[2] < iy < r[3]:
                        active_index = i
                        break

            # 进度计算逻辑优化：即时重置
            now = time.time()
            hit_index = -1
            for i in range(3):
                if i == active_index:
                    if self.hover_start[i] == 0: self.hover_start[i] = now
                    self.progress[i] = min(100, int((now - self.hover_start[i]) / 1.0 * 100))
                    if self.progress[i] >= 100:
                        hit_index = i
                        self.hover_start[i] = 0 # 击中后立刻重置，防止连续触发
                else:
                    self.hover_start[i] = 0
                    self.progress[i] = 0

            # 仅生成预览图用于开发者后台 (样式不改)
            for i, hole in enumerate(self.holes):
                r = hole["rect"]
                color = (0, 255, 0) if i == active_index else (0, 0, 255)
                cv2.rectangle(frame, (int(r[0]*w), int(r[2]*h)), (int(r[1]*w), int(r[3]*h)), color, 2)
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # 更新输出缓存
            self.processed_data = {
                "image": img_base64,
                "interact": {"progress": self.progress.copy(), "hit_index": hit_index}
            }

    def get_latest(self):
        """供主线程调用，不计算，只取值"""
        return self.processed_data