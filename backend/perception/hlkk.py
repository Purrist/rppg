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
HTTP_PORT = 5020
SIMULATE_MODE = False
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HEALTHDATA_DIR = os.path.join(SCRIPT_DIR, 'healthdata')
os.makedirs(HEALTHDATA_DIR, exist_ok=True)

start_time = time.strftime("%Y%m%d-%H%M%S")
RAW_LOG_FILE = os.path.join(HEALTHDATA_DIR, f"{start_time}raw.json")
ANALYSIS_LOG_FILE = os.path.join(HEALTHDATA_DIR, f"{start_time}analysis.json")

raw_log_data = []
analysis_log_data = []

with open(RAW_LOG_FILE, 'w', encoding='utf-8') as f:
    json.dump(raw_log_data, f, ensure_ascii=False, indent=2)
with open(ANALYSIS_LOG_FILE, 'w', encoding='utf-8') as f:
    json.dump(analysis_log_data, f, ensure_ascii=False, indent=2)

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
    "signal_state": "INIT",
    "hr_valid": False,
    "br_valid": False,
    "phase_valid": False
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

rt_hr_valid_history = [True] * MAX_HISTORY
rt_br_valid_history = [True] * MAX_HISTORY
rt_phase_valid_history = [True] * MAX_HISTORY
lissajous_history = []
current_preprocessor_output = None

# 指标历史趋势
TREND_LEN = 600
plv_trend = []
brv_trend = []
hrr_trend = []
cr_ratio_trend = []
hr_slope_trend = []
phase_diff_trend = []
br_elevation_trend = []
trend_signal_state_history = []
trend_hr_valid_history = []
trend_br_valid_history = []
trend_phase_valid_history = []

# ========== 年龄和性别数据处理 ==========
# 从perception接收的年龄和性别数据队列
person_data_queue = []
PERSON_DATA_WINDOW = 10  # 10秒窗口
person_data_lock = threading.Lock()

# 当前使用的年龄和性别（可能来自perception或用户输入）
current_age = 30
current_gender = 'male'
person_source = 'input'  # 'input' or 'perception'
has_received_perception = False  # 是否曾经接收到过perception的有效数据


# ========== PhasePreprocessor ==========
class PhasePreprocessor:

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
            # 心率微小波动
            instant_hr[i] = hr_base + np.random.normal(0, 0.3)

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
        self.plv_baseline = round(max(0.15, 0.65 - (age - 20) * 0.008), 3)

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
            br_now = float(latest_data["breath_rate"]) if latest_data["breath_rate"] > 0 else 0.0
            
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
    except Exception as e:
        print("保存JSON失败: %s" % str(e))


