# -*- coding: utf-8 -*-
import serial
import struct
import time
import threading
import json
import os
import logging
from collections import deque
from flask import Flask, render_template, jsonify, request
import numpy as np

# 禁用Flask的访问日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ====================== 配置 ======================
PORT = "COM9"
BAUD = 115200
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODE_HISTORY_DIR = os.path.join(SCRIPT_DIR, "mode_history")

# ====================== 全局数据 ======================
data = {"breath": 0, "heart": 0, "distance": 0.0, "human": False, "mode": "stable"}
raw_data_cache_global = {"breath": 0, "heart": 0, "human": False}
data_status = "normal"

# 1. 实时缓存（连续，高频，仅存当前模式）
realtime_buf = {"time": [], "breath": [], "heart": []}

# 2. 历史缓存（离散去重，按模式分类，供长期多模式对比）
mode_history_cache = {
    "stable": {"time": [], "breath": [], "heart": []},
    "ultra": {"time": [], "breath": [], "heart": []},
    "smooth": {"time": [], "breath": [], "heart": []},
    "raw": {"time": [], "breath": [], "heart": []},
    "lowfreq": {"time": [], "breath": [], "heart": []}
}
last_written = {"breath": {}, "heart": {}}

# ====================== 初始化与持久化 ======================
RUN_TIMESTAMP = time.strftime("%Y%m%d_%H%M%S")

def init_history_system():
    global MODE_HISTORY_DIR
    MODE_HISTORY_DIR = os.path.join(SCRIPT_DIR, "mode_history")
    os.makedirs(MODE_HISTORY_DIR, exist_ok=True)
    for m in mode_history_cache.keys():
        last_written["breath"][m] = None
        last_written["heart"][m] = None

