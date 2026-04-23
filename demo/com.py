# -*- coding: utf-8 -*-
import serial
import struct
import time
import threading
from flask import Flask, render_template_string, jsonify, request

# ====================== 配置 ======================
PORT = "COM9"
BAUD = 115200

# ====================== 全局数据 ======================
data = {"breath": 0, "heart": 0, "distance": 0.0, "human": False, "mode": "smooth"}

realtime_buf = {"time": [], "breath": [], "heart": []}
longterm_buf = {"time": [], "breath": [], "heart": []}

breath_smooth_buf = []
heart_smooth_buf = []
last_human_time = 0.0

SMOOTH_WINDOW = 4
HUMAN_LOST_THRESHOLD = 1.0
REALTIME_MAX = 120
LONGTERM_MAX = 3600
SAMPLE_INTERVAL = 0.5

lock = threading.Lock()

# ====================== 工具函数 ======================
def verify_cksum(buf, cksum):
    acc = 0
    for b in buf:
        acc ^= b
    return (~acc & 0xFF) == cksum

def float_le(b):
    return struct.unpack('<f', b)[0]

def smooth_val(v, buf):
    buf.append(v)
    if len(buf) > SMOOTH_WINDOW:
        buf.pop(0)
    return round(sum(buf) / len(buf))

# ====================== 串口任务 ======================
def serial_task():
    global last_human_time
    buf = b""
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.005)
        print("✅ 串口已打开")
        while True:
            if ser.in_waiting:
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
                    fd = frame[8:8+dlen]
                    mode = data["mode"]

                    if tid == 0x0F09:
                        detected = fd[0] == 1
                        if detected:
                            last_human_time = time.time()
                        el = time.time() - last_human_time
                        data["human"] = detected if mode == "raw" else (detected or el < HUMAN_LOST_THRESHOLD)

                    elif tid == 0x0A14:
                        raw = round(float_le(fd[:4]))
                        if data["human"]:
                            if mode == "smooth" and 5 <= raw <= 60:
                                data["breath"] = smooth_val(raw, breath_smooth_buf)
                            else:
                                data["breath"] = raw
                        else:
                            data["breath"] = 0
                            breath_smooth_buf.clear()

                    elif tid == 0x0A15:
                        raw = round(float_le(fd[:4]))
                        if data["human"]:
                            if mode == "smooth" and 30 <= raw <= 180:
                                data["heart"] = smooth_val(raw, heart_smooth_buf)
                            else:
                                data["heart"] = raw
                        else:
                            data["heart"] = 0
                            heart_smooth_buf.clear()

                    elif tid == 0x0A16:
                        flag = struct.unpack('<I', fd[0:4])[0]
                        data["distance"] = round(float_le(fd[4:8]), 1) if flag == 1 else 0.0

                time.sleep(0.001)
    except Exception as e:
        print("串口异常:", e)

# ====================== 采样任务 ======================
def sampler_task():
    while True:
        time.sleep(SAMPLE_INTERVAL)
        ts = round(time.time(), 1)
        with lock:
            for store, mx in [(realtime_buf, REALTIME_MAX), (longterm_buf, LONGTERM_MAX)]:
                store["time"].append(ts)
                store["breath"].append(data["breath"])
                store["heart"].append(data["heart"])
                if len(store["time"]) > mx:
                    store["time"].pop(0)
                    store["breath"].pop(0)
                    store["heart"].pop(0)

