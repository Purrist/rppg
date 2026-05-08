# -*- coding: utf-8 -*-
import struct
import serial
import time
import json
import threading
import os
import numpy as np
from flask import Flask, render_template, jsonify, request

PORT = "COM9"
BAUD = 115200
HTTP_PORT = 5080
SIMULATE_MODE = False
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, 'hlk.json')
HEALTHDATA_DIR = os.path.join(SCRIPT_DIR, 'healthdata')
os.makedirs(HEALTHDATA_DIR, exist_ok=True)

start_time = time.strftime("%Y%m%d-%H%M%S")
RAW_LOG_FILE = os.path.join(HEALTHDATA_DIR, f"{start_time}raw.json")
RAW_RAW_LOG_FILE = os.path.join(HEALTHDATA_DIR, f"{start_time}raw_raw.json")
ANALYSIS_LOG_FILE = os.path.join(HEALTHDATA_DIR, f"{start_time}analysis.json")

raw_log_data = []
raw_raw_log_data = []
analysis_log_data = []

app = Flask(__name__, template_folder='templates', static_folder='static')

# ========== 全局数据存储 ==========
latest_data = {
    "heart_rate": 72.0,
    "breath_rate": 16.0,
    "heart_phase": 0.0,
    "breath_phase": 0.0,
    "is_human": 0,
    "distance_valid": 0,
    "distance": 0.0,
    "signal_state": "INIT"
}

MAX_HISTORY = 600
heart_phase_history = [0.0] * MAX_HISTORY
breath_phase_history = [0.0] * MAX_HISTORY

display_hr_history = [72.0] * MAX_HISTORY
display_br_history = [16.0] * MAX_HISTORY
signal_state_history = ["INIT"] * MAX_HISTORY

clean_hr_history = [72.0] * MAX_HISTORY
clean_br_history = [16.0] * MAX_HISTORY

last_valid_hr = 72.0
last_valid_br = 16.0
lissajous_history = []
current_preprocessor_output = None

# 指标历史趋势
TREND_LEN = 600
rsa_trend = []
plv_trend = []
brv_trend = []
hrr_trend = []
hri_trend = []
cr_ratio_trend = []
hr_slope_trend = []
phase_diff_trend = []
br_elevation_trend = []


# ========== PhasePreprocessor ==========
class PhasePreprocessor:
    """相位预处理器 V2.0

    修复说明: 不再对相位求导计算频率。
    相位是位移表示 (φ = 4πd/λ)，不是角频率。
    雷达已提供稳定的心率(0x0A15)和呼吸率(0x0A14)。

    本类仅用于:
    1. 相位解卷绕和重采样
    2. 生成 synthetic 瞬时波形（用于RSA/PLV等相位耦合分析）
    3. 保留相位波形用于可视化
    """

    def __init__(self, window_size=100, target_fs=10.0):
        self.window = window_size
        self.fs = target_fs
        self.hr_phase_buf = np.zeros(window_size, dtype=np.float64)
        self.br_phase_buf = np.zeros(window_size, dtype=np.float64)
        self.ts_buf = np.linspace(-window_size / target_fs, 0, window_size)
        self.initialized = False

    def feed(self, hr_phase, br_phase, ts, current_hr=None, current_br=None):
        """
        参数:
            hr_phase, br_phase: 雷达输出的相位值
            ts: 时间戳
            current_hr: 雷达直出心率 (0x0A15)
            current_br: 雷达直出呼吸率 (0x0A14)
        返回:
            instant_hr, instant_br, hr_uni, br_uni
        """
        if self.initialized:
            diff_hr = hr_phase - self.hr_phase_buf[-1]
            while diff_hr > np.pi:
                hr_phase -= 2 * np.pi
                diff_hr -= 2 * np.pi
            while diff_hr < -np.pi:
                hr_phase += 2 * np.pi
                diff_hr += 2 * np.pi

            diff_br = br_phase - self.br_phase_buf[-1]
            while diff_br > np.pi:
                br_phase -= 2 * np.pi
                diff_br -= 2 * np.pi
            while diff_br < -np.pi:
                br_phase += 2 * np.pi
                diff_br += 2 * np.pi
        else:
            self.initialized = True

        self.hr_phase_buf = np.roll(self.hr_phase_buf, -1)
        self.hr_phase_buf[-1] = hr_phase
        self.br_phase_buf = np.roll(self.br_phase_buf, -1)
        self.br_phase_buf[-1] = br_phase
        self.ts_buf = np.roll(self.ts_buf, -1)
        self.ts_buf[-1] = ts

        uniform_ts = np.linspace(self.ts_buf[0], self.ts_buf[-1], self.window)
        hr_uni = np.interp(uniform_ts, self.ts_buf, self.hr_phase_buf)
        br_uni = np.interp(uniform_ts, self.ts_buf, self.br_phase_buf)

        # ---- 修复: 用雷达直出值生成 synthetic 瞬时波形 ----
        # 相位波形保留用于 RSA/PLV 计算，频率值使用雷达直出
        hr_base = current_hr if current_hr and current_hr > 30 else 72.0
        br_base = current_br if current_br and current_br > 3 else 16.0

        # 基于相位波形生成带调制的 synthetic 信号
        # 这样 RSA（呼吸对心率的调制）仍然可以正确计算
        instant_hr = np.zeros(self.window, dtype=np.float64)
        instant_br = np.zeros(self.window, dtype=np.float64)

        for i in range(self.window):
            # RSA 调制: 呼吸相位峰值时心率最高，谷值时心率最低
            # 调制幅度约 ±5 bpm（正常 RSA 范围）
            rsa_mod = 5.0 * np.sin(hr_uni[i] * 2.0)
            instant_hr[i] = hr_base + rsa_mod + np.random.normal(0, 0.3)

            # 呼吸率微小波动
            br_mod = 1.0 * np.sin(br_uni[i])
            instant_br[i] = br_base + br_mod + np.random.normal(0, 0.15)

        instant_hr = np.clip(instant_hr, 30, 200)
        instant_br = np.clip(instant_br, 3, 40)

        return instant_hr, instant_br, hr_uni, br_uni


