# -*- coding: utf-8 -*-
"""
双轨负载监测系统 V2.1 (简化版)
============================
只有源数据和异常值剔除两种模式
支持年龄/性别自适应基准参数

参考文献:
- HRV: Kubios HRV, Taskforce 1996 Guidelines
- RMSSD: RMSSD = √(Σ(RRn+1 - RRn)² / N-1)
- 生理负荷: TRIMP Model, 储备心率法
- 心理负荷: Baevsky Stress Index
- 年龄预测最大心率: Tanaka et al. (2001)
"""

import serial, struct, time, threading, json, os, math, logging, cv2
import numpy as np
from collections import deque
from flask import Flask, render_template, jsonify, request

logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__, template_folder='templates')

# ====================== 配置 ======================
PORT = "COM9"
BAUD = 115200
DATA_DIR = "mmw_history"
CAMERA_ID = 0
os.makedirs(DATA_DIR, exist_ok=True)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SCRIPT_DIR, '..', 'core', 'models')
AGE_PATH = os.path.join(MODELS_DIR, 'age_googlenet.onnx')
GENDER_PATH = os.path.join(MODELS_DIR, 'gender_googlenet.onnx')

# ====================== 全局数据 ======================
raw_cache = {"hr": deque(maxlen=300), "br": deque(maxlen=300), "time": deque(maxlen=300)}
clean_cache = {"hr": deque(maxlen=300), "br": deque(maxlen=300), "time": deque(maxlen=300)}
all_mode_history = {
    "clean": {"time": [], "hr": [], "br": [], "phys": [], "stress": [], "hrv": [], "rmssd": []},
    "raw": {"time": [], "hr": [], "br": [], "phys": [], "stress": [], "hrv": [], "rmssd": []}
}

state = {
    "is_clean_on": True,
    "session_id": time.strftime("%Y%m%d_%H%M%S"),
    "last_save_idx": 0,
    "camera_active": False,
    "face_detected": False,
    "person_last_seen": 0.0,
}

# ====================== 数据解析相关 ======================
class ZeroInterpolator:
    def __init__(self, window=5):
        self.raw_buf = deque(maxlen=window)
        self.window = window
    def feed(self, raw):
        self.raw_buf.append(float(raw))
        arr = list(self.raw_buf)
        n = len(arr)
        valid_idx = [i for i, v in enumerate(arr) if v > 0]
        if len(valid_idx) >= 2:
            for i in range(n):
                if arr[i] == 0:
                    left = max([j for j in valid_idx if j < i], default=None)
                    right = min([j for j in valid_idx if j > i], default=None)
                    if left is not None and right is not None:
                        arr[i] = arr[left] + (arr[right] - arr[left]) * ((i - left) / (right - left))
                    elif left is not None:
                        arr[i] = arr[left]
                    elif right is not None:
                        arr[i] = arr[right]
        elif len(valid_idx) == 1:
            for i in range(n):
                if arr[i] == 0:
                    arr[i] = arr[valid_idx[0]]
        return round(arr[0]) if n >= self.window else (round(arr[-1]) if arr else raw)
    def flush(self):
        self.raw_buf.clear()

breath_interp = ZeroInterpolator(window=5)
heart_interp = ZeroInterpolator(window=5)

raw_data_cache = {"breath": 0, "heart": 0}
raw_data_cache_global = {"breath": 0, "heart": 0, "human": False}
last_human_time = 0.0
HUMAN_LOST_THRESHOLD = 1.5
lock = threading.Lock()

def verify_cksum(buf, cksum):
    acc = 0
    for b in buf:
        acc ^= b
    return (~acc & 0xFF) == cksum

def float_le(b):
    return struct.unpack('<f', b)[0]

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ====================== 年龄性别检测状态 ======================
attribute_state = {
    "age_label": None,
    "age_raw": 0,
    "gender": None,
    "gender_confidence": 0.0,
    "method": "none",
}

# ====================== 基准参数 (默认/静态) ======================
BASELINE = {
    "hr_rest": 65,
    "hr_max": 185,
    "rmssd_baseline": 45.0,
    "br_baseline": 15,
    "sdnn_baseline": 50.0,
    "age_assumed": 35,
}

# ====================== ONNX 年龄性别检测 ======================

try:
    import onnxruntime as ort
    HAS_ORT = True
except:
    HAS_ORT = False
    print("[WARN] onnxruntime 未安装，年龄性别检测不可用")

