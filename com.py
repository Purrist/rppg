# -*- coding: utf-8 -*-
import serial
import struct
import time
import threading
from collections import deque
from flask import Flask, render_template_string, jsonify, request

# ====================== 配置 ======================
PORT = "COM9"
BAUD = 115200

# ====================== 全局数据 ======================
data = {"breath": 0, "heart": 0, "distance": 0.0, "human": False, "mode": "smooth"}

realtime_buf = {"time": [], "breath": [], "heart": []}
longterm_buf = {"time": [], "breath": [], "heart": []}

# ---- 0值插值器 ----
class ZeroInterpolator:
    """
    对传感器偶发的 0 值做延迟窗口线性插值。
    例: 98, 0, 0, 69  ->  98, 90, 80, 69
    例: 98, 0, 95     ->  98, 98, 95  (或 98, 96, 95，取决于窗口内有效值)
    引入约 (window-1) * SAMPLE_INTERVAL 秒的延迟。
    """
    def __init__(self, window=5):
        self.raw_buf = deque(maxlen=window)
        self.window = window

    def feed(self, raw):
        self.raw_buf.append(float(raw))
        arr = list(self.raw_buf)
        n = len(arr)

        # 找有效值索引
        valid_idx = [i for i, v in enumerate(arr) if v > 0]

        if len(valid_idx) >= 2:
            # 被有效值包围的 0 做线性插值；边缘 0 做最近有效值填充
            for i in range(n):
                if arr[i] == 0:
                    left = max([j for j in valid_idx if j < i], default=None)
                    right = min([j for j in valid_idx if j > i], default=None)
                    if left is not None and right is not None:
                        ratio = (i - left) / (right - left)
                        arr[i] = arr[left] + (arr[right] - arr[left]) * ratio
                    elif left is not None:
                        arr[i] = arr[left]
                    elif right is not None:
                        arr[i] = arr[right]
        elif len(valid_idx) == 1:
            # 只有一个有效值，全部填充
            for i in range(n):
                if arr[i] == 0:
                    arr[i] = arr[valid_idx[0]]
        # 全 0 则保持原样

        # 返回最旧值（延迟输出），缓冲未满时返回最新插值结果
        if n >= self.window:
            return round(arr[0])
        else:
            return round(arr[-1]) if arr else raw

    def flush(self):
        self.raw_buf.clear()


breath_interp = ZeroInterpolator(window=5)
heart_interp = ZeroInterpolator(window=5)

# ---- 平滑状态 ----
breath_hist = []          # 中值滤波历史
heart_hist = []           # 中值滤波历史
breath_ema = 0.0          # EMA 状态
heart_ema = 0.0           # EMA 状态
ema_initialized = {"breath": False, "heart": False}

last_human_time = 0.0
away_start_time = None

last_valid_data = {"breath": 0, "heart": 0}
consecutive_invalid_count = 0
data_status = "normal"

# ---- 参数 ----
MEDIAN_WINDOW = 7
EMA_ALPHA_BREATH = 0.15
EMA_ALPHA_HEART = 0.25
HUMAN_LOST_THRESHOLD = 1.5
AWAY_FADE_DURATION = 2.0
REALTIME_MAX = 120
LONGTERM_MAX = 3600
SAMPLE_INTERVAL = 0.5
DIFF_THRESHOLD_BREATH = 12
DIFF_THRESHOLD_HEART = 25
MAX_INVALID_FRAMES = 8

lock = threading.Lock()

# ====================== 工具函数 ======================
def verify_cksum(buf, cksum):
    acc = 0
    for b in buf:
        acc ^= b
    return (~acc & 0xFF) == cksum

def float_le(b):
    return struct.unpack('<f', b)[0]

