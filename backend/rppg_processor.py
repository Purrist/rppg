# rppg_processor.py - rPPG 心率检测模块
# 使用 MediaPipe 人脸检测 + ICA算法 + 带通滤波

import cv2
import numpy as np
from collections import deque
import time
from scipy import signal
from scipy.ndimage import uniform_filter1d

# 尝试导入MediaPipe
try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False
    print("[rPPG] MediaPipe未安装，使用OpenCV")


class RPPGProcessor:
    """rPPG 心率检测处理器 - 改进版"""
    
    def __init__(self, fps=30, window_size=300, min_bpm=50, max_bpm=180):
        self.fps = fps
        self.window_size = window_size  # 10秒窗口
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        
        # 信号缓冲区
        self.rgb_buffer = deque(maxlen=window_size)
        self.time_buffer = deque(maxlen=window_size)
        
        # 人脸检测器
        if HAS_MEDIAPIPE:
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.6
            )
        else:
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
        
        # 结果
        self.bpm = None
        self.bpm_history = deque(maxlen=5)  # 平滑历史
        self.confidence = 0.0
        self.last_face_rect = None
        self.last_roi = None
        
        # 性能优化
        self.frame_count = 0
        self.process_every_n = 2  # 每2帧处理一次
        
        # 上次检测到的人脸位置（用于稳定）
        self.last_face_pos = None
        self.face_stable_count = 0
        
    def detect_face_mediapipe(self, frame):
        """MediaPipe人脸检测"""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_detector.process(rgb_frame)
        
        if results.detections:
            detection = results.detections[0]
            bboxC = detection.location_data.relative_bounding_box
            h, w, _ = frame.shape
            
            x = int(bboxC.xmin * w)
            y = int(bboxC.ymin * h)
            width = int(bboxC.width * w)
            height = int(bboxC.height * h)
            
            # 边界检查
            x = max(0, min(x, w - 10))
            y = max(0, min(y, h - 10))
            width = max(10, min(width, w - x))
            height = max(10, min(height, h - y))
            
            # 检查位置稳定性
            current_pos = (x, y, width, height)
            if self.last_face_pos:
                # 计算位置变化
                dx = abs(x - self.last_face_pos[0])
                dy = abs(y - self.last_face_pos[1])
                if dx < 30 and dy < 30:  # 位置稳定
                    self.face_stable_count += 1
                    # 使用稳定位置
                    if self.face_stable_count > 5:
                        x = int(0.7 * self.last_face_pos[0] + 0.3 * x)
                        y = int(0.7 * self.last_face_pos[1] + 0.3 * y)
                        width = int(0.7 * self.last_face_pos[2] + 0.3 * width)
                        height = int(0.7 * self.last_face_pos[3] + 0.3 * height)
                else:
                    self.face_stable_count = 0
            
            self.last_face_pos = current_pos
            
            # 提取额头区域（上半部分中间）
            roi_x = x + int(width * 0.2)
            roi_y = y + int(height * 0.05)
            roi_w = int(width * 0.6)
            roi_h = int(height * 0.25)
            
            return (roi_x, roi_y, roi_w, roi_h), (x, y, width, height)
        
        return None, None
    
    def detect_face_opencv(self, frame):
        """OpenCV人脸检测"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )
        
        if len(faces) > 0:
            x, y, w, h = faces[0]
            roi_x = x + int(w * 0.2)
            roi_y = y + int(h * 0.05)
            roi_w = int(w * 0.6)
            roi_h = int(h * 0.25)
            return (roi_x, roi_y, roi_w, roi_h), (x, y, w, h)
        
        return None, None
    
    def detect_face(self, frame):
        """检测人脸"""
        if HAS_MEDIAPIPE:
            return self.detect_face_mediapipe(frame)
        else:
            return self.detect_face_opencv(frame)
    
    def extract_rgb_mean(self, frame, roi):
        """提取ROI区域的RGB均值"""
        x, y, w, h = roi
        if w <= 0 or h <= 0:
            return None
        
        roi_frame = frame[y:y+h, x:x+w]
        if roi_frame.size == 0:
            return None
        
        # 空间平均
        mean = cv2.mean(roi_frame)[:3]
        return mean
    
    def bandpass_filter(self, data, low_cut, high_cut, fs, order=4):
        """带通滤波"""
        nyq = 0.5 * fs
        low = low_cut / nyq
        high = high_cut / nyq
        
        # 边界检查
        low = max(0.001, min(low, 0.99))
        high = max(low + 0.001, min(high, 0.99))
        
        try:
            b, a = signal.butter(order, [low, high], btype='band')
            return signal.filtfilt(b, a, data)
        except:
            return data
    
    def ica_based_hr(self, rgb_signals):
        """
        基于ICA的心率提取
        更鲁棒的方法
        """
        if len(rgb_signals) < 90:
            return None, 0
        
        signals = np.array(rgb_signals)
        n = len(signals)
        
        # 归一化
        signals = (signals - np.mean(signals, axis=0)) / (np.std(signals, axis=0) + 1e-10)
        
        # CHROM方法
        B = signals[:, 0]
        G = signals[:, 1]
        R = signals[:, 2]
        
        # 线性组合
        Xs = 3 * R - 2 * G
        Ys = 1.5 * R + G - 1.5 * B
        
        # 标准化
        Xs = (Xs - np.mean(Xs)) / (np.std(Xs) + 1e-10)
        Ys = (Ys - np.mean(Ys)) / (np.std(Ys) + 1e-10)
        
        # 计算alpha
        std_X = np.std(Xs)
        std_Y = np.std(Ys)
        alpha = std_X / (std_Y + 1e-10)
        
        # 组合信号
        S = Xs - alpha * Ys
        
        # 带通滤波 (0.8Hz - 3Hz, 即 48-180 BPM)
        try:
            S = self.bandpass_filter(S, 0.8, 3.0, self.fps)
        except:
            pass
        
        return S
    
    def calculate_bpm(self, signal):
        """使用FFT计算心率"""
        if signal is None or len(signal) < 90:
            return None, 0
        
        # 去除直流
        signal = signal - np.mean(signal)
        
        # 加窗
        window = np.hanning(len(signal))
        signal = signal * window
        
        # FFT
        n = len(signal)
        freqs = np.fft.rfftfreq(n, 1.0 / self.fps)
        fft_vals = np.abs(np.fft.rfft(signal))
        
        # 心率范围
        min_freq = self.min_bpm / 60
        max_freq = self.max_bpm / 60
        
        min_idx = np.argmax(freqs >= min_freq)
        max_idx = np.argmax(freqs >= max_freq)
        if max_idx <= min_idx:
            max_idx = len(freqs)
        
        # 找峰值
        search_range = fft_vals[min_idx:max_idx]
        if len(search_range) == 0:
            return None, 0
        
        peak_idx = np.argmax(search_range) + min_idx
        
        # BPM
        bpm = freqs[peak_idx] * 60
        
        # 置信度
        noise_level = np.mean(fft_vals[min_idx:max_idx]) + 1e-10
        peak_power = fft_vals[peak_idx]
        confidence = peak_power / noise_level
        
        # 检查是否有效
        if confidence < 2.0:
            return None, confidence
        
        # 检查BPM是否合理
        if bpm < self.min_bpm or bpm > self.max_bpm:
            return None, confidence
        
        return bpm, confidence
    
    def process_frame(self, frame):
        """处理单帧图像"""
        self.frame_count += 1
        
        # 跳帧
        if self.frame_count % self.process_every_n != 0:
            return self.bpm, self.confidence, self.last_face_rect, self.last_roi
        
        # 检测人脸
        roi, face = self.detect_face(frame)
        
        self.last_face_rect = face
        self.last_roi = roi
        
        if roi is None:
            self.face_stable_count = 0
            return self.bpm, self.confidence, face, roi
        
        # 提取RGB均值
        rgb_mean = self.extract_rgb_mean(frame, roi)
        
        if rgb_mean is None:
            return self.bpm, self.confidence, face, roi
        
        # 添加到缓冲区
        self.rgb_buffer.append(rgb_mean)
        self.time_buffer.append(time.time())
        
        # 窗口满时计算心率
        if len(self.rgb_buffer) >= self.window_size // 2:
            signal = self.ica_based_hr(list(self.rgb_buffer))
            bpm, confidence = self.calculate_bpm(signal)
            
            if bpm is not None and confidence > 2.5:
                # 添加到历史
                self.bpm_history.append(bpm)
                
                # 使用历史平滑
                if len(self.bpm_history) >= 3:
                    self.bpm = np.median(self.bpm_history)
                else:
                    self.bpm = bpm
                
                self.confidence = confidence
        
        return self.bpm, self.confidence, face, roi
    
    def get_status(self):
        return {
            "bpm": round(self.bpm, 1) if self.bpm else None,
            "confidence": round(self.confidence, 2),
            "buffer_size": len(self.rgb_buffer),
            "face_stable": self.face_stable_count
        }
