# -*- coding: utf-8 -*-
import struct
import serial
import time
import json
import threading
import os
import numpy as np
from scipy import signal
from scipy.stats import norm
from flask import Flask, render_template, jsonify, request

PORT = "COM9"
BAUD = 115200
HTTP_PORT = 5080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, 'hlk.json')

app = Flask(__name__, template_folder='templates', static_folder='static')

# ========== 全局数据存储 ==========
latest_data = {
    "heart_rate": 72,
    "breath_rate": 16,
    "heart_phase": 0.0,
    "breath_phase": 0.0
}

max_data_points = 300
heart_phase_history = []
breath_phase_history = []
heart_rate_history = []
breath_rate_history = []

for i in range(max_data_points):
    heart_phase_history.append(0.0)
    breath_phase_history.append(0.0)
    heart_rate_history.append(72)
    breath_rate_history.append(16)

lissajous_history = []
current_preprocessor_output = None

# 历史缓冲区
hrr_history = []
cr_history = []
brv_history = []
rsa_history = []
lock_r_history = []
cr_trajectory = []
phase_diff_history = []
cpli_history = []
cli_history = []
fsi_history = []
sdnn_history = []
rmssd_history = []
valence_history = []
arousal_history = []
hrv_optimal_history = []
hr_stability_history = []
ans_coord_history = []
br_hr_sync_history = []

# ========== PhasePreprocessor ==========
class PhasePreprocessor:
    def __init__(self, window_size=100, target_fs=10.0):
        self.window = window_size
        self.fs = target_fs
        self.hr_phase_buf = np.zeros(window_size, dtype=np.float64)
        self.br_phase_buf = np.zeros(window_size, dtype=np.float64)
        self.ts_buf = np.linspace(-window_size/target_fs, 0, window_size)
        self.initialized = False

    def feed(self, hr_phase, br_phase, ts):
        if self.initialized:
            diff_hr = hr_phase - self.hr_phase_buf[-1]
            if diff_hr > np.pi: hr_phase -= 2 * np.pi
            if diff_hr < -np.pi: hr_phase += 2 * np.pi
            diff_br = br_phase - self.br_phase_buf[-1]
            if diff_br > np.pi: br_phase -= 2 * np.pi
            if diff_br < -np.pi: br_phase += 2 * np.pi
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
        dt = 1.0 / self.fs
        instant_hr = (np.gradient(hr_uni, dt) / (2 * np.pi)) * 60
        instant_br = (np.gradient(br_uni, dt) / (2 * np.pi)) * 60
        instant_hr = np.clip(instant_hr, 30, 200)
        instant_br = np.clip(instant_br, 3, 40)
        return instant_hr, instant_br, hr_uni, br_uni

