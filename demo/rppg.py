"""
rPPG 心率监测 V8.2 (精确 ROI + 快速响应)

V8.1 → V8.2 改动:
  1. ROI 定义重写: 不再猜关键点位置，改用 468 点计算精确人脸框
     + 眉毛关键点(159/145)定位额头/脸颊分界线
  2. EMA 加快: alpha 从 0.04→0.12（高质量时 ~2 秒跟踪变化）
  3. 质量门槛降低: 25→20，避免长时间冻结
  4. 中值窗口缩小: 9→7
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file, request
from scipy.signal import butter, filtfilt, find_peaks
import mediapipe as mp
import threading
import time
import os
import csv
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ============================================================
#  配置参数
# ============================================================
CAMERA_ID_DEFAULT = 0
DEFAULT_IP_CAMERA_URL = "http://10.215.158.45:8080/video"

POS_WINDOW         = 48
BUFFER_SIZE        = 300
HR_MIN_FREQ        = 0.75
HR_MAX_FREQ        = 3.0
BW_ORDER           = 3
BW_LOW             = 0.7
BW_HIGH            = 3.5
MEDIAN_KERNEL      = 5
HR_MEDIAN_WIN      = 7         # V8.1=9 → V8.2=7
HR_MAX_DELTA_SEC   = 8         # V8.1=6 → V8.2=8（稍放宽）
EMA_ALPHA_HIGH      = 0.12     # V8.1=0.04 → 0.12（快 ~2s 跟踪）
EMA_ALPHA_LOW       = 0.05     # V8.1=0.015 → 0.05
DETECT_INTERVAL    = 3
COMPUTE_INTERVAL   = 8
MIN_BUFFER_COMPUTE = POS_WINDOW * 3
MIN_ROI_PIXELS     = 400       # V8.1=300 → 400（稍微提高，过滤太小的区域）
BASE_MOTION_THRESH = 12.0
MOTION_PATIENCE    = 10
LIGHT_CHANGE_THRESH = 25.0
CSV_LOG_INTERVAL   = 10
MOTION_HISTORY_LEN = 5
BBOX_RETAIN_FRAMES = 30
PEAK_MIN_DISTANCE   = 12


# ============================================================
#  数据记录器
# ============================================================
class DataLogger:
    def __init__(self, filename='rppg_log.csv'):
        self.filename = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), filename)
        self.buffer = []
        self.counter = 0
        self._init_file()

    def _init_file(self):
        with open(self.filename, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                'time', 'hr', 'quality', 'roi_name',
                'skin_ratio', 'motion', 'fps',
                'hr_method', 'hr_peak', 'hr_fft'])
        print(f"[OK] 日志: {self.filename}")

    def log(self, hr, quality, roi_name, skin_ratio,
            motion, fps, method, hr_peak, hr_fft):
        self.counter += 1
        self.buffer.append([
            datetime.now().strftime('%H:%M:%S'),
            round(hr, 1), round(quality, 0), roi_name,
            round(skin_ratio, 3), round(motion, 1), round(fps, 1),
            method, round(hr_peak, 1), round(hr_fft, 1)])
        if self.counter % CSV_LOG_INTERVAL == 0:
            self._flush()

    def _flush(self):
        if not self.buffer:
            return
        with open(self.filename, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(self.buffer)
        self.buffer = []


# ============================================================
#  rPPG 处理器 V8.2
# ============================================================
class RPPGProcessor:

    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.camera_url = None
        self.cap = None
        self.logger = DataLogger()

        self.rgb_buffer = []
        self.time_buffer = []
        self.hr_raw_history = []
        self.hr_output_history = []
        self.pulse_history = []

        self.hr = 0.0
        self.signal_quality = 0.0
        self.face_detected = False
        self.face_confidence = 0.0
        self.fps = 0.0
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.processed_frames = 0
        self.actual_fs = 0.0
        self.last_hr_time = 0.0

        self.current_roi_name = "none"
        self.best_skin_ratio = 0.0
        self.active_roi_count = 0
        self.fusion_weights = {}

        self.all_roi_rects = []
        self.display_roi_rect = None

        self.prev_roi_gray = None
        self.motion_history = deque(maxlen=MOTION_HISTORY_LEN)
        self.motion_score = 0.0
        self.motion_threshold = BASE_MOTION_THRESH
        self.motion_frames = 0
        self.signal_paused = False
        self.paused_reason = ""

        self.prev_roi_brightness = None
        self.light_change_detected = False
        self.light_change_counter = 0

        self.bbox_lost_frames = 0
        self.bbox_lost = False

        self.last_hr_fft = 0.0
        self.last_hr_peak = 0.0
        self.hr_method = "--"

        self.lock = threading.Lock()
        self.running = True

        self.switch_lock = threading.Lock()
        self.switch_event = threading.Event()
        self.switch_target = None
        self.last_landmarks = None

    # -------------------- 摄像头管理 --------------------
    def _open_cap(self, src):
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            print(f"[ERROR] 无法打开视频源: {src}")
            return None
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def start(self):
        if self.camera_url:
            self.cap = self._open_cap(self.camera_url)
            print(f"[OK] 摄像头 (IP): {self.camera_url}")
        else:
            self.cap = self._open_cap(self.camera_id)
            print(f"[OK] 摄像头 (本地): {self.camera_id}")

        if self.cap is None:
            raise RuntimeError("无法打开任何摄像头")

        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[OK] 分辨率: {w}x{h}")

        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.3,
            min_tracking_confidence=0.3,
        )
        print("[OK] FaceMesh (468 关键点，精确 ROI)")
        print(f"[OK] 缓冲区 {BUFFER_SIZE} 帧 ({BUFFER_SIZE/30:.1f}s)")
        print(f"[OK] EMA alpha={EMA_ALPHA_HIGH}(high) / {EMA_ALPHA_LOW}(low)")

        threading.Thread(target=self._switch_worker, daemon=True).start()

    def stop(self):
        self.running = False
        self.switch_event.set()
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.logger._flush()

    def _switch_worker(self):
        while self.running:
            self.switch_event.wait()
            self.switch_event.clear()
            target = self.switch_target
            if target is None:
                continue
            src_type, src_val = target

            with self.switch_lock:
                self._reset_state()
                if self.cap and self.cap.isOpened():
                    self.cap.release()
                self.cap = None

                if src_type == 'local':
                    self.camera_url = None
                    self.camera_id = int(src_val)
                    self.cap = self._open_cap(int(src_val))
                else:
                    self.camera_url = str(src_val)
                    self.camera_id = None
                    self.cap = self._open_cap(str(src_val))

                if self.cap is None:
                    self.camera_url = None
                    self.camera_id = 0
                    self.cap = self._open_cap(0)

    def _reset_state(self):
        self.rgb_buffer.clear()
        self.time_buffer.clear()
        self.hr_raw_history.clear()
        self.hr_output_history.clear()
        self.pulse_history.clear()
        self.prev_roi_gray = None
        self.prev_roi_brightness = None
        self.last_landmarks = None
        self.all_roi_rects = []
        self.display_roi_rect = None
        self.best_skin_ratio = 0.0
        self.active_roi_count = 0
        self.fusion_weights = {}
        self.motion_history.clear()
        self.motion_frames = 0
        self.bbox_lost = False
        self.bbox_lost_frames = 0
        self.light_change_detected = False
        self.light_change_counter = 0
        self.signal_paused = False
        self.paused_reason = ""

    def request_switch(self, src_type, src_val):
        self.switch_target = (src_type, src_val)
        self.switch_event.set()

    # ================================================================
    #  [V8.2] ROI 定义：基于 468 点人脸框 + 眉毛分界线
    # ================================================================
    def define_rois_from_mesh(self, frame, landmarks):
        """
        V8 的问题：用 pts[159], pts[116], pts[234] 等单个关键点定义脸颊角落，
        这些点的实际位置不一定在脸颊区域内，导致 ROI 太小或位置错误。

        V8.2 的做法：
        1. 用全部 468 个关键点计算精确的人脸边界框
        2. 用眉毛关键点 (159=左眉尾, 145=右眉尾) 确定额头/脸颊分界线
        3. 在这个精确框内按比例定义 3 个区域

        额头 (weight=0.5): 脸顶部 → 眉毛上方
        左脸颊 (weight=1.2): 眉毛下方 → 下颌，左半边
        右脸颊 (weight=1.2): 眉毛下方 → 下颌，右半边
        """
        h, w = frame.shape[:2]
        pts = landmarks.landmark

        # --- 步骤 1: 用全部 468 个关键点计算精确人脸框 ---
        xs = [lm.x * w for lm in pts]
        ys = [lm.y * h for lm in pts]
        face_x1 = int(min(xs))
        face_y1 = int(min(ys))
        face_x2 = int(max(xs))
        face_y2 = int(max(ys))
        face_w = face_x2 - face_x1
        face_h = face_y2 - face_y1

        # --- 步骤 2: 眉毛 y 坐标（额头/脸颊分界线）---
        # pts[159] = 左眉毛外端, pts[145] = 右眉毛外端
        # 取两者 y 均值作为分界线
        brow_y = int((pts[159].y + pts[145].y) / 2 * h)

        # --- 步骤 3: 定义 3 个 ROI ---
        def safe(x1, y1, x2, y2):
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            if (x2 - x1) * (y2 - y1) < MIN_ROI_PIXELS:
                return None
            return (x1, y1, x2, y2)

        rois = []

        # 额头: 脸顶 → 眉毛上方，水平居中
        # y: face顶部 5% → 眉毛上方 3%
        # x: 脸宽 15%-85%（避边缘）
        fh_rect = safe(
            face_x1 + int(face_w * 0.15),
            face_y1 + int(face_h * 0.05),
            face_x2 - int(face_w * 0.15),
            brow_y - int(face_h * 0.03),
        )
        if fh_rect:
            rois.append(("forehead", fh_rect, 0.5))

        # 脸颊区域: 眉毛下方 → 脸底部 8%
        cheek_y1 = brow_y + int(face_h * 0.05)
        cheek_y2 = face_y2 - int(face_h * 0.08)

        # 左脸颊: 脸左边 5% → 脸中心偏左
        # x: 脸宽 5% → 45%
        lc_rect = safe(
            face_x1 + int(face_w * 0.05),
            cheek_y1,
            face_x1 + int(face_w * 0.45),
            cheek_y2,
        )
        if lc_rect:
            rois.append(("left_cheek", lc_rect, 1.2))

        # 右脸颊: 脸中心偏右 → 脸右边 5%
        # x: 脸宽 55% → 95%
        rc_rect = safe(
            face_x1 + int(face_w * 0.55),
            cheek_y1,
            face_x2 - int(face_w * 0.05),
            cheek_y2,
        )
        if rc_rect:
            rois.append(("right_cheek", rc_rect, 1.2))

        return rois

    # -------------------- HSV 皮肤检测 --------------------
    def compute_skin_ratio(self, roi_bgr):
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 15, 40])
        upper = np.array([30, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        return np.sum(mask > 0) / mask.size

    # -------------------- 多 ROI 融合 --------------------
    def extract_fused_rgb(self, frame, roi_list):
        candidates = []
        all_rects = []

        for name, rect, weight in roi_list:
            x1, y1, x2, y2 = rect
            roi = frame[y1:y2, x1:x2]
            if roi.shape[0] * roi.shape[1] < MIN_ROI_PIXELS:
                continue
            skin_ratio = self.compute_skin_ratio(roi)
            mean_rgb = np.mean(roi.reshape(-1, 3), axis=0)[::-1].copy()
            score = skin_ratio * weight
            candidates.append({
                "name": name, "rect": (x1, y1, x2, y2),
                "mean_rgb": mean_rgb, "skin_ratio": skin_ratio,
                "score": score, "weight": weight,
            })
            all_rects.append((name, (x1, y1, x2, y2), skin_ratio))

        if not candidates:
            return None, None, 0.0, 0, {}, []

        total_w = 0.0
        fused = np.zeros(3, dtype=np.float64)
        for c in candidates:
            wt = max(c["skin_ratio"], 0.05) * c["weight"]
            fused += wt * c["mean_rgb"]
            total_w += wt
        if total_w > 0:
            fused /= total_w

        best = max(candidates, key=lambda c: c["score"])
        weights = {c["name"]: round(c["skin_ratio"], 2) for c in candidates}

        return (fused, best["rect"], best["skin_ratio"],
                len(candidates), weights, all_rects)

    # -------------------- 多帧运动累积 --------------------
    def detect_motion(self, roi_gray):
        if self.prev_roi_gray is None:
            self.prev_roi_gray = roi_gray.copy()
            self.motion_history.clear()
            return 0.0
        if roi_gray.shape != self.prev_roi_gray.shape:
            self.prev_roi_gray = roi_gray.copy()
            self.motion_history.clear()
            return 0.0
        diff = cv2.absdiff(roi_gray, self.prev_roi_gray)
        self.prev_roi_gray = roi_gray.copy()
        self.motion_history.append(float(np.mean(diff)))
        return max(self.motion_history) if self.motion_history else 0.0

    # -------------------- 光照/运动解耦 --------------------
    def detect_lighting_change(self, roi_gray):
        current = float(np.mean(roi_gray))
        changed = False
        if self.prev_roi_brightness is not None:
            delta = abs(current - self.prev_roi_brightness)
            if delta > LIGHT_CHANGE_THRESH:
                changed = True
                self.light_change_detected = True
                self.light_change_counter = 30
                self.motion_threshold = self._base_motion_thresh(roi_gray) * 2.5
            else:
                if self.light_change_counter > 0:
                    self.light_change_counter -= 1
                    f = 1.0 + 1.5 * (self.light_change_counter / 30)
                    self.motion_threshold = self._base_motion_thresh(roi_gray) * f
                    if self.light_change_counter == 0:
                        self.light_change_detected = False
                else:
                    self.light_change_detected = False
        self.prev_roi_brightness = current
        return changed

    def _base_motion_thresh(self, roi_gray):
        b = float(np.mean(roi_gray))
        if b < 50:
            return BASE_MOTION_THRESH * 1.5
        if b > 200:
            return BASE_MOTION_THRESH * 0.8
        return BASE_MOTION_THRESH

    # -------------------- POS 投影 --------------------
    def pos_extract(self, rgb_signals):
        N = POS_WINDOW
        T = len(rgb_signals)
        if T < N:
            return None
        rgb = np.array(rgb_signals, dtype=np.float64)
        h1 = np.array([1.0, -1.0, 0.0]) / np.sqrt(2.0)
        h2 = np.array([1.0, 1.0, -2.0]) / np.sqrt(6.0)
        pulse = np.zeros(T - N + 1)
        for i in range(T - N + 1):
            window = rgb[i:i + N]
            centered = window - np.mean(window, axis=0)
            p1 = centered @ h1
            p2 = centered @ h2
            s1, s2 = np.std(p1), np.std(p2)
            pulse[i] = p1[-1] + (s1 / s2) * p2[-1] if s2 > 1e-8 else p1[-1]
        return pulse

    # -------------------- 信号处理 --------------------
    def median_filter(self, signal, kernel=5):
        if len(signal) < kernel:
            return signal
        half = kernel // 2
        padded = np.pad(signal, half, mode='edge')
        out = np.empty_like(signal)
        for i in range(len(signal)):
            out[i] = np.median(padded[i:i + kernel])
        return out

    def detrend(self, signal):
        signal = signal - np.mean(signal)
        if len(signal) < 3:
            return signal
        x = np.arange(len(signal), dtype=np.float64)
        return signal - np.polyval(np.polyfit(x, signal, 1), x)

    def butter_bandpass(self, signal, fs):
        nyq = 0.5 * fs
        if nyq <= 0:
            return signal
        low = max(0.001, BW_LOW / nyq)
        high = min(0.999, BW_HIGH / nyq)
        if high <= low:
            return signal
        try:
            b, a = butter(BW_ORDER, [low, high], btype='band')
            return filtfilt(b, a, signal)
        except Exception:
            return signal

    # -------------------- FFT 心率 --------------------
    def estimate_hr_fft(self, pulse, timestamps):
        if pulse is None:
            return 0.0, 0.0
        n = len(pulse)
        if n < POS_WINDOW * 2:
            return 0.0, 0.0
        valid_ts = timestamps[-n:]
        dt = np.median(np.diff(valid_ts))
        if dt <= 0.005 or dt > 0.15:
            return 0.0, 0.0
        self.actual_fs = 1.0 / dt
        fs = self.actual_fs

        signal = self.median_filter(pulse.copy(), MEDIAN_KERNEL)
        signal = self.detrend(signal)
        signal = self.butter_bandpass(signal, fs)
        if np.std(signal) < 1e-8:
            return 0.0, 0.0

        windowed = signal * np.hanning(n)
        freqs = np.fft.rfftfreq(n, d=dt)
        mags = np.abs(np.fft.rfft(windowed))
        mask = (freqs >= HR_MIN_FREQ) & (freqs <= HR_MAX_FREQ)
        if not np.any(mask):
            return 0.0, 0.0

        hr_mags = mags[mask]
        hr_freqs = freqs[mask]
        peak_idx = np.argmax(hr_mags)
        hr_bpm = hr_freqs[peak_idx] * 60.0
        quality = np.clip(
            (hr_mags[peak_idx] / (np.mean(hr_mags) + 1e-10)) * 12, 0, 100)

        if hr_bpm < 45 or hr_bpm > 180:
            quality *= 0.1
            hr_bpm = 0.0
        return hr_bpm, quality

    # -------------------- 峰值检测心率 --------------------
    def estimate_hr_peak(self, pulse, timestamps):
        if pulse is None:
            return 0.0, 0.0
        n = len(pulse)
        if n < POS_WINDOW * 2:
            return 0.0, 0.0
        valid_ts = timestamps[-n:]
        dt = np.median(np.diff(valid_ts))
        if dt <= 0.005 or dt > 0.15:
            return 0.0, 0.0

        signal = self.median_filter(pulse.copy(), MEDIAN_KERNEL)
        signal = self.detrend(signal)
        signal = self.butter_bandpass(signal, 1.0 / dt)
        if np.std(signal) < 1e-8:
            return 0.0, 0.0

        min_dist = max(PEAK_MIN_DISTANCE, int(dt * 60 / 45))
        peaks, _ = find_peaks(signal, distance=min_dist, height=0)
        if len(peaks) < 3:
            return 0.0, 0.0

        peak_times = np.array([valid_ts[-n + p] for p in peaks])
        rr = np.diff(peak_times)
        med_rr = np.median(rr)
        if med_rr <= 0:
            return 0.0, 0.0
        clean = rr[np.abs(rr - med_rr) / med_rr < 0.4]
        if len(clean) < 2:
            return 0.0, 0.0

        hr_bpm = 60.0 / np.median(clean)
        cv = np.std(clean) / (np.mean(clean) + 1e-10)
        quality = np.clip(100 - cv * 200, 0, 100)

        if hr_bpm < 45 or hr_bpm > 180:
            quality *= 0.1
            hr_bpm = 0.0
        return hr_bpm, quality

    # -------------------- 双路融合 --------------------
    def estimate_hr_combined(self, pulse, timestamps):
        hr_fft, q_fft = self.estimate_hr_fft(pulse, timestamps)
        hr_peak, q_peak = self.estimate_hr_peak(pulse, timestamps)
        self.last_hr_fft = hr_fft
        self.last_hr_peak = hr_peak

        fv, pv = hr_fft > 0, hr_peak > 0
        if fv and pv:
            d = abs(hr_fft - hr_peak)
            if d < 8:
                return (hr_fft + hr_peak) / 2, max(q_fft, q_peak), "avg"
            elif d < 20:
                if q_fft >= q_peak:
                    return hr_fft, q_fft * 0.9, "fft"
                return hr_peak, q_peak * 0.9, "peak"
            else:
                if q_fft > q_peak * 1.3:
                    return hr_fft, q_fft * 0.7, "fft"
                if q_peak > q_fft * 1.3:
                    return hr_peak, q_peak * 0.7, "peak"
                return 0.0, 0.0, "none"
        elif fv:
            return hr_fft, q_fft, "fft"
        elif pv:
            return hr_peak, q_peak, "peak"
        return 0.0, 0.0, "none"

    # -------------------- [V8.2] 心率限制 + 快速 EMA --------------------
    def apply_hr_limits(self, raw_hr, quality, now):
        """
        四层过滤:
        1. 质量门槛 >= 20
        2. 中值平滑 (窗口 7)
        3. 速度限制 (8 BPM/s)
        4. EMA (alpha=0.12 高质量, 0.05 低质量)
        """
        if quality < 20:
            return self.hr

        # 中值
        self.hr_raw_history.append(raw_hr)
        if len(self.hr_raw_history) > HR_MEDIAN_WIN * 3:
            self.hr_raw_history.pop(0)
        if len(self.hr_raw_history) >= HR_MEDIAN_WIN:
            hr_med = float(np.median(
                self.hr_raw_history[-HR_MEDIAN_WIN:]))
        else:
            hr_med = raw_hr

        # 速度限制
        if self.hr > 0 and self.last_hr_time > 0:
            dt_s = now - self.last_hr_time
            if dt_s > 0:
                mx = HR_MAX_DELTA_SEC * dt_s
                delta = hr_med - self.hr
                if abs(delta) > mx:
                    hr_med = self.hr + np.sign(delta) * mx

        if hr_med < 45 or hr_med > 180:
            return self.hr

        # EMA 低通
        alpha = EMA_ALPHA_HIGH if quality >= 30 else EMA_ALPHA_LOW
        if self.hr > 0:
            hr_ema = alpha * hr_med + (1 - alpha) * self.hr
        else:
            hr_ema = hr_med

        self.last_hr_time = now
        return hr_ema

    # -------------------- 诊断 --------------------
    def get_diagnostics(self):
        diags = []
        if not self.face_detected:
            diags.append("FACE_PARTIAL" if self.bbox_lost else "NO_FACE")
        elif self.signal_paused:
            diags.append("MOTION")
        elif self.light_change_detected:
            diags.append("LIGHT_CHANGE")
        elif self.best_skin_ratio < 0.3:
            diags.append("LOW_SKIN")
        elif self.signal_quality < 20:
            diags.append("LOW_SNR")
        elif len(self.rgb_buffer) < MIN_BUFFER_COMPUTE:
            diags.append("BUFFERING")
        else:
            diags.append("OK")
        return diags

    # -------------------- FaceMesh 检测 --------------------
    def _handle_face_detection(self, frame, rgb_frame):
        if self.processed_frames % DETECT_INTERVAL == 1:
            results = self.face_mesh.process(rgb_frame)
            if results.multi_face_landmarks:
                self.last_landmarks = results.multi_face_landmarks[0]
                self.face_detected = True
                self.face_confidence = 0.8
                self.bbox_lost = False
                self.bbox_lost_frames = 0
            else:
                if (self.last_landmarks is not None and
                        self.bbox_lost_frames < BBOX_RETAIN_FRAMES):
                    self.bbox_lost_frames += 1
                    self.bbox_lost = True
                    self.face_detected = True
                    self.face_confidence = max(0, self.face_confidence - 0.03)
                else:
                    self.last_landmarks = None
                    self.face_detected = False
                    self.bbox_lost = False
                    self.bbox_lost_frames = 0
                    self.all_roi_rects = []
                    self.display_roi_rect = None
                    self.current_roi_name = "none"
                    self.best_skin_ratio = 0
                    self.active_roi_count = 0
                    self.fusion_weights = {}
                    self.prev_roi_gray = None
                    self.prev_roi_brightness = None

    # -------------------- 单帧处理 --------------------
    def process_frame(self, frame):
        now = time.time()
        self.frame_count += 1
        elapsed = now - self.last_fps_time
        if elapsed >= 1.0:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.last_fps_time = now
        self.processed_frames += 1

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._handle_face_detection(frame, rgb_frame)

        if self.last_landmarks is not None:
            roi_list = self.define_rois_from_mesh(frame, self.last_landmarks)
            result = self.extract_fused_rgb(frame, roi_list)

            if result[0] is not None:
                (fused_rgb, best_rect, best_skin,
                 active_cnt, weights, all_rects) = result

                self.all_roi_rects = all_rects
                self.display_roi_rect = best_rect
                self.current_roi_name = "fused"
                self.best_skin_ratio = round(best_skin, 2)
                self.active_roi_count = active_cnt
                self.fusion_weights = weights

                best_roi = frame[best_rect[1]:best_rect[3],
                                 best_rect[0]:best_rect[2]]
                roi_gray = cv2.cvtColor(best_roi, cv2.COLOR_BGR2GRAY)

                self.detect_lighting_change(roi_gray)
                self.motion_score = self.detect_motion(roi_gray)

                if self.motion_score > self.motion_threshold:
                    self.motion_frames += 1
                    if self.motion_frames >= MOTION_PATIENCE:
                        self.signal_paused = True
                        self.paused_reason = "motion"
                else:
                    if self.motion_frames > 0:
                        self.motion_frames = max(0, self.motion_frames - 2)
                    if self.motion_frames == 0:
                        self.signal_paused = False
                        self.paused_reason = ""

                if not self.signal_paused:
                    with self.lock:
                        self.rgb_buffer.append(fused_rgb)
                        self.time_buffer.append(now)
                        if len(self.rgb_buffer) > BUFFER_SIZE:
                            self.rgb_buffer.pop(0)
                            self.time_buffer.pop(0)

                        if (len(self.rgb_buffer) >= MIN_BUFFER_COMPUTE and
                                self.processed_frames % COMPUTE_INTERVAL == 0):

                            pulse = self.pos_extract(np.array(self.rgb_buffer))
                            if pulse is not None and len(pulse) > POS_WINDOW * 2:
                                hr_raw, quality, method = \
                                    self.estimate_hr_combined(
                                        pulse, self.time_buffer)
                                if self.light_change_detected:
                                    quality *= 0.5
                                if hr_raw > 0:
                                    new_hr = self.apply_hr_limits(
                                        hr_raw, quality, now)
                                    self.hr = new_hr
                                    self.signal_quality = quality
                                    self.hr_method = method
                                    self.hr_output_history.append(
                                        round(new_hr, 1))
                                    if len(self.hr_output_history) > 120:
                                        self.hr_output_history.pop(0)
                                    self.logger.log(
                                        new_hr, quality, method,
                                        best_skin, self.motion_score,
                                        self.fps, method,
                                        self.last_hr_peak,
                                        self.last_hr_fft)

                                if len(pulse) > 48:
                                    p = pulse[-128:].copy()
                                    p = self.median_filter(p, 3)
                                    p = self.detrend(p)
                                    ps = np.std(p)
                                    if ps > 1e-8:
                                        p = p / ps
                                    self.pulse_history = p.tolist()
                else:
                    self.signal_quality *= 0.9
            else:
                self.all_roi_rects = []
                self.display_roi_rect = None
                self.current_roi_name = "none"
                self.best_skin_ratio = 0
                self.active_roi_count = 0
                self.fusion_weights = {}

        return frame

    # -------------------- HUD --------------------
    def draw_hud(self, frame):
        h, w = frame.shape[:2]

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 82), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        # 绘制全部 3 个 ROI
        ROI_COLORS = {
            "forehead":    (0, 200, 255),
            "left_cheek":  (0, 230, 118),
            "right_cheek": (255, 180, 0),
        }
        ROI_LABELS = {
            "forehead":    "Forehead",
            "left_cheek":  "L-Cheek",
            "right_cheek": "R-Cheek",
        }

        for name, (x1, y1, x2, y2), skin_r in self.all_roi_rects:
            color = ROI_COLORS.get(name, (200, 200, 200))
            label = f"{ROI_LABELS.get(name, name)} {skin_r:.0%}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
            cv2.putText(frame, label, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, color, 1)

        # 心率
        if self.hr > 0:
            hr_str = f"{self.hr:.0f} BPM"
            if self.signal_paused:
                hc = (0, 80, 255)
            elif self.light_change_detected:
                hc = (0, 180, 255)
            elif self.signal_quality >= 30:
                hc = (0, 230, 118)
            else:
                hc = (0, 180, 100)
        else:
            hr_str = "-- BPM"
            hc = (0, 100, 70)

        cv2.putText(frame, hr_str, (16, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, hc, 2)
        cv2.putText(frame, f"[{self.hr_method}]",
                    (16, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (100, 100, 100), 1)

        src_str = "IP" if self.camera_url else f"Local {self.camera_id}"
        if self.camera_url:
            try:
                from urllib.parse import urlparse
                p = urlparse(self.camera_url)
                src_str = f"IP {p.hostname}:{p.port}"
            except Exception:
                pass
        cv2.putText(frame, f"[{src_str}]",
                    (w - 130, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                    (80, 80, 80), 1)

        if self.face_detected:
            line = (f"Q:{self.signal_quality:.0f}% "
                    f"motion:{self.motion_score:.1f}/"
                    f"{self.motion_threshold:.0f} "
                    f"ROIs:{self.active_roi_count} "
                    f"fft:{self.last_hr_fft:.0f} "
                    f"peak:{self.last_hr_peak:.0f}")
            cv2.putText(frame, line, (100, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 180, 100), 1)
        else:
            cv2.putText(frame, "NO FACE DETECTED",
                        (100, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 80, 255), 1)

        fps_str = f"{self.fps:.0f}fps buf:{len(self.rgb_buffer)}/{BUFFER_SIZE}"
        cv2.putText(frame, fps_str, (w - 210, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (80, 80, 80), 1)

        buf_pct = len(self.rgb_buffer) / BUFFER_SIZE if BUFFER_SIZE else 0
        bc = ((0, 230, 118) if buf_pct >= 0.8 else
              (0, 130, 70) if not self.signal_paused else (0, 80, 200))
        cv2.rectangle(frame, (0, h - 3), (int(w * buf_pct), h), bc, -1)

        return frame


# ============================================================
#  Flask
# ============================================================
processor = RPPGProcessor()
processor.camera_url = DEFAULT_IP_CAMERA_URL
processor.camera_id = None
processor.start()


@app.route('/')
def index():
    html_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'cam.html')
    if os.path.exists(html_path):
        return send_file(html_path)
    return "<h1>cam.html not found</h1>"


@app.route('/video_feed')
def video_feed():
    def generate():
        while processor.running:
            try:
                with processor.switch_lock:
                    cap = processor.cap
                    if cap is None or not cap.isOpened():
                        time.sleep(0.05)
                        continue
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                frame = processor.process_frame(frame)
                frame = processor.draw_hud(frame)
                ok, jpeg = cv2.imencode(
                    '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    continue
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n'
                       + jpeg.tobytes() + b'\r\n')
            except Exception as e:
                print(f"[ERROR] {repr(e)}")
                time.sleep(0.01)
                continue
    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/camera', methods=['GET', 'POST'])
def api_camera():
    if request.method == 'GET':
        with processor.lock:
            return jsonify({
                'type': 'ip' if processor.camera_url else 'local',
                'src': processor.camera_url if processor.camera_url
                      else processor.camera_id,
            })
    data = request.get_json(force=True, silent=True) or {}
    ct = str(data.get('type', '')).strip().lower()
    cs = data.get('src')
    if ct == 'local':
        processor.request_switch('local', int(cs))
        return jsonify({'status': 'ok'})
    elif ct == 'default_ip':
        processor.request_switch('ip', DEFAULT_IP_CAMERA_URL)
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'invalid type'}), 400


@app.route('/api/hr')
def get_hr():
    with processor.lock:
        return jsonify({
            'hr': round(processor.hr, 1),
            'quality': round(processor.signal_quality, 0),
            'face': processor.face_detected,
            'fps': round(processor.fps, 1),
            'buffer': len(processor.rgb_buffer),
            'buffer_max': BUFFER_SIZE,
            'hr_history': processor.hr_output_history[-80:],
            'pulse': processor.pulse_history[-120:]
                           if processor.pulse_history else [],
            'roi_name': processor.current_roi_name,
            'skin_ratio': processor.best_skin_ratio,
            'motion_score': round(processor.motion_score, 1),
            'motion_threshold': round(processor.motion_threshold, 1),
            'motion_paused': processor.signal_paused,
            'light_change': processor.light_change_detected,
            'active_rois': processor.active_roi_count,
            'fusion_weights': processor.fusion_weights,
            'hr_method': processor.hr_method,
            'hr_fft': round(processor.last_hr_fft, 1),
            'hr_peak': round(processor.last_hr_peak, 1),
            'diagnostics': processor.get_diagnostics(),
        })


if __name__ == '__main__':
    try:
        print("=" * 58)
        print("  rPPG Monitor V8.2 (Accurate ROI + Responsive)")
        print("  ROI: Face bbox(468pts) + eyebrow boundary")
        print("  EMA: alpha=0.12(high)/0.05(low)")
        print("  Weights: forehead=0.5, cheeks=1.2")
        print("-" * 58)
        print("  http://localhost:5000")
        print("=" * 58)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭...")
    finally:
        processor.stop()