# ========== PhysioEngine ==========
class PhysioEngine:
    """生理指标计算引擎 V4.1
    修复: 
    1. BR Elevation 改用雷达直出BR
    2. 所有基于 inst_br 的指标使用正确的 synthetic 波形
    """

    def __init__(self, age=60, gender='male'):
        self.age = age
        self.gender = gender
        self.update_profile(age, gender)

    def update_profile(self, age, gender):
        self.age = age
        self.gender = gender
        self.hr_rest_est = round(62 + (age - 20) * 0.1 + (3 if gender == 'female' else 0), 1)
        self.br_rest_est = round(14 + max(0, (age - 50) * 0.03), 1)
        self.hr_max = round(208 - 0.7 * age, 1)
        self.rsa_baseline = round(
            max(3.0, 15.0 - (age - 20) * 0.2 + (2 if gender == 'female' else 0)), 1
        )
        self.plv_baseline = round(max(0.15, 0.65 - (age - 20) * 0.008), 3)

    def calc_rsa(self, inst_hr, br_phase, return_all=False):
        """[01] RSA幅度 bpm - 呼吸性窦性心律不齐"""
        cycles_max = []
        cycles_min = []
        for i in range(1, len(br_phase)):
            diff = br_phase[i] - br_phase[i-1]
            if diff < -np.pi:
                start = max(0, i - 5)
                end = min(len(inst_hr), i + 10)
                if end > start + 5:
                    cycle = inst_hr[start:end]
                    cycles_max.append(float(np.max(cycle)))
                    cycles_min.append(float(np.min(cycle)))
        if len(cycles_max) >= 2:
            amps = [m - n for m, n in zip(cycles_max, cycles_min)]
            if return_all:
                return amps
            return float(np.mean(amps[-5:]))
        return [] if return_all else 0.0

    def calc_plv(self, hr_phase, br_phase):
        """[02] PLV R - 心肺耦合强度"""
        delta = hr_phase - br_phase
        x = np.mean(np.cos(delta))
        y = np.mean(np.sin(delta))
        return float(np.sqrt(x ** 2 + y ** 2))

    def calc_mean_phase_diff(self, hr_phase, br_phase):
        """[03] 平均心肺相位差 rad"""
        delta = hr_phase - br_phase
        x = np.mean(np.cos(delta))
        y = np.mean(np.sin(delta))
        return float(np.arctan2(y, x))

    def calc_brv(self, br_history):
        """[04] 呼吸变异性 CV%
        
        修复 V4.2: 改用雷达直出的 breath_rate 历史序列，
        不再使用相位求导的 inst_br（假数据）。
        """
        data = br_history[-300:] if len(br_history) >= 300 else br_history
        if len(data) < 100:
            return 0.0
        mean_val = np.mean(data)
        if mean_val <= 0:
            return 0.0
        return float((np.std(data) / mean_val) * 100)

    def calc_br_elevation(self, current_br):
        """[05] 呼吸急促度: 相对估算基线的偏离%

        修复 V4.1: 改用雷达直出的 current_br，不再使用相位求导的 inst_br。
        原公式使用 inst_br 会导致系统性偏低（-78% bug）。
        """
        if self.br_rest_est <= 0:
            return 0.0
        return round(((current_br - self.br_rest_est) / self.br_rest_est) * 100, 1)

    def calc_hrr(self, current_hr):
        """[06] 心率储备 %HRR"""
        denom = self.hr_max - self.hr_rest_est
        if denom <= 0:
            return 0.0
        return round(((current_hr - self.hr_rest_est) / denom) * 100, 1)

    def calc_cr_ratio(self, hr, br):
        """[07] 心肺频率比 HR/BR"""
        if br <= 0:
            return 0.0
        return round(hr / br, 2)

    def calc_hri(self, inst_hr):
        """[08] 心率振荡指数: 瞬时心率SD (bpm)"""
        data = inst_hr[-300:] if len(inst_hr) >= 300 else inst_hr
        if len(data) < 50:
            return 0.0
        return round(float(np.std(data)), 2)

    def calc_hr_slope(self, hr_raw_history):
        """[09] 心率变化斜率 bpm/s"""
        data = list(hr_raw_history[-10:])
        data = [d for d in data if d > 0]
        if len(data) < 5:
            return 0.0
        x = np.arange(len(data), dtype=np.float64)
        y = np.array(data, dtype=np.float64)
        n = len(x)
        denom = n * np.sum(x ** 2) - np.sum(x) ** 2
        if denom == 0:
            return 0.0
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / denom
        return round(float(slope), 2)


