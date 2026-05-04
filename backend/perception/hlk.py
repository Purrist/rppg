# -*- coding: utf-8 -*-
import struct
import serial
import time
import json
import threading
import os

from flask import Flask, render_template, jsonify

PORT = "COM9"
BAUD = 115200
HTTP_PORT = 5080
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, 'hlk.json')

app = Flask(__name__, template_folder='templates')

# 数据存储 - 用简单的变量代替锁
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
        print("数据已保存到: %s" % JSON_FILE)
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
            print("✓ 串口连接成功！")
            break
        except Exception as e:
            print("✗ 串口连接失败: %s" % e)
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
                        
                        print("0x%04X - 相位数据: 心跳=%.4f, 呼吸=%.4f" % (tid, heart_phase, breath_phase))
                    
                    elif tid == 0x0A14 and len(fd) >= 4:
                        breath_rate = float_le(fd[:4])
                        latest_data["breath_rate"] = breath_rate
                        print("0x%04X - 呼吸率: %.1f" % (tid, breath_rate))
                    
                    elif tid == 0x0A15 and len(fd) >= 4:
                        heart_rate = float_le(fd[:4])
                        latest_data["heart_rate"] = heart_rate
                        print("0x%04X - 心率: %.0f" % (tid, heart_rate))
                    
                    elif tid == 0x0A16 and len(fd) >= 8:
                        distance = float_le(fd[4:8])
                        print("0x%04X - 距离: %.2f" % (tid, distance))
                    
                    elif tid == 0x0A18 and len(fd) >= 2:
                        target_count = (fd[1] << 8) | fd[0]
                        print("0x%04X - 目标数: %d" % (tid, target_count))
                    
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
    return jsonify({
        "heart_rate": latest_data["heart_rate"],
        "breath_rate": latest_data["breath_rate"],
        "heart_phase": latest_data["heart_phase"],
        "breath_phase": latest_data["breath_phase"],
        "rt": {
            "heart_phase": list(heart_phase_history),
            "breath_phase": list(breath_phase_history),
            "heart_rate": list(heart_rate_history),
            "breath_rate": list(breath_rate_history)
        }
    })

if __name__ == '__main__':
    print("=" * 60)
    print("HLK-LD6002 毫米波雷达 - 协议解析器")
    print("数据将保存到: %s" % JSON_FILE)
    print("=" * 60)

    threading.Thread(target=serial_thread, daemon=True).start()

    print("\nWeb服务器运行在 http://127.0.0.1:%d" % HTTP_PORT)
    print("=" * 60 + "\n")

    app.run(host="127.0.0.1", port=HTTP_PORT, debug=False, use_reloader=False)