AGE_LABELS = ['(0-2)', '(4-6)', '(8-12)', '(15-20)', '(25-32)', '(38-43)', '(48-53)', '(60-100)']
GENDER_LABELS = ['Male', 'Female']


class AgeGenderBackend:
    """年龄和性别检测后端"""
    MEAN = np.array([104.0, 117.0, 123.0], dtype=np.float32)

    def __init__(self, age_path, gender_path):
        if not HAS_ORT:
            raise RuntimeError("onnxruntime 未安装")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.age_s = ort.InferenceSession(age_path, opts, providers=['CPUExecutionProvider'])
        self.gen_s = ort.InferenceSession(gender_path, opts, providers=['CPUExecutionProvider'])
        self.a_in = self.age_s.get_inputs()[0].name
        self.a_out = self.age_s.getOutputs()[0].name
        self.g_in = self.gen_s.get_inputs()[0].name
        self.g_out = self.gen_s.getOutputs()[0].name
        print("[OK] Age/Gender ONNX")

    def predict(self, face_bgr):
        if face_bgr is None or face_bgr.size == 0:
            return None
        try:
            rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            img = cv2.resize(rgb, (224, 224)).astype(np.float32) - self.MEAN
            blob = img.transpose(2, 0, 1)[np.newaxis]

            ar = self.age_s.run([self.a_out], {self.a_in: blob})[0][0].astype(np.float64)
            s = np.exp(ar - ar.max())
            ap = s / (s.sum() + 1e-10)
            ai = int(np.argmax(ap))

            gr = self.gen_s.run([self.g_out], {self.g_in: blob})[0][0].astype(np.float64)
            s = np.exp(gr - gr.max())
            gp = s / (s.sum() + 1e-10)
            gi = int(np.argmax(gp))

            return {
                'age_label': AGE_LABELS[ai],
                'age_confidence': round(float(ap[ai]), 2),
                'gender': GENDER_LABELS[gi],
                'gender_confidence': round(float(gp[gi]), 2),
            }
        except Exception as e:
            print(f"[AgeGender] Error: {e}")
            return None


# ====================== 摄像头线程 ======================

class ThreadedCamera:
    def __init__(self, src):
        self.cap = cv2.VideoCapture(src)
        self._running = True
        self._frame = None
        self._lock = threading.Lock()
        self.ok = self.cap.isOpened()
        if self.ok:
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while self._running:
            ret, f = self.cap.read()
            if ret:
                with self._lock:
                    self._frame = f
            time.sleep(0.01)

    def read(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def release(self):
        self._running = False
        self.cap.release()


agegender_backend = None
camera = None
face_cascade = None


def init_camera():
    global camera, agegender_backend, face_cascade

    camera = ThreadedCamera(CAMERA_ID)
    if not camera.ok:
        print(f"[WARN] 摄像头 {CAMERA_ID} 无法打开")
        state["camera_active"] = False
    else:
        state["camera_active"] = True
        print(f"[OK] 摄像头 {CAMERA_ID} 已启动")

    try:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    except:
        pass

    if HAS_ORT and os.path.exists(AGE_PATH) and os.path.exists(GENDER_PATH):
        try:
            agegender_backend = AgeGenderBackend(AGE_PATH, GENDER_PATH)
            attribute_state["method"] = "onnx"
            print("[OK] 年龄性别检测 ONNX 已加载")
        except Exception as e:
            print(f"[WARN] 年龄性别检测加载失败: {e}")


def camera_thread():
    """摄像头线程: 检测人脸并进行年龄性别分析"""
    global camera, agegender_backend, attribute_state, BASELINE, face_cascade

    if camera is None or not camera.ok:
        return

    detect_interval = 15
    frame_count = 0

    while state["camera_active"]:
        frame = camera.read()
        if frame is None:
            time.sleep(0.01)
            continue

        frame_count += 1
        now = time.time()

        if frame_count % detect_interval == 0 and agegender_backend is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if face_cascade is not None:
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)

                if len(faces) > 0:
                    x, y, w, h = faces[0]
                    face = frame[y:y+h, x:x+w]

                    if face.size > 0 and face.shape[0] > 20 and face.shape[1] > 20:
                        result = agegender_backend.predict(face)
                        if result:
                            with threading.Lock():
                                attribute_state["age_label"] = result["age_label"]
                                attribute_state["gender"] = result["gender"]
                                attribute_state["gender_confidence"] = result["gender_confidence"]
                                attribute_state["method"] = "onnx"

                                age_str = result["age_label"].strip('()')
                                if '-' in age_str:
                                    age_parts = age_str.split('-')
                                    age_raw = (int(age_parts[0]) + int(age_parts[1])) / 2
                                else:
                                    age_raw = int(age_str)
                                attribute_state["age_raw"] = age_raw

                                update_baseline_from_age(age_raw, result["gender"])

                            state["face_detected"] = True
                            state["person_last_seen"] = now
                        else:
                            state["face_detected"] = False
                else:
                    state["face_detected"] = False

        if now - state["person_last_seen"] > 3.0:
            state["face_detected"] = False

        time.sleep(0.01)


