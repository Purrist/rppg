"""
rPPG 心率监测 V5 (信号融合版)

V4.1 → V5 改动:
  1. 多 ROI 加权融合替代"选一个"（消除 ROI 跳变，SNR 更高）
  2. 自适应运动阈值（暗光下噪声更大）
  3. 光照突变检测（开灯/关灯时保护信号）
  4. CSV 数据记录（自动保存到 rppg_log.csv）
  5. 心跳动画与真实心率同步（前端 CSS）
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file
from scipy.signal import butter, filtfilt
import mediapipe as mp
import threading
import time
import os
import csv
from datetime import datetime

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
HR_MAX_DELTA_SEC   = 15
DETECT_INTERVAL    = 2
COMPUTE_INTERVAL   = 4
MIN_BUFFER_COMPUTE = POS_WINDOW * 3
MIN_ROI_PIXELS     = 300
BASE_MOTION_THRESH = 12.0
MOTION_PATIENCE    = 8
LIGHT_CHANGE_THRESH = 25.0  # 亮度变化超过此值视为光照突变
CSV_LOG_INTERVAL   = 10     # 每 N 次计算写入一次 CSV


# ============================================================
#  数据记录器
# ============================================================
class DataLogger:
    """将心率数据自动保存到 CSV 文件"""

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
                'skin_ratio', 'motion', 'fps'
            ])
        print(f"[OK] 日志文件: {self.filename}")

    def log(self, hr, quality, roi_name, skin_ratio, motion, fps):
        self.counter += 1
        self.buffer.append([
            datetime.now().strftime('%H:%M:%S'),
            round(hr, 1),
            round(quality, 0),
            roi_name,
            round(skin_ratio, 3),
            round(motion, 1),
            round(fps, 1),
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
#  rPPG 处理器 V5
# ============================================================
class RPPGProcessor:

    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.cap = None
        self.face_detector = None
        self.bbox_smoother = BBoxSmoother(alpha=0.4)
        self.logger = DataLogger()

        # 缓冲区
        self.rgb_buffer = []
        self.time_buffer = []
        self.hr_raw_history = []
        self.hr_output_history = []
        self.pulse_history = []

        # 状态
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

        # ROI 融合状态
        self.current_roi_name = "none"
        self.best_roi_rect = None  # 用于视频框显示
        self.best_skin_ratio = 0.0
        self.active_roi_count = 0
        self.fusion_weights = {}

        # 运动检测
        self.prev_roi_gray = None
        self.motion_score = 0.0
        self.motion_threshold = BASE_MOTION_THRESH
        self.motion_frames = 0
        self.signal_paused = False
        self.paused_reason = ""

        # 光照检测（V5 新增）
        self.prev_roi_brightness = None
        self.light_change_detected = False

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
            min_detection_confidence=0.4,
        )

        print(f"[OK] 摄像头 {self.camera_id} 已打开")
        print(f"[OK] MediaPipe 远距离人脸模型 (0.5-5m)")
        print(f"[OK] Butterworth {BW_LOW}-{BW_HIGH}Hz order={BW_ORDER}")
        print(f"[OK] 多ROI信号融合 + 光照突变检测 + CSV记录")

    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.logger._flush()  # 关闭时写入剩余数据

    # -------------------- 多 ROI 定义 --------------------
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

    # -------------------- 核心：多 ROI 信号融合 --------------------
    def extract_all_rois(self, frame, rois):
        """
        提取所有候选 ROI 的信息
        返回: (fused_rgb, best_rect, skin_ratio, active_count, weights)
        fused_rgb: 所有合格 ROI 的加权融合 RGB 均值
        """
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

            # BGR → RGB 空间平均
            mean_rgb = np.mean(roi.reshape(-1, 3), axis=0)[::-1].copy()

            # 每个候选的权重 = 皮肤比例 × 区域权重
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

        # --- 加权融合（核心改动） ---
        # 每个候选的贡献权重 = max(0, skin_ratio) * weight
        # 即使皮肤比例很低也参与融合（权重自然就低）
        total_weight = 0.0
        fused_rgb = np.zeros(3, dtype=np.float64)

        for c in candidates:
            w = max(c["skin_ratio"], 0.05) * c["weight"]
            fused_rgb += w * c["mean_rgb"]
            total_weight += w

        if total_weight > 0:
            fused_rgb /= total_weight

        # 选得分最高的 ROI 用于视频框显示
        best = max(candidates, key=lambda c: c["score"])

        # 收集权重信息
        weight_info = {c["name"]: round(c["skin_ratio"], 2)
                       for c in candidates}

        return (fused_rgb, best["rect"], best["skin_ratio"],
                len(candidates), weight_info)

    # -------------------- 自适应运动阈值 --------------------
    def compute_motion_threshold(self, roi_gray):
        """暗光下噪声更大，需要更高的运动阈值"""
        mean_brightness = float(np.mean(roi_gray))
        if mean_brightness < 50:
            return BASE_MOTION_THRESH * 1.5
        elif mean_brightness > 200:
            return BASE_MOTION_THRESH * 0.8
        return BASE_MOTION_THRESH

    # -------------------- 运动检测 --------------------
    def detect_motion(self, roi_gray):
        if self.prev_roi_gray is None:
            self.prev_roi_gray = roi_gray.copy()
            return 0.0

        h, w = roi_gray.shape[:2]
        ph, pw = self.prev_roi_gray.shape[:2]
        if h != ph or w != pw:
            self.prev_roi_gray = roi_gray.copy()
            return 0.0

        diff = cv2.absdiff(roi_gray, self.prev_roi_gray)
        motion = float(np.mean(diff))
        self.prev_roi_gray = roi_gray.copy()
        return motion

    # -------------------- 光照突变检测 --------------------
    def detect_lighting_change(self, roi_gray):
        """
        检测 ROI 整体亮度突变（开灯/关灯/遮挡）
        光照突变不暂停信号，但降低质量评分
        """
        current_brightness = float(np.mean(roi_gray))
        changed = False

        if self.prev_roi_brightness is not None:
            delta = abs(current_brightness - self.prev_roi_brightness)
            if delta > LIGHT_CHANGE_THRESH:
                changed = True
                self.light_change_detected = True
            else:
                self.light_change_detected = False

        self.prev_roi_brightness = current_brightness
        return changed

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

    # -------------------- 心率估计 --------------------
    def estimate_hr(self, pulse_signal, timestamps):
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

    # -------------------- 心率输出限制 --------------------
    def apply_hr_limits(self, raw_hr, quality, now):
        if quality < 20:
            return self.hr

        self.hr_raw_history.append(raw_hr)
        if len(self.hr_raw_history) > HR_MEDIAN_WIN * 3:
            self.hr_raw_history.pop(0)
        if len(self.hr_raw_history) >= HR_MEDIAN_WIN:
            hr_smooth = float(np.median(self.hr_raw_history[-HR_MEDIAN_WIN:]))
        else:
            hr_smooth = raw_hr

        if self.hr > 0 and self.last_hr_time > 0:
            dt = now - self.last_hr_time
            if dt > 0:
                max_delta = HR_MAX_DELTA_SEC * dt
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
            diags.append("NO_FACE")
        elif self.signal_paused and self.paused_reason == "motion":
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

        # 人脸检测
        if self.processed_frames % DETECT_INTERVAL == 1:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)
            if results.detections:
                det = results.detections[0]
                raw_bbox = det.location_data.relative_bounding_box
                smoothed = self.bbox_smoother.update(raw_bbox)
                self.last_bbox = smoothed
                self.face_confidence = det.score[0] if det.score else 0
                self.face_detected = True
            else:
                self.bbox_smoother.bbox = None
                self.last_bbox = None
                self.face_detected = False
                self.current_roi_name = "none"
                self.best_skin_ratio = 0
                self.active_roi_count = 0
                self.fusion_weights = {}
                self.prev_roi_gray = None
                self.prev_roi_brightness = None

        if self.last_bbox is not None:
            candidates = self.define_rois(frame, self.last_bbox)

            # V5 核心：多 ROI 加权融合
            result = self.extract_all_rois(frame, candidates)

            if result[0] is not None:
                fused_rgb, best_rect, best_skin, active_cnt, weights = result

                roi_rect = best_rect
                self.current_roi_name = "fused"
                self.best_roi_rect = best_rect
                self.best_skin_ratio = round(best_skin, 2)
                self.active_roi_count = active_cnt
                self.fusion_weights = weights

                # 运动检测（用得分最高的 ROI）
                best_roi = frame[best_rect[1]:best_rect[3],
                                 best_rect[0]:best_rect[2]]
                roi_gray = cv2.cvtColor(best_roi, cv2.COLOR_BGR2GRAY)

                # 自适应运动阈值
                self.motion_threshold = self.compute_motion_threshold(roi_gray)
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

                # 光照突变检测
                self.detect_lighting_change(roi_gray)

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
                                hr_raw, quality = self.estimate_hr(
                                    pulse, self.time_buffer
                                )

                                # 光照突变时降低质量
                                if self.light_change_detected:
                                    quality *= 0.5

                                if hr_raw > 0:
                                    new_hr = self.apply_hr_limits(
                                        hr_raw, quality, now
                                    )
                                    self.hr = new_hr
                                    self.signal_quality = quality

                                    self.hr_output_history.append(
                                        round(new_hr, 1)
                                    )
                                    if len(self.hr_output_history) > 120:
                                        self.hr_output_history.pop(0)

                                    # CSV 记录
                                    self.logger.log(
                                        new_hr, quality, "fused",
                                        best_skin, self.motion_score,
                                        self.fps
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
        cv2.rectangle(overlay, (0, 0), (w, 68), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        # ROI 框
        if roi_rect:
            x1, y1, x2, y2 = roi_rect
            if self.signal_paused:
                box_color = (0, 80, 255)
                label = "FUSED [MOTION]"
            elif self.light_change_detected:
                box_color = (0, 180, 255)
                label = f"FUSED [LIGHT] skin:{self.best_skin_ratio:.0%}"
            else:
                box_color = (0, 230, 118)
                label = (f"FUSED x{self.active_roi_count} "
                         f"skin:{self.best_skin_ratio:.0%} "
                         f"thresh:{self.motion_threshold:.0f}")
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
            elif self.signal_quality >= 20:
                hr_color = (0, 180, 100)
            else:
                hr_color = (0, 130, 80)
        else:
            hr_str = "-- BPM"
            hr_color = (0, 100, 70)

        cv2.putText(frame, hr_str, (16, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, hr_color, 2)

        # 状态
        if self.face_detected:
            line1 = (f"Q:{self.signal_quality:.0f}% "
                     f"motion:{self.motion_score:.1f}/{self.motion_threshold:.0f} "
                     f"ROIs:{self.active_roi_count}")
            cv2.putText(frame, line1, (16, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 200, 100), 1)

            # 融合权重（第二行右侧）
            if self.fusion_weights:
                w_str = " ".join(
                    f"{k[:3]}:{v:.0%}" for k, v in self.fusion_weights.items()
                )
                cv2.putText(frame, w_str, (w - len(w_str) * 6 - 10, 56),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (80, 80, 80), 1)
        else:
            cv2.putText(frame, "NO FACE DETECTED", (16, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 80, 255), 1)

        # FPS
        fps_str = f"{self.fps:.0f}fps buf:{len(self.rgb_buffer)}/{BUFFER_SIZE}"
        cv2.putText(frame, fps_str, (w - 180, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (80, 80, 80), 1)

        # 底部进度条
        buf_pct = len(self.rgb_buffer) / BUFFER_SIZE if BUFFER_SIZE else 0
        bar_color = (0, 230, 118) if buf_pct >= 0.8 else \
                    (0, 130, 70) if not self.signal_paused else (0, 80, 200)
        cv2.rectangle(frame, (0, h - 3), (int(w * buf_pct), h),
                      bar_color, -1)

        return frame


# ============================================================
#  Flask 路由
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
            'active_rois': processor.active_roi_count,
            'fusion_weights': processor.fusion_weights,
            'diagnostics': processor.get_diagnostics(),
        })


if __name__ == '__main__':
    try:
        print("=" * 58)
        print("  rPPG Monitor V5 (Multi-ROI Fusion)")
        print("  ROI: 4 candidates → weighted fusion (no switching)")
        print("  Motion: adaptive threshold + lighting change detect")
        print("  Log: auto-save to rppg_log.csv")
        print("-" * 58)
        print("  http://localhost:5000")
        print("=" * 58)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭...")
    finally:
        processor.stop()
