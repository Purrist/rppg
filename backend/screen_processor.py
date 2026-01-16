import cv2
import numpy as np
import threading
from queue import Queue
import time
import os

class ScreenProcessor:
    def __init__(self, camera_url):
        self.camera_url = camera_url
        self.cap = None
        self.running = False
        self.thread = None
        
        self.screen_regions = {
            "red": {"x": 0.2, "y": 0.5, "width": 0.15, "height": 0.2},
            "yellow": {"x": 0.5, "y": 0.5, "width": 0.15, "height": 0.2},
            "blue": {"x": 0.8, "y": 0.5, "width": 0.15, "height": 0.2}
        }
        
        self.hand_detected = False
        self.selected_region = None
        self.selection_confidence = 0.0
        self.frame_queue = Queue(maxsize=1)
        
        self.selection_start_time = None
        self.MIN_SELECTION_TIME = 3.0
    
    def connect_camera(self):
        if self.cap is not None:
            self.cap.release()
        
        print(f"[外接摄像头] 正在连接: {self.camera_url}")
        
        # 使用多线程实现超时控制
        import threading
        
        self.cap = None
        connect_error = None
        
        def connect_task():
            nonlocal self, connect_error
            try:
                # 判断是否为网络摄像头URL
                if isinstance(self.camera_url, str) and (self.camera_url.startswith('http://') or self.camera_url.startswith('https://')):
                    # 使用HTTP协议后端，移除backend参数让OpenCV自动检测
                    self.cap = cv2.VideoCapture(self.camera_url)
                else:
                    # 本地摄像头
                    self.cap = cv2.VideoCapture(self.camera_url)
                
                if not self.cap.isOpened():
                    connect_error = Exception(f"无法打开外接摄像头: {self.camera_url}")
                    return
                
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 30)
            except Exception as e:
                connect_error = e
        
        # 创建线程并启动
        thread = threading.Thread(target=connect_task)
        thread.daemon = True
        thread.start()
        
        # 等待最多3秒
        thread.join(timeout=3)
        
        if thread.is_alive():
            # 线程超时，强制退出
            raise Exception(f"外接摄像头连接超时: {self.camera_url}")
        
        if connect_error:
            raise connect_error
        
        if not self.cap or not self.cap.isOpened():
            raise Exception(f"无法打开外接摄像头: {self.camera_url}")
        
        print("[外接摄像头] 连接成功！")
    
    def detect_hand_occlusion(self, frame):
        h, w = frame.shape[:2]
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        for region_name, region in self.screen_regions.items():
            x = int(region["x"] * w)
            y = int(region["y"] * h)
            width = int(region["width"] * w)
            height = int(region["height"] * h)
            
            roi = gray[y:y+height, x:x+width]
            
            mean_brightness = np.mean(roi)
            
            if mean_brightness < 100:
                self.hand_detected = True
                self.selected_region = region_name
                self.selection_confidence = 1.0 - (mean_brightness / 100)
                
                cv2.rectangle(frame, (x, y), (x+width, y+height), (0, 255, 0), 2)
                
                return region_name
        
        self.hand_detected = False
        self.selected_region = None
        self.selection_confidence = 0.0
        
        return None
    
    def process_frame(self, frame):
        h, w = frame.shape[:2]
        
        detected_region = self.detect_hand_occlusion(frame)
        
        if detected_region:
            if self.selection_start_time is None:
                self.selection_start_time = time.time()
            else:
                elapsed = time.time() - self.selection_start_time
                if elapsed >= self.MIN_SELECTION_TIME:
                    self.selection_confidence = min(1.0, elapsed / self.MIN_SELECTION_TIME)
        
        return frame
    
    def get_state(self):
        return {
            "hand_detected": self.hand_detected,
            "selected_region": self.selected_region,
            "selection_confidence": self.selection_confidence,
            "selection_time": time.time() - self.selection_start_time if self.selection_start_time else 0
        }
    
    def capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            processed_frame = self.process_frame(frame)
            
            if not self.frame_queue.full():
                self.frame_queue.put(processed_frame)
    
    def start(self):
        self.connect_camera()
        self.running = True
        self.thread = threading.Thread(target=self.capture_loop)
        self.thread.daemon = True
        self.thread.start()
        print("[外接摄像头] 处理线程已启动")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        print("[外接摄像头] 已停止")
    
    def get_frame(self):
        if not self.frame_queue.empty():
            return self.frame_queue.get()
        return None