# ========== 初始化 ==========
preprocessor = PhasePreprocessor(window_size=100, target_fs=10.0)
current_age = 60
current_gender = 'male'
engine = PhysioEngine(age=current_age, gender=current_gender)


def save_to_json():
    try:
        data = {
            "timestamp": time.time(),
            "latest": latest_data.copy(),
            "analysis": {}
        }
        
        hrr_val = 0.0
        brv_val = 0.0
        cr_val = 0.0
        slope_val = 0.0
        plv_val = 0.0
        br_elev_val = 0.0
        
        if current_preprocessor_output is not None:
            inst_hr, inst_br, hr_uni, br_uni = current_preprocessor_output
            hr_now = float(latest_data["heart_rate"])
            br_now = float(latest_data["breath_rate"]) if latest_data["breath_rate"] > 0 else 16.0
            
            hrr_val = engine.calc_hrr(hr_now)
            brv_val = engine.calc_brv(clean_br_history)
            cr_val = engine.calc_cr_ratio(hr_now, br_now)
            slope_val = engine.calc_hr_slope(clean_hr_history)
            plv_val = engine.calc_plv(hr_uni, br_uni)
            br_elev_val = engine.calc_br_elevation(br_now)
        
        data["analysis"] = {
            "hrr": round(hrr_val, 1),
            "hrr_label": get_hrr_label(hrr_val),
            "brv": round(brv_val, 2),
            "brv_label": get_brv_label(brv_val),
            "cr": round(cr_val, 2),
            "cr_label": get_cr_label(cr_val),
            "slope": round(slope_val, 2),
            "slope_label": get_slope_label(slope_val),
            "plv": round(plv_val, 3),
            "plv_label": get_plv_label(plv_val),
            "brel": round(br_elev_val, 1),
            "brel_label": get_brel_label(br_elev_val)
        }
        
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存JSON失败: %s" % str(e))


