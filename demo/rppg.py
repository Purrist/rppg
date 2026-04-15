"""
rPPG 心率监测 V6 (鲁棒增强版)

V5 → V6:
  1. 多帧运动累积（取 max 而非单帧，捕捉往复运动）
  2. 光照/运动解耦（开灯不误判为运动）
  3. FFT + 峰值检测双路融合（两种方法互补）
  4. bbox 丢失后保留状态（短暂侧脸不丢信号）
  5. MediaPipe 侧脸容错（检测丢失后 30 帧内继续用旧 bbox）
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file
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
CAMERA_ID          = 0
POS_WINDOW         = 48
BUFFER_SIZE        = 180
HR_MIN_FREQ        = 0.75
HR_MAX_FREQ        = 3.0
BW_ORDER           = 3
BW_LOW             = 0.7
BW_HIGH            = 3.5
MEDIAN_KERNEL      = 5
HR_MEDIAN_WIN      = 5
HR_MAX_DELTA_SEC   = 12      # V5是15，收紧一点减少响应延迟
DETECT_INTERVAL    = 2
COMPUTE_INTERVAL   = 4
MIN_BUFFER_COMPUTE = POS_WINDOW * 3
MIN_ROI_PIXELS     = 300
BASE_MOTION_THRESH = 12.0
MOTION_PATIENCE    = 10      # V5是8，多给2帧宽容度
LIGHT_CHANGE_THRESH = 25.0
CSV_LOG_INTERVAL   = 10

# V6 新增
MOTION_HISTORY_LEN = 5       # 运动历史帧数
BBOX_RETAIN_FRAMES = 30      # bbox 丢失后保留状态的帧数（~1秒）
PEAK_MIN_DISTANCE   = 12     # 峰值最小间隔帧（0.4s@30fps）


# ============================================================
#  数据记录器
# ============================================================
class DataLogger:
    def __init__(self, filename='rppg_log.csv'):
        self.filename = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), filename
        )
        self.buffer = []
        self.counter = 0
        self._init_file()

    def _init_file(self):
        with open(self.filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'time', 'hr', 'quality', 'roi_name',
                'skin_ratio', 'motion', 'fps',
                'hr_method', 'hr_peak', 'hr_fft',
            ])
        print(f"[OK] 日志: {self.filename}")

    def log(self, hr, quality, roi_name, skin_ratio,
            motion, fps, method, hr_peak, hr_fft):
        self.counter += 1
        self.buffer.append([
            datetime.now().strftime('%H:%M:%S'),
            round(hr, 1), round(quality, 0), roi_name,
            round(skin_ratio, 3), round(motion, 1), round(fps, 1),
            method, round(hr_peak, 1), round(hr_fft, 1),
        ])
        if self.counter % CSV_LOG_INTERVAL == 0:
            self._flush()

    def _flush(self):
        if not self.buffer:
            return
        with open(self.filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(self.buffer)
        self.buffer = []


# ============================================================
#  BBox 平滑器
# ============================================================
class BBoxSmoother:
    def __init__(self, alpha=0.4):
        self.alpha = alpha
        self.bbox = None

    def update(self, new_bbox):
        if new_bbox is None:
            self.bbox = None
            return None
        if self.bbox is None:
            self.bbox = new_bbox
            return new_bbox
        b, n = self.bbox, new_bbox
        self.bbox = type(n)(
            xmin=b.xmin + self.alpha * (n.xmin - b.xmin),
            ymin=b.ymin + self.alpha * (n.ymin - b.ymin),
            width=b.width + self.alpha * (n.width - b.width),
            height=b.height + self.alpha * (n.height - b.height),
        )
        return self.bbox


# ============================================================
#  rPPG 处理器 V6
# ============================================================
class RPPGProcessor:

    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.cap = None
        self.face_detector = None
        self.bbox_smoother = BBoxSmoother(alpha=0.4)
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
        self.last_bbox = None
        self.actual_fs = 0.0
        self.last_hr_time = 0.0

        # ROI 融合
        self.current_roi_name = "none"
        self.best_roi_rect = None
        self.best_skin_ratio = 0.0
        self.active_roi_count = 0
        self.fusion_weights = {}

        # V6: 运动检测升级
        self.prev_roi_gray = None
        self.motion_history = deque(maxlen=MOTION_HISTORY_LEN)
        self.motion_score = 0.0
        self.motion_threshold = BASE_MOTION_THRESH
        self.motion_frames = 0
        self.signal_paused = False
        self.paused_reason = ""

        # V6: 光照/运动解耦
        self.prev_roi_brightness = None
        self.light_change_detected = False
        self.light_change_counter = 0   # 光照恢复计数器

        # V6: bbox 丢失后保留状态
        self.bbox_lost_frames = 0
        self.bbox_lost = False

        # V6: 双路心率
        self.last_hr_fft = 0.0
        self.last_hr_peak = 0.0
        self.hr_method = "--"

        self.lock = threading.Lock()
        self.running = True

    def start(self):
        self.cap = cv2.VideoCapture(self.camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开摄像头 {self.camera_id}")

        self.face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.3,  # V5是0.4，降低以提高侧脸检测率
        )

        print(f"[OK] 摄像头 {self.camera_id} 已打开")
        print(f"[OK] MediaPipe confidence=0.3 (侧脸容错)")
        print(f"[OK] 多帧运动累积 + 光照/运动解耦")
        print(f"[OK] FFT + 峰值检测双路心率")

    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.logger._flush()

    # -------------------- ROI 定义 --------------------
    def define_rois(self, frame, bbox):
        h, w = frame.shape[:2]
        x_min = int(bbox.xmin * w)
        y_min = int(bbox.ymin * h)
        bw = int(bbox.width * w)
        bh = int(bbox.height * h)

        return [
            {
                "name": "forehead_wide",
                "rect": (x_min + int(bw * .15), y_min + int(bh * .12),
                         x_min + int(bw * .85), y_min + int(bh * .42)),
                "weight": 1.2,
            },
            {
                "name": "forehead_core",
                "rect": (x_min + int(bw * .25), y_min + int(bh * .18),
                         x_min + int(bw * .75), y_min + int(bh * .38)),
                "weight": 1.5,
            },
            {
                "name": "left_cheek",
                "rect": (x_min + int(bw * .10), y_min + int(bh * .45),
                         x_min + int(bw * .40), y_min + int(bh * .72)),
                "weight": 0.8,
            },
            {
                "name": "right_cheek",
                "rect": (x_min + int(bw * .60), y_min + int(bh * .45),
                         x_min + int(bw * .90), y_min + int(bh * .72)),
                "weight": 0.8,
            },
        ]

    # -------------------- HSV 皮肤检测 --------------------
    def compute_skin_ratio(self, roi_bgr):
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 15, 40])
        upper = np.array([30, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        return np.sum(mask > 0) / mask.size

    # -------------------- 多 ROI 融合 --------------------
    def extract_all_rois(self, frame, rois):
        h, w = frame.shape[:2]
        candidates = []

        for roi_info in rois:
            x1, y1, x2, y2 = roi_info["rect"]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            roi = frame[y1:y2, x1:x2]
            if roi.shape[0] * roi.shape[1] < MIN_ROI_PIXELS:
                continue

            skin_ratio = self.compute_skin_ratio(roi)
            mean_rgb = np.mean(roi.reshape(-1, 3), axis=0)[::-1].copy()
            score = skin_ratio * roi_info["weight"]

            candidates.append({
                "name": roi_info["name"],
                "rect": (x1, y1, x2, y2),
                "roi": roi,
                "mean_rgb": mean_rgb,
                "skin_ratio": skin_ratio,
                "score": score,
                "weight": roi_info["weight"],
            })

        if not candidates:
            return None, None, 0.0, 0, {}

        total_weight = 0.0
        fused_rgb = np.zeros(3, dtype=np.float64)

        for c in candidates:
            wt = max(c["skin_ratio"], 0.05) * c["weight"]
            fused_rgb += wt * c["mean_rgb"]
            total_weight += wt

        if total_weight > 0:
            fused_rgb /= total_weight

        best = max(candidates, key=lambda c: c["score"])
        weight_info = {c["name"]: round(c["skin_ratio"], 2)
                       for c in candidates}

        return (fused_rgb, best["rect"], best["skin_ratio"],
                len(candidates), weight_info)

    # -------------------- V6: 多帧运动累积 --------------------
    def detect_motion(self, roi_gray):
        """
        V5: 单帧差分 → 快速往复运动互相抵消
        V6: 保存最近 5 帧差分，取 max → 捕捉任何方向的突发运动
        """
        if self.prev_roi_gray is None:
            self.prev_roi_gray = roi_gray.copy()
            self.motion_history.clear()
            return 0.0

        h, w = roi_gray.shape[:2]
        ph, pw = self.prev_roi_gray.shape[:2]
        if h != ph or w != pw:
            self.prev_roi_gray = roi_gray.copy()
            self.motion_history.clear()
            return 0.0

        diff = cv2.absdiff(roi_gray, self.prev_roi_gray)
        current_motion = float(np.mean(diff))

        self.prev_roi_gray = roi_gray.copy()
        self.motion_history.append(current_motion)

        # 取历史最大值（而非当前值），捕捉任何突发运动
        return max(self.motion_history) if self.motion_history else 0.0

    # -------------------- V6: 光照/运动解耦 --------------------
    def detect_lighting_change(self, roi_gray):
        """
        V5: 光照突变和运动检测独立，可能双重惩罚
        V6: 光照突变时临时提高运动阈值（避免误判为运动）
             同时给光照恢复一个渐退期
        """
        current_brightness = float(np.mean(roi_gray))
        changed = False

        if self.prev_roi_brightness is not None:
            delta = abs(current_brightness - self.prev_roi_brightness)
            if delta > LIGHT_CHANGE_THRESH:
                changed = True
                self.light_change_detected = True
                self.light_change_counter = 30  # 30 帧恢复期
                # 关键：光照突变时提高运动阈值，避免误判
                self.motion_threshold = self._base_motion_threshold(roi_gray) * 2.5
            else:
                # 渐退恢复：计数器递减，到 0 时恢复正常阈值
                if self.light_change_counter > 0:
                    self.light_change_counter -= 1
                    # 恢复期间阈值仍然偏高
                    factor = 1.0 + 1.5 * (self.light_change_counter / 30)
                    self.motion_threshold = self._base_motion_threshold(roi_gray) * factor
                    if self.light_change_counter == 0:
                        self.light_change_detected = False
                else:
                    self.light_change_detected = False

        self.prev_roi_brightness = current_brightness
        return changed

    def _base_motion_threshold(self, roi_gray):
        """基础运动阈值（根据亮度自适应）"""
        mean_b = float(np.mean(roi_gray))
        if mean_b < 50:
            return BASE_MOTION_THRESH * 1.5
        elif mean_b > 200:
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

    # -------------------- 信号处理工具 --------------------
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
        coeffs = np.polyfit(x, signal, 1)
        return signal - np.polyval(coeffs, x)

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

    # -------------------- V6: FFT 心率估计 --------------------
    def estimate_hr_fft(self, pulse_signal, timestamps):
        """FFT 频域心率估计"""
        if pulse_signal is None:
            return 0.0, 0.0
        n = len(pulse_signal)
        if n < POS_WINDOW * 2:
            return 0.0, 0.0

        valid_ts = timestamps[-n:]
        dt = np.median(np.diff(valid_ts))
        if dt <= 0.005 or dt > 0.15:
            return 0.0, 0.0
        fs = 1.0 / dt
        self.actual_fs = fs

        signal = pulse_signal.copy()
        signal = self.median_filter(signal, MEDIAN_KERNEL)
        signal = self.detrend(signal)
        signal = self.butter_bandpass(signal, fs)

        if np.std(signal) < 1e-8:
            return 0.0, 0.0

        windowed = signal * np.hanning(n)
        fft_result = np.fft.rfft(windowed)
        freqs = np.fft.rfftfreq(n, d=dt)
        magnitudes = np.abs(fft_result)

        mask = (freqs >= HR_MIN_FREQ) & (freqs <= HR_MAX_FREQ)
        if not np.any(mask):
            return 0.0, 0.0

        hr_mags = magnitudes[mask]
        hr_freqs = freqs[mask]
        peak_idx = np.argmax(hr_mags)
        peak_mag = hr_mags[peak_idx]
        peak_freq = hr_freqs[peak_idx]

        quality = np.clip((peak_mag / (np.mean(hr_mags) + 1e-10)) * 12, 0, 100)
        hr_bpm = peak_freq * 60.0

        if hr_bpm < 45 or hr_bpm > 180:
            quality *= 0.1
            hr_bpm = 0.0

        return hr_bpm, quality

    # -------------------- V6: 峰值检测心率 --------------------
    def estimate_hr_peak(self, pulse_signal, timestamps):
        """
        基于波峰检测的心率估计
        与 FFT 互补：FFT 擅长稳态信号，峰值检测擅长捕捉瞬态变化
        """
        if pulse_signal is None:
            return 0.0, 0.0
        n = len(pulse_signal)
        if n < POS_WINDOW * 2:
            return 0.0, 0.0

        valid_ts = timestamps[-n:]
        dt = np.median(np.diff(valid_ts))
        if dt <= 0.005 or dt > 0.15:
            return 0.0, 0.0

        signal = pulse_signal.copy()
        signal = self.median_filter(signal, MEDIAN_KERNEL)
        signal = self.detrend(signal)
        signal = self.butter_bandpass(signal, 1.0 / dt)

        if np.std(signal) < 1e-8:
            return 0.0, 0.0

        # 自适应最小峰间距：根据当前采样率计算
        # 最小心率 45 BPM → 最大间距 = 60/45/fs 帧
        # 最小心率 45 BPM → 最小间距 = fs/45 帧（即 0.67s@30fps）
        min_dist = max(PEAK_MIN_DISTANCE, int(dt * 60 / 45))

        # 找峰
        peaks, properties = find_peaks(signal, distance=min_dist, height=0)

        if len(peaks) < 3:
            return 0.0, 0.0

        # 计算峰间间隔（以秒为单位）
        peak_times = np.array([valid_ts[-n + p] for p in peaks])
        rr_intervals = np.diff(peak_times)

        # 去除异常间隔（偏离中位数超过 40%）
        median_rr = np.median(rr_intervals)
        if median_rr <= 0:
            return 0.0, 0.0
        clean_rr = rr_intervals[np.abs(rr_intervals - median_rr) / median_rr < 0.4]

        if len(clean_rr) < 2:
            return 0.0, 0.0

        hr_bpm = 60.0 / np.median(clean_rr)

        # 质量：峰间间隔的一致性（变异系数越小越好）
        cv = np.std(clean_rr) / (np.mean(clean_rr) + 1e-10)
        quality = np.clip(100 - cv * 200, 0, 100)

        if hr_bpm < 45 or hr_bpm > 180:
            quality *= 0.1
            hr_bpm = 0.0

        return hr_bpm, quality

    # -------------------- V6: 双路心率融合 --------------------
    def estimate_hr_combined(self, pulse_signal, timestamps):
        """
        FFT + 峰值检测融合策略:
        - 两者接近（<8 BPM）→ 取平均，质量取最大
        - 两者差异大 → 取质量高的，质量惩罚
        - 只有一个有效 → 直接用那个
        """
        hr_fft, q_fft = self.estimate_hr_fft(pulse_signal, timestamps)
        hr_peak, q_peak = self.estimate_hr_peak(pulse_signal, timestamps)

        self.last_hr_fft = hr_fft
        self.last_hr_peak = hr_peak

        fft_valid = hr_fft > 0
        peak_valid = hr_peak > 0

        if fft_valid and peak_valid:
            delta = abs(hr_fft - hr_peak)
            if delta < 8:
                # 一致：取平均
                hr = (hr_fft + hr_peak) / 2
                quality = max(q_fft, q_peak)
                method = "avg"
            elif delta < 20:
                # 轻微分歧：取质量高的
                if q_fft >= q_peak:
                    hr, quality = hr_fft, q_fft * 0.9
                    method = "fft"
                else:
                    hr, quality = hr_peak, q_peak * 0.9
                    method = "peak"
            else:
                # 严重分歧：只取质量明显更高的
                if q_fft > q_peak * 1.3:
                    hr, quality = hr_fft, q_fft * 0.7
                    method = "fft"
                elif q_peak > q_fft * 1.3:
                    hr, quality = hr_peak, q_peak * 0.7
                    method = "peak"
                else:
                    # 都不确定，保持上次值
                    return 0.0, 0.0, "none"
        elif fft_valid:
            hr, quality = hr_fft, q_fft
            method = "fft"
        elif peak_valid:
            hr, quality = hr_peak, q_peak
            method = "peak"
        else:
            return 0.0, 0.0, "none"

        return hr, quality, method

    # -------------------- 心率输出限制 --------------------
    def apply_hr_limits(self, raw_hr, quality, now):
        if quality < 15:   # V5是20，稍微放宽避免长时间不更新
            return self.hr

        self.hr_raw_history.append(raw_hr)
        if len(self.hr_raw_history) > HR_MEDIAN_WIN * 3:
            self.hr_raw_history.pop(0)
        if len(self.hr_raw_history) >= HR_MEDIAN_WIN:
            hr_smooth = float(np.median(self.hr_raw_history[-HR_MEDIAN_WIN:]))
        else:
            hr_smooth = raw_hr

        if self.hr > 0 and self.last_hr_time > 0:
            dt_sec = now - self.last_hr_time
            if dt_sec > 0:
                max_delta = HR_MAX_DELTA_SEC * dt_sec
                delta = hr_smooth - self.hr
                if abs(delta) > max_delta:
                    hr_smooth = self.hr + np.sign(delta) * max_delta

        if hr_smooth < 45 or hr_smooth > 180:
            return self.hr

        self.last_hr_time = now
        return hr_smooth

    # -------------------- 诊断信息 --------------------
    def get_diagnostics(self):
        diags = []
        if not self.face_detected:
            if self.bbox_lost:
                diags.append("FACE_PARTIAL")
            else:
                diags.append("NO_FACE")
        elif self.signal_paused and self.paused_reason == "motion":
            diags.append("MOTION")
        elif self.light_change_detected:
            diags.append("LIGHT_CHANGE")
        elif self.best_skin_ratio < 0.3:
            diags.append("LOW_SKIN")
        elif self.signal_quality < 15:
            diags.append("LOW_SNR")
        elif len(self.rgb_buffer) < MIN_BUFFER_COMPUTE:
            diags.append("BUFFERING")
        else:
            diags.append("OK")
        return diags

    # -------------------- V6: bbox 丢失处理 --------------------
    def _handle_face_detection(self, frame, rgb_frame):
        """
        V5: 丢检测 → 立即清空所有状态
        V6: 丢检测 → 保留 bbox 最多 BBOX_RETAIN_FRAMES 帧
             短暂侧脸/遮挡不会中断信号采集
        """
        if self.processed_frames % DETECT_INTERVAL == 1:
            results = self.face_detector.process(rgb_frame)

            if results.detections:
                det = results.detections[0]
                raw_bbox = det.location_data.relative_bounding_box
                smoothed = self.bbox_smoother.update(raw_bbox)
                self.last_bbox = smoothed
                self.face_confidence = det.score[0] if det.score else 0
                self.face_detected = True
                self.bbox_lost = False
                self.bbox_lost_frames = 0
            else:
                # 检测丢失
                if self.last_bbox is not None and self.bbox_lost_frames < BBOX_RETAIN_FRAMES:
                    # 保留上次 bbox，继续工作
                    self.bbox_lost_frames += 1
                    self.bbox_lost = True
                    self.face_detected = True  # 逻辑上仍视为"有脸"
                    self.face_confidence = max(0, self.face_confidence - 0.05)
                else:
                    # 超时，彻底丢失
                    self.last_bbox = None
                    self.face_detected = False
                    self.bbox_lost = False
                    self.bbox_lost_frames = 0
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
        roi_rect = None

        # V6: 改进的人脸检测（带丢失容错）
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._handle_face_detection(frame, rgb_frame)

        if self.last_bbox is not None:
            candidates = self.define_rois(frame, self.last_bbox)
            result = self.extract_all_rois(frame, candidates)

            if result[0] is not None:
                fused_rgb, best_rect, best_skin, active_cnt, weights = result
                roi_rect = best_rect
                self.current_roi_name = "fused"
                self.best_roi_rect = best_rect
                self.best_skin_ratio = round(best_skin, 2)
                self.active_roi_count = active_cnt
                self.fusion_weights = weights

                # 运动检测
                best_roi = frame[best_rect[1]:best_rect[3],
                                 best_rect[0]:best_rect[2]]
                roi_gray = cv2.cvtColor(best_roi, cv2.COLOR_BGR2GRAY)

                # V6: 光照检测（在运动检测之前，解耦两者）
                self.detect_lighting_change(roi_gray)

                # V6: 多帧运动累积
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

                # 采集信号
                if not self.signal_paused:
                    with self.lock:
                        self.rgb_buffer.append(fused_rgb)
                        self.time_buffer.append(now)

                        if len(self.rgb_buffer) > BUFFER_SIZE:
                            self.rgb_buffer.pop(0)
                            self.time_buffer.pop(0)

                        if (len(self.rgb_buffer) >= MIN_BUFFER_COMPUTE and
                                self.processed_frames % COMPUTE_INTERVAL == 0):

                            pulse = self.pos_extract(
                                np.array(self.rgb_buffer)
                            )

                            if pulse is not None and len(pulse) > POS_WINDOW * 2:
                                # V6: 双路融合心率估计
                                hr_raw, quality, method = self.estimate_hr_combined(
                                    pulse, self.time_buffer
                                )

                                if self.light_change_detected:
                                    quality *= 0.5

                                if hr_raw > 0:
                                    new_hr = self.apply_hr_limits(
                                        hr_raw, quality, now
                                    )
                                    self.hr = new_hr
                                    self.signal_quality = quality
                                    self.hr_method = method

                                    self.hr_output_history.append(
                                        round(new_hr, 1)
                                    )
                                    if len(self.hr_output_history) > 120:
                                        self.hr_output_history.pop(0)

                                    self.logger.log(
                                        new_hr, quality, method,
                                        best_skin, self.motion_score,
                                        self.fps, method,
                                        self.last_hr_peak,
                                        self.last_hr_fft
                                    )

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
                self.current_roi_name = "none"
                self.best_skin_ratio = 0
                self.active_roi_count = 0
                self.fusion_weights = {}

        return frame, roi_rect

    # -------------------- HUD --------------------
    def draw_hud(self, frame, roi_rect):
        h, w = frame.shape[:2]

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 78), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        if roi_rect:
            x1, y1, x2, y2 = roi_rect
            if self.signal_paused:
                box_color = (0, 80, 255)
                label = f"FUSED [MOTION]"
            elif self.light_change_detected:
                box_color = (0, 180, 255)
                label = f"FUSED [LIGHT]"
            elif self.bbox_lost:
                box_color = (0, 180, 100)
                label = f"FUSED [RETAIN {self.bbox_lost_frames}]"
            else:
                box_color = (0, 230, 118)
                label = (f"FUSED x{self.active_roi_count} "
                         f"skin:{self.best_skin_ratio:.0%}")
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(frame, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, box_color, 1)

        # 心率
        if self.hr > 0:
            hr_str = f"{self.hr:.0f} BPM"
            if self.signal_paused:
                hr_color = (0, 80, 255)
            elif self.light_change_detected:
                hr_color = (0, 180, 255)
            elif self.signal_quality >= 30:
                hr_color = (0, 230, 118)
            elif self.signal_quality >= 15:
                hr_color = (0, 180, 100)
            else:
                hr_color = (0, 130, 80)
        else:
            hr_str = "-- BPM"
            hr_color = (0, 100, 70)

        cv2.putText(frame, hr_str, (16, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, hr_color, 2)

        # 方法标签
        method_str = f"[{self.hr_method}]"
        cv2.putText(frame, method_str, (16, 56),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)

        # 状态信息（第三行）
        if self.face_detected:
            line1 = (f"Q:{self.signal_quality:.0f}% "
                     f"motion:{self.motion_score:.1f}/{self.motion_threshold:.0f} "
                     f"ROIs:{self.active_roi_count} "
                     f"fft:{self.last_hr_fft:.0f} "
                     f"peak:{self.last_hr_peak:.0f}")
            cv2.putText(frame, line1, (100, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 180, 100), 1)
        else:
            cv2.putText(frame, "NO FACE DETECTED", (100, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 80, 255), 1)

        # FPS
        fps_str = f"{self.fps:.0f}fps buf:{len(self.rgb_buffer)}/{BUFFER_SIZE}"
        cv2.putText(frame, fps_str, (w - 200, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (80, 80, 80), 1)

        # 底部进度条
        buf_pct = len(self.rgb_buffer) / BUFFER_SIZE if BUFFER_SIZE else 0
        bar_color = (0, 230, 118) if buf_pct >= 0.8 else \
                    (0, 130, 70) if not self.signal_paused else (0, 80, 200)
        cv2.rectangle(frame, (0, h - 3), (int(w * buf_pct), h),
                      bar_color, -1)

        return frame


# ============================================================
#  Flask
# ============================================================

processor = RPPGProcessor(camera_id=0)
processor.start()


@app.route('/')
def index():
    html_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'cam.html'
    )
    if os.path.exists(html_path):
        return send_file(html_path)
    return "<h1>cam.html not found</h1>"


@app.route('/video_feed')
def video_feed():
    def generate():
        while processor.running:
            try:
                if not (processor.cap and processor.cap.isOpened()):
                    time.sleep(0.1)
                    continue

                ret, frame = processor.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue

                frame, roi_rect = processor.process_frame(frame)
                frame = processor.draw_hud(frame, roi_rect)

                ok, jpeg = cv2.imencode(
                    '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                if not ok:
                    continue

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n'
                       + jpeg.tobytes() + b'\r\n')

            except Exception as e:
                print(f"[ERROR] {repr(e)}")
                time.sleep(0.01)
                continue

    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/hr')
def get_hr():
    with processor.lock:
        return jsonify({
            'hr': round(processor.hr, 1),
            'quality': round(processor.signal_quality, 0),
            'face': processor.face_detected,
            'confidence': round(processor.face_confidence, 2),
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
            'bbox_lost': processor.bbox_lost,
            'bbox_lost_frames': processor.bbox_lost_frames,
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
        print("  rPPG Monitor V6 (Robust Edition)")
        print("  Motion: multi-frame max (not single-frame)")
        print("  Light:  decoupled from motion (threshold boost)")
        print("  HR:     FFT + peak detection fusion")
        print("  Face:   bbox retain 30 frames on detection loss")
        print("-" * 58)
        print("  http://localhost:5000")
        print("=" * 58)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭...")
    finally:
        processor.stop()