# ====================== Flask ======================
app = Flask(__name__)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LD6002 雷达监测</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
html,body{width:100%;height:100%;background:#0c1018;color:#c8cee0;overflow:hidden}
.wrapper{display:grid;grid-template-rows:auto 1fr 1.5fr auto;height:100vh;gap:10px;padding:14px 16px}
/* ---- 顶栏 ---- */
.top-bar{display:flex;align-items:center;justify-content:space-between}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;flex:1}
.card{background:linear-gradient(135deg,#151c2c,#1a2236);border-radius:10px;padding:14px 18px;position:relative;overflow:hidden;border:1px solid #232e44}
.card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;border-radius:3px 0 0 3px}
.card.blue::before{background:#4285F4}.card.red::before{background:#EA4335}
.card.green::before{background:#34A853}.card.yellow::before{background:#FBBC05}
.card .label{font-size:12px;color:#6b7a94;margin-bottom:6px;letter-spacing:.5px}
.card .val{font-size:28px;font-weight:700;line-height:1.1}
.card .unit{font-size:12px;color:#556;margin-left:4px;font-weight:400}
.blue .val{color:#4285F4}.red .val{color:#EA4335}
.green .val{color:#34A853}.yellow .val{color:#FBBC05}
.card .sub{font-size:11px;color:#4a5570;margin-top:4px}
.mode-group{display:flex;background:#151c2c;border-radius:8px;padding:3px;gap:2px;border:1px solid #232e44;margin-left:14px;flex-shrink:0}
.mode-btn{padding:8px 18px;border:none;border-radius:6px;background:transparent;color:#556;cursor:pointer;font-size:13px;transition:.2s;white-space:nowrap}
.mode-btn.active{background:#4285F4;color:#fff;box-shadow:0 2px 8px rgba(66,133,244,.35)}
.mode-btn:hover:not(.active){color:#8899b0}
/* ---- 图表行 ---- */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;min-height:0}
.chart-panel{background:#111827;border-radius:10px;border:1px solid #1e2a3e;display:flex;flex-direction:column;overflow:hidden}
.chart-header{display:flex;align-items:center;justify-content:space-between;padding:8px 14px;border-bottom:1px solid #1a2438;flex-shrink:0}
.chart-title{font-size:12px;color:#6b7a94;font-weight:600;letter-spacing:.3px}
.chart-hint{font-size:10px;color:#3a4560;display:flex;gap:10px}
.chart-body{flex:1;position:relative;min-height:0;padding:4px 8px 8px}
.chart-body canvas{width:100%!important;height:100%!important}
/* ---- 底栏 ---- */
.controls{display:flex;align-items:center;gap:20px;padding:8px 14px;background:#151c2c;border-radius:8px;border:1px solid #232e44}
.ctrl-group{display:flex;align-items:center;gap:6px;font-size:12px;color:#6b7a94}
.ctrl-group input{width:52px;padding:4px 6px;background:#1a2236;border:1px solid #2a3650;border-radius:5px;color:#c8cee0;text-align:center;font-size:12px}
.ctrl-group input:focus{outline:none;border-color:#4285F4}
.apply-btn{padding:5px 16px;background:#4285F4;border:none;border-radius:5px;color:#fff;font-size:12px;cursor:pointer;transition:.15s}
.apply-btn:hover{background:#5a9cf4}
.status-dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle}
.status-dot.on{background:#34A853;box-shadow:0 0 6px rgba(52,168,83,.6)}
.status-dot.off{background:#555}
.mode-tag{font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600;margin-left:8px}
.mode-tag.smooth{background:rgba(66,133,244,.15);color:#4285F4}
.mode-tag.raw{background:rgba(234,67,53,.15);color:#EA4335}
</style>
</head>
<body>
<div class="wrapper">
  <div class="top-bar">
    <div class="cards">
      <div class="card blue">
        <div class="label">呼吸率</div>
        <div><span class="val" id="vBreath">-</span><span class="unit">bpm</span></div>
      </div>
      <div class="card red">
        <div class="label">心率</div>
        <div><span class="val" id="vHeart">-</span><span class="unit">bpm</span></div>
      </div>
      <div class="card green">
        <div class="label">距离</div>
        <div><span class="val" id="vDist">-</span><span class="unit">cm</span></div>
      </div>
      <div class="card yellow">
        <div class="label">状态</div>
        <div class="val" id="vHuman" style="font-size:22px">
          <span class="status-dot off" id="dotHuman"></span><span id="txtHuman">等待</span>
          <span class="mode-tag smooth" id="modeTag">平滑</span>
        </div>
      </div>
    </div>
    <div class="mode-group">
      <button class="mode-btn active" id="btnSmooth" onclick="setMode('smooth')">平滑模式</button>
      <button class="mode-btn" id="btnRaw" onclick="setMode('raw')">源数据</button>
    </div>
  </div>

  <div class="charts-row">
    <div class="chart-panel">
      <div class="chart-header"><span class="chart-title">实时呼吸波形</span><span class="chart-hint">最近 60s</span></div>
      <div class="chart-body"><canvas id="rtBreath"></canvas></div>
    </div>
    <div class="chart-panel">
      <div class="chart-header"><span class="chart-title">实时心率波形</span><span class="chart-hint">最近 60s</span></div>
      <div class="chart-body"><canvas id="rtHeart"></canvas></div>
    </div>
  </div>

  <div class="charts-row">
    <div class="chart-panel">
      <div class="chart-header"><span class="chart-title">长期呼吸趋势</span><span class="chart-hint">滚轮缩放 · 拖拽平移 · 双击重置</span></div>
      <div class="chart-body"><canvas id="ltBreath"></canvas></div>
    </div>
    <div class="chart-panel">
      <div class="chart-header"><span class="chart-title">长期心率趋势</span><span class="chart-hint">滚轮缩放 · 拖拽平移 · 双击重置</span></div>
      <div class="chart-body"><canvas id="ltHeart"></canvas></div>
    </div>
  </div>

  <div class="controls">
    <div class="ctrl-group"><span>呼吸Y轴:</span><input type="number" id="bMin" value="0"><span>~</span><input type="number" id="bMax" value="30"></div>
    <div class="ctrl-group"><span>心率Y轴:</span><input type="number" id="hMin" value="40"><span>~</span><input type="number" id="hMax" value="120"></div>
    <button class="apply-btn" onclick="applyScale()">应用范围</button>
    <div style="flex:1"></div>
    <div class="ctrl-group" style="color:#3a4560"><span id="pointInfo">0 点</span></div>
  </div>
</div>

<script>
/* ========== 时间格式化 ========== */
function fmtTs(ts) {
    var d = new Date(ts * 1000);
    return String(d.getHours()).padStart(2,'0') + ':' +
           String(d.getMinutes()).padStart(2,'0') + ':' +
           String(d.getSeconds()).padStart(2,'0');
}

/* ========== 通用图表配置工厂 ========== */
function makeOpts(isZoomable, yMin, yMax) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { intersect: false, mode: 'index' },
        elements: { point: { radius: 0 }, line: { borderWidth: 1.8, tension: 0.3 } },
        scales: {
            x: {
                type: 'linear',
                grid: { color: '#1a2236', drawBorder: false },
                ticks: { color: '#3a4a64', font: { size: 10 }, maxTicksLimit: 8,
                         callback: function(v) { return fmtTs(v); } }
            },
            y: {
                min: yMin, max: yMax,
                grid: { color: '#1a2236', drawBorder: false, borderDash: [3,3] },
                ticks: { color: '#3a4a64', font: { size: 10 }, maxTicksLimit: 6 }
            }
        },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: '#1a2236', borderColor: '#2a3a54', borderWidth: 1,
                titleColor: '#6b7a94', bodyColor: '#c8cee0', bodyFont: { size: 13 },
                callbacks: {
                    title: function(items) { return fmtTs(items[0].parsed.x); },
                    label: function(item) { return item.dataset.label + ': ' + item.parsed.y; }
                }
            },
            zoom: isZoomable ? {
                zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'xy' },
                pan: { enabled: true, mode: 'xy' }
            } : false
        }
    };
}

/* ========== 初始化四个图表 ========== */
var bMin = 0, bMax = 30, hMin = 40, hMax = 120;

var rtB = new Chart(document.getElementById('rtBreath'), {
    type: 'line',
    data: { datasets: [{ label: '呼吸率', data: [], borderColor: '#4285F4', backgroundColor: 'rgba(66,133,244,0.08)', fill: true }] },
    options: makeOpts(false, bMin, bMax)
});
var rtH = new Chart(document.getElementById('rtHeart'), {
    type: 'line',
    data: { datasets: [{ label: '心率', data: [], borderColor: '#EA4335', backgroundColor: 'rgba(234,67,53,0.08)', fill: true }] },
    options: makeOpts(false, hMin, hMax)
});
var ltB = new Chart(document.getElementById('ltBreath'), {
    type: 'line',
    data: { datasets: [{ label: '呼吸率', data: [], borderColor: '#4285F4', backgroundColor: 'rgba(66,133,244,0.06)', fill: true }] },
    options: makeOpts(true, bMin, bMax)
});
var ltH = new Chart(document.getElementById('ltHeart'), {
    type: 'line',
    data: { datasets: [{ label: '心率', data: [], borderColor: '#EA4335', backgroundColor: 'rgba(234,67,53,0.06)', fill: true }] },
    options: makeOpts(true, hMin, hMax)
});

/* 长期图表双击重置 */
document.getElementById('ltBreath').addEventListener('dblclick', function() { ltB.resetZoom(); });
document.getElementById('ltHeart').addEventListener('dblclick', function() { ltH.resetZoom(); });

/* ========== 数据映射辅助 ========== */
function toPoints(times, vals) {
    var pts = [];
    for (var i = 0; i < times.length; i++) pts.push({ x: times[i], y: vals[i] });
    return pts;
}

/* ========== 模式切换 ========== */
var currentMode = 'smooth';
function setMode(m) {
    currentMode = m;
    document.getElementById('btnSmooth').className = 'mode-btn' + (m === 'smooth' ? ' active' : '');
    document.getElementById('btnRaw').className = 'mode-btn' + (m === 'raw' ? ' active' : '');
    var tag = document.getElementById('modeTag');
    tag.className = 'mode-tag ' + m;
    tag.textContent = m === 'smooth' ? '平滑' : '源数据';
    fetch('/mode?v=' + m);
}

/* ========== Y轴范围 ========== */
function applyScale() {
    bMin = parseFloat(document.getElementById('bMin').value) || 0;
    bMax = parseFloat(document.getElementById('bMax').value) || 30;
    hMin = parseFloat(document.getElementById('hMin').value) || 0;
    hMax = parseFloat(document.getElementById('hMax').value) || 150;
    [rtB, ltB].forEach(function(c) { c.options.scales.y.min = bMin; c.options.scales.y.max = bMax; c.update('none'); });
    [rtH, ltH].forEach(function(c) { c.options.scales.y.min = hMin; c.options.scales.y.max = hMax; c.update('none'); });
}
document.querySelectorAll('.ctrl-group input').forEach(function(el) {
    el.addEventListener('keydown', function(e) { if (e.key === 'Enter') applyScale(); });
});

/* ========== 实时数据刷新 (250ms) ========== */
setInterval(function() {
    fetch('/data').then(function(r) { return r.json(); }).then(function(d) {
        document.getElementById('vBreath').textContent = d.breath;
        document.getElementById('vHeart').textContent = d.heart;
        document.getElementById('vDist').textContent = d.distance;
        var dot = document.getElementById('dotHuman');
        var txt = document.getElementById('txtHuman');
        if (d.human) { dot.className = 'status-dot on'; txt.textContent = '有人'; }
        else { dot.className = 'status-dot off'; txt.textContent = '无人'; }
        /* 模式同步 */
        if (d.mode !== currentMode) setMode(d.mode);
        /* 实时图表 */
        rtB.data.datasets[0].data = toPoints(d.rt.time, d.rt.breath);
        rtH.data.datasets[0].data = toPoints(d.rt.time, d.rt.heart);
        rtB.update('none');
        rtH.update('none');
    });
}, 250);

/* ========== 长期数据刷新 (2s) ========== */
setInterval(function() {
    fetch('/longterm').then(function(r) { return r.json(); }).then(function(d) {
        ltB.data.datasets[0].data = toPoints(d.time, d.breath);
        ltH.data.datasets[0].data = toPoints(d.time, d.heart);
        ltB.update('none');
        ltH.update('none');
        document.getElementById('pointInfo').textContent = d.time.length + ' 点';
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
    with lock:
        rt = {"time": list(realtime_buf["time"]),
              "breath": list(realtime_buf["breath"]),
              "heart": list(realtime_buf["heart"])}
    return jsonify({"breath": data["breath"], "heart": data["heart"],
                    "distance": data["distance"], "human": data["human"],
                    "mode": data["mode"], "rt": rt})

@app.route('/longterm')
def get_longterm():
    with lock:
        lt = {"time": list(longterm_buf["time"]),
              "breath": list(longterm_buf["breath"]),
              "heart": list(longterm_buf["heart"])}
    return jsonify(lt)

@app.route('/mode')
def set_mode():
    data["mode"] = request.args.get('v', 'smooth')
    return "ok"

if __name__ == "__main__":
    threading.Thread(target=serial_task, daemon=True).start()
    threading.Thread(target=sampler_task, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
