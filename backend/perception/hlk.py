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
from flask import Flask, render_template, jsonify

PORT = "COM9"
BAUD = 115200
HTTP_PORT = 5080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, 'hlk.json')

app = Flask(__name__, template_folder='templates', static_folder='static')

# ========== 数据存储 ==========
latest_data = {
    "heart_rate": 72,
    "breath_rate": 16,
    "heart_phase": 0,
    "breath_phase": 0
}

max_data_points = 100
heart_phase_history = []
breath_phase_history = []
heart_rate_history = []
breath_rate_history = []

# 初始化历史数据
for i in range(max_data_points):
    heart_phase_history.append(0)
    breath_phase_history.append(0)
    heart_rate_history.append(72)
    breath_rate_history.append(16)

# ========== 生理指标计算引擎 ==========

class PhysiologyCalculator:
    """基于雷达心率和呼吸率的生理指标计算引擎"""

    def __init__(self, age=25, hr_rest=60):
        self.age = age
        self.hr_max = 220 - age
        self.hr_rest = hr_rest
        self.baseline_hr = 70
        self.baseline_rr = 15

    def compute_hrv(self, hr_history):
        """从心率历史计算 HRV 指标"""
        hr = np.array(hr_history)
        hr = hr[hr > 0]
        if len(hr) < 5:
            return {'sdnn': 0, 'rmssd': 0, 'cvrr': 0, 'mrr': 0}

        rr_intervals = 60.0 / hr  # 秒
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
        """基于 HR 和 SDNN 估算 LF/HF 比值"""
        lf_hf = 2.0 + (70 - hr_mean) / 20
        if sdnn > 0:
            lf_hf += (45 - sdnn) / 100
        return max(0.5, min(10.0, lf_hf))

    def compute_physiological_load(self, hr, br, hrv):
        """生理负荷指数 CPLI"""
        hrr = (hr - self.hr_rest) / (self.hr_max - self.hr_rest) * 100
        lf_hf = self.estimate_lf_hf(hr, hrv['sdnn'])
        stress_index = min(100, lf_hf * 10)
        hf_norm = 100 / (1 + lf_hf)
        cpli = 0.3 * hrr/100 + 0.4 * stress_index/100 + 0.3 * (100 - hf_norm)/100
        return {
            'hrr': float(hrr),
            'lf_hf': float(lf_hf),
            'stress_index': float(stress_index),
            'hf_norm': float(hf_norm),
            'cpli': float(min(1.0, max(0, cpli)))
        }

    def compute_cognitive_load(self, hr, br, hrv):
        """认知负荷指数 CLI"""
        hr_delta = hr - self.baseline_hr
        rr_delta = br - self.baseline_rr
        hrv_suppression = max(0, (50 - hrv['sdnn']) / 50 * 100) if hrv['sdnn'] > 0 else 0
        cli = 0.4 * hr_delta/30 + 0.3 * rr_delta/10 + 0.3 * hrv_suppression/100
        return {
            'hr_delta': float(hr_delta),
            'rr_delta': float(rr_delta),
            'hrv_suppression': float(hrv_suppression),
            'cli': float(min(1.0, max(0, cli)))
        }

    def compute_flow(self, hr, br, hrv):
        """心流指数 FSI"""
        hrv_optimal = np.exp(-((hrv['sdnn'] - 45)**2)/(2*15**2)) if hrv['sdnn'] > 0 else 0.5
        hr_stability = np.exp(-((hrv['cvrr'] - 3.5)**2)/(2*1.5**2)) if hrv['cvrr'] > 0 else 0.5
        lf_hf = self.estimate_lf_hf(hr, hrv['sdnn'])
        ans_coord = np.exp(-((lf_hf - 1.5)**2)/(2*0.8**2))
        expected_rr = hr / 4
        br_hr_sync = np.exp(-((br - expected_rr)**2)/(2*2**2))
        fsi = np.mean([hrv_optimal, hr_stability, ans_coord, br_hr_sync])
        return {
            'hrv_optimal': float(hrv_optimal),
            'hr_stability': float(hr_stability),
            'ans_coordination': float(ans_coord),
            'br_hr_sync': float(br_hr_sync),
            'fsi': float(min(1.0, max(0, fsi)))
        }

    def compute_emotion(self, hr, br, hrv):
        """情绪识别 Valence-Arousal"""
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

        if valence >= 0.5 and arousal >= 0.5:
            quadrant = "High Arousal Positive"
        elif valence >= 0.5 and arousal < 0.5:
            quadrant = "Low Arousal Positive"
        elif valence < 0.5 and arousal >= 0.5:
            quadrant = "High Arousal Negative"
        else:
            quadrant = "Low Arousal Negative"

        return {
            'valence': float(valence),
            'arousal': float(arousal),
            'quadrant': quadrant
        }

    def compute_all(self, hr, br, hr_history):
        """计算所有生理指标"""
        hrv = self.compute_hrv(hr_history)
        phys = self.compute_physiological_load(hr, br, hrv)
        cog = self.compute_cognitive_load(hr, br, hrv)
        flow = self.compute_flow(hr, br, hrv)
        emotion = self.compute_emotion(hr, br, hrv)

        return {
            'hrv': hrv,
            'physiological': phys,
            'cognitive': cog,
            'flow': flow,
            'emotion': emotion
        }

# 初始化计算器
calc = PhysiologyCalculator()

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

                        heart_phase_history.append(heart_phase)
                        breath_phase_history.append(breath_phase)
                        heart_rate_history.append(latest_data["heart_rate"])
                        breath_rate_history.append(latest_data["breath_rate"])

                        if len(heart_phase_history) > max_data_points:
                            heart_phase_history.pop(0)
                        if len(breath_phase_history) > max_data_points:
                            breath_phase_history.pop(0)
                        if len(heart_rate_history) > max_data_points:
                            heart_rate_history.pop(0)
                        if len(breath_rate_history) > max_data_points:
                            breath_rate_history.pop(0)

                    elif tid == 0x0A14 and len(fd) >= 4:
                        breath_rate = float_le(fd[:4])
                        latest_data["breath_rate"] = breath_rate

                    elif tid == 0x0A15 and len(fd) >= 4:
                        heart_rate = float_le(fd[:4])
                        latest_data["heart_rate"] = heart_rate

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
    return render_template('hlk.html')

@app.route('/data')
def get_data():
    # 数据清洗
    br_cleaned = []
    for i, br in enumerate(breath_rate_history):
        if br == 0 and i > 0:
            br_cleaned.append(br_cleaned[-1] if br_cleaned[-1] > 0 else 7)
        else:
            br_cleaned.append(br)

    # 计算所有生理指标
    hr_current = latest_data["heart_rate"]
    br_current = latest_data["breath_rate"] if latest_data["breath_rate"] > 0 else (br_cleaned[-1] if br_cleaned else 7)

    metrics = calc.compute_all(hr_current, br_current, heart_rate_history)

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
        "metrics": metrics
    })

if __name__ == '__main__':
    print("=" * 60)
    print("HLK-LD6002 毫米波雷达 - 高级生理指标解析器")
    print("支持: HRV / 生理负荷 / 认知负荷 / 心流 / 情绪识别")
    print("数据将保存到: %s" % JSON_FILE)
    print("=" * 60)

    threading.Thread(target=serial_thread, daemon=True).start()

    print("\nWeb服务器运行在 http://127.0.0.1:%d" % HTTP_PORT)
    print("=" * 60 + "\n")

    app.run(host="127.0.0.1", port=HTTP_PORT, debug=False, use_reloader=False)