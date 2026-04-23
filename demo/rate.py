# -*- coding: utf-8 -*-
import serial
import struct
import time
import threading
import os
import csv
from datetime import datetime
from collections import deque
from flask import Flask, Response, jsonify, render_template_string, request
import cv2
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks
import mediapipe as mp

# ================================================================
# ===================== 全局配置与依赖 ============================
# ================================================================
PORT = "COM9"
BAUD = 115200

# 雷达配置
RADAR_SMOOTH_WINDOW = 4
RADAR_HUMAN_THRESHOLD = 1.0
RADAR_RT_MAX = 120
RADAR_LT_MAX = 3600
RADAR_SAMPLE_INTERVAL = 0.5

# rPPG 配置
CAMERA_ID_DEFAULT = 0
POS_WINDOW = 48
BUFFER_SIZE = 300
HR_MIN_FREQ = 0.85
HR_MAX_FREQ = 2.8
BW_ORDER = 3
BW_LOW = 0.85
BW_HIGH = 2.8
MEDIAN_KERNEL = 5
HR_MEDIAN_WIN = 7
HR_MAX_DELTA_SEC = 10
EMA_ALPHA_BASE = 0.06
MAX_DISPLAY_CHANGE_BASE = 10
DETECT_INTERVAL = 3
COMPUTE_INTERVAL = 8
MIN_BUFFER_COMPUTE = POS_WINDOW * 3
MIN_ROI_PIXELS = 400
BASE_MOTION_THRESH = 12.0
MOTION_PATIENCE = 10
LIGHT_CHANGE_THRESH = 25.0
MOTION_HISTORY_LEN = 5
BBOX_RETAIN_FRAMES = 30
PEAK_MIN_DISTANCE = 12
DISPLAY_UPDATE_SEC = 3.0
MIN_CHEEK_RATIO = 0.28

# ================================================================
# ===================== 雷达数据处理逻辑 ==========================
# ================================================================
radar_data = {"breath": 0, "heart": 0, "distance": 0.0, "human": False, "mode": "smooth"}
radar_rt_buf = {"time": [], "breath": [], "heart": []}
radar_lt_buf = {"time": [], "breath": [], "heart": []}
radar_breath_smooth = []
radar_heart_smooth = []
last_human_time = 0.0
radar_lock = threading.Lock()

def verify_cksum(buf, cksum):
    acc = 0
    for b in buf: acc ^= b
    return (~acc & 0xFF) == cksum

def float_le(b): return struct.unpack('<f', b)[0]

def smooth_val(v, buf):
    buf.append(v)
    if len(buf) > RADAR_SMOOTH_WINDOW: buf.pop(0)
    return round(sum(buf) / len(buf))

def serial_task():
    global last_human_time
    buf = b""
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.005)
        print("✅ 雷达串口已打开")
        while True:
            if ser.in_waiting:
                buf += ser.read(ser.in_waiting)
                while len(buf) >= 8:
                    if buf[0] != 0x01: buf = buf[1:]; continue
                    dlen = (buf[3] << 8) | buf[4]
                    flen = 8 + dlen + (1 if dlen > 0 else 0)
                    if len(buf) < flen or flen > 1024: buf = buf[1:]; break
                    frame = buf[:flen]; buf = buf[flen:]
                    if not verify_cksum(frame[0:7], frame[7]): continue
                    if dlen > 0 and not verify_cksum(frame[8:8+dlen], frame[8+dlen]): continue
                    tid = (frame[5] << 8) | frame[6]
                    fd = frame[8:8+dlen]
                    mode = radar_data["mode"]
                    if tid == 0x0F09:
                        det = fd[0] == 1
                        if det: last_human_time = time.time()
                        el = time.time() - last_human_time
                        radar_data["human"] = det if mode == "raw" else (det or el < RADAR_HUMAN_THRESHOLD)
                    elif tid == 0x0A14:
                        raw = round(float_le(fd[:4]))
                        if radar_data["human"]:
                            radar_data["breath"] = smooth_val(raw, radar_breath_smooth) if mode == "smooth" and 5 <= raw <= 60 else raw
                        else:
                            radar_data["breath"] = 0; radar_breath_smooth.clear()
                    elif tid == 0x0A15:
                        raw = round(float_le(fd[:4]))
                        if radar_data["human"]:
                            radar_data["heart"] = smooth_val(raw, radar_heart_smooth) if mode == "smooth" and 30 <= raw <= 180 else raw
                        else:
                            radar_data["heart"] = 0; radar_heart_smooth.clear()
                    elif tid == 0x0A16:
                        flag = struct.unpack('<I', fd[0:4])[0]
                        radar_data["distance"] = round(float_le(fd[4:8]), 1) if flag == 1 else 0.0
                time.sleep(0.001)
    except Exception as e: print("雷达串口异常:", e)

def sampler_task():
    while True:
        time.sleep(RADAR_SAMPLE_INTERVAL)
        ts = round(time.time(), 1)
        with radar_lock:
            for store, mx in [(radar_rt_buf, RADAR_RT_MAX), (radar_lt_buf, RADAR_LT_MAX)]:
                store["time"].append(ts)
                store["breath"].append(radar_data["breath"])
                store["heart"].append(radar_data["heart"])
                if len(store["time"]) > mx:
                    store["time"].pop(0); store["breath"].pop(0); store["heart"].pop(0)

