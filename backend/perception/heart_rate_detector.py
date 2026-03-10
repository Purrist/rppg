# perception/heart_rate_detector.py
# 心率检测模块 - 改进版rPPG

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
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


class HeartRateDetector:
    """
    心率检测器 - 改进版
    
    特点：
    1. 使用CHROM算法（更鲁棒）
    2. 多ROI融合（额头+脸颊）
    3. 强平滑处理（减少波动）
    4. 置信度评估
    5. HRV计算
    """
    
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        
        # 信号缓冲区（更长窗口，更稳定）
        self.rgb_buffer = deque(maxlen=300)  # 10秒
        self.time_buffer = deque(maxlen=300)
        
        # 人脸检测器
        if HAS_MEDIAPIPE:
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5
            )
            # 面部网格（更精确的ROI）
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                min_detection_confidence=0.5
            )
        else:
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
        
        # 结果
        self.bpm = None
        self.hrv = None
        self.confidence = 0.0
        
        # 平滑处理
        self.bpm_history = deque(maxlen=30)  # 1秒历史
        self.smoothed_bpm = None
        
        # 上次有效的人脸位置
        self.last_face_rect = None
        self.last_rois = None
        
        # 信号质量
        self.signal_quality = 0.0
        
        # 跳帧
        self.frame_count = 0
        self.process_every_n = 2
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        检测心率
        
        Args:
            frame: BGR图像
        
        Returns:
            {
                "bpm": 72.5,
                "hrv": 45.0,
                "confidence": 0.85
            }
        """
        self.frame_count += 1
        
        if self.frame_count % self.process_every_n != 0:
            return {
                "bpm": self.smoothed_bpm,
                "hrv": self.hrv,
                "confidence": self.confidence
            }
        
        # 检测人脸和ROI
        rois = self._detect_face_rois(frame)
        
        if rois is None:
            # 没有检测到人脸，降低置信度
            self.confidence = max(0, self.confidence - 0.1)
            return {
                "bpm": self.smoothed_bpm,
                "hrv": self.hrv,
                "confidence": self.confidence
            }
        
        # 提取RGB信号
        rgb_means = self._extract_rgb_means(frame, rois)
        
        if rgb_means is None:
            return {
                "bpm": self.smoothed_bpm,
                "hrv": self.hrv,
                "confidence": self.confidence
            }
        
        # 添加到缓冲区
        self.rgb_buffer.append(rgb_means)
        self.time_buffer.append(time.time())
        
        # 计算心率
        if len(self.rgb_buffer) >= 150:  # 至少5秒数据
            bpm, hrv, conf = self._calculate_hr()
            
            if bpm is not None and conf > 0.3:
                # 添加到历史
                self.bpm_history.append(bpm)
                
                # 强平滑
                if len(self.bpm_history) >= 5:
                    # 使用中值滤波去除异常值
                    recent = list(self.bpm_history)[-15:]
                    self.smoothed_bpm = np.median(recent)
                    
                    # 进一步平滑
                    if self.smoothed_bpm:
                        # 限制变化幅度
                        if self.bpm is not None:
                            max_change = 3  # 每次最多变化3 BPM
                            diff = self.smoothed_bpm - (self.bpm or self.smoothed_bpm)
                            if abs(diff) > max_change:
                                self.smoothed_bpm = (self.bpm or self.smoothed_bpm) + np.sign(diff) * max_change
                
                self.bpm = bpm
                self.hrv = hrv
                self.confidence = conf
        
        return {
            "bpm": self.smoothed_bpm,
            "hrv": self.hrv,
            "confidence": self.confidence
        }
    
    def _detect_face_rois(self, frame: np.ndarray) -> Optional[list]:
        """检测人脸并提取ROI区域"""
        h, w = frame.shape[:2]
        
        if HAS_MEDIAPIPE:
            return self._detect_rois_mediapipe(frame, h, w)
        else:
            return self._detect_rois_opencv(frame, h, w)
    
    def _detect_rois_mediapipe(self, frame: np.ndarray, h: int, w: int) -> Optional[list]:
        """使用MediaPipe检测ROI"""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 使用面部网格获取更精确的ROI
        results = self.face_mesh.process(rgb_frame)
        
        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0]
            
            # 提取额头ROI（landmark 10: 额头中心）
            # 提取左脸颊ROI（landmark 234）
            # 提取右脸颊ROI（landmark 454）
            
            rois = []
            
            # 额头区域
            forehead_x = int(landmarks.landmark[10].x * w)
            forehead_y = int(landmarks.landmark[10].y * h)
            roi_size = 30
            rois.append((
                max(0, forehead_x - roi_size),
                max(0, forehead_y - roi_size),
                roi_size * 2,
                roi_size * 2
            ))
            
            # 左脸颊
            left_x = int(landmarks.landmark[234].x * w)
            left_y = int(landmarks.landmark[234].y * h)
            rois.append((
                max(0, left_x - 20),
                max(0, left_y - 20),
                40, 40
            ))
            
            # 右脸颊
            right_x = int(landmarks.landmark[454].x * w)
            right_y = int(landmarks.landmark[454].y * h)
            rois.append((
                max(0, right_x - 20),
                max(0, right_y - 20),
                40, 40
            ))
            
            self.last_rois = rois
            return rois
        
        # 回退到人脸检测
        results = self.face_detector.process(rgb_frame)
        
        if results.detections:
            detection = results.detections[0]
            bboxC = detection.location_data.relative_bounding_box
            
            x = int(bboxC.xmin * w)
            y = int(bboxC.ymin * h)
            width = int(bboxC.width * w)
            height = int(bboxC.height * h)
            
            # 边界检查
            x = max(0, min(x, w - 10))
            y = max(0, min(y, h - 10))
            width = max(10, min(width, w - x))
            height = max(10, min(height, h - y))
            
            # 提取额头ROI
            roi_x = x + int(width * 0.25)
            roi_y = y + int(height * 0.08)
            roi_w = int(width * 0.5)
            roi_h = int(height * 0.2)
            
            rois = [(roi_x, roi_y, roi_w, roi_h)]
            self.last_rois = rois
            return rois
        
        return self.last_rois
    
    def _detect_rois_opencv(self, frame: np.ndarray, h: int, w: int) -> Optional[list]:
        """使用OpenCV检测ROI"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )
        
        if len(faces) > 0:
            x, y, width, height = faces[0]
            roi_x = x + int(width * 0.25)
            roi_y = y + int(height * 0.08)
            roi_w = int(width * 0.5)
            roi_h = int(height * 0.2)
            
            rois = [(roi_x, roi_y, roi_w, roi_h)]
            self.last_rois = rois
            return rois
        
        return self.last_rois
    
    def _extract_rgb_means(self, frame: np.ndarray, rois: list) -> Optional[Tuple]:
        """从多个ROI提取RGB均值"""
        if not rois:
            return None
        
        rgb_means = []
        
        for roi in rois:
            x, y, w, h = roi
            if w <= 0 or h <= 0:
                continue
            
            # 边界检查
            x = max(0, x)
            y = max(0, y)
            w = min(w, frame.shape[1] - x)
            h = min(h, frame.shape[0] - y)
            
            if w <= 0 or h <= 0:
                continue
            
            roi_frame = frame[y:y+h, x:x+w]
            if roi_frame.size == 0:
                continue
            
            # 计算均值
            mean = cv2.mean(roi_frame)[:3]
            rgb_means.append(mean)
        
        if not rgb_means:
            return None
        
        # 多ROI平均
        avg_r = np.mean([m[2] for m in rgb_means])
        avg_g = np.mean([m[1] for m in rgb_means])
        avg_b = np.mean([m[0] for m in rgb_means])
        
        return (avg_b, avg_g, avg_r)
    
    def _calculate_hr(self) -> Tuple[Optional[float], Optional[float], float]:
        """计算心率和HRV"""
        if len(self.rgb_buffer) < 150:
            return None, None, 0.0
        
        signals = np.array(list(self.rgb_buffer))
        
        # CHROM算法
        B = signals[:, 0]
        G = signals[:, 1]
        R = signals[:, 2]
        
        # 归一化
        B_norm = (B - np.mean(B)) / (np.std(B) + 1e-10)
        G_norm = (G - np.mean(G)) / (np.std(G) + 1e-10)
        R_norm = (R - np.mean(R)) / (np.std(R) + 1e-10)
        
        # CHROM线性组合
        Xs = 3 * R_norm - 2 * G_norm
        Ys = 1.5 * R_norm + G_norm - 1.5 * B_norm
        
        # 标准化
        Xs = (Xs - np.mean(Xs)) / (np.std(Xs) + 1e-10)
        Ys = (Ys - np.mean(Ys)) / (np.std(Ys) + 1e-10)
        
        # 计算alpha
        alpha = np.std(Xs) / (np.std(Ys) + 1e-10)
        
        # 组合信号
        S = Xs - alpha * Ys
        
        # 带通滤波 (0.67Hz - 3Hz, 即 40-180 BPM)
        try:
            nyq = 0.5 * self.fps
            low = 0.67 / nyq
            high = min(3.0 / nyq, 0.99)
            
            if low < high:
                b, a = signal.butter(4, [low, high], btype='band')
                S = signal.filtfilt(b, a, S)
        except:
            pass
        
        # FFT
        n = len(S)
        freqs = np.fft.rfftfreq(n, 1.0 / self.fps)
        fft_vals = np.abs(np.fft.rfft(S))
        
        # 心率范围 (50-120 BPM，更保守的范围)
        min_freq = 50 / 60
        max_freq = 120 / 60
        
        min_idx = np.argmax(freqs >= min_freq)
        max_idx = np.argmax(freqs >= max_freq)
        if max_idx <= min_idx:
            max_idx = len(freqs)
        
        # 找峰值
        search_range = fft_vals[min_idx:max_idx]
        if len(search_range) == 0:
            return None, None, 0.0
        
        peak_idx = np.argmax(search_range) + min_idx
        
        # BPM
        bpm = freqs[peak_idx] * 60
        
        # 置信度
        noise_level = np.mean(fft_vals[min_idx:max_idx]) + 1e-10
        peak_power = fft_vals[peak_idx]
        confidence = min(1.0, peak_power / noise_level / 5)
        
        # HRV计算（基于峰值宽度）
        hrv = None
        if confidence > 0.3:
            # 使用频谱宽度估计HRV
            half_max = peak_power / 2
            left_idx = peak_idx
            right_idx = peak_idx
            
            while left_idx > min_idx and fft_vals[left_idx] > half_max:
                left_idx -= 1
            while right_idx < max_idx and fft_vals[right_idx] > half_max:
                right_idx += 1
            
            # HRV = 频率宽度 * 60 (ms)
            freq_width = freqs[right_idx] - freqs[left_idx]
            hrv = freq_width * 60 * 1000  # 转换为ms
        
        # 验证BPM合理性
        if bpm < 50 or bpm > 120:
            confidence *= 0.5
        
        return bpm, hrv, confidence
    
    def reset(self):
        """重置状态"""
        self.rgb_buffer.clear()
        self.time_buffer.clear()
        self.bpm_history.clear()
        self.bpm = None
        self.smoothed_bpm = None
        self.hrv = None
        self.confidence = 0.0