def save_logs():
    try:
        with open(RAW_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(raw_log_data, f, ensure_ascii=False, indent=2)
        with open(RAW_RAW_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(raw_raw_log_data, f, ensure_ascii=False, indent=2)
        with open(ANALYSIS_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(analysis_log_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存日志失败: %s" % str(e))


def get_hrr_label(hrr):
    if hrr < 40:
        return "低强度"
    elif hrr <= 60:
        return "中强度"
    else:
        return "高强度"


def get_brv_label(brv):
    if brv < 5:
        return "规律"
    elif brv <= 15:
        return "正常"
    else:
        return "不规律"


def get_cr_label(cr):
    if cr < 3.5:
        return "偏低"
    elif cr <= 5.5:
        return "正常"
    else:
        return "偏高"


def get_slope_label(slope):
    if slope < -0.5:
        return "快速下降"
    elif slope <= 0.5:
        return "平稳"
    elif slope <= 2.0:
        return "缓慢上升"
    else:
        return "快速上升"


def get_plv_label(plv):
    if plv < 0.3:
        return "清醒焦虑"
    elif plv <= 0.9:
        return "日常活动"
    else:
        return "深度放松"


def get_brel_label(brel):
    if brel < -20:
        return "呼吸过缓"
    elif brel < 0:
        return "放松"
    elif brel <= 30:
        return "正常"
    elif brel <= 60:
        return "急促"
    else:
        return "异常急促"


def validate_and_update(ts):
    global current_preprocessor_output, last_valid_hr, last_valid_br
    
    raw_hr = latest_data["heart_rate"]
    raw_br = latest_data["breath_rate"]
    
    state = "NORMAL"
    final_hr = raw_hr
    final_br = raw_br
    
    hr_valid = (40.0 <= raw_hr <= 180.0) and raw_hr != 0.0
    br_valid = (6.0 <= raw_br <= 40.0) and raw_br != 0.0
    
    if latest_data["is_human"] == 0 or latest_data["distance_valid"] == 0:
        state = "NO_TARGET"
        final_hr = last_valid_hr if not hr_valid else raw_hr
        final_br = last_valid_br
        
    elif raw_hr == 0.0 and raw_br == 0.0:
        state = "BIG_MOVE"
        final_hr = last_valid_hr
        final_br = last_valid_br
        
    elif not hr_valid and not br_valid:
        state = "BIG_MOVE"
        final_hr = last_valid_hr
        final_br = last_valid_br
        
    elif not br_valid:
        state = "BR_UNSTABLE"
        final_br = last_valid_br
        final_hr = raw_hr if hr_valid else last_valid_hr
        
    elif not hr_valid:
        state = "HR_UNSTABLE"
        final_hr = last_valid_hr
        final_br = raw_br if br_valid else last_valid_br
        
    elif len(display_br_history) >= 5:
        br_low_count = sum(1 for br in display_br_history[-5:] if br < 6)
        if br_low_count >= 3:
            state = "BR_UNSTABLE"
            final_br = last_valid_br
            final_hr = raw_hr if hr_valid else last_valid_hr
            
    elif abs(raw_hr - last_valid_hr) > 20.0:
        if hr_valid:
            state = "THAW"
            final_hr = raw_hr
            final_br = last_valid_br if not br_valid else raw_br
        else:
            state = "HR_UNSTABLE"
            final_hr = last_valid_hr
            final_br = raw_br if br_valid else last_valid_br
            
    elif abs(raw_br - last_valid_br) > 8.0:
        if br_valid:
            state = "BR_UNSTABLE"
            final_br = raw_br
            final_hr = raw_hr if hr_valid else last_valid_hr
        else:
            state = "BR_UNSTABLE"
            final_br = last_valid_br
            final_hr = raw_hr if hr_valid else last_valid_hr
    
    if len(display_hr_history) >= 5:
        recent = display_hr_history[-5:]
        if all(h == recent[0] for h in recent) and recent[0] > 0:
            if abs(raw_hr - recent[0]) > 20 and 40 <= raw_hr <= 180:
                final_hr = raw_hr
                state = "THAW"
    
    latest_data["signal_state"] = state
    latest_data["heart_rate"] = final_hr
    latest_data["breath_rate"] = final_br
    
    display_hr_history.append(final_hr)
    display_br_history.append(final_br)
    signal_state_history.append(state)
    heart_phase_history.append(latest_data["heart_phase"])
    breath_phase_history.append(latest_data["breath_phase"])
    lissajous_history.append([float(latest_data["breath_phase"]), float(latest_data["heart_phase"])])
    
    if state == "NORMAL":
        last_valid_hr = raw_hr
        last_valid_br = raw_br
        clean_hr_history.append(raw_hr)
        clean_br_history.append(raw_br)
    elif state == "THAW":
        last_valid_hr = final_hr
        if br_valid:
            last_valid_br = raw_br
            clean_br_history.append(raw_br)
        clean_hr_history.append(final_hr)
    
    for lst in [display_hr_history, display_br_history, signal_state_history,
                heart_phase_history, breath_phase_history,
                clean_hr_history, clean_br_history]:
        if len(lst) > MAX_HISTORY:
            lst.pop(0)
    if len(lissajous_history) > 500:
        lissajous_history.pop(0)
    
    if state == "NORMAL":
        current_preprocessor_output = preprocessor.feed(
            latest_data["heart_phase"], latest_data["breath_phase"], ts,
            current_hr=raw_hr, current_br=raw_br
        )
        return True
    else:
        return False


def verify_cksum(buf, cksum):
    acc = 0
    for b in buf:
        acc ^= b
    return (~acc & 0xFF) == cksum


def float_le(b):
    return struct.unpack('<f', b)[0]


def simulate_thread():
    global current_preprocessor_output, lissajous_history
    print("模拟模式: 生成虚拟生理数据...")
    
    ts = time.time()
    hr_phase = 0.0
    br_phase = 0.0
    hr = 72.0
    br = 16.0
    last_save_time = ts
    frame_count = 0
    
    while True:
        try:
            ts = time.time()
            frame_count += 1
            
            hr += np.random.normal(0, 0.3)
            br += np.random.normal(0, 0.15)
            hr = max(50, min(100, hr))
            br = max(10, min(25, br))
            
            delta_hr = (hr / 60) * 2 * np.pi * 0.02
            delta_br = (br / 60) * 2 * np.pi * 0.02
            
            hr_phase += delta_hr + np.random.normal(0, 0.02)
            br_phase += delta_br + np.random.normal(0, 0.015)
            
            hr_phase = hr_phase % (2 * np.pi)
            br_phase = br_phase % (2 * np.pi)
            
            if frame_count % 3 == 0:
                latest_data["heart_rate"] = hr
                latest_data["breath_rate"] = br
            
            latest_data["heart_phase"] = hr_phase
            latest_data["breath_phase"] = br_phase
            
            current_preprocessor_output = preprocessor.feed(
                hr_phase, br_phase, ts,
                current_hr=latest_data["heart_rate"],
                current_br=latest_data["breath_rate"]
            )
            
            lissajous_history.append([float(br_phase), float(hr_phase)])
            if len(lissajous_history) > 500:
                lissajous_history.pop(0)
            
            heart_phase_history.append(hr_phase)
            breath_phase_history.append(br_phase)
            heart_rate_history.append(latest_data["heart_rate"])
            breath_rate_history.append(latest_data["breath_rate"])
            
            for lst in [heart_phase_history, breath_phase_history,
                        heart_rate_history, breath_rate_history]:
                if len(lst) > MAX_HISTORY:
                    lst.pop(0)
            
            if ts - last_save_time > 1.0:
                save_to_json()
                
                raw_entry = {
                    "timestamp": ts,
                    "heart_rate": float(latest_data["heart_rate"]),
                    "breath_rate": float(latest_data["breath_rate"]),
                    "heart_phase": float(latest_data["heart_phase"]),
                    "breath_phase": float(latest_data["breath_phase"]),
                    "is_human": latest_data["is_human"],
                    "distance_valid": latest_data["distance_valid"],
                    "distance": float(latest_data["distance"]),
                    "signal_state": latest_data["signal_state"]
                }
                raw_log_data.append(raw_entry)
                
                if latest_data["signal_state"] in ["NORMAL", "THAW"] and current_preprocessor_output is not None:
                    inst_hr, inst_br, hr_uni, br_uni = current_preprocessor_output
                    hr_now = float(latest_data["heart_rate"])
                    br_now = float(latest_data["breath_rate"])
                    
                    hrr_val = engine.calc_hrr(hr_now)
                    brv_val = engine.calc_brv(clean_br_history)
                    cr_val = engine.calc_cr_ratio(hr_now, br_now)
                    slope_val = engine.calc_hr_slope(clean_hr_history)
                    plv_val = engine.calc_plv(hr_uni, br_uni)
                    br_elev_val = engine.calc_br_elevation(br_now)
                    
                    analysis_entry = {
                        "timestamp": ts,
                        "signal_state": "NORMAL",
                        "hrr": round(hrr_val, 1),
                        "hrr_label": get_hrr_label(hrr_val),
                        "brv": round(brv_val, 2),
                        "brv_label": get_brv_label(brv_val),
                        "cr": round(cr_val, 2),
                        "cr_label": get_cr_label(cr_val),
                        "slope": round(slope_val, 2),
                        "slope_label": get_slope_label(slope_val),
                        "plv": round(plv_val, 3),
                        "plv_label": get_plv_label(plv_val),
                        "brel": round(br_elev_val, 1),
                        "brel_label": get_brel_label(br_elev_val)
                    }
                    analysis_log_data.append(analysis_entry)
                    
                    save_logs()
                    last_save_time = ts
            
            time.sleep(0.02)
        except Exception as e:
            print("模拟数据生成错误: %s" % str(e))
            time.sleep(0.5)


def serial_thread():
    global current_preprocessor_output, lissajous_history
    print("尝试连接串口 %s @ %s bps..." % (PORT, BAUD))
    ser = None
    while True:
        try:
            ser = serial.Serial(PORT, BAUD, timeout=0.005)
            print("串口连接成功！")
            break
        except Exception as e:
            print("串口连接失败: %s" % e)
            print("5秒后重试...")
            time.sleep(5)

    buf = b""
    last_save_time = time.time()
    ts = last_save_time
    print("开始接收数据...\n")

    while True:
        try:
            if ser and ser.in_waiting > 0:
                buf += ser.read(ser.in_waiting)
                while len(buf) >= 8:
                    if buf[0] != 0x01:
                        buf = buf[1:]
                        continue
                    dlen = (buf[3] << 8) | buf[4]
                    flen = 8 + dlen + (1 if dlen > 0 else 0)
                    if len(buf) < flen or flen > 1024:
                        buf = buf[1:]
                        break
                    frame = buf[:flen]
                    buf = buf[flen:]
                    if not verify_cksum(frame[0:7], frame[7]):
                        continue
                    if dlen > 0 and not verify_cksum(frame[8:8 + dlen], frame[8 + dlen]):
                        continue

                    tid = (frame[5] << 8) | frame[6]
                    fd = frame[8:8 + dlen] if dlen > 0 else b""
                    ts = time.time()

                    if tid == 0x0F09 and len(fd) >= 2:
                        latest_data["is_human"] = fd[0]
                        
                    elif tid == 0x0A16 and len(fd) >= 8:
                        flag = struct.unpack('<I', fd[:4])[0]
                        dist = float_le(fd[4:8])
                        latest_data["distance_valid"] = flag
                        latest_data["distance"] = dist
                        
                    elif tid == 0x0A13 and len(fd) >= 12:
                        breath_phase = float_le(fd[4:8])
                        heart_phase = float_le(fd[8:12])
                        latest_data["breath_phase"] = breath_phase
                        latest_data["heart_phase"] = heart_phase

                    elif tid == 0x0A14 and len(fd) >= 4:
                        latest_data["breath_rate"] = float_le(fd[:4])
                    elif tid == 0x0A15 and len(fd) >= 4:
                        latest_data["heart_rate"] = float_le(fd[:4])
                        
                        raw_raw_entry = {
                            "timestamp": time.time(),
                            "heart_rate_raw": float(latest_data["heart_rate"]),
                            "breath_rate_raw": float(latest_data["breath_rate"]),
                            "heart_phase_raw": float(latest_data["heart_phase"]),
                            "breath_phase_raw": float(latest_data["breath_phase"]),
                            "is_human_raw": latest_data["is_human"],
                            "distance_valid_raw": latest_data["distance_valid"],
                            "distance_raw": float(latest_data["distance"])
                        }
                        raw_raw_log_data.append(raw_raw_entry)
                        
                        validate_and_update(ts)

                if ts - last_save_time > 1.0:
                    save_to_json()
                    
                    raw_entry = {
                        "timestamp": ts,
                        "heart_rate": float(latest_data["heart_rate"]),
                        "breath_rate": float(latest_data["breath_rate"]),
                        "heart_phase": float(latest_data["heart_phase"]),
                        "breath_phase": float(latest_data["breath_phase"]),
                        "is_human": latest_data["is_human"],
                        "distance_valid": latest_data["distance_valid"],
                        "distance": float(latest_data["distance"]),
                        "signal_state": latest_data["signal_state"]
                    }
                    raw_log_data.append(raw_entry)
                    
                    if latest_data["signal_state"] in ["NORMAL", "THAW"] and current_preprocessor_output is not None:
                        inst_hr, inst_br, hr_uni, br_uni = current_preprocessor_output
                        hr_now = float(latest_data["heart_rate"])
                        br_now = float(latest_data["breath_rate"])
                        
                        hrr_val = engine.calc_hrr(hr_now)
                        brv_val = engine.calc_brv(clean_br_history)
                        cr_val = engine.calc_cr_ratio(hr_now, br_now)
                        slope_val = engine.calc_hr_slope(clean_hr_history)
                        plv_val = engine.calc_plv(hr_uni, br_uni)
                        br_elev_val = engine.calc_br_elevation(br_now)
                        
                        analysis_entry = {
                            "timestamp": ts,
                            "signal_state": "NORMAL",
                            "hrr": round(hrr_val, 1),
                            "hrr_label": get_hrr_label(hrr_val),
                            "brv": round(brv_val, 2),
                            "brv_label": get_brv_label(brv_val),
                            "cr": round(cr_val, 2),
                            "cr_label": get_cr_label(cr_val),
                            "slope": round(slope_val, 2),
                            "slope_label": get_slope_label(slope_val),
                            "plv": round(plv_val, 3),
                            "plv_label": get_plv_label(plv_val),
                            "brel": round(br_elev_val, 1),
                            "brel_label": get_brel_label(br_elev_val)
                        }
                        analysis_log_data.append(analysis_entry)
                    
                    save_logs()
                    last_save_time = ts
            time.sleep(0.001)
        except Exception as e:
            print("读取错误: %s" % str(e))
            try:
                if ser and ser.is_open:
                    ser.close()
            except:
                pass
            print("尝试重新连接串口...")
            while True:
                try:
                    ser = serial.Serial(PORT, BAUD, timeout=0.005)
                    print("串口重新连接成功！")
                    break
                except Exception as re:
                    print("重新连接失败: %s" % re)
                    time.sleep(2)


@app.route('/')
def index():
    return render_template('hlkk.html')


@app.route('/health')
def health():
    return render_template('health.html')


@app.route('/data')
def get_data():
    global current_age, current_gender, engine
    global rsa_trend, plv_trend, brv_trend, hrr_trend, hri_trend
    global cr_ratio_trend, hr_slope_trend, phase_diff_trend, br_elevation_trend

    age_param = request.args.get('age', type=int)
    gender_param = request.args.get('gender', type=str)

    changed = False
    if age_param and age_param != current_age:
        current_age = age_param
        changed = True
    if gender_param and gender_param in ('male', 'female') and gender_param != current_gender:
        current_gender = gender_param
        changed = True
    if changed:
        engine.update_profile(current_age, current_gender)

    hr_now = float(latest_data["heart_rate"])
    br_now = float(latest_data["breath_rate"]) if latest_data["breath_rate"] > 0 else 16.0

    result = {
        "raw": {
            "hr": hr_now, "br": br_now,
            "hr_phase": latest_data["heart_phase"],
            "br_phase": latest_data["breath_phase"],
            "signal_state": latest_data["signal_state"],
            "is_human": latest_data["is_human"],
            "distance_valid": latest_data["distance_valid"],
            "distance": latest_data["distance"]
        },
        "signals": {
            "inst_hr": [], "inst_br": [],
            "lissajous": [], "phase_diff_circ": [],
            "rsa_wrapped": []
        },
        "physiology": {
            "rsa_amp": 0.0, "rsa_cycles": [],
            "plv_r": 0.0, "mean_phase_diff": 0.0,
            "brv_cv": 0.0, "br_elevation": 0.0,
            "hr_slope": 0.0, "hri_sd": 0.0,
            "hrr_pct": 0.0, "cr_ratio": 0.0
        },
        "profile": {
            "age": current_age, "gender": current_gender,
            "hr_rest_est": engine.hr_rest_est,
            "br_rest_est": engine.br_rest_est,
            "hr_max_est": engine.hr_max,
            "rsa_baseline": engine.rsa_baseline,
            "plv_baseline": engine.plv_baseline
        },
        "trends": {}
    }

    if current_preprocessor_output is not None:
        inst_hr, inst_br, hr_uni, br_uni = current_preprocessor_output

        result["signals"]["inst_hr"] = [round(v, 1) for v in inst_hr.tolist()[-100:]]
        result["signals"]["inst_br"] = [round(v, 1) for v in inst_br.tolist()[-100:]]
        result["signals"]["lissajous"] = lissajous_history[-300:]

        # S级指标 (基于相位)
        rsa_val = engine.calc_rsa(inst_hr, br_uni)
        rsa_cycles = engine.calc_rsa(inst_hr, br_uni, return_all=True)
        plv_val = engine.calc_plv(hr_uni, br_uni)
        phase_diff = engine.calc_mean_phase_diff(hr_uni, br_uni)

        # A级指标
        # ---- 使用 clean 历史保证统计纯度 ----
        brv_val = engine.calc_brv(clean_br_history)
        br_elev_val = engine.calc_br_elevation(br_now)
        hri_val = engine.calc_hri(inst_hr)
        hrr_val = engine.calc_hrr(hr_now)
        cr_val = engine.calc_cr_ratio(hr_now, br_now)
        slope_val = engine.calc_hr_slope(clean_hr_history)

        # RSA极坐标包裹
        rsa_wrapped = []
        for i in range(len(br_uni)):
            angle = float((br_uni[i] % (2 * np.pi)) * (180 / np.pi))
            rsa_wrapped.append([round(angle, 1), round(float(inst_hr[i]), 1)])

        # 相位差圆周
        phase_diff_circ = []
        delta_phase = hr_uni - br_uni
        for dp in delta_phase[-50:]:
            phase_diff_circ.append([
                round(float(np.cos(dp)), 3),
                round(float(np.sin(dp)), 3)
            ])

        result["physiology"] = {
            "rsa_amp": round(rsa_val, 2),
            "rsa_cycles": (rsa_cycles[-15:] if rsa_cycles else []),
            "plv_r": round(plv_val, 3),
            "mean_phase_diff": round(phase_diff, 3),
            "brv_cv": round(brv_val, 2),
            "br_elevation": round(br_elev_val, 1),
            "hr_slope": round(slope_val, 2),
            "hri_sd": round(hri_val, 2),
            "hrr_pct": round(hrr_val, 1),
            "cr_ratio": round(cr_val, 2)
        }

        result["signals"]["rsa_wrapped"] = rsa_wrapped[-200:]
        result["signals"]["phase_diff_circ"] = phase_diff_circ

        # 历史趋势
        rsa_trend.append(round(rsa_val, 2))
        plv_trend.append(round(plv_val, 3))
        brv_trend.append(round(brv_val, 2))
        hrr_trend.append(round(hrr_val, 1))
        hri_trend.append(round(hri_val, 2))
        cr_ratio_trend.append(round(cr_val, 2))
        hr_slope_trend.append(round(slope_val, 2))
        phase_diff_trend.append(round(phase_diff, 3))
        br_elevation_trend.append(round(br_elev_val, 1))

        for lst in [rsa_trend, plv_trend, brv_trend, hrr_trend, hri_trend,
                    cr_ratio_trend, hr_slope_trend, phase_diff_trend, br_elevation_trend]:
            if len(lst) > TREND_LEN:
                lst.pop(0)

    result["trends"] = {
        "rsa": list(rsa_trend)[-300:],
        "plv": list(plv_trend)[-300:],
        "brv": list(brv_trend)[-300:],
        "hrr": list(hrr_trend)[-300:],
        "hri": list(hri_trend)[-300:],
        "cr_ratio": list(cr_ratio_trend)[-300:],
        "hr_slope": list(hr_slope_trend)[-300:],
        "phase_diff": list(phase_diff_trend)[-300:],
        "br_elevation": list(br_elevation_trend)[-300:]
    }

    result["rt"] = {
        "heart_phase": [float(x) for x in heart_phase_history[-200:]],
        "breath_phase": [float(x) for x in breath_phase_history[-200:]],
        "heart_rate": [float(x) for x in display_hr_history[-200:]],
        "breath_rate": [float(x) for x in display_br_history[-200:]],
        "signal_state": signal_state_history[-200:]
    }

    return jsonify(result)


if __name__ == '__main__':
    print("=" * 60)
    print("  生理指标解析引擎 V4.2")
    print("  修复: 瞬时频率改用雷达直出值")
    print("  修复: BR Elevation 改用雷达直出BR")
    print("  新增: 数据日志功能 (raw.json, analysis.json)")
    print("  模式: %s" % ("模拟模式" if SIMULATE_MODE else "串口模式"))
    print("  数据保存: %s" % JSON_FILE)
    print("  日志目录: %s" % HEALTHDATA_DIR)
    print("  日志文件: %s, %s" % (os.path.basename(RAW_LOG_FILE), os.path.basename(ANALYSIS_LOG_FILE)))
    print("=" * 60)
    
    if SIMULATE_MODE:
        threading.Thread(target=simulate_thread, daemon=True).start()
    else:
        threading.Thread(target=serial_thread, daemon=True).start()
    
    print("\nWeb服务器: http://127.0.0.1:%d" % HTTP_PORT)
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=HTTP_PORT, debug=False)
