# -*- coding: utf-8 -*-
import serial
import struct
import time
import threading
from flask import Flask, render_template_string, jsonify

# ====================== 串口配置 ======================
PORT = "COM9"
BAUD = 115200

# ====================== 全局数据 ======================
data = {
    "breath": 15,
    "heart": 70,
    "distance": 0,
    "human": False,
    "breath_list": [],
    "heart_list": [],
    "time_list": []
}
step = 0

# ====================== Flask 网页服务 ======================
app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>HLK-LD6002 毫米波雷达上位机</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { font-family: Arial; margin:0; padding:0; box-sizing:border-box; }
        body { background: #f5f5f5; padding: 20px; }
        .container { max-width:1200px; margin:auto; }
        .panel { background:white; padding:20px; border-radius:12px; margin-bottom:20px; box-shadow:0 2px 10px #00000010; }
        .grid { display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:15px; }
        .card { padding:20px; border-radius:10px; color:white; font-size:18px; }
        .card h3 { font-size:28px; margin-bottom:10px; }
        .bg-blue { background:#4285F4; }
        .bg-red { background:#EA4335; }
        .bg-green { background:#34A853; }
        .bg-orange { background:#FBBC05; color:#222; }
        .chart-box { height:400px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="panel grid">
            <div class="card bg-blue">
                呼吸率<br><h3 id="breath">--</h3> 次/分
            </div>
            <div class="card bg-red">
                心率<br><h3 id="heart">--</h3> 次/分
            </div>
            <div class="card bg-green">
                距离<br><h3 id="dist">--</h3> cm
            </div>
            <div class="card bg-orange">
                人体状态<br><h3 id="human">--</h3>
            </div>
        </div>

        <div class="panel">
            <h2>呼吸率趋势</h2>
            <canvas class="chart-box" id="breathChart"></canvas>
        </div>
        <div class="panel">
            <h2>心率趋势</h2>
            <canvas class="chart-box" id="heartChart"></canvas>
        </div>
    </div>

    <script>
        const breathCtx = document.getElementById('breathChart').getContext('2d');
        const heartCtx = document.getElementById('heartChart').getContext('2d');

        const breathChart = new Chart(breathCtx, {
            type: 'line', data: {
                labels: [], datasets: [{label: '呼吸率', borderColor: '#4285F4', tension:0.4, data:[]}]
            }, options: { responsive:true, maintainAspectRatio:false }
        });

        const heartChart = new Chart(heartCtx, {
            type: 'line', data: {
                labels: [], datasets: [{label: '心率', borderColor: '#EA4335', tension:0.4, data:[]}]
            }, options: { responsive:true, maintainAspectRatio:false }
        });

        async function update() {
            const res = await fetch('/data');
            const d = await res.json();

            document.getElementById('breath').innerText = d.breath;
            document.getElementById('heart').innerText = d.heart;
            document.getElementById('dist').innerText = d.distance;
            document.getElementById('human').innerText = d.human ? '有人' : '无人';

            if (d.time.length > breathChart.data.labels.length) {
                breathChart.data.labels = d.time;
                breathChart.data.datasets[0].data = d.breath_list;
                heartChart.data.labels = d.time;
                heartChart.data.datasets[0].data = d.heart_list;
                breathChart.update();
                heartChart.update();
            }
        }
        setInterval(update, 500);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/data')
def get_data():
    return jsonify({
        "breath": data["breath"],
        "heart": data["heart"],
        "distance": round(data["distance"],1),
        "human": data["human"],
        "time": data["time_list"],
        "breath_list": data["breath_list"],
        "heart_list": data["heart_list"]
    })

# ====================== 串口解析 ======================
def float_from_le(bytes_data):
    return struct.unpack('<f', bytes_data)[0]

def serial_task():
    global step
    buffer = b""
    try:
        ser = serial.Serial(
            port=PORT, baudrate=BAUD,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.01
        )
        print("✅ 串口已打开")

        while True:
            if ser.in_waiting:
                buffer += ser.read(ser.in_waiting)

            while len(buffer) >= 8:
                if buffer[0] != 0x01:
                    buffer = buffer[1:]
                    continue

                data_len = (buffer[3] << 8) | buffer[4]
                frame_len = 1 + 2 + 2 + 2 + 1 + data_len + 1

                if len(buffer) < frame_len or frame_len > 2048:
                    buffer = buffer[1:]
                    break

                frame = buffer[:frame_len]
                buffer = buffer[frame_len:]
                type_id = (frame[5] << 8) | frame[6]
                frame_data = frame[8:8+data_len]

                # 解析数据
                if type_id == 0x0F09:
                    data["human"] = frame_data[0] == 1

                elif type_id == 0x0A14:
                    data["breath"] = round(float_from_le(frame_data[:4]))
                    data["breath_list"].append(data["breath"])

                elif type_id == 0x0A15:
                    data["heart"] = round(float_from_le(frame_data[:4]))
                    data["heart_list"].append(data["heart"])
                    data["time_list"].append(step)
                    step +=1

                    # 保留最近40个点
                    if len(data["time_list"]) > 40:
                        data["time_list"].pop(0)
                        data["breath_list"].pop(0)
                        data["heart_list"].pop(0)

                elif type_id == 0x0A16:
                    data["distance"] = float_from_le(frame_data[4:8])

            time.sleep(0.001)
    except Exception as e:
        print("串口异常:", e)

# ====================== 启动 ======================
if __name__ == "__main__":
    threading.Thread(target=serial_task, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False)