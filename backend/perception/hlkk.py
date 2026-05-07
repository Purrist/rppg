# -*- coding: utf-8 -*-
import struct
import serial
import time
import json
import threading
import os
import numpy as np
from flask import Flask, render_template, jsonify, request, send_from_directory

PORT = "COM9"
BAUD = 115200
HTTP_PORT = 5080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, 'hlk.json')

app = Flask(__name__, template_folder='templates', static_folder='static')

# ========== 全局数据存储 ==========
latest_data = {
    "heart_rate": 72.0,
    "breath_rate": 16.0,
    "heart_phase": 0.0,
    "breath_phase": 0.0
}

MAX_HISTORY = 600
heart_phase_history = [0.0] * MAX_HISTORY
breath_phase_history = [0.0] * MAX_HISTORY
heart_rate_history = [72.0] * MAX_HISTORY
breath_rate_history = [16.0] * MAX_HISTORY
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
    """相位预处理器: 解卷绕 -> 重采样10Hz -> 求导得瞬时频率"""

    def __init__(self, window_size=100, target_fs=10.0):
        self.window = window_size
        self.fs = target_fs
        self.hr_phase_buf = np.zeros(window_size, dtype=np.float64)
        self.br_phase_buf = np.zeros(window_size, dtype=np.float64)
        self.ts_buf = np.linspace(-window_size / target_fs, 0, window_size)
        self.initialized = False

    def feed(self, hr_phase, br_phase, ts):
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

        dt = 1.0 / self.fs
        instant_hr = (np.gradient(hr_uni, dt) / (2 * np.pi)) * 60
        instant_br = (np.gradient(br_uni, dt) / (2 * np.pi)) * 60

        instant_hr = np.clip(instant_hr, 30, 200)
        instant_br = np.clip(instant_br, 3, 40)

        return instant_hr, instant_br, hr_uni, br_uni