# ================================================================
# ======================= rPPG 处理逻辑 ===========================
# ================================================================
class DataLogger:
    def __init__(self, filename='rppg_log.csv'):
        self.filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        self.buffer = []; self.counter = 0; self._init_file()
    def _init_file(self):
        with open(self.filename, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['time','hr','quality','roi_name','skin_ratio','motion','fps','hr_method','hr_peak','hr_fft'])
    def log(self, hr, quality, roi_name, skin_ratio, motion, fps, method, hr_peak, hr_fft):
        self.counter += 1
        self.buffer.append([datetime.now().strftime('%H:%M:%S'), round(hr,1), round(quality,0), roi_name, round(skin_ratio,3), round(motion,1), round(fps,1), method, round(hr_peak,1), round(hr_fft,1)])
        if self.counter % 10 == 0: self._flush()
    def _flush(self):
        if not self.buffer: return
        with open(self.filename, 'a', newline='', encoding='utf-8') as f: csv.writer(f).writerows(self.buffer)
        self.buffer = []

class RPPGProcessor:
    def __init__(self, camera_id=0):
        self.camera_id = camera_id; self.camera_url = None; self.cap = None; self.logger = DataLogger()
        self.rgb_buffer = []; self.time_buffer = []; self.hr_raw_history = []; self.hr_output_history = []; self.pulse_history = []
        self.hr = 0.0; self._hr_internal = 0.0; self.signal_quality = 0.0; self.face_detected = False; self.face_confidence = 0.0
        self.fps = 0.0; self.frame_count = 0; self.last_fps_time = time.time(); self.processed_frames = 0; self.actual_fs = 0.0
        self.last_hr_time = 0.0; self.last_display_update = 0.0; self.current_roi_name = "none"; self.best_skin_ratio = 0.0
        self.active_roi_count = 0; self.fusion_weights = {}; self.all_roi_rects = []; self.display_roi_rect = None
        self.prev_roi_gray = None; self.motion_history = deque(maxlen=MOTION_HISTORY_LEN); self.motion_score = 0.0
        self.motion_threshold = BASE_MOTION_THRESH; self.motion_frames = 0; self.signal_paused = False; self.paused_reason = ""
        self.prev_roi_brightness = None; self.light_change_detected = False; self.light_change_counter = 0
        self.bbox_lost_frames = 0; self.bbox_lost = False; self.last_hr_fft = 0.0; self.last_hr_peak = 0.0; self.hr_method = "--"
        self.lock = threading.Lock(); self.running = True; self.switch_lock = threading.Lock()
        self.switch_event = threading.Event(); self.switch_target = None; self.last_landmarks = None

    def _open_cap(self, src, timeout=3.0):
        start_time = time.time(); cap = cv2.VideoCapture(src)
        is_ip = isinstance(src, str) and ('http' in src or 'rtsp' in src)
        if is_ip:
            while time.time() - start_time < timeout:
                if cap.isOpened():
                    try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except: pass
                    return cap
                time.sleep(0.1)
            cap.release(); return None
        else:
            if not cap.isOpened(): return None
            try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except: pass
            return cap

    def start(self):
        self.cap = self._open_cap(self.camera_url if self.camera_url else self.camera_id)
        if self.cap is None: raise RuntimeError("无法打开摄像头")
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=False, min_detection_confidence=0.3, min_tracking_confidence=0.3)
        threading.Thread(target=self._switch_worker, daemon=True).start()

    def stop(self):
        self.running = False; self.switch_event.set()
        if self.cap and self.cap.isOpened(): self.cap.release()
        self.logger._flush()

    def _switch_worker(self):
        while self.running:
            self.switch_event.wait(); target = self.switch_target
            self.switch_target = None; self.switch_event.clear()
            if not target: continue
            src_type, src_val = target
            with self.switch_lock:
                self._reset_state()
                if self.cap and self.cap.isOpened(): self.cap.release(); self.cap = None
                if src_type == 'local': self.camera_url = None; self.camera_id = int(src_val); self.cap = self._open_cap(int(src_val))
                else: self.camera_url = str(src_val); self.camera_id = None; self.cap = self._open_cap(str(src_val))
                if self.cap is None: self.camera_url = None; self.camera_id = CAMERA_ID_DEFAULT; self.cap = self._open_cap(CAMERA_ID_DEFAULT)

    def _reset_state(self):
        for lst in [self.rgb_buffer, self.time_buffer, self.hr_raw_history, self.hr_output_history, self.pulse_history]: lst.clear()
        self.prev_roi_gray = None; self.prev_roi_brightness = None; self.last_landmarks = None
        self.all_roi_rects = []; self.display_roi_rect = None; self.best_skin_ratio = 0.0; self.active_roi_count = 0
        self.fusion_weights = {}; self.motion_history.clear(); self.motion_frames = 0; self.bbox_lost = False
        self.bbox_lost_frames = 0; self.light_change_detected = False; self.light_change_counter = 0
        self.signal_paused = False; self.paused_reason = ""; self._hr_internal = 0.0; self.hr = 0.0

    def request_switch(self, src_type, src_val): self.switch_target = (src_type, src_val); self.switch_event.set()

    def define_rois_from_mesh(self, frame, landmarks):
        h, w = frame.shape[:2]; pts = landmarks.landmark
        xs = [lm.x * w for lm in pts]; ys = [lm.y * h for lm in pts]
        face_x1, face_x2 = int(min(xs)), int(max(xs)); face_y1, face_y2 = int(min(ys)), int(max(ys))
        face_w = face_x2 - face_x1; face_h = face_y2 - face_y1; brow_y = int((pts[159].y + pts[145].y) / 2 * h); nose_x = int(pts[4].x * w)
        def safe(x1, y1, x2, y2):
            x1, y1 = max(0, x1), max(0, y1); x2, y2 = min(w, x2), min(h, y2)
            return (x1, y1, x2, y2) if (x2 > x1 and y2 > y1 and (x2-x1)*(y2-y1) >= MIN_ROI_PIXELS) else None
        rois = []
        fh = safe(face_x1 + int(face_w*0.15), face_y1 + int(face_h*0.05), face_x2 - int(face_w*0.15), brow_y - int(face_h*0.03))
        if fh: rois.append(("forehead", fh, 0.5))
        ck_y1, ck_y2 = brow_y + int(face_h*0.06), face_y2 - int(face_h*0.08)
        lw, rw = nose_x - face_x1, face_x2 - nose_x
        if lw >= face_w * MIN_CHEEK_RATIO:
            lc = safe(face_x1 + int(face_w*0.05), ck_y1, nose_x - int(face_w*0.02), ck_y2)
            if lc: rois.append(("left_cheek", lc, 1.2))
        if rw >= face_w * MIN_CHEEK_RATIO:
            rc = safe(nose_x + int(face_w*0.02), ck_y1, face_x2 - int(face_w*0.05), ck_y2)
            if rc: rois.append(("right_cheek", rc, 1.2))
        return rois

    def compute_skin_ratio(self, roi_bgr):
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([0, 15, 40]), np.array([30, 255, 255]))
        return np.sum(mask > 0) / mask.size

    def extract_fused_rgb(self, frame, roi_list):
        candidates = []; all_rects = []
        for name, rect, weight in roi_list:
            x1, y1, x2, y2 = rect; roi = frame[y1:y2, x1:x2]
            if roi.shape[0] * roi.shape[1] < MIN_ROI_PIXELS: continue
            sr = self.compute_skin_ratio(roi); mean_rgb = np.mean(roi.reshape(-1, 3), axis=0)[::-1].copy()
            candidates.append({"name": name, "rect": rect, "mean_rgb": mean_rgb, "skin_ratio": sr, "score": sr * weight, "weight": weight})
            all_rects.append((name, rect, sr))
        if not candidates: return None, None, 0.0, 0, {}, []
        total_w = 0.0; fused = np.zeros(3, dtype=np.float64)
        for c in candidates:
            wt = max(c["skin_ratio"], 0.05) * c["weight"]; fused += wt * c["mean_rgb"]; total_w += wt
        if total_w > 0: fused /= total_w
        best = max(candidates, key=lambda c: c["score"])
        return fused, best["rect"], best["skin_ratio"], len(candidates), {c["name"]: round(c["skin_ratio"], 2) for c in candidates}, all_rects

    def detect_motion(self, roi_gray):
        if self.prev_roi_gray is None or roi_gray.shape != self.prev_roi_gray.shape:
            self.prev_roi_gray = roi_gray.copy(); self.motion_history.clear(); return 0.0
        diff = cv2.absdiff(roi_gray, self.prev_roi_gray); self.prev_roi_gray = roi_gray.copy()
        self.motion_history.append(float(np.mean(diff))); return max(self.motion_history) if self.motion_history else 0.0

    def detect_lighting_change(self, roi_gray):
        cur = float(np.mean(roi_gray)); changed = False
        if self.prev_roi_brightness is not None:
            delta = abs(cur - self.prev_roi_brightness)
            if delta > LIGHT_CHANGE_THRESH: changed = True; self.light_change_detected = True; self.light_change_counter = 30; self.motion_threshold = self._base_motion_thresh(roi_gray) * 2.5
            else:
                if self.light_change_counter > 0: self.light_change_counter -= 1
                f = 1.0 + 1.5 * (self.light_change_counter / 30); self.motion_threshold = self._base_motion_thresh(roi_gray) * f
                if self.light_change_counter == 0: self.light_change_detected = False
        else: self.light_change_detected = False
        self.prev_roi_brightness = cur; return changed

    def _base_motion_thresh(self, roi_gray):
        b = float(np.mean(roi_gray))
        return BASE_MOTION_THRESH * (1.5 if b < 50 else (0.8 if b > 200 else 1.0))

    def pos_extract(self, rgb_signals):
        N, T = POS_WINDOW, len(rgb_signals)
        if T <= N: return None
        rgb = np.array(rgb_signals, dtype=np.float64)
        h1 = np.array([1.0, -1.0, 0.0]) / np.sqrt(2.0); h2 = np.array([1.0, 1.0, -2.0]) / np.sqrt(6.0)
        pulse = np.zeros(T - N + 1)
        for i in range(T - N + 1):
            window = rgb[i:i + N]; centered = window - np.mean(window, axis=0)
            p1 = centered @ h1; p2 = centered @ h2; s1, s2 = np.std(p1), np.std(p2)
            pulse[i] = p1[-1] + (s1 / s2) * p2[-1] if s2 > 1e-8 else p1[-1]
        return pulse

    def median_filter(self, signal, kernel=5):
        if len(signal) < kernel: return signal
        half = kernel // 2; padded = np.pad(signal, half, mode='edge'); out = np.empty_like(signal)
        for i in range(len(signal)): out[i] = np.median(padded[i:i + kernel])
        return out

    def detrend(self, signal):
        signal = signal - np.mean(signal)
        if len(signal) < 3: return signal
        x = np.arange(len(signal), dtype=np.float64)
        return signal - np.polyval(np.polyfit(x, signal, 1), x)

    def butter_bandpass(self, signal, fs):
        nyq = 0.5 * fs
        if nyq <= 0: return signal
        low = max(0.001, BW_LOW / nyq); high = min(0.999, BW_HIGH / nyq)
        if high <= low: return signal
        try: b, a = butter(BW_ORDER, [low, high], btype='band'); return filtfilt(b, a, signal)
        except: return signal

    def estimate_hr_fft(self, pulse, timestamps):
        if pulse is None: return 0.0, 0.0
        n = len(pulse)
        if n < POS_WINDOW * 2: return 0.0, 0.0
        valid_ts = timestamps[-n:]; dt = np.median(np.diff(valid_ts))
        if dt <= 0.005 or dt > 0.15: return 0.0, 0.0
        self.actual_fs = 1.0 / dt; fs = self.actual_fs; signal = self.median_filter(pulse.copy(), MEDIAN_KERNEL)
        signal = self.detrend(signal); signal = self.butter_bandpass(signal, fs)
        if np.std(signal) < 1e-8: return 0.0, 0.0
        windowed = signal * np.hanning(n); freqs = np.fft.rfftfreq(n, d=dt); mags = np.abs(np.fft.rfft(windowed))
        mask = (freqs >= HR_MIN_FREQ) & (freqs <= HR_MAX_FREQ)
        if not np.any(mask): return 0.0, 0.0
        hr_mags = mags[mask]; hr_freqs = freqs[mask]; peak_idx = np.argmax(hr_mags)
        if 0 < peak_idx < len(hr_freqs) - 1:
            a = np.log(hr_mags[peak_idx - 1] + 1e-10); b = np.log(hr_mags[peak_idx] + 1e-10); g = np.log(hr_mags[peak_idx + 1] + 1e-10)
            denom = a - 2 * b + g; peak_freq = hr_freqs[peak_idx - 1] + (0.5 * (a - g) / denom) * (hr_freqs[peak_idx] - hr_freqs[peak_idx - 1]) if abs(denom) > 1e-10 else hr_freqs[peak_idx]
        else: peak_freq = hr_freqs[peak_idx]
        hr_bpm = peak_freq * 60.0; quality = np.clip((hr_mags[peak_idx] / (np.mean(hr_mags) + 1e-10)) * 12, 0, 100)
        if hr_bpm < 45 or hr_bpm > 180: quality *= 0.1; hr_bpm = 0.0
        return hr_bpm, quality

    def estimate_hr_peak(self, pulse, timestamps):
        if pulse is None: return 0.0, 0.0
        n = len(pulse)
        if n < POS_WINDOW * 2: return 0.0, 0.0
        valid_ts = timestamps[-n:]; dt = np.median(np.diff(valid_ts))
        if dt <= 0.005 or dt > 0.15: return 0.0, 0.0
        signal = self.median_filter(pulse.copy(), MEDIAN_KERNEL); signal = self.detrend(signal); signal = self.butter_bandpass(signal, 1.0 / dt)
        if np.std(signal) < 1e-8: return 0.0, 0.0
        min_dist = max(PEAK_MIN_DISTANCE, int(dt * 60 / 45)); peaks, _ = find_peaks(signal, distance=min_dist, height=0)
        if len(peaks) < 3: return 0.0, 0.0
        peak_times = np.array([valid_ts[-n + p] for p in peaks]); rr = np.diff(peak_times); med_rr = np.median(rr)
        if med_rr <= 0: return 0.0, 0.0
        clean = rr[np.abs(rr - med_rr) / med_rr < 0.4]
        if len(clean) < 2: return 0.0, 0.0
        hr_bpm = 60.0 / np.median(clean); cv = np.std(clean) / (np.mean(clean) + 1e-10); quality = np.clip(100 - cv * 200, 0, 100)
        if hr_bpm < 45 or hr_bpm > 180: quality *= 0.1; hr_bpm = 0.0
        return hr_bpm, quality

    def estimate_hr_combined(self, pulse, timestamps):
        hr_fft, q_fft = self.estimate_hr_fft(pulse, timestamps); hr_peak, q_peak = self.estimate_hr_peak(pulse, timestamps)
        self.last_hr_fft = hr_fft; self.last_hr_peak = hr_peak; fv, pv = hr_fft > 0, hr_peak > 0
        if fv and pv:
            d = abs(hr_fft - hr_peak)
            if d < 8: return hr_peak * 0.6 + hr_fft * 0.4, max(q_fft, q_peak), "p60f40"
            if q_peak >= 25: return hr_peak, q_peak, "peak"
            return (hr_peak, q_peak * 0.9, "peak") if q_peak >= q_fft else (hr_fft, q_fft * 0.9, "fft")
        elif pv: return hr_peak, q_peak, "peak"
        elif fv: return hr_fft, q_fft, "fft"
        return 0.0, 0.0, "none"

    @staticmethod
    def _get_ema_alpha(quality):
        if quality >= 65: return 0.15
        if quality >= 45: return 0.10
        if quality >= 25: return EMA_ALPHA_BASE
        return 0.03

    @staticmethod
    def _get_max_display_change(quality):
        if quality >= 65: return 25
        if quality >= 45: return 15
        if quality >= 25: return MAX_DISPLAY_CHANGE_BASE
        return 5

    def apply_hr_limits(self, raw_hr, quality, now):
        if quality < 15: return self._hr_internal
        self.hr_raw_history.append(raw_hr)
        if len(self.hr_raw_history) > HR_MEDIAN_WIN * 3: self.hr_raw_history.pop(0)
        hr_med = float(np.median(self.hr_raw_history[-HR_MEDIAN_WIN:])) if len(self.hr_raw_history) >= HR_MEDIAN_WIN else raw_hr
        if self._hr_internal > 0 and self.last_hr_time > 0:
            dt_s = now - self.last_hr_time
            if dt_s > 0:
                mx = HR_MAX_DELTA_SEC * dt_s; delta = hr_med - self._hr_internal
                if abs(delta) > mx: hr_med = self._hr_internal + np.sign(delta) * mx
        if hr_med < 45 or hr_med > 180: return self._hr_internal
        alpha = self._get_ema_alpha(quality)
        self._hr_internal = alpha * hr_med + (1 - alpha) * self._hr_internal if self._hr_internal > 0 else hr_med
        self.last_hr_time = now
        return self._hr_internal

    def get_diagnostics(self):
        if not self.face_detected: return ["FACE_PARTIAL" if self.bbox_lost else "NO_FACE"]
        if self.signal_paused: return ["MOTION"]
        if self.light_change_detected: return ["LIGHT_CHANGE"]
        if self.best_skin_ratio < 0.3: return ["LOW_SKIN"]
        if self.signal_quality < 15: return ["LOW_SNR"]
        if len(self.rgb_buffer) < MIN_BUFFER_COMPUTE: return ["BUFFERING"]
        return ["OK"]

    def process_frame(self, frame):
        now = time.time(); self.frame_count += 1
        elapsed = now - self.last_fps_time
        if elapsed >= 1.0: self.fps = self.frame_count / elapsed; self.frame_count = 0; self.last_fps_time = now
        self.processed_frames += 1; rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        if self.processed_frames % DETECT_INTERVAL == 0:
            results = self.face_mesh.process(rgb_frame)
            if results.multi_face_landmarks:
                self.last_landmarks = results.multi_face_landmarks[0]; self.face_detected = True; self.face_confidence = 0.8; self.bbox_lost = False; self.bbox_lost_frames = 0
            else:
                if self.last_landmarks is not None and self.bbox_lost_frames < BBOX_RETAIN_FRAMES:
                    self.bbox_lost_frames += 1; self.bbox_lost = True; self.face_detected = True; self.face_confidence = max(0, self.face_confidence - 0.03)
                else:
                    self.last_landmarks = None; self.face_detected = False; self.bbox_lost = False; self.bbox_lost_frames = 0
                    self.all_roi_rects = []; self.display_roi_rect = None; self.current_roi_name = "none"; self.best_skin_ratio = 0
                    self.active_roi_count = 0; self.fusion_weights = {}; self.prev_roi_gray = None; self.prev_roi_brightness = None

        if self.last_landmarks is not None:
            roi_list = self.define_rois_from_mesh(frame, self.last_landmarks)
            result = self.extract_fused_rgb(frame, roi_list)
            if result[0] is not None:
                fused_rgb, best_rect, best_skin, active_cnt, weights, all_rects = result
                self.all_roi_rects = all_rects; self.display_roi_rect = best_rect; self.current_roi_name = "fused"
                self.best_skin_ratio = round(best_skin, 2); self.active_roi_count = active_cnt; self.fusion_weights = weights
                best_roi = frame[best_rect[1]:best_rect[3], best_rect[0]:best_rect[2]]
                roi_gray = cv2.cvtColor(best_roi, cv2.COLOR_BGR2GRAY)
                self.detect_lighting_change(roi_gray); self.motion_score = self.detect_motion(roi_gray)
                if self.motion_score > self.motion_threshold:
                    self.motion_frames += 1
                    if self.motion_frames >= MOTION_PATIENCE: self.signal_paused = True; self.paused_reason = "motion"
                else:
                    if self.motion_frames > 0: self.motion_frames = max(0, self.motion_frames - 1)
                    if self.motion_frames == 0: self.signal_paused = False; self.paused_reason = ""
                
                if not self.signal_paused:
                    with self.lock:
                        self.rgb_buffer.append(fused_rgb); self.time_buffer.append(now)
                        if len(self.rgb_buffer) > BUFFER_SIZE: self.rgb_buffer.pop(0); self.time_buffer.pop(0)
                        if len(self.rgb_buffer) >= MIN_BUFFER_COMPUTE and self.processed_frames % COMPUTE_INTERVAL == 0:
                            buf_snap = list(self.rgb_buffer); ts_snap = list(self.time_buffer)
                            pulse = self.pos_extract(np.array(buf_snap))
                            if pulse is not None and len(pulse) > POS_WINDOW * 2:
                                hr_raw, quality, method = self.estimate_hr_combined(pulse, ts_snap)
                                if self.light_change_detected: quality *= 0.7
                                if hr_raw > 0: self._hr_internal = self.apply_hr_limits(hr_raw, quality, now)
                                self.signal_quality = quality; self.hr_method = method
                                if now - self.last_display_update >= DISPLAY_UPDATE_SEC:
                                    candidate = self._hr_internal
                                    max_chg = self._get_max_display_change(quality)
                                    if self.hr > 0 and abs(candidate - self.hr) > max_chg: candidate = self.hr + np.sign(candidate - self.hr) * max_chg
                                    self.hr = candidate; self.last_display_update = now
                                    self.hr_output_history.append(round(candidate, 1))
                                    if len(self.hr_output_history) > 120: self.hr_output_history.pop(0)
                                if len(pulse) > 48:
                                    p = pulse[-128:].copy(); p = self.median_filter(p, 3); p = self.detrend(p); ps = np.std(p)
                                    self.pulse_history = (p / ps).tolist() if ps > 1e-8 else []
                                self.logger.log(self._hr_internal, quality, method, best_skin, self.motion_score, self.fps, method, self.last_hr_peak, self.last_hr_fft)
            else: self.signal_quality *= 0.9
        return frame

    def draw_hud(self, frame):
        h, w = frame.shape[:2]; overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 52), (0, 0, 0), -1); cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        ROI_COLORS = {"forehead": (0, 200, 255), "left_cheek": (0, 230, 118), "right_cheek": (255, 180, 0)}
        for name, (x1, y1, x2, y2), skin_r in self.all_roi_rects:
            color = ROI_COLORS.get(name, (200, 200, 200))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        if self.hr > 0:
            hc = (0, 80, 255) if self.signal_paused else (0, 180, 255) if self.light_change_detected else (0, 230, 118) if self.signal_quality >= 30 else (0, 180, 100)
            cv2.putText(frame, f"{self.hr:.0f} BPM", (12, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, hc, 2)
        else: cv2.putText(frame, "-- BPM", (12, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 100, 70), 2)
        if self.face_detected:
            cv2.putText(frame, f"Q:{self.signal_quality:.0f}% M:{self.motion_score:.1f} [{self.hr_method}]", (150, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 180, 100), 1)
        return frame

# ================================================================
# ========================= Flask App =============================
# ================================================================
app = Flask(__name__)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Fusion Rate Monitor - Radar & rPPG</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
html,body{width:100%;height:100%;background:#0c1018;color:#c8cee0;overflow:hidden}
.wrapper{display:grid;grid-template-rows:auto 1.1fr 1.3fr auto;height:100vh;gap:8px;padding:10px 14px}
.top-bar{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}
.card{background:linear-gradient(135deg,#151c2c,#1a2236);border-radius:8px;padding:10px 14px;position:relative;overflow:hidden;border:1px solid #232e44;display:flex;flex-direction:column;justify-content:center}
.card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;border-radius:3px 0 0 3px}
.card.c1::before{background:#4285F4}.card.c2::before{background:#EA4335}.card.c3::before{background:#FF9800}
.card.c4::before{background:#34A853}.card.c5::before{background:#FBBC05}.card.c6::before{background:#AB47BC}
.label{font-size:11px;color:#5a6a84;margin-bottom:4px;letter-spacing:.3px}
.val{font-size:24px;font-weight:700;line-height:1}
.unit{font-size:10px;color:#445;margin-left:3px;font-weight:400}
.c1 .val{color:#4285F4}.c2 .val{color:#EA4335}.c3 .val{color:#FF9800}
.c4 .val{color:#34A853}.c5 .val{color:#FBBC05}.c6 .val{color:#AB47BC}
.sub{font-size:10px;color:#3e4e68;margin-top:2px}
.status-dot{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:3px;vertical-align:middle}
.status-dot.on{background:#34A853;box-shadow:0 0 6px rgba(52,168,83,.6)}.status-dot.off{background:#555}
.mode-tag{font-size:9px;padding:1px 6px;border-radius:3px;font-weight:600;margin-left:6px}
.mode-tag.smooth{background:rgba(66,133,244,.15);color:#4285F4}.mode-tag.raw{background:rgba(234,67,53,.15);color:#EA4335}

.row{display:grid;gap:8px;min-height:0}
.row-rt{grid-template-columns:1fr 1fr 1.2fr}
.row-lt{grid-template-columns:1fr 1fr 1.2fr}
.panel{background:#111827;border-radius:8px;border:1px solid #1e2a3e;display:flex;flex-direction:column;overflow:hidden}
.panel-head{display:flex;align-items:center;justify-content:space-between;padding:5px 10px;border-bottom:1px solid #1a2438;flex-shrink:0}
.panel-title{font-size:11px;color:#5a6a84;font-weight:600}
.panel-hint{font-size:9px;color:#2e3e54}
.panel-body{flex:1;position:relative;min-height:0;padding:2px 6px 6px}
.panel-body canvas{width:100%!important;height:100%!important}
.video-container{flex:1;position:relative;background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden}
.video-container img{width:100%;height:100%;object-fit:cover;opacity:0.9}

.controls{display:flex;align-items:center;gap:16px;padding:6px 12px;background:#151c2c;border-radius:8px;border:1px solid #232e44;font-size:11px;color:#5a6a84}
.ctrl-group{display:flex;align-items:center;gap:4px}
.ctrl-group input{width:46px;padding:3px 4px;background:#1a2236;border:1px solid #2a3650;border-radius:4px;color:#c8cee0;text-align:center;font-size:11px}
.ctrl-group input:focus{outline:none;border-color:#4285F4}
.apply-btn{padding:4px 12px;background:#4285F4;border:none;border-radius:4px;color:#fff;font-size:11px;cursor:pointer}
.mode-group{display:flex;background:#1a2236;border-radius:5px;padding:2px;gap:1px;border:1px solid #232e44;margin-left:auto}
.mode-btn{padding:4px 14px;border:none;border-radius:4px;background:transparent;color:#556;cursor:pointer;font-size:11px;transition:.2s}
.mode-btn.active{background:#4285F4;color:#fff}
</style>
</head>
<body>
<div class="wrapper">
  <div class="top-bar">
    <div class="card c1">
      <div class="label">雷达呼吸率</div>
      <div><span class="val" id="vRadarBreath">-</span><span class="unit">bpm</span></div>
    </div>
    <div class="card c2">
      <div class="label">雷达心率</div>
      <div><span class="val" id="vRadarHeart">-</span><span class="unit">bpm</span></div>
    </div>
    <div class="card c3">
      <div class="label">rPPG 心率</div>
      <div><span class="val" id="vRppgHeart">-</span><span class="unit">bpm</span></div>
      <div class="sub" id="rppgSub">等待检测</div>
    </div>
    <div class="card c4">
      <div class="label">雷达距离</div>
      <div><span class="val" id="vDist">-</span><span class="unit">cm</span></div>
    </div>
    <div class="card c5">
      <div class="label">人员状态</div>
      <div class="val" style="font-size:18px">
        <span class="status-dot off" id="dotHuman"></span><span id="txtHuman">等待</span>
        <span class="mode-tag smooth" id="modeTag">平滑</span>
      </div>
    </div>
    <div class="card c6">
      <div class="label">rPPG 质量 / FPS</div>
      <div><span class="val" id="vQuality" style="font-size:20px">-</span><span class="unit">%</span> &nbsp; <span class="val" id="vFps" style="font-size:16px;color:#4a5570">-</span></div>
    </div>
  </div>

  <div class="row row-rt">
    <div class="panel">
      <div class="panel-head"><span class="panel-title">雷达实时呼吸</span><span class="panel-hint">60s</span></div>
      <div class="panel-body"><canvas id="rtBreath"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel-head"><span class="panel-title">雷达实时心率</span><span class="panel-hint">60s</span></div>
      <div class="panel-body"><canvas id="rtHeart"></canvas></div>
    </div>
    <div class="panel" style="grid-row: span 1;">
      <div class="panel-head"><span class="panel-title">rPPG 视频 / 脉搏波</span><span class="panel-hint">实时</span></div>
      <div class="video-container"><img src="/video_feed" id="rppgImg"></div>
      <div class="panel-body" style="height:30%;flex-shrink:0;border-top:1px solid #1a2438"><canvas id="rtPulse"></canvas></div>
    </div>
  </div>

  <div class="row row-lt">
    <div class="panel">
      <div class="panel-head"><span class="panel-title">雷达长期呼吸</span><span class="panel-hint">缩放·平移·双击重置</span></div>
      <div class="panel-body"><canvas id="ltBreath"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel-head"><span class="panel-title">雷达长期心率</span><span class="panel-hint">缩放·平移·双击重置</span></div>
      <div class="panel-body"><canvas id="ltHeart"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel-head"><span class="panel-title">rPPG 心率趋势</span><span class="panel-hint">缩放·平移·双击重置</span></div>
      <div class="panel-body"><canvas id="ltRppg"></canvas></div>
    </div>
  </div>

  <div class="controls">
    <div class="ctrl-group">雷达呼吸Y:<input type="number" id="bMin" value="0">~<input type="number" id="bMax" value="30"></div>
    <div class="ctrl-group">雷达心率Y:<input type="number" id="hMin" value="40">~<input type="number" id="hMax" value="120"></div>
    <div class="ctrl-group">rPPG心率Y:<input type="number" id="rpMin" value="40">~<input type="number" id="rpMax" value="120"></div>
    <button class="apply-btn" onclick="applyScale()">应用</button>
    <div class="mode-group">
      <button class="mode-btn active" id="btnSmooth" onclick="setMode('smooth')">雷达平滑</button>
      <button class="mode-btn" id="btnRaw" onclick="setMode('raw')">雷达源数据</button>
    </div>
  </div>
</div>

<script>
var bMin=0,bMax=30,hMin=40,hMax=120,rpMin=40,rpMax=120;
function fmtTs(ts){var d=new Date(ts*1000);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0')}

function makeOpts(isZoom, yMin, yMax, isTimeX){
  return {
    responsive:true, maintainAspectRatio:false, animation:false,
    interaction:{intersect:false,mode:'index'},
    elements:{point:{radius:0},line:{borderWidth:1.8,tension:0.3}},
    scales:{
      x: (isTimeX ? {type:'linear',grid:{color:'#1a2236'},ticks:{color:'#3a4a64',font:{size:9},maxTicksLimit:6,callback:function(v){return fmtTs(v)}}} 
               : {display:false}),
      y:{min:yMin,max:yMax,grid:{color:'#1a2236',borderDash:[3,3]},ticks:{color:'#3a4a64',font:{size:9},maxTicksLimit:5}}
    },
    plugins:{
      legend:{display:false},
      tooltip:{enabled:isTimeX,backgroundColor:'#1a2236',borderColor:'#2a3a54',borderWidth:1,titleColor:'#6b7a94',bodyColor:'#c8cee0',
        callbacks:{title:function(i){return fmtTs(i[0].parsed.x)},label:function(i){return i.dataset.label+': '+i.parsed.y}}},
      zoom: isZoom ? {zoom:{wheel:{enabled:true},pinch:{enabled:true},mode:'xy'},pan:{enabled:true,mode:'xy'}} : false
    }
  };
}

var rtB=new Chart(document.getElementById('rtBreath'),{type:'line',data:{datasets:[{label:'呼吸率',data:[],borderColor:'#4285F4',backgroundColor:'rgba(66,133,244,0.08)',fill:true}]},options:makeOpts(false,bMin,bMax,true)});
var rtH=new Chart(document.getElementById('rtHeart'),{type:'line',data:{datasets:[{label:'心率',data:[],borderColor:'#EA4335',backgroundColor:'rgba(234,67,53,0.08)',fill:true}]},options:makeOpts(false,hMin,hMax,true)});
var rtP=new Chart(document.getElementById('rtPulse'),{type:'line',data:{datasets:[{label:'脉搏波',data:[],borderColor:'#FF9800',borderWidth:1.5}]},options:makeOpts(false,-2,2,false)});
var ltB=new Chart(document.getElementById('ltBreath'),{type:'line',data:{datasets:[{label:'呼吸率',data:[],borderColor:'#4285F4',backgroundColor:'rgba(66,133,244,0.06)',fill:true}]},options:makeOpts(true,bMin,bMax,true)});
var ltH=new Chart(document.getElementById('ltHeart'),{type:'line',data:{datasets:[{label:'心率',data:[],borderColor:'#EA4335',backgroundColor:'rgba(234,67,53,0.06)',fill:true}]},options:makeOpts(true,hMin,hMax,true)});
var ltR=new Chart(document.getElementById('ltRppg'),{type:'line',data:{datasets:[{label:'rPPG心率',data:[],borderColor:'#FF9800',backgroundColor:'rgba(255,152,0,0.06)',fill:true}]},options:makeOpts(true,rpMin,rpMax,true)});

['ltBreath','ltHeart','ltRppg'].forEach(id=>{document.getElementById(id).addEventListener('dblclick',function(){eval(id.charAt(0).toUpperCase()+id.slice(1)).resetZoom()})});

function toPts(t,v){var p=[];for(var i=0;i<t.length;i++)p.push({x:t[i],y:v[i]});return p}

var currentMode='smooth';
function setMode(m){
  currentMode=m;
  document.getElementById('btnSmooth').className='mode-btn'+(m==='smooth'?' active':'');
  document.getElementById('btnRaw').className='mode-btn'+(m==='raw'?' active':'');
  var tag=document.getElementById('modeTag');tag.className='mode-tag '+m;tag.textContent=m==='smooth'?'平滑':'源数据';
  fetch('/mode?v='+m);
}

function applyScale(){
  bMin=parseFloat(document.getElementById('bMin').value)||0;bMax=parseFloat(document.getElementById('bMax').value)||30;
  hMin=parseFloat(document.getElementById('hMin').value)||0;hMax=parseFloat(document.getElementById('hMax').value)||150;
  rpMin=parseFloat(document.getElementById('rpMin').value)||0;rpMax=parseFloat(document.getElementById('rpMax').value)||150;
  [rtB,ltB].forEach(c=>{c.options.scales.y.min=bMin;c.options.scales.y.max=bMax;c.update('none')});
  [rtH,ltH].forEach(c=>{c.options.scales.y.min=hMin;c.options.scales.y.max=hMax;c.update('none')});
  [ltR].forEach(c=>{c.options.scales.y.min=rpMin;c.options.scales.y.max=rpMax;c.update('none')});
}

setInterval(function(){
  Promise.all([fetch('/data').then(r=>r.json()), fetch('/api/hr').then(r=>r.json())]).then(([rd,rh])=>{
    document.getElementById('vRadarBreath').textContent=rd.breath;
    document.getElementById('vRadarHeart').textContent=rd.heart;
    document.getElementById('vDist').textContent=rd.distance;
    var dot=document.getElementById('dotHuman'),txt=document.getElementById('txtHuman');
    if(rd.human){dot.className='status-dot on';txt.textContent='有人'}else{dot.className='status-dot off';txt.textContent='无人'}
    if(rd.mode!==currentMode)setMode(rd.mode);

    document.getElementById('vRppgHeart').textContent=rh.hr>0?rh.hr:'--';
    document.getElementById('vQuality').textContent=rh.quality;
    document.getElementById('vFps').textContent=rh.fps;
    var subTxt = rh.face ? (rh.hr_method !== "--" ? "Method: "+rh.hr_method : "Buffering...") : "NO FACE";
    document.getElementById('rppgSub').textContent = subTxt;

    rtB.data.datasets[0].data=toPts(rd.rt.time,rd.rt.breath);rtB.update('none');
    rtH.data.datasets[0].data=toPts(rd.rt.time,rd.rt.heart);rtH.update('none');
    
    var pulseData=[];
    for(var i=0;i<rh.pulse.length;i++)pulseData.push({x:i,y:rh.pulse[i]});
    rtP.data.datasets[0].data=pulseData;rtP.update('none');
  });
}, 300);

setInterval(function(){
  Promise.all([fetch('/longterm').then(r=>r.json())]).then(([ld])=>{
    ltB.data.datasets[0].data=toPts(ld.time,ld.breath);ltB.update('none');
    ltH.data.datasets[0].data=toPts(ld.time,ld.heart);ltH.update('none');
  });
  // rPPG 历史单独从 /api/hr 获取，因为已经在300ms里拿了，这里做个简易缓存更新
  fetch('/api/hr').then(r=>r.json()).then(rh=>{
    var timePts=[], hrPts=[];
    var len = rh.hr_history.length;
    var now = Date.now()/1000;
    for(var i=len-1,j=0; i>=0 && j<400; i--, j++){
      timePts.unshift(now - j * 3); // 约每3秒一个点
      hrPts.unshift(rh.hr_history[i]);
    }
    ltR.data.datasets[0].data=toPts(timePts, hrPts);ltR.update('none');
  });
}, 2000);
</script>
</body>
</html>"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/data')
def get_data():
    with radar_lock:
        rt = {"time": list(radar_rt_buf["time"]), "breath": list(radar_rt_buf["breath"]), "heart": list(radar_rt_buf["heart"])}
    return jsonify({"breath": radar_data["breath"], "heart": radar_data["heart"], "distance": radar_data["distance"], "human": radar_data["human"], "mode": radar_data["mode"], "rt": rt})

@app.route('/longterm')
def get_longterm():
    with radar_lock:
        lt = {"time": list(radar_lt_buf["time"]), "breath": list(radar_lt_buf["breath"]), "heart": list(radar_lt_buf["heart"])}
    return jsonify(lt)

@app.route('/mode')
def set_mode():
    radar_data["mode"] = request.args.get('v', 'smooth')
    return "ok"

@app.route('/video_feed')
def video_feed():
    def generate():
        while processor.running:
            try:
                with processor.switch_lock:
                    cap = processor.cap
                    if cap is None or not cap.isOpened(): time.sleep(0.05); continue
                    ret, frame = cap.read()
                    if not ret: time.sleep(0.01); continue
                    frame = processor.process_frame(frame)
                    frame = processor.draw_hud(frame)
                    ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not ok: continue
                    yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            except Exception as e: print("[ERROR]", repr(e)); time.sleep(0.01)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/hr')
def get_hr():
    with processor.lock:
        return jsonify({
            'hr': round(processor.hr, 1), 'quality': round(processor.signal_quality, 0),
            'face': processor.face_detected, 'fps': round(processor.fps, 1),
            'hr_history': processor.hr_output_history[-80:],
            'pulse': processor.pulse_history[-120:] if processor.pulse_history else [],
            'hr_method': processor.hr_method
        })

if __name__ == "__main__":
    # 启动雷达
    threading.Thread(target=serial_task, daemon=True).start()
    threading.Thread(target=sampler_task, daemon=True).start()
    
    # 启动 rPPG
    processor = RPPGProcessor(camera_id=CAMERA_ID_DEFAULT)
    try:
        processor.start()
        print("=" * 60)
        print(" Fusion Rate Monitor (Radar + rPPG)")
        print(" Radar: COM9 @ 115200 | rPPG: Local Cam 0")
        print(" http://localhost:5000")
        print("=" * 60)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭...")
    finally:
        processor.stop()