def save_history_to_disk():
    for m, hist in mode_history_cache.items():
        if not hist["time"]: continue
        filepath = os.path.join(MODE_HISTORY_DIR, f"{RUN_TIMESTAMP}_{m}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f: json.dump(hist, f)
        except Exception as e: print(f"❌ 保存历史 {m} 失败: {e}")

# ====================== 算法引擎 ======================
class RobustEstimator:
    def __init__(self, window_sec=6.0, min_samples=5):
        self.window_sec = window_sec; self.min_samples = min_samples
        self.buffer = deque(); self.last_output = 0; self.confidence = 0.0
        self.trend_buffer = deque(maxlen=5)
    def feed(self, timestamp, value):
        if value > 0: 
            self.buffer.append((timestamp, value))
            self.trend_buffer.append(value)
        cutoff = timestamp - self.window_sec
        while self.buffer and self.buffer[0][0] < cutoff: self.buffer.popleft()
    def estimate(self, timestamp):
        if len(self.buffer) < self.min_samples: return self.last_output, 0.0
        vals = [v for t, v in self.buffer]
        q1, q3 = np.percentile(vals, 25), np.percentile(vals, 75); iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        filtered = [v for v in vals if lower <= v <= upper]
        if len(filtered) < self.min_samples // 2 + 1: filtered = vals
        
        n = len(filtered)
        weights = np.exp(np.linspace(-1, 0, n))
        weighted_median = np.average(filtered, weights=weights)
        
        if len(self.trend_buffer) >= 3:
            recent = list(self.trend_buffer)[-3:]
            trend = (recent[-1] - recent[0]) / 2
            pred = weighted_median + trend * 0.3
            est = round(pred)
        else:
            est = round(weighted_median)
            
        self.confidence = min(len(filtered) / 12.0, 1.0)
        self.last_output = est; return est, self.confidence
    def flush(self): self.buffer.clear(); self.last_output = 0; self.confidence = 0.0; self.trend_buffer.clear()

ESTIMATORS = {
    "smooth": {"window": 3.0, "min": 3}, "stable": {"window": 6.0, "min": 5},
    "ultra": {"window": 8.0, "min": 8}, "raw": {"window": 0.5, "min": 1}, "lowfreq": {"window": 2.0, "min": 3}
}

all_mode_estimators = {
    "stable": {
        "breath": RobustEstimator(window_sec=6.0, min_samples=5),
        "heart": RobustEstimator(window_sec=6.0, min_samples=5)
    },
    "ultra": {
        "breath": RobustEstimator(window_sec=8.0, min_samples=8),
        "heart": RobustEstimator(window_sec=8.0, min_samples=8)
    }
}

class AdaptiveSmoothState:
    def __init__(self):
        self.breath_hist = deque(maxlen=15)
        self.heart_hist = deque(maxlen=15)
        self.breath_ema = 0.0
        self.heart_ema = 0.0
        self.ema_alpha_breath = 0.15
        self.ema_alpha_heart = 0.25
        self.ema_init = {"breath": False, "heart": False}
        self.last_valid = {"breath": 0, "heart": 0}
        self.consecutive_jump = {"breath": 0, "heart": 0}
        self.jump_recovery = {"breath": False, "heart": False}
        
    def process(self, new_b, new_h, is_human):
        if not is_human:
            self.__init__()
            return {"breath": 0, "heart": 0}
            
        results = {}
        
        b_result = self._process_single(
            new_b, self.breath_hist, self.breath_ema, 
            self.ema_alpha_breath, self.ema_init["breath"],
            self.last_valid["breath"], self.consecutive_jump["breath"],
            self.jump_recovery["breath"], 4, 60, 10
        )
        self.breath_ema = b_result["ema"]
        self.ema_init["breath"] = True
        self.last_valid["breath"] = b_result["out"] if b_result["out"] > 0 else self.last_valid["breath"]
        self.consecutive_jump["breath"] = b_result["jump_count"]
        self.jump_recovery["breath"] = b_result["recovering"]
        results["breath"] = b_result["out"]
        
        h_result = self._process_single(
            new_h, self.heart_hist, self.heart_ema,
            self.ema_alpha_heart, self.ema_init["heart"],
            self.last_valid["heart"], self.consecutive_jump["heart"],
            self.jump_recovery["heart"], 30, 180, 15
        )
        self.heart_ema = h_result["ema"]
        self.ema_init["heart"] = True
        self.last_valid["heart"] = h_result["out"] if h_result["out"] > 0 else self.last_valid["heart"]
        self.consecutive_jump["heart"] = h_result["jump_count"]
        self.jump_recovery["heart"] = h_result["recovering"]
        results["heart"] = h_result["out"]
        
        return results
    
    def _process_single(self, new_val, hist, ema, alpha, initialized, last_valid, jump_count, recovering, min_v, max_v, jump_thresh):
        if new_val <= 0:
            return {"out": round(ema) if initialized else 0, "ema": ema, 
                    "jump_count": jump_count, "recovering": recovering}
        
        hist.append(new_val)
        
        if len(hist) >= 3:
            med = sorted(hist)[len(hist) // 2]
        else:
            med = new_val
            
        is_jump = False
        if last_valid > 0 and abs(med - last_valid) > jump_thresh:
            is_jump = True
            jump_count += 1
        else:
            jump_count = max(0, jump_count - 1)
            
        adaptive_alpha = alpha
        if jump_count >= 2:
            adaptive_alpha = alpha * 0.3
            recovering = True
        elif recovering and jump_count == 0:
            adaptive_alpha = alpha * 0.7
            recovering = False
        elif len(hist) >= 5:
            recent = list(hist)[-5:]
            local_std = np.std(recent)
            if local_std < 2:
                adaptive_alpha = min(alpha * 1.5, 0.5)
            elif local_std > 5:
                adaptive_alpha = alpha * 0.5
                
        if not initialized or ema == 0:
            new_ema = float(med)
        else:
            if is_jump and jump_count < 3:
                max_step = jump_thresh * 0.3
                diff = med - ema
                if abs(diff) > max_step:
                    med = ema + max_step * (1 if diff > 0 else -1)
            new_ema = ema * (1 - adaptive_alpha) + med * adaptive_alpha
            
        out = round(clamp(new_ema, min_v, max_v))
        
        return {"out": out, "ema": new_ema, "jump_count": jump_count, "recovering": recovering}

all_mode_smooth_state = AdaptiveSmoothState()

class LowFreqState:
    def __init__(self):
        self.buf = {"breath": [], "heart": []}
        self.last_t = 0.0
        self.data = {"breath": 0, "heart": 0}
        self.ema = {"breath": 0.0, "heart": 0.0}
        self.ema_init = {"breath": False, "heart": False}
        self.WINDOW_SEC = 3.0
        self.ALPHA = 0.3
        
    def process(self, new_b, new_h, is_human):
        if not is_human:
            self.__init__()
            return {"breath": 0, "heart": 0}
            
        now = time.time()
        if new_b > 0: self.buf["breath"].append(new_b)
        if new_h > 0: self.buf["heart"].append(new_h)
        
        if now - self.last_t >= self.WINDOW_SEC:
            results = {}
            for key, raw_list in self.buf.items():
                if raw_list:
                    med = sorted(raw_list)[len(raw_list) // 2]
                    if not self.ema_init[key] or self.ema[key] == 0:
                        self.ema[key] = float(med)
                        self.ema_init[key] = True
                    else:
                        self.ema[key] = self.ema[key] * (1 - self.ALPHA) + med * self.ALPHA
                    results[key] = round(self.ema[key])
                else:
                    results[key] = round(self.ema[key]) if self.ema_init[key] else 0
                    
            self.buf["breath"].clear()
            self.buf["heart"].clear()
            self.last_t = now
            self.data = results
            
        return {"breath": clamp(self.data["breath"], 4, 60), 
                "heart": clamp(self.data["heart"], 30, 180)}

all_mode_lowfreq_state = LowFreqState()

class RawLimiter:
    def __init__(self):
        self.last_valid = {"breath": 0, "heart": 0}
        self.hist = {"breath": deque(maxlen=3), "heart": deque(maxlen=3)}
        
    def process(self, new_b, new_h, is_human):
        if not is_human:
            self.__init__()
            return {"breath": 0, "heart": 0}
            
        results = {}
        for key, val, last, min_v, max_v in [
            ("breath", new_b, self.last_valid["breath"], 4, 60),
            ("heart", new_h, self.last_valid["heart"], 30, 180)
        ]:
            if val <= 0:
                results[key] = last if last > 0 else 0
                continue
                
            self.hist[key].append(val)
            if len(self.hist[key]) >= 2 and last > 0:
                max_change = 15 if key == "heart" else 8
                if abs(val - last) > max_change:
                    med = sorted(self.hist[key])[len(self.hist[key]) // 2]
                    val = med
                    
            results[key] = clamp(val, min_v, max_v)
            if results[key] > 0:
                self.last_valid[key] = results[key]
                
        return results

all_mode_raw_state = RawLimiter()

all_mode_last_valid = {
    "stable": {"breath": 0, "heart": 0},
    "ultra": {"breath": 0, "heart": 0},
    "smooth": {"breath": 0, "heart": 0},
    "lowfreq": {"breath": 0, "heart": 0},
    "raw": {"breath": 0, "heart": 0}
}

# 用于当前显示的全局estimators
breath_estimator = RobustEstimator(window_sec=6.0, min_samples=5)
heart_estimator = RobustEstimator(window_sec=6.0, min_samples=5)

class ZeroInterpolator:
    def __init__(self, window=5): self.raw_buf = deque(maxlen=window); self.window = window
    def feed(self, raw):
        self.raw_buf.append(float(raw)); arr = list(self.raw_buf); n = len(arr); valid_idx = [i for i, v in enumerate(arr) if v > 0]
        if len(valid_idx) >= 2:
            for i in range(n):
                if arr[i] == 0:
                    left = max([j for j in valid_idx if j < i], default=None); right = min([j for j in valid_idx if j > i], default=None)
                    if left is not None and right is not None: arr[i] = arr[left] + (arr[right] - arr[left]) * ((i - left) / (right - left))
                    elif left is not None: arr[i] = arr[left]
                    elif right is not None: arr[i] = arr[right]
        elif len(valid_idx) == 1:
            for i in range(n):
                if arr[i] == 0: arr[i] = arr[valid_idx[0]]
        return round(arr[0]) if n >= self.window else (round(arr[-1]) if arr else raw)
    def flush(self): self.raw_buf.clear()

breath_interp = ZeroInterpolator(window=5); heart_interp = ZeroInterpolator(window=5)
breath_hist = []; heart_hist = []; breath_ema = 0.0; heart_ema = 0.0
ema_initialized = {"breath": False, "heart": False}; last_human_time = 0.0; away_start_time = None
last_valid_data = {"breath": 0, "heart": 0}; consecutive_invalid_count = 0
MEDIAN_WINDOW = 7; EMA_ALPHA_BREATH = 0.15; EMA_ALPHA_HEART = 0.25
HUMAN_LOST_THRESHOLD = 1.5; AWAY_FADE_DURATION = 2.0; REALTIME_MAX = 120; SAMPLE_INTERVAL = 0.5
DIFF_THRESHOLD_BREATH = 12; DIFF_THRESHOLD_HEART = 25; MAX_INVALID_FRAMES = 8; lock = threading.Lock()

def verify_cksum(buf, cksum):
    acc = 0
    for b in buf: acc ^= b
    return (~acc & 0xFF) == cksum
def float_le(b): return struct.unpack('<f', b)[0]
def median_filter(v, buf, window):
    buf.append(v)
    if len(buf) > window: buf.pop(0)
    if len(buf) < 3: return v
    return sorted(buf)[len(buf) // 2]
def ema_filter(v, prev, alpha, initialized):
    if not initialized or prev == 0: return v, True
    return prev * (1 - alpha) + v * alpha, True
def clamp(v, lo, hi): return max(lo, min(hi, v))

def process_lowfreq(b, h):
    if not hasattr(process_lowfreq, 'buf'): process_lowfreq.buf = {"breath": [], "heart": []}
    if not hasattr(process_lowfreq, 'last_t'): process_lowfreq.last_t = 0.0
    if not hasattr(process_lowfreq, 'data'): process_lowfreq.data = {"breath": 0, "heart": 0}
    now = time.time()
    if b > 0: process_lowfreq.buf["breath"].append(b)
    if h > 0: process_lowfreq.buf["heart"].append(h)
    if now - process_lowfreq.last_t >= 2.0:
        if process_lowfreq.buf["breath"]: process_lowfreq.data["breath"] = round(sum(process_lowfreq.buf["breath"]) / len(process_lowfreq.buf["breath"]))
        if process_lowfreq.buf["heart"]: process_lowfreq.data["heart"] = round(sum(process_lowfreq.buf["heart"]) / len(process_lowfreq.buf["heart"]))
        process_lowfreq.buf["breath"].clear(); process_lowfreq.buf["heart"].clear(); process_lowfreq.last_t = now
    return process_lowfreq.data["breath"], process_lowfreq.data["heart"]

def process_all_modes(new_b, new_h, is_human):
    global all_mode_estimators, all_mode_smooth_state, all_mode_lowfreq_state, all_mode_raw_state, all_mode_last_valid
    now = time.time()
    results = {}

    if not is_human:
        for mode in ["stable", "ultra"]:
            all_mode_estimators[mode]["breath"].flush()
            all_mode_estimators[mode]["heart"].flush()
            all_mode_last_valid[mode] = {"breath": 0, "heart": 0}
        all_mode_smooth_state = AdaptiveSmoothState()
        all_mode_lowfreq_state = LowFreqState()
        all_mode_raw_state = RawLimiter()
        for mode in ["stable", "ultra", "smooth", "lowfreq", "raw"]:
            results[mode] = {"breath": 0, "heart": 0}
        return results

    for mode in ["stable", "ultra"]:
        est_b = all_mode_estimators[mode]["breath"]
        est_h = all_mode_estimators[mode]["heart"]
        est_b.feed(now, new_b)
        est_h.feed(now, new_h)
        b_est, b_conf = est_b.estimate(now)
        h_est, h_conf = est_h.estimate(now)
        last_v = all_mode_last_valid[mode]
        b_out = last_v["breath"] if b_conf < 0.3 and last_v["breath"] > 0 else b_est
        h_out = last_v["heart"] if h_conf < 0.3 and last_v["heart"] > 0 else h_est
        if last_v["breath"] > 0 and abs(b_out - last_v["breath"]) > DIFF_THRESHOLD_BREATH: b_out = last_v["breath"]
        if last_v["heart"] > 0 and abs(h_out - last_v["heart"]) > DIFF_THRESHOLD_HEART: h_out = last_v["heart"]
        b_out = b_out if b_out > 0 else last_v["breath"]
        h_out = h_out if h_out > 0 else last_v["heart"]
        all_mode_last_valid[mode] = {"breath": b_out, "heart": h_out}
        results[mode] = {"breath": clamp(b_out, 4, 60), "heart": clamp(h_out, 30, 180)}

    smooth_res = all_mode_smooth_state.process(new_b, new_h, is_human)
    results["smooth"] = smooth_res

    lowfreq_res = all_mode_lowfreq_state.process(new_b, new_h, is_human)
    results["lowfreq"] = lowfreq_res

    raw_res = all_mode_raw_state.process(new_b, new_h, is_human)
    results["raw"] = raw_res

    return results

def process_sensor_data(new_b, new_h, is_human):
    global last_valid_data, consecutive_invalid_count, data_status, breath_ema, heart_ema
    global ema_initialized, away_start_time, breath_estimator, heart_estimator
    now = time.time()
    if not is_human:
        if away_start_time is None: away_start_time = now
        elapsed = now - away_start_time
        if elapsed < AWAY_FADE_DURATION:
            ratio = max(0.0, 1.0 - elapsed / AWAY_FADE_DURATION); data_status = "away"
            return (round(last_valid_data["breath"] * ratio), round(last_valid_data["heart"] * ratio), "away")
        else:
            consecutive_invalid_count = 0; last_valid_data = {"breath": 0, "heart": 0}
            breath_ema = 0.0; heart_ema = 0.0; ema_initialized = {"breath": False, "heart": False}
            breath_hist.clear(); heart_hist.clear(); breath_interp.flush(); heart_interp.flush()
            breath_estimator.flush(); heart_estimator.flush(); data_status = "away"; return 0, 0, "away"
    away_start_time = None; mode = data["mode"]
    if mode in ["stable", "ultra"]:
        breath_estimator.feed(now, new_b); heart_estimator.feed(now, new_h)
        b_est, b_conf = breath_estimator.estimate(now); h_est, h_conf = heart_estimator.estimate(now)
        b_out = last_valid_data["breath"] if b_conf < 0.3 and last_valid_data["breath"] > 0 else b_est
        h_out = last_valid_data["heart"] if h_conf < 0.3 and last_valid_data["heart"] > 0 else h_est
        if last_valid_data["breath"] > 0 and abs(b_out - last_valid_data["breath"]) > DIFF_THRESHOLD_BREATH: b_out = last_valid_data["breath"]
        if last_valid_data["heart"] > 0 and abs(h_out - last_valid_data["heart"]) > DIFF_THRESHOLD_HEART: h_out = last_valid_data["heart"]
        last_valid_data["breath"] = b_out if b_out > 0 else last_valid_data["breath"]
        last_valid_data["heart"] = h_out if h_out > 0 else last_valid_data["heart"]
        data_status = "normal" if min(b_conf, h_conf) > 0.6 else "compensating"; return round(b_out), round(h_out), data_status
    elif mode == "smooth":
        b_med = median_filter(new_b, breath_hist, MEDIAN_WINDOW); h_med = median_filter(new_h, heart_hist, MEDIAN_WINDOW)
        b_ema, ema_initialized["breath"] = ema_filter(b_med, breath_ema, EMA_ALPHA_BREATH, ema_initialized["breath"])
        h_ema, ema_initialized["heart"] = ema_filter(h_med, heart_ema, EMA_ALPHA_HEART, ema_initialized["heart"])
        breath_ema = b_ema; heart_ema = h_ema
        is_b_invalid = (new_b == 0 or abs(new_b - last_valid_data["breath"]) > DIFF_THRESHOLD_BREATH) if last_valid_data["breath"] > 0 else (new_b == 0)
        is_h_invalid = (new_h == 0 or abs(new_h - last_valid_data["heart"]) > DIFF_THRESHOLD_HEART) if last_valid_data["heart"] > 0 else (new_h == 0)
        if is_b_invalid or is_h_invalid:
            consecutive_invalid_count += 1
            if consecutive_invalid_count < MAX_INVALID_FRAMES: data_status = "compensating"; return round(breath_ema), round(heart_ema), "compensating"
            else: last_valid_data = {"breath": b_ema, "heart": h_ema}; consecutive_invalid_count = 0; data_status = "recovered"; return round(b_ema), round(h_ema), "recovered"
        else: consecutive_invalid_count = 0; data_status = "normal"; last_valid_data = {"breath": b_ema, "heart": h_ema}; return round(b_ema), round(h_ema), "normal"
    else: return new_b, new_h, "normal"

# ====================== 线程任务 ======================
def serial_task():
    global last_human_time; buf = b""; raw_data_cache = {"breath": 0, "heart": 0}
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.005); print("✅ 串口已打开")
        while True:
            if ser.in_waiting:
                buf += ser.read(ser.in_waiting)
                while len(buf) >= 8:
                    if buf[0] != 0x01: buf = buf[1:]; continue
                    dlen = (buf[3] << 8) | buf[4]; flen = 8 + dlen + (1 if dlen > 0 else 0)
                    if len(buf) < flen or flen > 1024: buf = buf[1:]; break
                    frame = buf[:flen]; buf = buf[flen:]
                    if not verify_cksum(frame[0:7], frame[7]): continue
                    if dlen > 0 and not verify_cksum(frame[8:8+dlen], frame[8+dlen]): continue
                    tid = (frame[5] << 8) | frame[6]; fd = frame[8:8+dlen]; mode = data["mode"]
                    if tid == 0x0F09:
                        detected = fd[0] == 1
                        if detected: last_human_time = time.time()
                        is_human = detected if mode == "raw" else (detected or (time.time() - last_human_time) < HUMAN_LOST_THRESHOLD)
                        pb, ph, status = process_sensor_data(raw_data_cache["breath"], raw_data_cache["heart"], is_human)
                        if mode == "smooth": data["breath"], data["heart"] = clamp(pb, 4, 60), clamp(ph, 30, 180)
                        elif mode in ["stable", "ultra"]: data["breath"], data["heart"] = clamp(pb, 4, 60), clamp(ph, 30, 180)
                        elif mode == "lowfreq": lb, lh = process_lowfreq(raw_data_cache["breath"], raw_data_cache["heart"]); data["breath"], data["heart"] = clamp(lb, 4, 60), clamp(lh, 30, 180)
                        else: data["breath"], data["heart"] = raw_data_cache["breath"], raw_data_cache["heart"]
                        data["human"] = is_human
                        raw_data_cache_global.update({"breath": raw_data_cache["breath"], "heart": raw_data_cache["heart"], "human": is_human})
                    elif tid == 0x0A14: raw_data_cache["breath"] = breath_interp.feed(round(float_le(fd[:4])))
                    elif tid == 0x0A15: raw_data_cache["heart"] = heart_interp.feed(round(float_le(fd[:4])))
                    elif tid == 0x0A16: data["distance"] = round(float_le(fd[4:8]), 1) if struct.unpack('<I', fd[0:4])[0] == 1 else 0.0
                time.sleep(0.001)
    except Exception as e: print("串口异常:", e); time.sleep(2)

def sampler_task():
    while True:
        time.sleep(SAMPLE_INTERVAL); ts = time.time()
        with lock:
            current_mode = data["mode"]
            raw_b = raw_data_cache_global["breath"]
            raw_h = raw_data_cache_global["heart"]
            is_human = raw_data_cache_global["human"]

            all_results = process_all_modes(raw_b, raw_h, is_human)

            for mode, result in all_results.items():
                cur_breath = result["breath"]
                cur_heart = result["heart"]

                if mode == current_mode:
                    data["breath"] = cur_breath
                    data["heart"] = cur_heart
                    realtime_buf["time"].append(ts)
                    realtime_buf["breath"].append(cur_breath)
                    realtime_buf["heart"].append(cur_heart)
                    if len(realtime_buf["time"]) > REALTIME_MAX:
                        for k in realtime_buf: realtime_buf[k].pop(0)

                if cur_breath != last_written["breath"][mode] or cur_heart != last_written["heart"][mode]:
                    mode_history_cache[mode]["time"].append(ts)
                    mode_history_cache[mode]["breath"].append(cur_breath)
                    mode_history_cache[mode]["heart"].append(cur_heart)
                    last_written["breath"][mode] = cur_breath
                    last_written["heart"][mode] = cur_heart

def disk_writer_task():
    while True:
        time.sleep(5.0)
        with lock: save_history_to_disk()

# ====================== Flask ======================
app = Flask(__name__, template_folder='templates')

@app.route('/')
def index(): return render_template('com.html')

@app.route('/data')
def get_data():
    with lock:
        rt = {"time": list(realtime_buf["time"]), "breath": list(realtime_buf["breath"]), "heart": list(realtime_buf["heart"])}
        return jsonify({"breath": data["breath"], "heart": data["heart"], "distance": data["distance"], "human": data["human"], "mode": data["mode"], "status": data_status, "breath_confidence": breath_estimator.confidence, "heart_confidence": heart_estimator.confidence, "rt": rt})

@app.route('/longterm')
def get_longterm():
    # 返回所有模式的完整历史数据字典
    with lock:
        # 返回深拷贝防止前端修改影响后端
        return json.loads(json.dumps(mode_history_cache))

@app.route('/mode')
def set_mode():
    new_mode = request.args.get('v', 'stable')
    if new_mode != data["mode"]:
        data["mode"] = new_mode
        if new_mode in ESTIMATORS:
            cfg = ESTIMATORS[new_mode]
            global breath_estimator, heart_estimator
            breath_estimator = RobustEstimator(window_sec=cfg["window"], min_samples=cfg["min"])
            heart_estimator = RobustEstimator(window_sec=cfg["window"], min_samples=cfg["min"])
    return "ok"

if __name__ == "__main__":
    init_history_system()
    threading.Thread(target=serial_task, daemon=True).start()
    threading.Thread(target=sampler_task, daemon=True).start()
    threading.Thread(target=disk_writer_task, daemon=True).start()
    app.run(host="127.0.0.1", port=5020, debug=False, use_reloader=False)