def median_filter(v, buf, window):
    buf.append(v)
    if len(buf) > window:
        buf.pop(0)
    if len(buf) < 3:
        return v
    sorted_buf = sorted(buf)
    return sorted_buf[len(sorted_buf) // 2]

def ema_filter(v, prev, alpha, initialized):
    if not initialized or prev == 0:
        return v, True
    new_val = prev * (1 - alpha) + v * alpha
    return new_val, True

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def process_sensor_data(new_b, new_h, is_human):
    """
    处理传感器数据：
    1. 无人且 < AWAY_FADE_DURATION：线性淡出到 0
    2. 无人且 >= AWAY_FADE_DURATION：强制归零并清空所有状态
    3. 有人：中值滤波去尖峰 → EMA 平滑 → 自适应异常检测
    """
    global last_valid_data, consecutive_invalid_count, data_status
    global breath_ema, heart_ema, ema_initialized
    global away_start_time

    now = time.time()

    if not is_human:
        if away_start_time is None:
            away_start_time = now

        elapsed = now - away_start_time

        if elapsed < AWAY_FADE_DURATION:
            ratio = max(0.0, 1.0 - elapsed / AWAY_FADE_DURATION)
            data_status = "away"
            return (
                round(last_valid_data["breath"] * ratio),
                round(last_valid_data["heart"] * ratio),
                "away"
            )
        else:
            consecutive_invalid_count = 0
            last_valid_data = {"breath": 0, "heart": 0}
            breath_ema = 0.0
            heart_ema = 0.0
            ema_initialized = {"breath": False, "heart": False}
            breath_hist.clear()
            heart_hist.clear()
            # 清空插值器，避免旧数据干扰下次回座
            breath_interp.flush()
            heart_interp.flush()
            data_status = "away"
            return 0, 0, "away"

    # 回座，重置离座计时
    away_start_time = None

    # 中值滤波
    b_med = median_filter(new_b, breath_hist, MEDIAN_WINDOW)
    h_med = median_filter(new_h, heart_hist, MEDIAN_WINDOW)

    # EMA 平滑
    b_ema, ema_initialized["breath"] = ema_filter(
        b_med, breath_ema, EMA_ALPHA_BREATH, ema_initialized["breath"]
    )
    h_ema, ema_initialized["heart"] = ema_filter(
        h_med, heart_ema, EMA_ALPHA_HEART, ema_initialized["heart"]
    )
    breath_ema = b_ema
    heart_ema = h_ema

    # 异常检测
    is_b_invalid = (new_b == 0 or abs(new_b - last_valid_data["breath"]) > DIFF_THRESHOLD_BREATH) \
        if last_valid_data["breath"] > 0 else (new_b == 0)
    is_h_invalid = (new_h == 0 or abs(new_h - last_valid_data["heart"]) > DIFF_THRESHOLD_HEART) \
        if last_valid_data["heart"] > 0 else (new_h == 0)

    if is_b_invalid or is_h_invalid:
        consecutive_invalid_count += 1
        if consecutive_invalid_count < MAX_INVALID_FRAMES:
            data_status = "compensating"
            return round(breath_ema), round(heart_ema), "compensating"
        else:
            last_valid_data["breath"] = b_ema
            last_valid_data["heart"] = h_ema
            consecutive_invalid_count = 0
            data_status = "recovered"
            return round(b_ema), round(h_ema), "recovered"
    else:
        consecutive_invalid_count = 0
        data_status = "normal"
        last_valid_data["breath"] = b_ema
        last_valid_data["heart"] = h_ema
        return round(b_ema), round(h_ema), "normal"


# ====================== 串口任务 ======================
def serial_task():
    global last_human_time
    buf = b""
    raw_data_cache = {"breath": 0, "heart": 0, "breath_valid": False, "heart_valid": False}
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
                        is_human = detected if mode == "raw" else (detected or el < HUMAN_LOST_THRESHOLD)

                        processed_breath, processed_heart, status = process_sensor_data(
                            raw_data_cache["breath"],
                            raw_data_cache["heart"],
                            is_human
                        )

                        if mode == "smooth":
                            data["breath"] = clamp(processed_breath, 4, 60)
                            data["heart"] = clamp(processed_heart, 30, 180)
                        else:
                            data["breath"] = raw_data_cache["breath"]
                            data["heart"] = raw_data_cache["heart"]

                        data["human"] = is_human

                    elif tid == 0x0A14:
                        raw = round(float_le(fd[:4]))
                        # 先过 0 值插值器，再存缓存
                        raw_data_cache["breath"] = breath_interp.feed(raw)
                        raw_data_cache["breath_valid"] = (4 <= raw <= 60)

                    elif tid == 0x0A15:
                        raw = round(float_le(fd[:4]))
                        raw_data_cache["heart"] = heart_interp.feed(raw)
                        raw_data_cache["heart_valid"] = (30 <= raw <= 180)

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
.top-bar{display:flex;align-items:center;justify-content:space-between}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;flex:1}
.card{background:linear-gradient(135deg,#151c2c,#1a2236);border-radius:10px;padding:14px 18px;position:relative;overflow:hidden;border:1px solid #232e44;transition:border-color 0.3s}
.card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;border-radius:3px 0 0 3px;transition:background 0.3s}
.card.blue::before{background:#4285F4}.card.red::before{background:#EA4335}
.card.green::before{background:#34A853}.card.yellow::before{background:#FBBC05}
.card.status-normal{border-color:#34A853}
.card.status-compensating{border-color:#FBBC05}
.card.status-compensating::before{background:#FBBC05}
.card.status-away{border-color:#555}
.card.status-away::before{background:#555}
.card.status-recovered{border-color:#4285F4}
.card.status-recovered::before{background:#4285F4}
.card .label{font-size:12px;color:#6b7a94;margin-bottom:6px;letter-spacing:.5px}
.card .val{font-size:28px;font-weight:700;line-height:1.1;transition:color 0.3s}
.card .unit{font-size:12px;color:#556;margin-left:4px;font-weight:400}
.blue .val{color:#4285F4}.red .val{color:#EA4335}
.green .val{color:#34A853}.yellow .val{color:#FBBC05}
.card.status-away .val{color:#555}
.card.status-compensating .val{color:#FBBC05}
.card.status-recovered .val{color:#4285F4}
.card .sub{font-size:11px;color:#4a5570;margin-top:4px}
.mode-group{display:flex;background:#151c2c;border-radius:8px;padding:3px;gap:2px;border:1px solid #232e44;margin-left:14px;flex-shrink:0}
.mode-btn{padding:8px 18px;border:none;border-radius:6px;background:transparent;color:#556;cursor:pointer;font-size:13px;transition:.2s;white-space:nowrap}
.mode-btn.active{background:#4285F4;color:#fff;box-shadow:0 2px 8px rgba(66,133,244,.35)}
.mode-btn:hover:not(.active){color:#8899b0}
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;min-height:0}
.chart-panel{background:#111827;border-radius:10px;border:1px solid #1e2a3e;display:flex;flex-direction:column;overflow:hidden}
.chart-header{display:flex;align-items:center;justify-content:space-between;padding:8px 14px;border-bottom:1px solid #1a2438;flex-shrink:0}
.chart-title{font-size:12px;color:#6b7a94;font-weight:600;letter-spacing:.3px}
.chart-hint{font-size:10px;color:#3a4560;display:flex;gap:10px}
.chart-body{flex:1;position:relative;min-height:0;padding:4px 8px 8px}
.chart-body canvas{width:100%!important;height:100%!important}
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
.status-sub{font-size:10px;margin-top:4px;color:#6b7a94}
</style>
</head>
<body>
<div class="wrapper">
  <div class="top-bar">
    <div class="cards">
      <div class="card blue" id="cardBreath">
        <div class="label">呼吸率</div>
        <div><span class="val" id="vBreath">-</span><span class="unit">bpm</span></div>
        <div class="status-sub" id="statusBreath">正常</div>
      </div>
      <div class="card red" id="cardHeart">
        <div class="label">心率</div>
        <div><span class="val" id="vHeart">-</span><span class="unit">bpm</span></div>
        <div class="status-sub" id="statusHeart">正常</div>
      </div>
      <div class="card green" id="cardDist">
        <div class="label">距离</div>
        <div><span class="val" id="vDist">-</span><span class="unit">cm</span></div>
        <div class="status-sub" id="statusDist">正常</div>
      </div>
      <div class="card yellow" id="cardStatus">
        <div class="label">状态</div>
        <div class="val" id="vHuman" style="font-size:22px">
          <span class="status-dot off" id="dotHuman"></span><span id="txtHuman">等待</span>
          <span class="mode-tag smooth" id="modeTag">平滑</span>
        </div>
        <div class="status-sub" id="statusText">数据正常</div>
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
function fmtTs(ts) {
    var d = new Date(ts * 1000);
    return String(d.getHours()).padStart(2,'0') + ':' +
           String(d.getMinutes()).padStart(2,'0') + ':' +
           String(d.getSeconds()).padStart(2,'0');
}
function makeOpts(isZoomable, yMin, yMax) {
    return {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { intersect: false, mode: 'index' },
        elements: { point: { radius: 0 }, line: { borderWidth: 1.8, tension: 0.3 } },
        scales: {
            x: { type: 'linear', grid: { color: '#1a2236', drawBorder: false },
                 ticks: { color: '#3a4a64', font: { size: 10 }, maxTicksLimit: 8,
                          callback: function(v) { return fmtTs(v); } } },
            y: { min: yMin, max: yMax, grid: { color: '#1a2236', drawBorder: false, borderDash: [3,3] },
                 ticks: { color: '#3a4a64', font: { size: 10 }, maxTicksLimit: 6 } }
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
document.getElementById('ltBreath').addEventListener('dblclick', function() { ltB.resetZoom(); });
document.getElementById('ltHeart').addEventListener('dblclick', function() { ltH.resetZoom(); });
function toPoints(times, vals) {
    var pts = [];
    for (var i = 0; i < times.length; i++) pts.push({ x: times[i], y: vals[i] });
    return pts;
}
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
setInterval(function() {
    fetch('/data').then(function(r) { return r.json(); }).then(function(d) {
        document.getElementById('vBreath').textContent = d.breath;
        document.getElementById('vHeart').textContent = d.heart;
        document.getElementById('vDist').textContent = d.distance;
        var dot = document.getElementById('dotHuman');
        var txt = document.getElementById('txtHuman');
        if (d.human) { dot.className = 'status-dot on'; txt.textContent = '有人'; }
        else { dot.className = 'status-dot off'; txt.textContent = '无人'; }
        var status = d.status || 'normal';
        var cards = ['cardBreath', 'cardHeart', 'cardDist', 'cardStatus'];
        var statusLabels = { 'normal': '正常', 'compensating': '补偿中', 'away': '离座', 'recovered': '已恢复' };
        var statusTexts = { 'normal': '数据正常', 'compensating': '数据波动，保持中', 'away': '无人检测', 'recovered': '数据已恢复' };
        cards.forEach(function(id) {
            var el = document.getElementById(id);
            el.className = el.className.replace(/status-\w+/g, '');
            el.classList.add('status-' + status);
        });
        document.getElementById('statusBreath').textContent = statusLabels[status];
        document.getElementById('statusHeart').textContent = statusLabels[status];
        document.getElementById('statusDist').textContent = statusLabels[status];
        document.getElementById('statusText').textContent = statusTexts[status];
        if (d.mode !== currentMode) setMode(d.mode);
        rtB.data.datasets[0].data = toPoints(d.rt.time, d.rt.breath);
        rtH.data.datasets[0].data = toPoints(d.rt.time, d.rt.heart);
        rtB.update('none');
        rtH.update('none');
    });
}, 250);
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
                    "mode": data["mode"], "status": data_status, "rt": rt})

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
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)
