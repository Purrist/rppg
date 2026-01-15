import cv2
import numpy as np
from scipy.signal import butter, filtfilt, detrend
import threading
from queue import Queue
import time

try:
    import mediapipe.python.solutions.face_mesh as mp_face_mesh
except:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh

class TabletProcessor:
    def __init__(self, camera_url):
        self.camera_url = camera_url
        self.cap = None
        self.running = False
        self.thread = None
        
        self.face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)
        
        self.FS = 30
        self.BUFFER_SIZE = 150
        self.raw_signals = []
        self.filtered_signals = []
        
        self.current_bpm = "--"
        self.current_emotion = "neutral"
        self.emotion_confidence = 0.0
        self.fatigue_level = "unknown"
        self.attention_score = 0.0
        self.posture_state = "unknown"
        
        self.frame_queue = Queue(maxsize=1)
        
        self.emotion_labels = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
        
    def connect_camera(self):
        if self.cap is not None:
            self.cap.release()
        
        print(f"[平板摄像头] 正在连接: {self.camera_url}")
        self.cap = cv2.VideoCapture(self.camera_url)
        
        if not self.cap.isOpened():
            raise Exception(f"无法打开平板摄像头: {self.camera_url}")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        print("[平板摄像头] 连接成功！")
    
    def butter_bandpass(self, data, lowcut=0.75, highcut=3.0, fs=30, order=2):
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return filtfilt(b, a, data)
    
    def detect_emotion(self, landmarks, frame):
        h, w = frame.shape[:2]
        
        left_eye_top = landmarks[159]
        left_eye_bottom = landmarks[145]
        right_eye_top = landmarks[386]
        right_eye_bottom = landmarks[374]
        nose = landmarks[1]
        mouth_top = landmarks[13]
        mouth_bottom = landmarks[14]
        mouth_left = landmarks[61]
        mouth_right = landmarks[291]
        
        eye_height_left = abs(left_eye_top.y - left_eye_bottom.y)
        eye_height_right = abs(right_eye_top.y - right_eye_bottom.y)
        avg_eye_height = (eye_height_left + eye_height_right) / 2
        
        mouth_width = abs(mouth_right.x - mouth_left.x)
        mouth_height = abs(mouth_bottom.y - mouth_top.y)
        mouth_aspect = mouth_height / (mouth_width + 1e-6)
        
        eyebrow_height = abs(landmarks[10].y - landmarks[152].y)
        
        if avg_eye_height < 0.015 and mouth_aspect < 0.15:
            emotion = "neutral"
            confidence = 0.7
        elif mouth_aspect > 0.25 and eyebrow_height < 0.02:
            emotion = "happy"
            confidence = 0.85
        elif avg_eye_height < 0.01:
            emotion = "sad"
            confidence = 0.75
        elif eyebrow_height > 0.03 and mouth_aspect < 0.1:
            emotion = "angry"
            confidence = 0.7
        elif avg_eye_height < 0.02 and mouth_aspect > 0.2:
            emotion = "surprise"
            confidence = 0.75
        else:
            emotion = "neutral"
            confidence = 0.6
        
        return emotion, confidence
    
    def detect_posture(self, landmarks, frame):
        h, w = frame.shape[:2]
        
        nose = landmarks[1]
        left_shoulder = landmarks[11]
        right_shoulder = landmarks[12]
        
        shoulder_slope = abs(left_shoulder.y - right_shoulder.y)
        head_tilt = abs(nose.x - (left_shoulder.x + right_shoulder.x) / 2)
        
        if shoulder_slope < 0.02 and head_tilt < 0.05:
            posture = "focused"
        elif shoulder_slope < 0.02 and head_tilt > 0.1:
            posture = "relaxed"
        elif shoulder_slope > 0.05:
            posture = "slouching"
        elif head_tilt > 0.15:
            posture = "leaning"
        else:
            posture = "neutral"
        
        return posture
    
    def detect_fatigue(self, landmarks, frame):
        h, w = frame.shape[:2]
        
        left_eye_top = landmarks[159]
        left_eye_bottom = landmarks[145]
        right_eye_top = landmarks[386]
        right_eye_bottom = landmarks[374]
        
        left_eye_height = abs(left_eye_top.y - left_eye_bottom.y)
        right_eye_height = abs(right_eye_top.y - right_eye_bottom.y)
        avg_eye_height = (left_eye_height + right_eye_height) / 2
        
        if avg_eye_height < 0.015:
            fatigue = "high"
        elif avg_eye_height < 0.025:
            fatigue = "medium"
        else:
            fatigue = "low"
        
        return fatigue
    
    def process_frame(self, frame):
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.face_mesh.process(rgb)
        
        if res.multi_face_landmarks:
            landmarks = res.multi_face_landmarks[0].landmark
            
            rois = [10, 234, 454]
            current_g_pool = []
            
            for idx in rois:
                cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
                r = 15
                if 0 < cy-r < h and 0 < cx-r < w:
                    roi_zone = frame[cy-r:cy+r, cx-r:cx+r]
                    current_g_pool.append(np.mean(roi_zone[:,:,1]))
                    cv2.circle(frame, (cx, cy), r, (0, 255, 0), -1)
            
            if current_g_pool:
                avg_g = np.mean(current_g_pool)
                global_g = np.mean(frame[:,:,1]) + 1e-6
                self.raw_signals.append(avg_g / global_g)
                
                if len(self.raw_signals) > self.BUFFER_SIZE:
                    self.raw_signals.pop(0)
                
                if len(self.raw_signals) == self.BUFFER_SIZE:
                    try:
                        processed = detrend(np.array(self.raw_signals))
                        y = self.butter_bandpass(processed)
                        self.filtered_signals = y.tolist()
                        
                        fft = np.abs(np.fft.rfft(y))
                        freqs = np.fft.rfftfreq(self.BUFFER_SIZE, 1/self.FS)
                        self.current_bpm = int(freqs[np.argmax(fft[1:])+1] * 60)
                    except:
                        pass
                
                emotion, emotion_conf = self.detect_emotion(landmarks, frame)
                self.current_emotion = emotion
                self.emotion_confidence = emotion_conf
                
                fatigue = self.detect_fatigue(landmarks, frame)
                self.fatigue_level = fatigue
                
                posture = self.detect_posture(landmarks, frame)
                self.posture_state = posture
                
                self.attention_score = 0.5 + (0.5 * (1.0 - emotion_conf))
        
        return frame
    
    def get_state(self):
        return {
            "bpm": self.current_bpm,
            "emotion": self.current_emotion,
            "emotion_confidence": self.emotion_confidence,
            "fatigue_level": self.fatigue_level,
            "attention_score": self.attention_score,
            "posture_state": self.posture_state
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
        print("[平板摄像头] 处理线程已启动")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        print("[平板摄像头] 已停止")
    
    def get_frame(self):
        if not self.frame_queue.empty():
            return self.frame_queue.get()
        return None
