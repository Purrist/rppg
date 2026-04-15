"""
rPPG 心率监测 V3 (精准稳定版)

针对 V1 的三个核心问题逐个修复:
  1. 心率跳动: Butterworth带通 + 中值平滑 + 变化速度限制(±15BPM/s)
  2. 人脸不稳: MediaPipe远距离模型 + bbox指数平滑
  3. ROI不准:  缩小到前额核心区域 + 面积合法性检查
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
CAMERA_ID         = 0
POS_WINDOW        = 48       # POS 滑动窗口（帧）
BUFFER_SIZE       = 180      # 总缓冲区 ~6秒（比V1的300帧响应更快）
HR_MIN_FREQ       = 0.75     # 45 BPM
HR_MAX_FREQ       = 3.0      # 180 BPM
BW_ORDER          = 3        # Butterworth 阶数
BW_LOW            = 0.7      # 带通下限 Hz
BW_HIGH           = 3.5      # 带通上限 Hz
MEDIAN_KERNEL     = 5        # 中值滤波核（去脉冲噪声）
HR_MEDIAN_WIN     = 5        # 心率中值平滑窗口
HR_MAX_DELTA_SEC  = 15       # 心率每秒最大变化量 BPM
DETECT_INTERVAL   = 2        # 每 2 帧检测一次人脸（V1是3，更频繁）
COMPUTE_INTERVAL  = 4        # 每 4 帧计算一次心率
MIN_BUFFER_COMPUTE = POS_WINDOW * 3  # 144 帧后开始计算
MIN_ROI_PIXELS    = 500      # ROI 最小像素数


# ============================================================
#  BBox 平滑器
# ============================================================
class BBoxSmoother:
    """对 MediaPipe 检测结果做指数移动平均，消除帧间抖动"""
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
#  rPPG 处理器
# ============================================================
class RPPGProcessor:

    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.cap = None
        self.face_detector = None
        self.bbox_smoother = BBoxSmoother(alpha=0.4)

        # 缓冲区
        self.rgb_buffer = []
        self.time_buffer = []
        self.hr_raw_history = []      # 原始心率（中值平滑前）
        self.hr_output_history = []   # 平滑后心率（给前端）
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
        self.roi_info = ""
        self.actual_fs = 0.0
        self.last_hr_time = 0.0       # 变化速度限制用

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

        # V1 用 model_selection=0 (近距0-2m)，改为 1 (远距0.5-5m)
        # 桌面场景人离摄像头通常 40-100cm，远距模型覆盖更稳
        self.face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.4,  # V1是0.5，稍微降低避免漏检
        )

        print(f"[OK] 摄像头 {self.camera_id} 已打开")
        print(f"[OK] MediaPipe 远距离人脸模型 (0.5-5m)")
        print(f"[OK] Butterworth {BW_LOW}-{BW_HIGH}Hz order={BW_ORDER}")

    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()

    # -------------------- ROI --------------------
    def get_forehead_roi(self, frame, bbox):
        """
        前额核心区域提取
        V1: 高度 15%-45%, 宽度 20%-80%  → 太大，容易包含头发和眉骨
        V3: 高度 20%-40%, 宽度 30%-70%  → 只取最纯净的前额中心
        """
        h, w = frame.shape[:2]
        x_min = int(bbox.xmin * w)
        y_min = int(bbox.ymin * h)
        bw = int(bbox.width * w)
        bh = int(bbox.height * h)

        fy1 = y_min + int(bh * 0.20)
        fy2 = y_min + int(bh * 0.40)
        fx1 = x_min + int(bw * 0.30)
        fx2 = x_min + int(bw * 0.70)

        fy1, fy2 = max(0, fy1), min(h, fy2)
        fx1, fx2 = max(0, fx1), min(w, fx2)

        if fy2 <= fy1 or fx2 <= fx1:
            return None, None

        roi = frame[fy1:fy2, fx1:fx2]
        roi_pixels = roi.shape[0] * roi.shape[1]
        self.roi_info = f"{roi.shape[1]}x{roi.shape[0]}"

        # 面积太小说明检测框不准，丢弃
        if roi_pixels < MIN_ROI_PIXELS:
            return None, None

        return roi, (fx1, fy1, fx2, fy2)

    # -------------------- POS 投影 --------------------
    def pos_extract(self, rgb_signals):
        """POS 正交投影（算法不变，这个是正确的）"""
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
        """中值滤波：去除光照突变等脉冲型噪声"""
        if len(signal) < kernel:
            return signal
        half = kernel // 2
        padded = np.pad(signal, half, mode='edge')
        out = np.empty_like(signal)
        for i in range(len(signal)):
            out[i] = np.median(padded[i:i + kernel])
        return out

    def detrend(self, signal):
        """去均值 + 去线性漂移"""
        signal = signal - np.mean(signal)
        if len(signal) < 3:
            return signal
        x = np.arange(len(signal), dtype=np.float64)
        coeffs = np.polyfit(x, signal, 1)
        return signal - np.polyval(coeffs, x)

    def butter_bandpass(self, signal, fs):
        """零相位 Butterworth 带通（V1 完全没有这一步！）"""
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
        """
        完整管线（V1 只有 Hanning+FFT，缺了前三步！）:
        中值去噪 → 去趋势 → Butterworth带通 → Hanning窗 → FFT → 找峰
        """
        if pulse_signal is None:
            return 0.0, 0.0
        n = len(pulse_signal)
        if n < POS_WINDOW * 2:
            return 0.0, 0.0

        # 实际采样率
        valid_ts = timestamps[-n:]
        dt = np.median(np.diff(valid_ts))
        if dt <= 0.005 or dt > 0.15:
            return 0.0, 0.0
        fs = 1.0 / dt
        self.actual_fs = fs

        signal = pulse_signal.copy()

        # 第1步：中值去噪
        signal = self.median_filter(signal, MEDIAN_KERNEL)

        # 第2步：去趋势
        signal = self.detrend(signal)

        # 第3步：Butterworth 带通（关键！V1 缺失）
        signal = self.butter_bandpass(signal, fs)

        if np.std(signal) < 1e-8:
            return 0.0, 0.0

        # 第4步：Hanning 窗 + FFT
        windowed = signal * np.hanning(n)
        fft_result = np.fft.rfft(windowed)
        freqs = np.fft.rfftfreq(n, d=dt)
        magnitudes = np.abs(fft_result)

        # 第5步：心率范围找主峰
        mask = (freqs >= HR_MIN_FREQ) & (freqs <= HR_MAX_FREQ)
        if not np.any(mask):
            return 0.0, 0.0

        hr_mags = magnitudes[mask]
        hr_freqs = freqs[mask]
        peak_idx = np.argmax(hr_mags)
        peak_mag = hr_mags[peak_idx]
        peak_freq = hr_freqs[peak_idx]

        # SNR 信号质量
        quality = np.clip((peak_mag / (np.mean(hr_mags) + 1e-10)) * 12, 0, 100)

        hr_bpm = peak_freq * 60.0
        if hr_bpm < 45 or hr_bpm > 180:
            quality *= 0.1
            hr_bpm = 0.0

        return hr_bpm, quality

    # -------------------- 心率输出限制（V1 完全没有！）--------------------
    def apply_hr_limits(self, raw_hr, quality, now):
        """
        三重保护防止心率跳变:
        1. 质量太低 → 不更新
        2. 中值平滑 → 去掉离群值
        3. 变化速度限制 → 每秒最多 ±15 BPM
        """
        # 保护1：质量太低不更新，保持上次的好值
        if quality < 20:
            return self.hr

        # 保护2：中值平滑
        self.hr_raw_history.append(raw_hr)
        if len(self.hr_raw_history) > HR_MEDIAN_WIN * 3:
            self.hr_raw_history.pop(0)
        if len(self.hr_raw_history) >= HR_MEDIAN_WIN:
            hr_smooth = float(np.median(self.hr_raw_history[-HR_MEDIAN_WIN:]))
        else:
            hr_smooth = raw_hr

        # 保护3：变化速度限制
        if self.hr > 0 and self.last_hr_time > 0:
            dt = now - self.last_hr_time
            if dt > 0:
                max_delta = HR_MAX_DELTA_SEC * dt
                delta = hr_smooth - self.hr
                if abs(delta) > max_delta:
                    # 限幅而不是拒绝，避免长时间不更新
                    hr_smooth = self.hr + np.sign(delta) * max_delta

        if hr_smooth < 45 or hr_smooth > 180:
            return self.hr

        self.last_hr_time = now
        return hr_smooth

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
        self.roi_info = ""

        # 人脸检测（每2帧，比V1的每3帧更频繁）
        if self.processed_frames % DETECT_INTERVAL == 1:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)
            if results.detections:
                det = results.detections[0]
                raw_bbox = det.location_data.relative_bounding_box
                # 关键改进：bbox 平滑，消除检测抖动
                smoothed = self.bbox_smoother.update(raw_bbox)
                self.last_bbox = smoothed
                self.face_confidence = det.score[0] if det.score else 0
                self.face_detected = True
            else:
                self.bbox_smoother.bbox = None
                self.last_bbox = None
                self.face_detected = False

        roi_rect = None

        if self.last_bbox is not None:
            roi, rect = self.get_forehead_roi(frame, self.last_bbox)
            if roi is not None and roi.size > 100:
                roi_rect = rect
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
                                # 关键改进：三重限制，不会跳变
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

                            # 波形（用处理后的干净信号）
                            if len(pulse) > 48:
                                p = pulse[-128:].copy()
                                p = self.median_filter(p, 3)
                                p = self.detrend(p)
                                ps = np.std(p)
                                if ps > 1e-8:
                                    p = p / ps
                                self.pulse_history = p.tolist()

        return frame, roi_rect

    # -------------------- HUD --------------------
    def draw_hud(self, frame, roi_rect):
        h, w = frame.shape[:2]

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 54), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        if roi_rect:
            x1, y1, x2, y2 = roi_rect
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 230, 118), 2)
            cv2.putText(frame, "Forehead ROI", (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 230, 118), 1)

        # 心率（颜色随质量变化）
        if self.hr > 0:
            hr_str = f"{self.hr:.0f} BPM"
            if self.signal_quality >= 30:
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

        # 状态信息（两行）
        if self.face_detected:
            line1 = (f"FACE | Q:{self.signal_quality:.0f}% | "
                     f"{self.fps:.0f}fps | ROI:{self.roi_info}")
            cv2.putText(frame, line1, (240, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 200, 100), 1)
            line2 = (f"fs:{self.actual_fs:.1f}Hz | "
                     f"buf:{len(self.rgb_buffer)}/{BUFFER_SIZE}")
            cv2.putText(frame, line2, (240, 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 140, 80), 1)
        else:
            cv2.putText(frame, "NO FACE DETECTED", (240, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 80, 255), 1)

        # 底部缓冲区进度条
        buf_pct = len(self.rgb_buffer) / BUFFER_SIZE if BUFFER_SIZE else 0
        bar_color = (0, 230, 118) if buf_pct >= 0.8 else (0, 130, 70)
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
    """MJPEG 视频流（带异常保护，不会断流）"""
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
                           if processor.pulse_history else []
        })


if __name__ == '__main__':
    try:
        print("=" * 58)
        print("  rPPG Monitor V3 (Stable & Accurate)")
        print("  Fix: HR jump / Face unstable / ROI inaccurate")
        print("  Pipeline: POS->Median->Detrend->BW->FFT->Limit")
        print("-" * 58)
        print("  http://localhost:5000")
        print("=" * 58)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭...")
    finally:
        processor.stop()