# ========== AdvancedPhysiologyCalculator ==========
class AdvancedPhysiologyCalculator:
    def __init__(self, age=60):
        self.age = age
        self.baseline_hr = 70
        self.baseline_br = 15
        self.update_age_profile(age)

    def update_age_profile(self, age):
        self.age = age
        self.hr_max = 208 - 0.7 * age
        self.rsa_baseline = max(3.0, 15.0 - (age - 20) * 0.2)
        self.lock_r_baseline = max(0.15, 0.65 - (age - 20) * 0.008)
        self.brv_anxiety_threshold = 2.5 if age > 65 else 4.0

    def calc_hrr(self, current_hr, rest_hr):
        if self.hr_max == rest_hr: return 0
        return ((current_hr - rest_hr) / (self.hr_max - rest_hr)) * 100

    def calc_cr(self, br, hr):
        if hr <= 0: return 0
        return (br / hr) * 60

    def calc_brv(self, instant_br_array):
        mean_br = np.mean(instant_br_array)
        if mean_br <= 0: return 0
        return (np.std(instant_br_array) / mean_br) * 100

    def calc_rsa_amplitude(self, instant_hr_array, br_phase_array, return_all=False):
        cycles_hr_max = []
        cycles_hr_min = []
        for i in range(1, len(br_phase_array)):
            if br_phase_array[i-1] > 5.5 and br_phase_array[i] <= 0.5 and br_phase_array[i] > -1.0:
                start_idx = max(0, i - 5)
                end_idx = min(len(instant_hr_array), i + int(10 * 1.0))
                if end_idx > start_idx + 5:
                    cycle_hr = instant_hr_array[start_idx:end_idx]
                    cycles_hr_max.append(np.max(cycle_hr))
                    cycles_hr_min.append(np.min(cycle_hr))
        if len(cycles_hr_max) >= 2:
            amplitudes = np.array(cycles_hr_max) - np.array(cycles_hr_min)
            if return_all:
                return [float(x) for x in amplitudes]
            return float(np.mean(amplitudes[-5:]))
        return [] if return_all else 0.0

    def calc_phase_lock_r(self, hr_phase_array, br_phase_array):
        delta_phase = hr_phase_array - br_phase_array
        x = np.mean(np.cos(delta_phase))
        y = np.mean(np.sin(delta_phase))
        R = np.sqrt(x**2 + y**2)
        return float(R)

    def compute_all_metrics(self, current_hr, current_br, preprocessor_data, rest_hr=65):
        instant_hr, instant_br, hr_uni, br_uni = preprocessor_data
        hrr = self.calc_hrr(current_hr, rest_hr)
        cr = self.calc_cr(current_br, current_hr)
        brv = self.calc_brv(instant_br[-60:]) if len(instant_br) >= 60 else 0
        rsa = self.calc_rsa_amplitude(instant_hr, br_uni)
        lock_r = self.calc_phase_lock_r(hr_uni, br_uni)
        is_cognitive_load = (current_hr > 70) and (rsa < self.rsa_baseline * 0.8) and (brv < self.brv_anxiety_threshold)
        is_startle = (lock_r < 0.1) and (cr < 3.0)
        return {
            "raw_physical": {"hrr": round(float(hrr), 1), "cr": round(float(cr), 2), "brv": round(float(brv), 2)},
            "ans_phase": {"rsa": round(float(rsa), 2), "lock_r": round(float(lock_r), 3)},
            "states": {"cognitive_load": bool(is_cognitive_load), "startle": bool(is_startle)},
            "baselines": {"hr_max_est": round(float(self.hr_max), 1), "rsa_est": round(float(self.rsa_baseline), 1),
                          "lock_est": round(float(self.lock_r_baseline), 2)}
        }