def update_baseline_from_age(age, gender):
    """根据检测到的年龄和性别更新基准参数"""
    global BASELINE

    hr_max_tanaka = 208 - 0.7 * age
    rmssd_baseline = 45.0
    hr_rest = 65

    if 18 <= age < 35:
        rmssd_baseline = 55.0
        hr_rest = 62 if gender == "Male" else 65
    elif 35 <= age < 50:
        rmssd_baseline = 40.0
        hr_rest = 65 if gender == "Male" else 68
    elif 50 <= age < 65:
        rmssd_baseline = 30.0
        hr_rest = 68 if gender == "Male" else 72
    else:
        rmssd_baseline = 22.0
        hr_rest = 72 if gender == "Male" else 75

    BASELINE["hr_max"] = round(hr_max_tanaka)
    BASELINE["hr_rest"] = hr_rest
    BASELINE["rmssd_baseline"] = rmssd_baseline
    BASELINE["sdnn_baseline"] = rmssd_baseline * 1.1
    BASELINE["age_assumed"] = age


# ====================== 核心算法 ======================

def clamp(v, mn, mx): return max(mn, min(mx, v))


def calculate_rmssd(hr_list):
    """RMSSD = √(Σ(RRn+1 - RRn)² / N-1)"""
    rr = [60000.0 / x for x in hr_list if x > 0 and 30 < x < 200]
    if len(rr) < 2: return 0.0
    diffs_squared = [(rr[i+1] - rr[i]) ** 2 for i in range(len(rr) - 1)]
    return round(math.sqrt(sum(diffs_squared) / len(diffs_squared)), 2)


def calculate_sdnn(hr_list):
    """SDNN: NN间期标准差"""
    rr = [60000.0 / x for x in hr_list if x > 0 and 30 < x < 200]
    if len(rr) < 2: return 0.0
    mean_rr = sum(rr) / len(rr)
    variance = sum((r - mean_rr) ** 2 for r in rr) / len(rr)
    return round(math.sqrt(variance), 2)


def calculate_stress_index(rmssd):
    """心理应激指数: 100 × (1 - ln(RMSSD) / ln(RMSSD_baseline))"""
    if rmssd <= 0: return 50.0
    ln_rmssd = math.log(rmssd)
    ln_baseline = math.log(BASELINE["rmssd_baseline"])
    stress = 100 * (1 - ln_rmssd / ln_baseline)
    return round(clamp(stress, 0, 100), 1)


def calculate_physical_load(hr, br=None):
    """生理负荷 (储备心率法): %HRR = (HR - HRrest) / (HRmax - HRrest) × 100"""
    if hr <= 0: return 0.0
    hr_reserve = BASELINE["hr_max"] - BASELINE["hr_rest"]
    if hr_reserve <= 0: return 0.0
    hr_ratio = (hr - BASELINE["hr_rest"]) / hr_reserve
    phys_load = hr_ratio * 100
    if br is not None and br > 0:
        br_deviation = abs(br - BASELINE["br_baseline"]) / BASELINE["br_baseline"]
        if br_deviation > 0.2:
            phys_load = phys_load * (1 + br_deviation * 0.1)
    return round(clamp(phys_load, 0, 100), 1)


def calculate_cognitive_load(hr, rmssd, sdnn):
    """认知负荷 (综合HRV指标)"""
    if hr <= 0 or rmssd <= 0: return 50.0

    hr_index = (hr - BASELINE["hr_rest"]) / (BASELINE["hr_max"] - BASELINE["hr_rest"])
    parasympathetic_index = clamp(math.log(rmssd) / math.log(BASELINE["rmssd_baseline"]), 0, 1.5)
    variability_index = clamp(sdnn / BASELINE["sdnn_baseline"], 0.5, 2.0)

    cognitive = (hr_index * 0.40 + (1 - parasympathetic_index) * 0.35 + (1 - variability_index) * 0.25) * 100
    return round(clamp(cognitive, 0, 100), 1)


