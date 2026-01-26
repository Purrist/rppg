import cv2
import mediapipe as mp
import time
import base64

class ScreenProcessor:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # 初始化 MediaPipe Hands
        self.mp_hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        
        # 预设三个地鼠洞识别区域 (归一化坐标: x_min, x_max, y_min, y_max)
        # 根据你手机摆放的角度，可以在此处微调
        self.holes = [
            {"id": 0, "rect": (0.05, 0.32, 0.35, 0.85)},
            {"id": 1, "rect": (0.37, 0.63, 0.35, 0.85)},
            {"id": 2, "rect": (0.68, 0.95, 0.35, 0.85)}
        ]
        
        self.hover_start = [0, 0, 0] # 记录进入区域的时间点
        self.progress = [0, 0, 0]    # 记录每个区域的停留进度 (0-100)

    def get_debug_frame(self):
        """获取带识别结果的Base64图片流及判定数据"""
        ret, frame = self.cap.read()
        if not ret:
            return None, None
        
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.mp_hands.process(rgb)
        
        active_index = -1
        # --- 1. 手指检测逻辑 ---
        if results.multi_hand_landmarks:
            for hand_lms in results.multi_hand_landmarks:
                # 绘制手部骨骼连线
                self.mp_draw.draw_landmarks(frame, hand_lms, mp.solutions.hands.HAND_CONNECTIONS)
                
                # 获取 8 号点：INDEX_FINGER_TIP (食指指尖)
                itip = hand_lms.landmark[8]
                ix, iy = itip.x, itip.y
                
                # 绘制食指尖亮点，方便调试看到手指位置
                cv2.circle(frame, (int(ix*w), int(iy*h)), 15, (255, 0, 255), -1)
                
                # 检查指尖坐标是否落在任何一个洞的矩形区域内
                for i, hole in enumerate(self.holes):
                    r = hole["rect"]
                    if r[0] < ix < r[1] and r[2] < iy < r[3]:
                        active_index = i
                        break

        # --- 2. 进度计算与视觉反馈 ---
        now = time.time()
        for i, hole in enumerate(self.holes):
            r = hole["rect"]
            x1, x2 = int(r[0]*w), int(r[1]*w)
            y1, y2 = int(r[2]*h), int(r[3]*h)
            
            # 如果手指在该区域内，进度增加
            if i == active_index:
                if self.hover_start[i] == 0: 
                    self.hover_start[i] = now
                # 1.0秒充满进度
                self.progress[i] = min(100, int((now - self.hover_start[i]) / 1.0 * 100))
                color = (0, 255, 0) # 绿色代表正在判定
            else:
                self.hover_start[i] = 0
                self.progress[i] = 0
                color = (0, 0, 255) # 红色代表空闲/未判定

            # 绘制区域边框
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            # 绘制进度文字
            cv2.putText(frame, f"HOLE {i}: {self.progress[i]}%", (x1, y1-15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # --- 3. 结果打包与图片编码 ---
        _, buffer = cv2.imencode('.jpg', frame)
        base64_img = base64.b64encode(buffer).decode('utf-8')
        
        # hit_index 只在进度达到100的那一瞬间返回
        res_data = {
            "progress": self.progress,
            "hit_index": active_index if self.progress[active_index] >= 100 else -1
        }
        
        return base64_img, res_data