# ========== 保留原有计算引擎 ==========
class PhysiologyCalculator:
    def __init__(self, age=25, hr_rest=60):
        self.age = age
        self.hr_max = 220 - age
        self.hr_rest = hr_rest
        self.baseline_hr = 70
        self.baseline_rr = 15

    def compute_hrv(self, hr_history):
        hr = np.array(hr_history)
        hr = hr[hr > 0]
        if len(hr) < 5:
            return {'sdnn': 0, 'rmssd': 0, 'cvrr': 0, 'mrr': 0}
        rr_intervals = 60.0 / hr
        rr_ms = rr_intervals * 1000
        if len(rr_ms) < 2:
            return {'sdnn': 0, 'rmssd': 0, 'cvrr': 0, 'mrr': float(np.mean(rr_ms))}
        diff_rr = np.diff(rr_ms)
        sdnn = float(np.std(rr_ms, ddof=1))
        rmssd = float(np.sqrt(np.mean(diff_rr**2)))
        cvrr = float(np.std(rr_ms, ddof=1) / np.mean(rr_ms) * 100)
        mrr = float(np.mean(rr_ms))
        return {'sdnn': sdnn, 'rmssd': rmssd, 'cvrr': cvrr, 'mrr': mrr}

    def estimate_lf_hf(self, hr_mean, sdnn):
        lf_hf = 2.0 + (70 - hr_mean) / 20
        if sdnn > 0:
            lf_hf += (45 - sdnn) / 100
        return max(0.5, min(10.0, lf_hf))

    def compute_physiological_load(self, hr, br, hrv):
        hrr = (hr - self.hr_rest) / (self.hr_max - self.hr_rest) * 100
        lf_hf = self.estimate_lf_hf(hr, hrv['sdnn'])
        stress_index = min(100, lf_hf * 10)
        hf_norm = 100 / (1 + lf_hf)
        cpli = 0.3 * hrr/100 + 0.4 * stress_index/100 + 0.3 * (100 - hf_norm)/100
        return {
            'hrr': float(hrr), 'lf_hf': float(lf_hf), 'stress_index': float(stress_index),
            'hf_norm': float(hf_norm), 'cpli': float(min(1.0, max(0, cpli)))
        }

    def compute_cognitive_load(self, hr, br, hrv):
        hr_delta = hr - self.baseline_hr
        rr_delta = br - self.baseline_rr
        hrv_suppression = max(0, (50 - hrv['sdnn']) / 50 * 100) if hrv['sdnn'] > 0 else 0
        cli = 0.4 * hr_delta/30 + 0.3 * rr_delta/10 + 0.3 * hrv_suppression/100
        return {
            'hr_delta': float(hr_delta), 'rr_delta': float(rr_delta),
            'hrv_suppression': float(hrv_suppression), 'cli': float(min(1.0, max(0, cli)))
        }

    def compute_flow(self, hr, br, hrv):
        hrv_optimal = np.exp(-((hrv['sdnn'] - 45)**2)/(2*15**2)) if hrv['sdnn'] > 0 else 0.5
        hr_stability = np.exp(-((hrv['cvrr'] - 3.5)**2)/(2*1.5**2)) if hrv['cvrr'] > 0 else 0.5
        lf_hf = self.estimate_lf_hf(hr, hrv['sdnn'])
        ans_coord = np.exp(-((lf_hf - 1.5)**2)/(2*0.8**2))
        expected_rr = hr / 4
        br_hr_sync = np.exp(-((br - expected_rr)**2)/(2*2**2))
        fsi = np.mean([hrv_optimal, hr_stability, ans_coord, br_hr_sync])
        return {
            'hrv_optimal': float(hrv_optimal), 'hr_stability': float(hr_stability),
            'ans_coordination': float(ans_coord), 'br_hr_sync': float(br_hr_sync),
            'fsi': float(min(1.0, max(0, fsi)))
        }

    def compute_emotion(self, hr, br, hrv):
        arousal = 0.4 * min(1.0, max(0, (hr - 60)/60))
        arousal += 0.3 * min(1.0, max(0, (br - 10)/20))
        if hrv['sdnn'] > 0:
            arousal += 0.3 * min(1.0, max(0, (60 - hrv['sdnn'])/50))
        arousal = min(1.0, max(0, arousal))
        lf_hf = self.estimate_lf_hf(hr, hrv['sdnn'])
        valence = 0.5 + 0.3 * np.exp(-((lf_hf - 2)**2)/(2*1.5**2))
        if hrv['rmssd'] > 0:
            valence += 0.2 * min(1.0, hrv['rmssd']/50)
        valence = min(1.0, max(0, valence))
        if valence >= 0.5 and arousal >= 0.5: quadrant = "High Arousal Positive"
        elif valence >= 0.5 and arousal < 0.5: quadrant = "Low Arousal Positive"
        elif valence < 0.5 and arousal >= 0.5: quadrant = "High Arousal Negative"
        else: quadrant = "Low Arousal Negative"
        return {'valence': float(valence), 'arousal': float(arousal), 'quadrant': quadrant}

    def compute_all(self, hr, br, hr_history):
        hrv = self.compute_hrv(hr_history)
        phys = self.compute_physiological_load(hr, br, hrv)
        cog = self.compute_cognitive_load(hr, br, hrv)
        flow = self.compute_flow(hr, br, hrv)
        emotion = self.compute_emotion(hr, br, hrv)
        return {'hrv': hrv, 'physiological': phys, 'cognitive': cog, 'flow': flow, 'emotion': emotion}

# 初始化
preprocessor = PhasePreprocessor(window_size=100, target_fs=10.0)
current_age = 60
calc_adv = AdvancedPhysiologyCalculator(age=current_age)
calc_legacy = PhysiologyCalculator()

def save_to_json():
    try:
        data_to_save = {
            "timestamp": time.time(),
            "latest": latest_data.copy(),
            "history": {
                "heart_phase": list(heart_phase_history),
                "breath_phase": list(breath_phase_history),
                "heart_rate": list(heart_rate_history),
                "breath_rate": list(breath_rate_history)
            }
        }
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存JSON失败: %s" % str(e))

def verify_cksum(buf, cksum):
    acc = 0
    for b in buf:
        acc ^= b
    return (~acc & 0xFF) == cksum