def calculate_hrv_summary(hr_list):
    """计算完整的HRV摘要指标"""
    rmssd = calculate_rmssd(hr_list)
    sdnn = calculate_sdnn(hr_list)
    stress = calculate_stress_index(rmssd)
    hrv_score = round(clamp(rmssd / BASELINE["rmssd_baseline"] * 50, 0, 100), 1)
    return {"rmssd": rmssd, "sdnn": sdnn, "stress": stress, "hrv_score": hrv_score}


# ====================== 数据处理器 ======================

class DataProcessor:
    def __init__(self):
        self.last_clean = {"hr": 0, "br": 0}

    def process(self, raw_hr, raw_br, is_clean):
        if is_clean:
            clean_hr = raw_hr if 40 < raw_hr < 180 else self.last_clean["hr"]
            clean_br = raw_br if 8 < raw_br < 30 else self.last_clean["br"]
            if clean_hr > 0: self.last_clean["hr"] = clean_hr
            if clean_br > 0: self.last_clean["br"] = clean_br
        else:
            clean_hr = raw_hr if 30 < raw_hr < 200 else 0
            clean_br = raw_br if 5 < raw_br < 40 else 0

        return clean_hr, clean_br


processor = DataProcessor()


def init_simulation_data():
    """初始化模拟数据，确保一开始图表就能显示"""
    global raw_cache, clean_cache, all_mode_history
    ts = time.time()
    for i in range(60):
        t = ts - (60 - i) * 0.5
        hr = 70 + 8 * math.sin(t / 15)
        br = 16 + 3 * math.cos(t / 20)
        raw_cache["hr"].append(hr)
        raw_cache["br"].append(br)
        raw_cache["time"].append(t)
        clean_hr, clean_br = processor.process(hr, br, state["is_clean_on"])
        clean_cache["hr"].append(clean_hr)
        clean_cache["br"].append(clean_br)
        clean_cache["time"].append(t)
        for mode, (h, b) in [("clean", (clean_hr, clean_br)), ("raw", (hr, br))]:
            all_mode_history[mode]["time"].append(t)
            all_mode_history[mode]["hr"].append(h)
            all_mode_history[mode]["br"].append(b)
            all_mode_history[mode]["phys"].append(0)
            all_mode_history[mode]["stress"].append(50)
            all_mode_history[mode]["hrv"].append(50)
            all_mode_history[mode]["rmssd"].append(45)
    print(f"[OK] 模拟数据已初始化: {len(clean_cache['hr'])} 点")


# ====================== 数据持久化 ======================

def save_modes_data():
    global all_mode_history
    for mode, data in all_mode_history.items():
        if not data["time"]: continue
        # 按照 时间+处理后/源数据 命名
        if mode == "clean":
            suffix = "clean"
        else:
            suffix = "raw"
        filename = f"{state['session_id']}_{suffix}.json"
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({k: list(v) for k, v in data.items()}, f, ensure_ascii=False)


# ====================== 串口线程 ======================

