"""
rPPG 远程光电容积描记法 - 心率监测系统
算法: POS (Plane-Orthogonal-to-Skin), Wang et al. 2015
从摄像头视频流中通过分析皮肤颜色微小变化来无接触测量心率
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file
import mediapipe as mp
import threading
import time
import os

app = Flask(__name__)


# ============================================================
#  POS rPPG 核心处理器
# ============================================================
class RPPGProcessor:
    """
    基于 POS 算法的 rPPG 心率估计器

    原理:
    1. 从面部前额 ROI 提取每帧的 RGB 空间均值时间序列
    2. 使用 POS 正交投影将 RGB 信号投影到脉搏信号方向
    3. 对脉搏信号做 FFT, 在 0.75-3.0 Hz (45-180 BPM) 范围内找主峰
    4. 主峰频率 × 60 = 心率 (BPM)
    """

    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.cap = None
        self.face_detector = None

        # --- 算法参数 ---
        self.pos_window = 48          # POS 窗口大小（帧），约 1.6 秒 @30fps
        self.buffer_size = 300        # 总信号缓冲区，约 10 秒
        self.hr_min_freq = 0.75       # 45 BPM
        self.hr_max_freq = 3.0        # 180 BPM
        self.detect_interval = 3      # 每 N 帧做一次人脸检测（降低开销）

        # --- 数据缓冲区 ---
        self.rgb_buffer = []          # [[R,G,B], ...]
        self.time_buffer = []         # [timestamp, ...]
        self.hr_history = []          # 心率历史，用于趋势图
        self.pulse_history = []       # 脉搏波形历史，用于波形显示

        # --- 状态 ---
        self.hr = 0.0
        self.signal_quality = 0.0
        self.face_detected = False
        self.face_confidence = 0.0
        self.fps = 0.0
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.processed_frames = 0
        self.last_bbox = None         # 缓存上一次的人脸框

        self.lock = threading.Lock()
        self.running = True

    def start(self):
        """初始化摄像头和 MediaPipe 人脸检测器"""
        self.cap = cv2.VideoCapture(self.camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开摄像头 {self.camera_id}，请检查连接")

        # MediaPipe 短距离人脸检测模型（适用于 <2m）
        self.face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=0.5
        )
        print(f"[OK] 摄像头 {self.camera_id} 已打开")
        print(f"[OK] MediaPipe FaceDetection 已加载")

    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()

    # -------------------- ROI 提取 --------------------
    def get_forehead_roi(self, frame, bbox):
        """
        从面部 bounding box 中提取前额 ROI
        前额区域血管丰富，且受表情/说话运动影响较小
        """
        h, w = frame.shape[:2]

        x_min = int(bbox.xmin * w)
        y_min = int(bbox.ymin * h)
        bw = int(bbox.width * w)
        bh = int(bbox.height * h)

        # 前额：面部上方 15%~45%，水平居中 20%~80%
        fy1 = y_min + int(bh * 0.15)
        fy2 = y_min + int(bh * 0.45)
        fx1 = x_min + int(bw * 0.2)
        fx2 = x_min + int(bw * 0.8)

        # 边界安全钳位
        fy1 = max(0, fy1)
        fy2 = min(h, fy2)
        fx1 = max(0, fx1)
        fx2 = min(w, fx2)

        if fy2 <= fy1 or fx2 <= fx1:
            return None, None

        roi = frame[fy1:fy2, fx1:fx2]
        return roi, (fx1, fy1, fx2, fy2)

    # -------------------- POS 算法 --------------------
    def pos_extract(self, rgb_signals):
        """
        POS (Plane-Orthogonal-to-Skin) 信号提取

        参考: Wang et al., "A Robust Algorithm for Extracting
              Remote PPG Signal", IEEE TBIOM 2015

        步骤:
        1. 对滑动窗口内的 RGB 序列去均值（去除直流分量）
        2. 投影到两个预定义正交方向:
           h1 = [1, -1, 0]^T / sqrt(2)   捕获 R-B 差异
           h2 = [1, 1, -2]^T / sqrt(6)   捕获 (R+G-2B) 差异
        3. 自适应加权组合: h = p1 + (σ1/σ2) * p2
           标准差比作为权重，自适应选择最佳投影方向

        参数:
            rgb_signals: np.array shape (T, 3), RGB 均值序列
        返回:
            pulse: np.array, 脉搏信号（长度 T - N + 1）
        """
        N = self.pos_window
        T = len(rgb_signals)

        if T < N:
            return None

        rgb = np.array(rgb_signals, dtype=np.float64)  # (T, 3)

        # 预定义正交投影向量
        h1 = np.array([1.0, -1.0, 0.0]) / np.sqrt(2.0)
        h2 = np.array([1.0, 1.0, -2.0]) / np.sqrt(6.0)

        pulse = np.zeros(T - N + 1)

        for i in range(T - N + 1):
            window = rgb[i:i + N]                    # (N, 3)
            mean_rgb = np.mean(window, axis=0)        # 窗口均值（去直流）
            centered = window - mean_rgb              # 中心化

            p1 = centered @ h1                        # (N,)
            p2 = centered @ h2                        # (N,)

            sigma1 = np.std(p1)
            sigma2 = np.std(p2)

            # 自适应加权：标准差比决定两个分量的贡献
            if sigma2 > 1e-8:
                alpha = sigma1 / sigma2
                pulse[i] = p1[-1] + alpha * p2[-1]
            else:
                pulse[i] = p1[-1]

        return pulse

    # -------------------- FFT 心率估计 --------------------
    def estimate_hr_fft(self, pulse_signal, timestamps):
        """
        通过 FFT 频谱分析估计心率

        步骤:
        1. 去趋势（去均值 + 去线性漂移）
        2. 加汉宁窗减少频谱泄漏
        3. FFT 变换到频域
        4. 在 [0.75, 3.0] Hz 范围内找最大谱线
        5. 主峰频率 × 60 = 心率 BPM

        返回:
            hr_bpm: 心率值（BPM）
            quality: 信号质量 0-100
        """
        if pulse_signal is None:
            return 0.0, 0.0

        n = len(pulse_signal)
        if n < 48:
            return 0.0, 0.0

        # 从时间戳计算实际采样率
        valid_ts = timestamps[-n:]
        dt_arr = np.diff(valid_ts)
        dt = np.median(dt_arr)
        if dt <= 0.005 or dt > 0.15:
            return 0.0, 0.0
        fs = 1.0 / dt

        # 去趋势
        signal = pulse_signal.copy()
        signal = signal - np.mean(signal)
        x = np.arange(n, dtype=np.float64)
        coeffs = np.polyfit(x, signal, 1)
        signal = signal - np.polyval(coeffs, x)

        # 汉宁窗
        window = np.hanning(n)
        windowed = signal * window

        # FFT
        fft_result = np.fft.rfft(windowed)
        freqs = np.fft.rfftfreq(n, d=dt)
        magnitudes = np.abs(fft_result)

        # 心率频率范围掩码
        mask = (freqs >= self.hr_min_freq) & (freqs <= self.hr_max_freq)
        if not np.any(mask):
            return 0.0, 0.0

        hr_freqs = freqs[mask]
        hr_mags = magnitudes[mask]

        # 找主峰
        peak_idx = np.argmax(hr_mags)
        peak_freq = hr_freqs[peak_idx]
        peak_mag = hr_mags[peak_idx]

        # 信号质量 = 主峰突出度（峰值 / 平均幅度）
        avg_mag = np.mean(hr_mags) + 1e-10
        snr = peak_mag / avg_mag
        quality = np.clip(snr * 12, 0, 100)

        hr_bpm = peak_freq * 60.0

        # 合理性检查
        if hr_bpm < 45 or hr_bpm > 180:
            quality *= 0.2

        return hr_bpm, quality

    # -------------------- 单帧处理 --------------------
    def process_frame(self, frame):
        """处理单帧：人脸检测 -> ROI 提取 -> 信号累积 -> 心率计算"""
        now = time.time()

        # FPS 统计
        self.frame_count += 1
        elapsed = now - self.last_fps_time
        if elapsed >= 1.0:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.last_fps_time = now

        self.processed_frames += 1

        # 每隔 detect_interval 帧做一次人脸检测
        if self.processed_frames % self.detect_interval == 1:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_detector.process(rgb_frame)

            if results.detections:
                det = results.detections[0]
                self.last_bbox = det.location_data.relative_bounding_box
                self.face_confidence = det.score[0] if det.score else 0
                self.face_detected = True
            else:
                self.last_bbox = None
                self.face_detected = False

        roi_rect = None

        # 使用缓存的人脸框提取 ROI
        if self.last_bbox is not None:
            roi, rect = self.get_forehead_roi(frame, self.last_bbox)
            if roi is not None and roi.size > 100:
                roi_rect = rect

                # 计算 ROI 空间平均颜色，BGR -> RGB
                mean_bgr = np.mean(roi.reshape(-1, 3), axis=0)
                mean_rgb = mean_bgr[::-1].copy()

                with self.lock:
                    self.rgb_buffer.append(mean_rgb)
                    self.time_buffer.append(now)

                    if len(self.rgb_buffer) > self.buffer_size:
                        self.rgb_buffer.pop(0)
                        self.time_buffer.pop(0)

                    # 每 6 帧计算一次心率（平衡精度和性能）
                    needed = self.pos_window * 4
                    if len(self.rgb_buffer) >= needed and \
                       len(self.rgb_buffer) % 6 == 0:

                        rgb_array = np.array(self.rgb_buffer)
                        pulse = self.pos_extract(rgb_array)

                        if pulse is not None and len(pulse) > 48:
                            hr, quality = self.estimate_hr_fft(
                                pulse, self.time_buffer
                            )

                            if hr > 0:
                                # 指数移动平均平滑心率
                                alpha = 0.25 if quality > 35 else 0.08
                                if self.hr > 0:
                                    self.hr = alpha * hr + (1 - alpha) * self.hr
                                else:
                                    self.hr = hr
                                self.signal_quality = quality

                            # 归一化脉搏波形用于前端显示
                            p_display = pulse[-128:]
                            p_display = p_display - np.mean(p_display)
                            p_std = np.std(p_display)
                            if p_std > 1e-8:
                                p_display = p_display / p_std
                            self.pulse_history = p_display.tolist()

                    # 心率历史（用于趋势图）
                    if self.hr > 0 and len(self.rgb_buffer) % 10 == 0:
                        self.hr_history.append(round(self.hr, 1))
                        if len(self.hr_history) > 120:
                            self.hr_history.pop(0)

        return frame, roi_rect

    # -------------------- HUD 绘制 --------------------
    def draw_hud(self, frame, roi_rect):
        """在视频帧上绘制 HUD 信息叠加层"""
        h, w = frame.shape[:2]

        # 顶部半透明信息条
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 54), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        # ROI 框
        if roi_rect:
            x1, y1, x2, y2 = roi_rect
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 230, 118), 2)
            cv2.putText(frame, "Forehead ROI", (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 230, 118), 1)

        # 心率数字
        hr_str = f"{self.hr:.0f} BPM" if self.hr > 0 else "-- BPM"
        hr_color = (0, 230, 118) if self.signal_quality > 30 else (0, 180, 100)
        cv2.putText(frame, hr_str, (16, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, hr_color, 2)

        # 状态信息
        if self.face_detected:
            status = f"FACE | Q:{self.signal_quality:.0f}% | {self.fps:.0f}fps"
            cv2.putText(frame, status, (240, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 100), 1)
        else:
            cv2.putText(frame, "NO FACE DETECTED", (240, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 80, 255), 1)

        # 算法标签
        cv2.putText(frame, "POS rPPG", (w - 120, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1)

        return frame


# ============================================================
#  Flask 路由
# ============================================================

processor = RPPGProcessor(camera_id=0)
processor.start()


@app.route('/')
def index():
    """返回 cam.html 页面"""
    html_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'cam.html'
    )
    if os.path.exists(html_path):
        return send_file(html_path)
    return ("<h1>cam.html not found</h1>"
            "<p>请将 cam.html 放在与 rppg.py 相同的目录下</p>")


@app.route('/video_feed')
def video_feed():
    """MJPEG 视频流端点"""
    def generate():
        while processor.running:
            ret, frame = processor.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame, roi_rect = processor.process_frame(frame)
            frame = processor.draw_hud(frame, roi_rect)

            ret, jpeg = cv2.imencode('.jpg', frame,
                                     [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n'
                   + jpeg.tobytes() + b'\r\n')

    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/hr')
def get_hr():
    """心率数据 JSON API"""
    with processor.lock:
        return jsonify({
            'hr': round(processor.hr, 1),
            'quality': round(processor.signal_quality, 0),
            'face': processor.face_detected,
            'confidence': round(processor.face_confidence, 2),
            'fps': round(processor.fps, 1),
            'buffer': len(processor.rgb_buffer),
            'buffer_max': processor.buffer_size,
            'hr_history': processor.hr_history[-80:],
            'pulse': processor.pulse_history[-120:] if processor.pulse_history else []
        })


# ============================================================
#  启动
# ============================================================
if __name__ == '__main__':
    try:
        print("=" * 55)
        print("  rPPG Remote Heart Rate Monitor")
        print("  Algorithm: POS (Plane-Orthogonal-to-Skin)")
        print("  ROI: Forehead region")
        print("  HR Range: 45 - 180 BPM")
        print("-" * 55)
        print("  Open browser -> http://localhost:5000")
        print("=" * 55)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断，正在关闭...")
    finally:
        processor.stop()