def float_le(b):
    return struct.unpack('<f', b)[0]

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
                    if dlen > 0 and not verify_cksum(frame[8:8+dlen], frame[8+dlen]):
                        continue
                    tid = (frame[5] << 8) | frame[6]
                    fd = frame[8:8+dlen] if dlen > 0 else b""
                    ts = time.time()

                    if tid == 0x0A13 and len(fd) >= 12:
                        total_phase = float_le(fd[0:4])
                        breath_phase = float_le(fd[4:8])
                        heart_phase = float_le(fd[8:12])
                        latest_data["breath_phase"] = breath_phase
                        latest_data["heart_phase"] = heart_phase
                        current_preprocessor_output = preprocessor.feed(heart_phase, breath_phase, ts)
                        lissajous_history.append([float(breath_phase), float(heart_phase)])
                        if len(lissajous_history) > 500:
                            lissajous_history.pop(0)
                        heart_phase_history.append(heart_phase)
                        breath_phase_history.append(breath_phase)
                        heart_rate_history.append(latest_data["heart_rate"])
                        breath_rate_history.append(latest_data["breath_rate"])
                        if len(heart_phase_history) > max_data_points: heart_phase_history.pop(0)
                        if len(breath_phase_history) > max_data_points: breath_phase_history.pop(0)
                        if len(heart_rate_history) > max_data_points: heart_rate_history.pop(0)
                        if len(breath_rate_history) > max_data_points: breath_rate_history.pop(0)

                    elif tid == 0x0A14 and len(fd) >= 4:
                        latest_data["breath_rate"] = float_le(fd[:4])
                    elif tid == 0x0A15 and len(fd) >= 4:
                        latest_data["heart_rate"] = float_le(fd[:4])

                    if ts - last_save_time > 1.0:
                        save_to_json()
                        last_save_time = ts
            time.sleep(0.001)
        except Exception as e:
            print("读取错误: %s" % str(e))
            try:
                if ser and ser.is_open: ser.close()
            except: pass
            time.sleep(0.5)

@app.route('/')
def index():
    return render_template('hlkk.html')