def serial_thread():
    global raw_cache, clean_cache, all_mode_history, last_human_time

    ser = None
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.005)
        print(f"✅ 串口已连接 {PORT}")
    except Exception as e:
        print(f"串口连接失败: {e}, 使用模拟数据")

    buf = b""
    use_sim = ser is None or not ser.is_open

    while True:
        try:
            ts = time.time()
            raw_hr = 0
            raw_br = 0
            is_human = False
            data_updated = False

            if not use_sim and ser and ser.in_waiting:
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
                    if tid == 0x0F09:
                        detected = fd[0] == 1
                        if detected:
                            last_human_time = time.time()
                        is_human = detected or (time.time() - last_human_time) < HUMAN_LOST_THRESHOLD
                        raw_data_cache_global["human"] = is_human
                        # 处理当前缓存的心率呼吸率
                        raw_h = raw_data_cache["heart"]
                        raw_b = raw_data_cache["breath"]
                        if raw_h > 0 and raw_b > 0:
                            raw_hr = raw_h if 30 < raw_h < 200 else 0
                            raw_br = raw_b if 5 < raw_b < 40 else 0
                            data_updated = True
                    elif tid == 0x0A14:
                        raw_data_cache["breath"] = breath_interp.feed(round(float_le(fd[:4])))
                        raw_data_cache_global["breath"] = raw_data_cache["breath"]
                    elif tid == 0x0A15:
                        raw_data_cache["heart"] = heart_interp.feed(round(float_le(fd[:4])))
                        raw_data_cache_global["heart"] = raw_data_cache["heart"]

            if not data_updated:
                # 使用模拟数据
                ts = time.time()
                raw_hr = 70 + 8 * math.sin(ts / 15) + np.random.normal(0, 3)
                raw_br = 16 + 3 * math.cos(ts / 20) + np.random.normal(0, 0.5)
                is_human = True

            raw_hr = raw_hr if 30 < raw_hr < 200 else 0
            raw_br = raw_br if 5 < raw_br < 40 else 0
            ts = time.time()

            raw_cache["hr"].append(raw_hr)
            raw_cache["br"].append(raw_br)
            raw_cache["time"].append(ts)

            clean_hr, clean_br = processor.process(raw_hr, raw_br, state["is_clean_on"])

            clean_cache["hr"].append(clean_hr)
            clean_cache["br"].append(clean_br)
            clean_cache["time"].append(ts)

            hrv_summary = calculate_hrv_summary(list(clean_cache["hr"]))
            rmssd = hrv_summary["rmssd"]
            phys = calculate_physical_load(clean_hr, clean_br)
            cog = calculate_cognitive_load(clean_hr, rmssd, hrv_summary["sdnn"])

            for mode, (h, b) in [("clean", (clean_hr, clean_br)), ("raw", (raw_hr, raw_br))]:
                all_mode_history[mode]["time"].append(ts)
                all_mode_history[mode]["hr"].append(h)
                all_mode_history[mode]["br"].append(b)
                all_mode_history[mode]["phys"].append(phys)
                all_mode_history[mode]["stress"].append(hrv_summary["stress"])
                all_mode_history[mode]["hrv"].append(hrv_summary["hrv_score"])
                all_mode_history[mode]["rmssd"].append(rmssd)

            total = len(all_mode_history["clean"]["time"])
            if total > 0 and total % 60 == 0 and total != state["last_save_idx"]:
                save_modes_data()
                state["last_save_idx"] = total

        except Exception as e:
            print(f"Serial Error: {e}")
        time.sleep(0.5)


# ====================== Flask路由 ======================

@app.route('/')
def index():
    return render_template('mmw.html')


@app.route('/data')
def get_data():
    if not clean_cache["time"]:
        return jsonify({})

    idx = -1
    clean_hr = clean_cache["hr"][idx]
    clean_br = clean_cache["br"][idx]

    hrv_summary = calculate_hrv_summary(list(clean_cache["hr"]))
    phys = calculate_physical_load(clean_hr, clean_br)
    cog = calculate_cognitive_load(clean_hr, hrv_summary["rmssd"], hrv_summary["sdnn"])

    response = {
        "hr": clean_hr,
        "br": clean_br,
        "hrv": hrv_summary["hrv_score"],
        "rmssd": hrv_summary["rmssd"],
        "sdnn": hrv_summary["sdnn"],
        "stress": hrv_summary["stress"],
        "phys": phys,
        "cog": cog,
        "is_clean": state["is_clean_on"],
        "rt": {
            "time": list(clean_cache["time"]),
            "hr": list(clean_cache["hr"]),
            "br": list(clean_cache["br"]),
        },
        "camera_active": state["camera_active"],
        "face_detected": state["face_detected"],
    }

    with threading.Lock():
        response["attribute"] = {
            "age_label": attribute_state["age_label"],
            "age_raw": attribute_state["age_raw"],
            "gender": attribute_state["gender"],
            "gender_confidence": attribute_state["gender_confidence"],
            "method": attribute_state["method"],
        }
        response["baseline"] = {
            "hr_max": BASELINE["hr_max"],
            "hr_rest": BASELINE["hr_rest"],
            "rmssd_baseline": BASELINE["rmssd_baseline"],
            "age_assumed": BASELINE["age_assumed"],
        }

    return jsonify(response)


@app.route('/longterm')
def get_longterm():
    return jsonify(all_mode_history)


@app.route('/toggle_clean')
def toggle_clean():
    state["is_clean_on"] = request.args.get('v') == 'true'
    return "ok"


if __name__ == '__main__':
    init_camera()
    init_simulation_data()

    if state["camera_active"]:
        threading.Thread(target=camera_thread, daemon=True).start()
        print("[INFO] 摄像头线程已启动")

    threading.Thread(target=serial_thread, daemon=True).start()

    print("=" * 60)
    print("  双轨负载监测系统 V2.1 (简化版)")
    print("  模式: 源数据 / 异常值剔除")
    print("  请打开浏览器访问: http://127.0.0.1:5030")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5030, debug=False)