# ========== PhysioEngine ==========
class PhysioEngine:
    """生理指标计算引擎 V4.0
    所有指标均有真实生理学意义，无伪造公式
    """

    def __init__(self, age=60, gender='male'):
        self.age = age
        self.gender = gender
        self.update_profile(age, gender)

    def update_profile(self, age, gender):
        self.age = age
        self.gender = gender
        # 估算静息心率: 成年男性基线约62bpm, 女性+3, 每增10岁+1
        self.hr_rest_est = round(62 + (age - 20) * 0.1 + (3 if gender == 'female' else 0), 1)
        # 估算静息呼吸率
        self.br_rest_est = round(14 + max(0, (age - 50) * 0.03), 1)
        # 最大心率 (Tanaka 2001)
        self.hr_max = round(208 - 0.7 * age, 1)
        # RSA年龄基线 (男性20岁约15bpm, 每10岁降2, 女性+2)
        self.rsa_baseline = round(
            max(3.0, 15.0 - (age - 20) * 0.2 + (2 if gender == 'female' else 0)), 1
        )
        # PLV基线
        self.plv_baseline = round(max(0.15, 0.65 - (age - 20) * 0.008), 3)

    # ---- S级: 心肺动力学 (基于相位) ----

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
        """[02] 相位锁定值 PLV R - 心肺耦合强度 Rayleigh Test"""
        delta = hr_phase - br_phase
        x = np.mean(np.cos(delta))
        y = np.mean(np.sin(delta))
        return float(np.sqrt(x ** 2 + y ** 2))

    def calc_mean_phase_diff(self, hr_phase, br_phase):
        """[03] 平均心肺相位差 (圆周均值, rad)"""
        delta = hr_phase - br_phase
        x = np.mean(np.cos(delta))
        y = np.mean(np.sin(delta))
        return float(np.arctan2(y, x))

    # ---- A级: 呼吸节律 ----

    def calc_brv(self, inst_br):
        """[04] 呼吸变异性 CV% (30秒窗口=300点)"""
        data = inst_br[-300:] if len(inst_br) >= 300 else inst_br
        if len(data) < 100:
            return 0.0
        mean_val = np.mean(data)
        if mean_val <= 0:
            return 0.0
        return float((np.std(data) / mean_val) * 100)

    def calc_br_elevation(self, inst_br):
        """[05] 呼吸急促度: 相对估算基线的偏离%"""
        data = inst_br[-150:] if len(inst_br) >= 150 else inst_br
        if len(data) < 50:
            return 0.0
        current_mean = np.mean(data)
        if self.br_rest_est <= 0:
            return 0.0
        return round(((current_mean - self.br_rest_est) / self.br_rest_est) * 100, 1)

    # ---- A级: 心率动力学 (基于雷达直出) ----

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
        """[08] 心率振荡指数: 瞬时心率SD (30秒窗口, bpm)"""
        data = inst_hr[-300:] if len(inst_hr) >= 300 else inst_hr
        if len(data) < 50:
            return 0.0
        return round(float(np.std(data)), 2)

    def calc_hr_slope(self, hr_raw_history):
        """[09] 心率变化斜率 bpm/s (雷达直出HR, 10秒线性回归)"""
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
        data = {"timestamp": time.time(), "latest": latest_data.copy()}
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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

                    if tid == 0x0A13 and len(fd) >= 12:
                        breath_phase = float_le(fd[4:8])
                        heart_phase = float_le(fd[8:12])
                        latest_data["breath_phase"] = breath_phase
                        latest_data["heart_phase"] = heart_phase

                        current_preprocessor_output = preprocessor.feed(
                            heart_phase, breath_phase, ts
                        )

                        lissajous_history.append([float(breath_phase), float(heart_phase)])
                        if len(lissajous_history) > 500:
                            lissajous_history.pop(0)

                        heart_phase_history.append(heart_phase)
                        breath_phase_history.append(breath_phase)
                        heart_rate_history.append(latest_data["heart_rate"])
                        breath_rate_history.append(latest_data["breath_rate"])

                        for lst in [heart_phase_history, breath_phase_history,
                                    heart_rate_history, breath_rate_history]:
                            if len(lst) > MAX_HISTORY:
                                lst.pop(0)

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
                if ser and ser.is_open:
                    ser.close()
            except:
                pass
            time.sleep(0.5)


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
            "br_phase": latest_data["breath_phase"]
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

        # S级指标
        rsa_val = engine.calc_rsa(inst_hr, br_uni)
        rsa_cycles = engine.calc_rsa(inst_hr, br_uni, return_all=True)
        plv_val = engine.calc_plv(hr_uni, br_uni)
        phase_diff = engine.calc_mean_phase_diff(hr_uni, br_uni)

        # A级指标
        brv_val = engine.calc_brv(inst_br)
        br_elev_val = engine.calc_br_elevation(inst_br)
        hri_val = engine.calc_hri(inst_hr)
        hrr_val = engine.calc_hrr(hr_now)
        cr_val = engine.calc_cr_ratio(hr_now, br_now)
        slope_val = engine.calc_hr_slope(heart_rate_history)

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

    br_cleaned = []
    for br_val in breath_rate_history:
        if br_val <= 0:
            br_cleaned.append(br_cleaned[-1] if br_cleaned and br_cleaned[-1] > 0 else 16.0)
        else:
            br_cleaned.append(float(br_val))

    result["rt"] = {
        "heart_phase": [float(x) for x in heart_phase_history[-200:]],
        "breath_phase": [float(x) for x in breath_phase_history[-200:]],
        "heart_rate": [float(x) for x in heart_rate_history[-200:]],
        "breath_rate": br_cleaned[-200:]
    }

    return jsonify(result)


if __name__ == '__main__':
    print("=" * 60)
    print("  生理指标解析引擎 V4.0")
    print("  基于相位动力学: RSA / PLV / BRV / HRR / CR / HRI")
    print("  数据保存: %s" % JSON_FILE)
    print("=" * 60)
    threading.Thread(target=serial_thread, daemon=True).start()
    print("\nWeb服务器: http://127.0.0.1:%d" % HTTP_PORT)
    print("=" * 60 + "\n")
    #app.run(host="127.0.0.1", port=HTTP_PORT, debug=False, use_reloader=False)
    app.run(host="127.0.0.1", port=HTTP_PORT, debug=False)