@app.route('/data')
def get_data():
    global current_age, calc_adv, calc_legacy
    global hrr_history, cr_history, brv_history, rsa_history, lock_r_history, cr_trajectory
    global phase_diff_history, cpli_history, cli_history, fsi_history
    global sdnn_history, rmssd_history, valence_history, arousal_history
    global hrv_optimal_history, hr_stability_history, ans_coord_history, br_hr_sync_history

    age_param = request.args.get('age', type=int)
    if age_param and age_param != current_age:
        current_age = age_param
        calc_adv.update_age_profile(current_age)

    hr_current = latest_data["heart_rate"]
    br_current = latest_data["breath_rate"] if latest_data["breath_rate"] > 0 else 16

    br_cleaned = []
    for i, br in enumerate(breath_rate_history):
        if br == 0 and i > 0:
            br_cleaned.append(br_cleaned[-1] if br_cleaned[-1] > 0 else 7)
        else:
            br_cleaned.append(br)

    metrics_adv = None
    instant_hr_list = []
    instant_br_list = []
    hr_delta_list = []
    br_delta_list = []
    rsa_wrapped = []
    rsa_cycles = []
    lock_r_data = list(lock_r_history)
    phase_diff_list = list(phase_diff_history)
    brv_dynamic = []

    if current_preprocessor_output is not None:
        instant_hr, instant_br, hr_uni, br_uni = current_preprocessor_output
        metrics_adv = calc_adv.compute_all_metrics(hr_current, br_current, current_preprocessor_output, rest_hr=65)
        hrr_history.append(metrics_adv['raw_physical']['hrr'])
        cr_history.append(metrics_adv['raw_physical']['cr'])
        brv_history.append(metrics_adv['raw_physical']['brv'])
        rsa_history.append(metrics_adv['ans_phase']['rsa'])
        lock_r_history.append(metrics_adv['ans_phase']['lock_r'])
        cr_trajectory.append([hr_current, br_current])
        phase_diff = float(np.mean(hr_uni - br_uni))
        phase_diff_history.append(phase_diff)
        for buf in [hrr_history, cr_history, brv_history, rsa_history, lock_r_history, cr_trajectory, phase_diff_history]:
            if len(buf) > max_data_points: buf.pop(0)
        instant_hr_list = instant_hr.tolist()[-100:]
        instant_br_list = instant_br.tolist()[-100:]
        hr_delta = instant_hr - calc_adv.baseline_hr
        br_delta = instant_br - calc_adv.baseline_br
        hr_delta_list = hr_delta.tolist()[-100:]
        br_delta_list = br_delta.tolist()[-100:]
        for i in range(len(br_uni)):
            angle = float((br_uni[i] % (2 * np.pi)) * (180 / np.pi))
            rsa_wrapped.append([angle, float(instant_hr[i])])
        rsa_wrapped = rsa_wrapped[-200:]
        rsa_cycles = calc_adv.calc_rsa_amplitude(instant_hr, br_uni, return_all=True)
        if rsa_cycles: rsa_cycles = rsa_cycles[-15:]
        else: rsa_cycles = []
        lock_r_data = list(lock_r_history)[-100:]
        phase_diff_list = list(phase_diff_history)[-100:]
        instant_br_full = instant_br.tolist()
        for i in range(max(0, len(instant_br_full)-60), len(instant_br_full)):
            window = instant_br_full[max(0, i-10):i+1]
            if len(window) > 1 and np.mean(window) > 0:
                brv_dynamic.append((np.std(window) / np.mean(window)) * 100)
            else:
                brv_dynamic.append(0)

    metrics_legacy = calc_legacy.compute_all(hr_current, br_current, heart_rate_history)
    cpli_history.append(metrics_legacy['physiological']['cpli'])
    cli_history.append(metrics_legacy['cognitive']['cli'])
    fsi_history.append(metrics_legacy['flow']['fsi'])
    sdnn_history.append(metrics_legacy['hrv']['sdnn'])
    rmssd_history.append(metrics_legacy['hrv']['rmssd'])
    valence_history.append(metrics_legacy['emotion']['valence'])
    arousal_history.append(metrics_legacy['emotion']['arousal'])
    hrv_optimal_history.append(metrics_legacy['flow']['hrv_optimal'])
    hr_stability_history.append(metrics_legacy['flow']['hr_stability'])
    ans_coord_history.append(metrics_legacy['flow']['ans_coordination'])
    br_hr_sync_history.append(metrics_legacy['flow']['br_hr_sync'])
    for buf in [cpli_history, cli_history, fsi_history, sdnn_history, rmssd_history,
                valence_history, arousal_history, hrv_optimal_history, hr_stability_history,
                ans_coord_history, br_hr_sync_history]:
        if len(buf) > max_data_points: buf.pop(0)

    phase_diff_circ = []
    if len(phase_diff_history) >= 10:
        for pd_val in phase_diff_history[-50:]:
            phase_diff_circ.append([float(np.cos(pd_val)), float(np.sin(pd_val))])

    return jsonify({
        "heart_rate": latest_data["heart_rate"],
        "breath_rate": latest_data["breath_rate"],
        "heart_phase": latest_data["heart_phase"],
        "breath_phase": latest_data["breath_phase"],
        "rt": {
            "heart_phase": list(heart_phase_history),
            "breath_phase": list(breath_phase_history),
            "heart_rate": list(heart_rate_history),
            "breath_rate": br_cleaned
        },
        "instant_hr": instant_hr_list,
        "instant_br": instant_br_list,
        "hr_delta": hr_delta_list,
        "br_delta": br_delta_list,
        "rsa_wrapped": rsa_wrapped,
        "rsa_cycles": rsa_cycles,
        "lissajous": lissajous_history[-300:],
        "lock_r_history": lock_r_data,
        "cr_trajectory": cr_trajectory[-200:],
        "phase_diff_history": phase_diff_list,
        "phase_diff_circ": phase_diff_circ,
        "brv_dynamic": brv_dynamic[-100:] if brv_dynamic else [],
        "metrics_adv": metrics_adv,
        "metrics_legacy": metrics_legacy,
        "profile": {
            "age": current_age,
            "hr_max_est": round(calc_adv.hr_max, 1) if calc_adv else 0,
            "rsa_baseline": round(calc_adv.rsa_baseline, 1) if calc_adv else 0,
            "lock_r_baseline": round(calc_adv.lock_r_baseline, 2) if calc_adv else 0,
            "brv_threshold": calc_adv.brv_anxiety_threshold if calc_adv else 2.5
        },
        "trends": {
            "cpli": list(cpli_history)[-100:],
            "cli": list(cli_history)[-100:],
            "fsi": list(fsi_history)[-100:],
            "sdnn": list(sdnn_history)[-100:],
            "rmssd": list(rmssd_history)[-100:],
            "valence": list(valence_history)[-100:],
            "arousal": list(arousal_history)[-100:],
            "hrv_optimal": list(hrv_optimal_history)[-100:],
            "hr_stability": list(hr_stability_history)[-100:],
            "ans_coord": list(ans_coord_history)[-100:],
            "br_hr_sync": list(br_hr_sync_history)[-100:]
        }
    })

if __name__ == '__main__':
    print("=" * 60)
    print("HLK-LD6002 毫米波雷达 - 高级生理指标解析器 V3.0")
    print("支持: 相位动力学 / HRR / CR / BRV / RSA / 相位锁定 / HRV / 情绪 / 心流")
    print("数据将保存到: %s" % JSON_FILE)
    print("=" * 60)
    threading.Thread(target=serial_thread, daemon=True).start()
    print("\nWeb服务器运行在 http://127.0.0.1:%d" % HTTP_PORT)
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=HTTP_PORT, debug=False, use_reloader=False)