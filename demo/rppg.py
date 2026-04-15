"""
rPPG 心率监测 V4.1 (修复 ROI 检测失败)

修复:
  1. select_best_roi 不再用硬门槛，永远返回最佳候选
  2. estimate_hr 频率掩码上限条件修复
  3. HSV 皮肤检测改为质量参考而非通行证
  4. 摄像头锁定更保守（不强制关闭自动曝光）
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file
from scipy.signal import butter, filtfilt
import mediapipe as mp
import threading
import time
import os

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
MOTION_THRESHOLD   = 12.0
MOTION_PATIENCE    = 8


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
#  rPPG 处理器 V4.1
# ============================================================
class RPPGProcessor:

    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.cap = None
        self.face_detector = None
        self.bbox_smoother = BBoxSmoother(alpha=0.4)

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

        # V4 状态
        self.current_roi_name = "none"
        self.current_roi_rect = None
        self.best_skin_ratio = 0.0
        self.prev_roi_gray = None
        self.motion_score = 0.0
        self.motion_frames = 0
        self.signal_paused = False
        self.paused_reason = ""

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

        # [FIX] 不再强制锁定曝光，很多摄像头手动模式会导致画面全黑
        # 只设置缓冲区大小，让摄像头自己管理曝光
        print("[OK] 摄像头参数: 自动曝光（不锁定，避免画面过暗）")

        self.face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.4,
        )

        print(f"[OK] 摄像头 {self.camera_id} 已打开")
        print(f"[OK] MediaPipe 远距离人脸模型 (0.5-5m)")
        print(f"[OK] Butterworth {BW_LOW}-{BW_HIGH}Hz order={BW_ORDER}")

    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()

    # -------------------- 多 ROI 定义 --------------------
    def define_rois(self, frame, bbox):
        h, w = frame.shape[:2]
        x_min = int(bbox.xmin * w)
        y_min = int(bbox.ymin * h)
        bw = int(bbox.width * w)
        bh = int(bbox.height * h)

        rois = []

        # ROI 1: 前额宽区（覆盖面大，容错高）
        rois.append({
            "name": "forehead_wide",
            "rect": (
                x_min + int(bw * 0.15),
                y_min + int(bh * 0.12),
                x_min + int(bw * 0.85),
                y_min + int(bh * 0.42),
            ),
            "weight": 1.2,
        })

        # ROI 2: 前额窄区（核心区域）
        rois.append({
            "name": "forehead_core",
            "rect": (
                x_min + int(bw * 0.25),
                y_min + int(bh * 0.18),
                x_min + int(bw * 0.75),
                y_min + int(bh * 0.38),
            ),
            "weight": 1.5,
        })

        # ROI 3: 左脸颊
        rois.append({
            "name": "left_cheek",
            "rect": (
                x_min + int(bw * 0.10),
                y_min + int(bh * 0.45),
                x_min + int(bw * 0.40),
                y_min + int(bh * 0.72),
            ),
            "weight": 0.8,
        })

        # ROI 4: 右脸颊
        rois.append({
            "name": "right_cheek",
            "rect": (
                x_min + int(bw * 0.60),
                y_min + int(bh * 0.45),
                x_min + int(bw * 0.90),
                y_min + int(bh * 0.72),
            ),
            "weight": 0.8,
        })

        return rois

    # -------------------- HSV 皮肤检测 --------------------
    def compute_skin_ratio(self, roi_bgr):
        """用 HSV 检测皮肤像素占比"""
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        # [FIX] 放宽 H 范围到 0-30（原来 0-25 太窄）
        # S 下限降到 15（原来 20）
        # V 下限降到 40（原来 50）
        lower = np.array([0, 15, 40])
        upper = np.array([30, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        return np.sum(mask > 0) / mask.size

    # -------------------- [FIX] 选择最佳 ROI --------------------
    def select_best_roi(self, frame, rois):
        """
        从候选 ROI 中选最佳区域
        V4 bug: 用了硬门槛 skin_ratio >= 0.55，没通过就返回 None
        V4.1 fix: 永远返回最佳候选，皮肤比例仅作为质量参考
        """
        h, w = frame.shape[:2]
        candidates = []

        for roi_info in rois:
            name = roi_info["name"]
            x1, y1, x2, y2 = roi_info["rect"]
            weight = roi_info["weight"]

            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            roi = frame[y1:y2, x1:x2]
            pixels = roi.shape[0] * roi.shape[1]

            if pixels < MIN_ROI_PIXELS:
                continue

            skin_ratio = self.compute_skin_ratio(roi)
            score = skin_ratio * weight

            candidates.append({
                "name": name,
                "rect": (x1, y1, x2, y2),
                "roi": roi,
                "skin_ratio": skin_ratio,
                "score": score,
                "pixels": pixels,
            })

        if not candidates:
            return None

        # [FIX] 关键改动：按评分排序，永远返回最佳候选
        # 不再用硬门槛拒绝
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[0]

    # -------------------- 运动检测 --------------------
    def detect_motion(self, roi_gray):
        if self.prev_roi_gray is None:
            self.prev_roi_gray = roi_gray
            return 0.0

        h, w = roi_gray.shape[:2]
        ph, pw = self.prev_roi_gray.shape[:2]
        if h != ph or w != pw:
            self.prev_roi_gray = roi_gray
            return 0.0

        diff = cv2.absdiff(roi_gray, self.prev_roi_gray)
        motion = float(np.mean(diff))
        self.prev_roi_gray = roi_gray
        return motion

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

    # -------------------- [FIX] 心率估计 --------------------
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

        # [FIX] 原来的 bug: (freqs >= HR_MIN_FREQ) 写了两遍
        # 修复为正确的下限+上限
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
            diags.append("MOTION_DETECTED")
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
                self.prev_roi_gray = None

        if self.last_bbox is not None:
            candidates = self.define_rois(frame, self.last_bbox)
            best = self.select_best_roi(frame, candidates)

            if best is not None:
                roi_rect = best["rect"]
                self.current_roi_name = best["name"]
                self.best_skin_ratio = round(best["skin_ratio"], 2)
                roi = best["roi"]
                roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

                self.motion_score = self.detect_motion(roi_gray)
                if self.motion_score > MOTION_THRESHOLD:
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
                    mean_rgb = np.mean(roi.reshape(-1, 3), axis=0)[::-1].copy()

                    with self.lock:
                        self.rgb_buffer.append(mean_rgb)
                        self.time_buffer.append(now)

                        if len(self.rgb_buffer) > BUFFER_SIZE:
                            self.rgb_buffer.pop(0)
                            self.time_buffer.pop(0)

                        if (len(self.rgb_buffer) >= MIN_BUFFER_COMPUTE and
                                self.processed_frames % COMPUTE_INTERVAL == 0):

                            pulse = self.pos_extract(np.array(self.rgb_buffer))

                            if pulse is not None and len(pulse) > POS_WINDOW * 2:
                                hr_raw, quality = self.estimate_hr(
                                    pulse, self.time_buffer
                                )

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

        return frame, roi_rect

    # -------------------- HUD --------------------
    def draw_hud(self, frame, roi_rect):
        h, w = frame.shape[:2]

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 68), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        if roi_rect:
            x1, y1, x2, y2 = roi_rect
            if self.signal_paused:
                box_color = (0, 80, 255)
                label = f"{self.current_roi_name} [MOTION]"
            else:
                box_color = (0, 230, 118)
                label = f"{self.current_roi_name} skin:{self.best_skin_ratio:.0%}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(frame, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, box_color, 1)

        if self.hr > 0:
            hr_str = f"{self.hr:.0f} BPM"
            if self.signal_paused:
                hr_color = (0, 80, 255)
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

        if self.face_detected:
            line1 = (f"ROI:{self.current_roi_name} "
                     f"skin:{self.best_skin_ratio:.0%} "
                     f"Q:{self.signal_quality:.0f}% "
                     f"motion:{self.motion_score:.1f}")
            cv2.putText(frame, line1, (16, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 200, 100), 1)
        else:
            cv2.putText(frame, "NO FACE DETECTED", (16, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 80, 255), 1)

        fps_str = f"{self.fps:.0f}fps buf:{len(self.rgb_buffer)}/{BUFFER_SIZE}"
        cv2.putText(frame, fps_str, (w - 180, 56),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (80, 80, 80), 1)

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
            'motion_paused': processor.signal_paused,
            'diagnostics': processor.get_diagnostics(),
        })


if __name__ == '__main__':
    try:
        print("=" * 58)
        print("  rPPG Monitor V4.1 (ROI Fix + Freq Mask Fix)")
        print("  Fix: select_best_roi always returns best candidate")
        print("  Fix: FFT freq mask upper bound restored")
        print("-" * 58)
        print("  http://localhost:5000")
        print("=" * 58)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭...")
    finally:
        processor.stop()