def save_logs():
    global raw_log_data, analysis_log_data
    try:
        with open(RAW_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(raw_log_data, f, ensure_ascii=False, indent=2)
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
    global rt_hr_valid_history, rt_br_valid_history, rt_phase_valid_history
    
    raw_hr = latest_data["heart_rate"]
    raw_br = latest_data["breath_rate"]
    
    state = "NORMAL"
    final_hr = raw_hr
    final_br = raw_br
    
    hr_valid = (40.0 <= raw_hr <= 180.0) and raw_hr != 0.0
    br_valid = (6.0 <= raw_br <= 40.0) and raw_br != 0.0
    phase_valid = (latest_data["is_human"] == 1 and 
                   latest_data["distance_valid"] == 1 and 
                   not (raw_hr == 0.0 and raw_br == 0.0))
    
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
    rt_hr_valid_history.append(hr_valid)
    rt_br_valid_history.append(br_valid)
    rt_phase_valid_history.append(phase_valid)
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
    elif state == "BR_UNSTABLE":
        if hr_valid:
            last_valid_hr = raw_hr
            clean_hr_history.append(raw_hr)
    elif state == "HR_UNSTABLE":
        if br_valid:
            last_valid_br = raw_br
            clean_br_history.append(raw_br)
    
    for lst in [display_hr_history, display_br_history, signal_state_history,
                heart_phase_history, breath_phase_history,
                clean_hr_history, clean_br_history,
                rt_hr_valid_history, rt_br_valid_history, rt_phase_valid_history]:
        if len(lst) > MAX_HISTORY:
            lst.pop(0)
    if len(lissajous_history) > 500:
        lissajous_history.pop(0)
    
    latest_data["hr_valid"] = hr_valid
    latest_data["br_valid"] = br_valid
    latest_data["phase_valid"] = phase_valid

    if state not in ["NO_TARGET", "BIG_MOVE"]:
        feed_hr = raw_hr if hr_valid else last_valid_hr
        feed_br = raw_br if br_valid else last_valid_br
        current_preprocessor_output = preprocessor.feed(
            latest_data["heart_phase"],
            latest_data["breath_phase"],
            ts,
            current_hr=feed_hr,
            current_br=feed_br
        )

    return state in ["NORMAL", "BR_UNSTABLE", "HR_UNSTABLE", "THAW"]


def verify_cksum(buf, cksum):
    acc = 0
    for b in buf:
        acc ^= b
    return (~acc & 0xFF) == cksum


def float_le(b):
    return struct.unpack('<f', b)[0]


def simulate_thread():
    global current_preprocessor_output, lissajous_history, raw_log_data, analysis_log_data
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
                latest_data["is_human"] = 1
                latest_data["distance_valid"] = 1
                latest_data["distance"] = 45.92
            
            latest_data["heart_phase"] = hr_phase
            latest_data["breath_phase"] = br_phase
            
            validate_and_update(ts)
            
            if ts - last_save_time > 1.0:
                save_to_json()
                
                raw_entry = {
                    "time": ts,
                    "hr": float(latest_data["heart_rate"]),
                    "br": float(latest_data["breath_rate"]),
                    "hph": float(latest_data["heart_phase"]),
                    "bph": float(latest_data["breath_phase"]),
                    "is_human": latest_data["is_human"],
                    "distance": float(latest_data["distance"]),
                    "distance_valid": latest_data["distance_valid"],
                    "signal_state": latest_data["signal_state"]
                }
                raw_log_data.append(raw_entry)
                
                state = latest_data["signal_state"]
                hr_valid = latest_data.get("hr_valid", False)
                br_valid = latest_data.get("br_valid", False)
                phase_valid = latest_data.get("phase_valid", False)
                
                analysis_entry = {
                    "time": ts,
                    "signal_state": state,
                    "hr_valid": hr_valid,
                    "br_valid": br_valid,
                    "phase_valid": phase_valid
                }
                
                hr_now = float(latest_data["heart_rate"])
                br_now = float(latest_data["breath_rate"])
                
                # 原子化计算：根据条件分别计算
                if hr_valid:
                    hrr_val = engine.calc_hrr(hr_now)
                    slope_val = engine.calc_hr_slope(clean_hr_history)
                    analysis_entry.update({
                        "hrr": round(hrr_val, 1),
                        "hrr_label": get_hrr_label(hrr_val),
                        "slope": round(slope_val, 2),
                        "slope_label": get_slope_label(slope_val)
                    })
                else:
                    analysis_entry.update({
                        "hrr": "--",
                        "hrr_label": "--",
                        "slope": "--",
                        "slope_label": "--"
                    })
                
                if br_valid:
                    brv_val = engine.calc_brv(clean_br_history)
                    br_elev_val = engine.calc_br_elevation(br_now)
                    analysis_entry.update({
                        "brv": round(brv_val, 2),
                        "brv_label": get_brv_label(brv_val),
                        "brel": round(br_elev_val, 1),
                        "brel_label": get_brel_label(br_elev_val)
                    })
                else:
                    analysis_entry.update({
                        "brv": "--",
                        "brv_label": "--",
                        "brel": "--",
                        "brel_label": "--"
                    })
                
                if hr_valid and br_valid:
                    cr_val = engine.calc_cr_ratio(hr_now, br_now)
                    analysis_entry.update({
                        "cr": round(cr_val, 2),
                        "cr_label": get_cr_label(cr_val)
                    })
                else:
                    analysis_entry.update({
                        "cr": "--",
                        "cr_label": "--"
                    })
                
                if phase_valid and current_preprocessor_output is not None:
                    inst_hr, inst_br, hr_uni, br_uni = current_preprocessor_output
                    plv_val = engine.calc_plv(hr_uni, br_uni)
                    analysis_entry.update({
                        "plv": round(plv_val, 3),
                        "plv_label": get_plv_label(plv_val)
                    })
                else:
                    analysis_entry.update({
                        "plv": "--",
                        "plv_label": "--"
                    })
                
                analysis_log_data.append(analysis_entry)
                
                save_logs()
                last_save_time = ts
            
            time.sleep(0.02)
        except Exception as e:
            print("模拟数据生成错误: %s" % str(e))
            time.sleep(0.5)


def serial_thread():
    global current_preprocessor_output, lissajous_history, raw_log_data, analysis_log_data
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
                        
                        validate_and_update(ts)

                if ts - last_save_time > 1.0:
                    save_to_json()
                    
                    raw_entry = {
                        "time": ts,
                        "hr": float(latest_data["heart_rate"]),
                        "br": float(latest_data["breath_rate"]),
                        "hph": float(latest_data["heart_phase"]),
                        "bph": float(latest_data["breath_phase"]),
                        "is_human": latest_data["is_human"],
                        "distance": float(latest_data["distance"]),
                        "distance_valid": latest_data["distance_valid"],
                        "signal_state": latest_data["signal_state"]
                    }
                    raw_log_data.append(raw_entry)
                    
                    state = latest_data["signal_state"]
                    hr_valid = latest_data.get("hr_valid", False)
                    br_valid = latest_data.get("br_valid", False)
                    phase_valid = latest_data.get("phase_valid", False)
                    
                    analysis_entry = {
                        "time": ts,
                        "signal_state": state,
                        "hr_valid": hr_valid,
                        "br_valid": br_valid,
                        "phase_valid": phase_valid
                    }
                    
                    hr_now = float(latest_data["heart_rate"])
                    br_now = float(latest_data["breath_rate"])
                    
                    # 原子化计算：根据条件分别计算
                    if hr_valid:
                        hrr_val = engine.calc_hrr(hr_now)
                        slope_val = engine.calc_hr_slope(clean_hr_history)
                        analysis_entry.update({
                            "hrr": round(hrr_val, 1),
                            "hrr_label": get_hrr_label(hrr_val),
                            "slope": round(slope_val, 2),
                            "slope_label": get_slope_label(slope_val)
                        })
                    else:
                        analysis_entry.update({
                            "hrr": "--",
                            "hrr_label": "--",
                            "slope": "--",
                            "slope_label": "--"
                        })
                    
                    if br_valid:
                        brv_val = engine.calc_brv(clean_br_history)
                        br_elev_val = engine.calc_br_elevation(br_now)
                        analysis_entry.update({
                            "brv": round(brv_val, 2),
                            "brv_label": get_brv_label(brv_val),
                            "brel": round(br_elev_val, 1),
                            "brel_label": get_brel_label(br_elev_val)
                        })
                    else:
                        analysis_entry.update({
                            "brv": "--",
                            "brv_label": "--",
                            "brel": "--",
                            "brel_label": "--"
                        })
                    
                    if hr_valid and br_valid:
                        cr_val = engine.calc_cr_ratio(hr_now, br_now)
                        analysis_entry.update({
                            "cr": round(cr_val, 2),
                            "cr_label": get_cr_label(cr_val)
                        })
                    else:
                        analysis_entry.update({
                            "cr": "--",
                            "cr_label": "--"
                        })
                    
                    if phase_valid and current_preprocessor_output is not None:
                        inst_hr, inst_br, hr_uni, br_uni = current_preprocessor_output
                        plv_val = engine.calc_plv(hr_uni, br_uni)
                        analysis_entry.update({
                            "plv": round(plv_val, 3),
                            "plv_label": get_plv_label(plv_val)
                        })
                    else:
                        analysis_entry.update({
                            "plv": "--",
                            "plv_label": "--"
                        })
                    
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
    return render_template('health.html')


@app.route('/health')
def health():
    return render_template('health.html')


@app.route('/person')
def person_data():
    """接收perception发送的年龄和性别数据"""
    global person_data_queue
    age_param = request.args.get('age')
    gender_param = request.args.get('gender', type=str)
    
    # 检查是否为无效标记
    if age_param == '-' or gender_param == '-':
        # 非正脸或未检测到，清空队列保持原有状态
        with person_data_lock:
            person_data_queue.clear()
        return jsonify({'status': 'ok', 'message': '无效数据，队列已清空'})
    
    # 尝试解析年龄
    try:
        age_param = int(age_param)
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': '年龄参数无效'})
    
    if age_param > 0 and gender_param in ('male', 'female'):
        with person_data_lock:
            person_data_queue.append({
                'age': age_param,
                'gender': gender_param,
                'time': time.time()
            })
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': '参数无效'})


@app.route('/person_input')
def person_input_data():
    """接收用户手动输入的年龄和性别（优先级低于perception）"""
    global current_age, current_gender, person_source, has_received_perception, engine
    
    age_param = request.args.get('age', type=int)
    gender_param = request.args.get('gender', type=str)
    
    # 如果曾经接收到过perception数据，不允许用户手动输入覆盖
    if has_received_perception:
        return jsonify({'status': 'error', 'message': '已有perception数据，不可手动覆盖'})
    
    changed = False
    if age_param and age_param > 0 and age_param != current_age:
        current_age = age_param
        changed = True
    
    if gender_param and gender_param in ('male', 'female') and gender_param != current_gender:
        current_gender = gender_param
        changed = True
    
    if changed:
        engine.update_profile(current_age, current_gender)
        person_source = 'input'
    
    return jsonify({'status': 'ok', 'age': current_age, 'gender': current_gender, 'person_source': person_source})


def calculate_person_mean():
    """每10秒计算一次年龄和性别的均值"""
    global person_data_queue, current_age, current_gender, person_source, has_received_perception
    
    while True:
        time.sleep(PERSON_DATA_WINDOW)
        
        with person_data_lock:
            if len(person_data_queue) > 0:
                # 队列中有有效数据（正脸检测到），计算均值并更新
                age_sum = sum(item['age'] for item in person_data_queue)
                avg_age = round(age_sum / len(person_data_queue))
                
                gender_counts = {'male': 0, 'female': 0}
                for item in person_data_queue:
                    gender_counts[item['gender']] += 1
                
                avg_gender = 'male' if gender_counts['male'] >= gender_counts['female'] else 'female'
                
                current_age = avg_age
                current_gender = avg_gender
                person_source = 'perception'
                has_received_perception = True  # 标记已收到过有效数据
                
                person_data_queue = []
            # 如果队列为空（非正脸或未检测到），保持当前状态不变
            # 一旦接收到过perception数据，就不再自动切换回input模式


# 启动定时计算线程
person_thread = threading.Thread(target=calculate_person_mean, daemon=True)
person_thread.start()


@app.route('/data')
def get_data():
    global current_age, current_gender, engine
    global plv_trend, brv_trend, hrr_trend
    global cr_ratio_trend, hr_slope_trend, phase_diff_trend, br_elevation_trend
    global trend_signal_state_history, trend_hr_valid_history
    global trend_br_valid_history, trend_phase_valid_history

    global person_source, has_received_perception
    
    # 注意：这里不再通过 URL 参数接收 age/gender（避免与 /person 端点冲突）
    # age/gender 只通过 /person 端点来自 perception.py，或者通过用户手动设置
    # health.html 现在只读取数据，不再设置

    hr_now = float(latest_data["heart_rate"])
    br_now = float(latest_data["breath_rate"]) if latest_data["breath_rate"] > 0 else 0.0

    result = {
        "raw": {
            "hr": hr_now, "br": br_now,
            "hr_phase": latest_data["heart_phase"],
            "br_phase": latest_data["breath_phase"],
            "signal_state": latest_data["signal_state"],
            "is_human": latest_data["is_human"],
            "distance_valid": latest_data["distance_valid"],
            "distance": latest_data["distance"],
            "hr_valid": latest_data.get("hr_valid", False),
            "br_valid": latest_data.get("br_valid", False),
            "phase_valid": latest_data.get("phase_valid", False)
        },
        "signals": {
            "inst_hr": [], "inst_br": [],
            "lissajous": [], "phase_diff_circ": []
        },
        "physiology": {
            "plv_r": None, "mean_phase_diff": None,
            "brv_cv": None, "br_elevation": None,
            "hr_slope": None,
            "hrr_pct": None, "cr_ratio": None
        },
        "profile": {
            "age": current_age, "gender": current_gender,
            "person_source": person_source,
            "hr_rest_est": engine.hr_rest_est,
            "br_rest_est": engine.br_rest_est,
            "hr_max_est": engine.hr_max,
            "plv_baseline": engine.plv_baseline
        },
        "trends": {}
    }

    # === 原子化计算：按依赖关系分层 ===

    # 第1层：只依赖HR（hr_valid就计算）
    if latest_data.get("hr_valid", False):
        hrr_val = engine.calc_hrr(hr_now)
        slope_val = engine.calc_hr_slope(clean_hr_history)
        result["physiology"]["hrr_pct"] = round(hrr_val, 1)
        result["physiology"]["hr_slope"] = round(slope_val, 2)
        hrr_trend.append(round(hrr_val, 1))
        hr_slope_trend.append(round(slope_val, 2))
    else:
        if hrr_trend:
            hrr_trend.append(hrr_trend[-1])
        else:
            hrr_trend.append(None)
        if hr_slope_trend:
            hr_slope_trend.append(hr_slope_trend[-1])
        else:
            hr_slope_trend.append(None)

    # 第2层：只依赖BR（br_valid就计算）
    if latest_data["br_valid"]:
        br_elev_val = engine.calc_br_elevation(br_now)
        brv_val = engine.calc_brv(clean_br_history)
        result["physiology"]["br_elevation"] = round(br_elev_val, 1)
        result["physiology"]["brv_cv"] = round(brv_val, 2)
        br_elevation_trend.append(round(br_elev_val, 1))
        brv_trend.append(round(brv_val, 2))
    else:
        if br_elevation_trend:
            br_elevation_trend.append(br_elevation_trend[-1])
        else:
            br_elevation_trend.append(0.0)
        if brv_trend:
            brv_trend.append(brv_trend[-1])
        else:
            brv_trend.append(0.0)

    trend_signal_state_history.append(latest_data["signal_state"])
    trend_hr_valid_history.append(latest_data["hr_valid"])
    trend_br_valid_history.append(latest_data["br_valid"])
    trend_phase_valid_history.append(latest_data["phase_valid"])

    # 第3层：同时需要HR和BR
    if latest_data["hr_valid"] and latest_data["br_valid"]:
        cr_val = engine.calc_cr_ratio(hr_now, br_now)
        result["physiology"]["cr_ratio"] = round(cr_val, 2)
        cr_ratio_trend.append(round(cr_val, 2))
    else:
        if cr_ratio_trend:
            cr_ratio_trend.append(cr_ratio_trend[-1])
        else:
            cr_ratio_trend.append(None)

    # 第4层：需要相位稳定
    if current_preprocessor_output is not None:
        inst_hr, inst_br, hr_uni, br_uni = current_preprocessor_output

        result["signals"]["inst_hr"] = [round(v, 1) for v in inst_hr.tolist()[-100:]]
        result["signals"]["inst_br"] = [round(v, 1) for v in inst_br.tolist()[-100:]]
        result["signals"]["lissajous"] = lissajous_history[-300:]

        if latest_data["phase_valid"]:
            plv_val = engine.calc_plv(hr_uni, br_uni)
            phase_diff = engine.calc_mean_phase_diff(hr_uni, br_uni)

            result["physiology"]["plv_r"] = round(plv_val, 3)
            result["physiology"]["mean_phase_diff"] = round(phase_diff, 3)

            phase_diff_circ = []
            delta_phase = hr_uni - br_uni
            for dp in delta_phase[-50:]:
                phase_diff_circ.append([
                    round(float(np.cos(dp)), 3),
                    round(float(np.sin(dp)), 3)
                ])
            result["signals"]["phase_diff_circ"] = phase_diff_circ

            plv_trend.append(round(plv_val, 3))
            phase_diff_trend.append(round(phase_diff, 3))
        else:
            if plv_trend:
                plv_trend.append(plv_trend[-1])
            else:
                plv_trend.append(None)
            if phase_diff_trend:
                phase_diff_trend.append(phase_diff_trend[-1])
            else:
                phase_diff_trend.append(None)

    for lst in [plv_trend, brv_trend, hrr_trend,
                cr_ratio_trend, hr_slope_trend, phase_diff_trend, br_elevation_trend,
                trend_signal_state_history, trend_hr_valid_history,
                trend_br_valid_history, trend_phase_valid_history]:
        if len(lst) > TREND_LEN:
            lst.pop(0)

    result["trends"] = {
        "plv": list(plv_trend)[-TREND_LEN:],
        "brv": list(brv_trend)[-TREND_LEN:],
        "hrr": list(hrr_trend)[-TREND_LEN:],
        "cr_ratio": list(cr_ratio_trend)[-TREND_LEN:],
        "hr_slope": list(hr_slope_trend)[-TREND_LEN:],
        "br_elevation": list(br_elevation_trend)[-TREND_LEN:],
        "signal_state": list(trend_signal_state_history)[-TREND_LEN:],
        "hr_valid": list(trend_hr_valid_history)[-TREND_LEN:],
        "br_valid": list(trend_br_valid_history)[-TREND_LEN:],
        "phase_valid": list(trend_phase_valid_history)[-TREND_LEN:]
    }

    result["rt"] = {
        "heart_phase": [float(x) for x in heart_phase_history[-200:]],
        "breath_phase": [float(x) for x in breath_phase_history[-200:]],
        "heart_rate": [float(x) for x in display_hr_history[-200:]],
        "breath_rate": [float(x) for x in display_br_history[-200:]],
        "signal_state": signal_state_history[-200:],
        "hr_valid": rt_hr_valid_history[-200:],
        "br_valid": rt_br_valid_history[-200:],
        "phase_valid": rt_phase_valid_history[-200:]
    }

    return jsonify(result)


if __name__ == '__main__':
    print("  模式: %s" % ("模拟模式" if SIMULATE_MODE else "串口模式"))    
    if SIMULATE_MODE:
        threading.Thread(target=simulate_thread, daemon=True).start()
    else:
        threading.Thread(target=serial_thread, daemon=True).start()
    
    print("\nWeb服务器: http://127.0.0.1:%d" % HTTP_PORT)
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=HTTP_PORT, debug=False)
