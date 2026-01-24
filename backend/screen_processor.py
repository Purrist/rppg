import cv2
import mediapipe as mp
import time

class ScreenProcessor:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.mp_hands = mp.solutions.hands.Hands(
            static_image_mode=False, 
            max_num_hands=1, 
            min_detection_confidence=0.7
        )
        # 归一化坐标定义的三个洞口 (x_min, x_max)
        self.holes_x = [(0.05, 0.3), (0.38, 0.62), (0.7, 0.95)]
        self.hover_start = [0, 0, 0] 
        self.progress = [0, 0, 0]

    def get_interaction(self):
        ret, frame = self.cap.read()
        if not ret: return None
        
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.mp_hands.process(rgb)
        
        active_index = -1
        if results.multi_hand_landmarks:
            # 8号点是食指指尖
            index_tip = results.multi_hand_landmarks[0].landmark[8]
            ix = index_tip.x
            for i, (xmin, xmax) in enumerate(self.holes_x):
                if xmin < ix < xmax:
                    active_index = i
                    break

        now = time.time()
        for i in range(3):
            if i == active_index:
                if self.hover_start[i] == 0: self.hover_start[i] = now
                duration = now - self.hover_start[i]
                self.progress[i] = min(100, int((duration / 1.0) * 100)) # 1秒充满
            else:
                self.hover_start[i] = 0
                self.progress[i] = 0
        
        return {"progress": self.progress, "hit_index": active_index if self.progress[active_index] >= 100 else -1}