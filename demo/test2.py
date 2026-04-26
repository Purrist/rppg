"""
test_v5.py —— 全修复版
  修复:
    1. [截断] warpAffine 画布放大 1.5 倍，再中心裁 256x256，下巴/嘴完整保留
    2. [Pitch 乱跳] 弃用 solvePnP，改用关键点几何比例估算姿态，绝对稳定
    3. [正脸崩] 恢复 test.py 原始预处理，不加任何增强
    4. [延迟] Queue maxsize=1
    5. [响应] smoothing window=6, pending 2帧/0.35阈值
    6. [姿态稳] Pose EMA 滤波 0.7/0.3
    7. [速度] MediaPipe 3帧检测+复用, ONNXRuntime 推理
"""
import os, sys, time, threading, traceback as tb, base64
from datetime import datetime
from queue import Queue
from collections import deque

import cv2, numpy as np, mediapipe as mp
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

IP_CAMERA_URL = "http://10.158.10.79:8080/video"
LOCAL_CAMERA = 0
g_camera_src = LOCAL_CAMERA
g_processor = None

ONNX_MODEL_PATH = r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\emotion-ferplus-8.onnx"
FER_LABELS = ['neutral', 'happiness', 'surprise', 'sadness',
              'anger', 'disgust', 'fear', 'contempt']

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_START = datetime.now().strftime("%Y%m%d_%H%M%S")
DEBUG_DIR = os.path.join(SCRIPT_DIR, "debug_aligned", RUN_START)
os.makedirs(DEBUG_DIR, exist_ok=True)
MAX_DBG = 30

# ========== ONNXRuntime 推理（比 OpenCV DNN 快） ==========
try:
    import onnxruntime as ort
    _ORT = True
except ImportError:
    _ORT = False
    print("[WARN] onnxruntime 未安装，回退到 OpenCV DNN")
    print("       pip install onnxruntime 可加速推理")


class EmotionDetector3Class:
    """原始预处理 + ONNXRuntime/OpenCV DNN"""
    def __init__(self, path):
        if _ORT:
            self.sess = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
            self.in_name = self.sess.get_inputs()[0].name
            print(f"[OK] FER+ ONNXRuntime: {os.path.basename(path)}")
        else:
            self.net = cv2.dnn.readNetFromONNX(path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            print(f"[OK] FER+ OpenCV DNN: {os.path.basename(path)}")

    def predict(self, bgr):
        # 和 test.py 完全一致：灰度 -> resize，不做任何增强
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, (64, 64), interpolation=cv2.INTER_AREA)
        blob = g.astype(np.float32).reshape(1, 1, 64, 64)

        if _ORT:
            scores = self.sess.run(None, {self.in_name: blob})[0][0]
        else:
            self.net.setInput(blob)
            scores = self.net.forward()[0]

        probs = self._sm(scores)
        p_happy = probs[1]
        p_calm  = probs[0] + probs[2] + probs[7]
        p_upset = probs[3] + probs[4] + probs[5] + probs[6]

        total = p_happy + p_calm + p_upset + 1e-6
        p_happy /= total; p_calm /= total; p_upset /= total

        final_probs = [p_calm, p_happy, p_upset]
        labels_3c = ["calm", "happy", "upset"]
        idx = int(np.argmax(final_probs))
        return labels_3c[idx], final_probs

    @staticmethod
    def _sm(x):
        e = np.exp(x - np.max(x))
        return e / e.sum()


class SmartAligner:
    """
    核心修复:
      - 几何法估算姿态：利用关键点比例，无万向锁，不跳变
      - 大画布 warpAffine：画布为原图 1.5 倍，再中心裁 256x256，绝不截断
      - MediaPipe 3 帧降频：复用上一次关键点，CPU 占用更低
    """
    def __init__(self):
        print("[INIT] SmartAligner (Geometry Pose + Big Canvas)")
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.frame_cnt = 0
        self.last_pts = None
        self.last_pose_raw = None
        self.last_pose = None  # EMA 滤波后

    def _estimate_pose(self, pts):
        """几何法估算 pitch/yaw/roll，稳定不跳变"""
        le = pts[33]
        re = pts[263]
        nose = pts[1]
        chin = pts[152]
        eye_c = (le + re) / 2.0
        eye_dist = np.linalg.norm(re - le)
        if eye_dist < 1:
            return None

        # roll: 双眼连线角度（最准）
        roll = np.degrees(np.arctan2(re[1] - le[1], re[0] - le[0]))

        # yaw: 鼻尖相对双眼中心的水平偏移
        # 正脸时 dx≈0；左转脸(左脸朝向相机)时 nose 在 eye_c 右侧，dx>0
        dx = (nose[0] - eye_c[0]) / eye_dist
        yaw = -dx * 55  # 经验系数：偏移 1.0*eye_dist ≈ 55°

        # pitch: 鼻尖到双眼连线的垂直偏移 + 下巴-鼻尖距离
        # 低头时 nose 在 eye_c 下方（图像 y 向下），dy_nose 增大
        dy_nose = (nose[1] - eye_c[1]) / eye_dist
        dy_chin = (chin[1] - nose[1]) / eye_dist
        # 低头：dy_nose 变大（正），dy_chin 也变大
        pitch = -(dy_nose * 35 + (dy_chin - 0.9) * 25)

        return (float(pitch), float(yaw), float(roll))

    def detect(self, frame):
        h, w = frame.shape[:2]
        self.frame_cnt += 1

        # ---- MediaPipe 3 帧降频：每 3 帧 process，中间复用 pts ----
        need_process = (self.frame_cnt % 3 == 0) or (self.last_pts is None)

        if need_process:
            try:
                # 降分辨率加速：320x240 检测，坐标再映射回原图
                small = cv2.resize(frame, (w // 2, h // 2))
                res = self.mesh.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
            except Exception as e:
                print(f"[WARN] mesh process: {e}")
                res = None

            if not res or not res.multi_face_landmarks:
                self.last_pts = None
                self.last_pose_raw = None
                return None, None, None

            lm = res.multi_face_landmarks[0]
            # 映射回原图坐标
            pts = np.array([[p.x * w, p.y * h] for p in lm.landmark], dtype=np.float32)
            self.last_pts = pts

            pose_raw = self._estimate_pose(pts)
            self.last_pose_raw = pose_raw
        else:
            pts = self.last_pts
            pose_raw = self.last_pose_raw

        if pts is None:
            return None, None, None

        # ---- Pose EMA 滤波 ----
        if pose_raw is not None:
            if self.last_pose is not None:
                pose = tuple(0.7 * p + 0.3 * lp for p, lp in zip(pose_raw, self.last_pose))
            else:
                pose = pose_raw
            self.last_pose = pose
        else:
            pose = self.last_pose

        # ---- 大画布对齐（彻底解决截断）----
        le = pts[33]
        re = pts[263]
        eye_c = ((le + re) / 2.0).astype(np.float32)
        dist = np.linalg.norm(re - le)
        if dist < 5:
            return None, None, None

        angle = np.degrees(np.arctan2(re[1] - le[1], re[0] - le[0]))

        # 计算 scale：让两眼在 256x256 中占 42% 宽度
        target_eye_dist = 256 * 0.42
        scale = target_eye_dist / dist

        # 画布放大 1.5 倍，确保平移后不会截断
        canvas_w = int(w * scale * 1.5)
        canvas_h = int(h * scale * 1.5)

        # 相似变换：绕 eye_c 旋转 + 等比缩放
        M = cv2.getRotationMatrix2D(tuple(eye_c), angle, scale)
        # 把 eye_c 移到画布中心
        M[0, 2] += canvas_w / 2 - eye_c[0]
        M[1, 2] += canvas_h / 2 - eye_c[1]

        big = cv2.warpAffine(frame, M, (canvas_w, canvas_h), flags=cv2.INTER_CUBIC)

        # 根据 pitch 动态调整垂直中心：低头(pitch负)时往下移，给下巴留空间
        pitch_offset = 0
        if pose:
            pitch_offset = int(np.clip(-pose[0] * 1.8, -70, 70))

        cx = canvas_w // 2
        cy = canvas_h // 2 + pitch_offset
        x1 = cx - 128
        y1 = cy - 128
        x2 = x1 + 256
        y2 = y1 + 256

        # 边界限制（如果超出画布，用黑边填充，绝不截断内容）
        pad_left = max(0, -x1)
        pad_top = max(0, -y1)
        pad_right = max(0, x2 - canvas_w)
        pad_bottom = max(0, y2 - canvas_h)

        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(canvas_w, x2)
        y2 = min(canvas_h, y2)

        crop = big[y1:y2, x1:x2]
        if crop.size == 0:
            return None, None, None

        # 如果有黑边需求，填充到 256x256
        if crop.shape[0] != 256 or crop.shape[1] != 256:
            aligned = np.zeros((256, 256, 3), dtype=np.uint8)
            aligned[pad_top:pad_top + crop.shape[0], pad_left:pad_left + crop.shape[1]] = crop
        else:
            aligned = crop

        # ---- 原图画框（用 pts 的 min/max + margin）----
        margin = int(dist * 0.5)
        xs, ys = pts[:, 0], pts[:, 1]
        x1b = max(0, int(xs.min()) - margin)
        y1b = max(0, int(ys.min()) - margin)
        x2b = min(w, int(xs.max()) + margin)
        y2b = min(h, int(ys.max()) + margin)
        box = (x1b, y1b, x2b, y2b)

        return aligned, box, pose


class TemporalSmoother:
    """Window=6, pending 2帧, 阈值 0.35"""
    def __init__(self, window=6):
        self.window = window
        self.history = deque(maxlen=window)
        self.state = "calm"
        self.conf = 0.0
        self.miss = 0
        self.pending = None
        self.pending_cnt = 0

    def update(self, label, probs, has_face):
        if not has_face:
            self.miss += 1
            self.pending = None
            self.pending_cnt = 0
            decay = 0.88 ** self.miss
            self.conf *= decay
            if self.conf < 0.03 or self.miss > 10:
                self.state = "calm"
                self.conf = 0.0
            return self.state, self.conf

        self.miss = 0
        if label is None:
            return self.state, self.conf

        self.history.append((label, probs))
        if len(self.history) < 3:
            self.state, self.conf = label, max(probs)
            return self.state, self.conf

        avg = {"calm": 0.0, "happy": 0.0, "upset": 0.0}
        for l, p in self.history:
            if l == "calm":   avg["calm"]  += p[0]
            elif l == "happy": avg["happy"] += p[1]
            else:              avg["upset"] += p[2]
        n = len(self.history)
        for k in avg:
            avg[k] /= n

        best = max(avg, key=avg.get)
        best_conf = avg[best]

        if best == self.state:
            self.pending = None
            self.pending_cnt = 0
            self.conf = self.conf * 0.4 + best_conf * 0.6
            return self.state, self.conf

        if self.pending == best:
            self.pending_cnt += 1
        else:
            self.pending = best
            self.pending_cnt = 1

        # 放宽：2帧确认，阈值 0.35
        if self.pending_cnt >= 2 and best_conf > 0.35:
            self.state = best
            self.conf = best_conf
            self.pending = None
            self.pending_cnt = 0
        else:
            self.conf = self.conf * 0.85 + best_conf * 0.15

        return self.state, self.conf


class Processor:
    def __init__(self, src):
        self.src = src
        self.cap = None
        self._open_cam(src)
        print(f"[OK] cam: {src}")
        print(f"[DEBUG] 对齐后视角 -> {DEBUG_DIR}")

        self.det = SmartAligner()
        self.fer = EmotionDetector3Class(ONNX_MODEL_PATH)
        self.smoother = TemporalSmoother(window=6)

        # Queue=1，减少延迟
        self.q = Queue(maxsize=1)
        self.lock = threading.Lock()
        self.jpeg = None
        self.box = None
        self.label = "calm"
        self.conf = 0.0
        self.pose = None
        self.aligned_preview = None

        self._nf = 0
        self._zz = False
        self._zc = 0
        self._dbg_b64 = []
        self.running = True

        threading.Thread(target=self._grab, daemon=True).start()
        threading.Thread(target=self._work, daemon=True).start()

    def _open_cam(self, src):
        try: self.cap.release()
        except: pass
        try:
            self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if self.cap.isOpened(): return
        except: pass
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _switch_cam(self):
        old = self.src
        self.src = LOCAL_CAMERA if old == IP_CAMERA_URL else IP_CAMERA_URL
        tag = "本地" if self.src == LOCAL_CAMERA else "IP"
        print(f"[WARN] {old} 失败, 自动切到{tag}")
        self._open_cam(self.src)

    def _grab(self):
        rt = 0
        while self.running:
            ok, f = self.cap.read()
            if not ok:
                self.cap.release()
                now = time.time()
                if rt == 0: rt = now
                elif now - rt >= 3:
                    rt = 0; self._switch_cam(); time.sleep(0.5)
                else: time.sleep(0.5)
                continue
            rt = 0
            if self.q.full():
                try: self.q.get_nowait()
                except: pass
            self.q.put(f)
            time.sleep(0.01)

    def _work(self):
        fc = 0
        while self.running:
            try: f = self.q.get(timeout=0.5)
            except: continue
            fc += 1

            try:
                if self._zz:
                    self._zc += 1
                    if self._zc >= 5:
                        self._zc = 0
                        crop, box, pose = self.det.detect(f)
                        if crop is not None:
                            self._zz = False; self._nf = 0
                            lb, pr = self.fer.predict(crop)
                            lb, cf = self.smoother.update(lb, pr, has_face=True)
                            self.label = lb; self.conf = cf
                            self.box = box; self.pose = pose
                            self._save(crop, lb)
                    time.sleep(0.2)
                    self._render(f)
                    continue

                crop, box, pose = self.det.detect(f)

                if crop is None:
                    self._nf += 1
                    lb, cf = self.smoother.update(None, None, has_face=False)
                    self.label = lb; self.conf = cf
                    self.box = None; self.pose = None
                    if self._nf >= 5: self._zz = True
                else:
                    self._nf = 0
                    if self._zz: self._zz = False

                    if fc % 2 == 0:
                        lb, pr = self.fer.predict(crop)
                        lb, cf = self.smoother.update(lb, pr, has_face=True)

                        # 大角度降置信度
                        if pose and (abs(pose[1]) > 55 or pose[0] < -45 or pose[0] > 35):
                            cf *= 0.5

                        self.label = lb; self.conf = cf
                        self.box = box; self.pose = pose
                        self._save(crop, lb)
                    else:
                        self.box = box; self.pose = pose

            except Exception as e:
                print(f"[ERR] {e}"); tb.print_exc()

            self._render(f)

    def _save(self, crop, label):
        try:
            ts = datetime.now().strftime("%H%M%S_%f")[:-3]

            fname_big = f"{ts}_{label}_256.jpg"
            cv2.imwrite(os.path.join(DEBUG_DIR, fname_big), crop)

            # 保存模型真实输入（和 predict 完全一致）
            model_input = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            model_input = cv2.resize(model_input, (64, 64), interpolation=cv2.INTER_AREA)
            fname_small = f"{ts}_{label}_64.jpg"
            cv2.imwrite(os.path.join(DEBUG_DIR, fname_small), model_input)

            preview = cv2.resize(crop, (112, 112))
            _, buf = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
            self.aligned_preview = buf.tobytes()

            _, buf64 = cv2.imencode(".jpg", model_input, [cv2.IMWRITE_JPEG_QUALITY, 60])
            b64 = base64.b64encode(buf64.tobytes()).decode()
            self._dbg_b64.append({"name": fname_small, "b64": b64})
            if len(self._dbg_b64) > MAX_DBG:
                self._dbg_b64 = self._dbg_b64[-MAX_DBG:]
        except Exception as e:
            print(f"[WARN] save failed: {e}")

    def _render(self, frame):
        try:
            if frame is None: return
            d = frame.copy()

            if self.box:
                x1, y1, x2, y2 = self.box
                color = (0, 200, 255)
                if self.label == "happy": color = (0, 255, 100)
                elif self.label == "upset": color = (0, 0, 255)

                cv2.rectangle(d, (x1, y1), (x2, y2), color, 2)
                Z = {"calm": "Calm", "happy": "Happy", "upset": "Upset"}
                txt = f"{Z[self.label]} ({self.conf:.0%})"
                tw, th = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                cv2.rectangle(d, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
                cv2.putText(d, txt, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            if self.pose:
                pitch, yaw, roll = self.pose
                cv2.putText(d, f"P:{pitch:+.0f} Y:{yaw:+.0f} R:{roll:+.0f}", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
                warns = []
                if pitch < -45: warns.append("HEAD DOWN")
                elif pitch > 35: warns.append("HEAD UP")
                if abs(yaw) > 55: warns.append("SIDE")
                if abs(roll) > 30: warns.append("TILT")
                if warns:
                    cv2.putText(d, " | ".join(warns), (10, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)

            if self.aligned_preview:
                preview = cv2.imdecode(np.frombuffer(self.aligned_preview, np.uint8), cv2.IMREAD_COLOR)
                if preview is not None:
                    ph, pw = preview.shape[:2]
                    h, w = d.shape[:2]
                    if ph < h and pw < w:
                        d[10:10+ph, w-pw-10:w-10] = preview
                        cv2.rectangle(d, (w-pw-10, 10), (w-10, 10+ph), (255, 255, 255), 1)

            ok, buf = cv2.imencode(".jpg", d, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                with self.lock:
                    self.jpeg = buf.tobytes()
        except Exception as e:
            print(f"[WARN] render failed: {e}")

    def stop(self):
        self.running = False
        try: self.cap.release()
        except: pass


def init():
    global g_processor
    if g_processor:
        g_processor.stop()
        time.sleep(0.3)
    g_processor = Processor(g_camera_src)


@app.route("/switch_camera", methods=["POST"])
def sw():
    global g_camera_src
    d = request.get_json() or {}
    c = d.get("cam", "")
    if c == "ip": g_camera_src = IP_CAMERA_URL
    elif c == "local": g_camera_src = LOCAL_CAMERA
    else: return jsonify(code=400)
    init()
    return jsonify(code=200)


@app.route("/video_feed")
def vf():
    def g():
        while True:
            if g_processor and g_processor.jpeg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + g_processor.jpeg + b"\r\n")
            time.sleep(0.033)
    return Response(g, mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/get_emotion")
def ge():
    if g_processor:
        with g_processor.lock:
            p = g_processor.pose
            return jsonify(
                emotion=g_processor.label,
                confidence=g_processor.conf,
                pose={
                    "pitch": round(p[0], 1) if p else 0,
                    "yaw": round(p[1], 1) if p else 0,
                    "roll": round(p[2], 1) if p else 0
                } if p else None
            )
    return jsonify(emotion="calm", confidence=0, pose=None)


@app.route("/debug_images")
def di():
    if not g_processor: return jsonify([])
    return jsonify(getattr(g_processor, "_dbg_b64", []))


@app.route("/")
def idx():
    return _HTML


_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
body{background:#0d1117;color:#c9d1d9;text-align:center;margin:0;padding:20px;font-family:'Segoe UI',sans-serif}
h2{color:#58a6ff}
.box{display:inline-block;border:2px solid #30363d;border-radius:12px;overflow:hidden;background:#161b22;margin-top:10px}
#live{display:block;width:640px;height:480px;object-fit:cover}
#ed{margin-top:16px;font-size:2.2em;font-weight:bold;min-height:50px;padding:10px;border-radius:8px;transition:all .3s}
#ed.happy{color:#3fb950;background:rgba(63,185,80,.1);border:1px solid #3fb950}
#ed.calm{color:#58a6ff;background:rgba(88,166,255,.1);border:1px solid #58a6ff}
#ed.upset{color:#f85149;background:rgba(248,81,73,.1);border:1px solid #f85149}
.cf{color:#8b949e;font-size:.4em;display:block;margin-top:4px}
#pose{margin-top:8px;font-family:'Courier New',monospace;font-size:.95em;color:#8b949e;background:#161b22;display:inline-block;padding:6px 14px;border-radius:6px;border:1px solid #30363d}
#warn{margin-top:6px;color:#f85149;font-weight:bold;font-size:1.05em;min-height:28px}
#dt{margin-top:20px;color:#58a6ff;font-size:1em}
#dg{display:flex;flex-wrap:wrap;justify-content:center;gap:10px;margin-top:8px;padding:10px;max-height:300px;overflow-y:auto;background:#161b22;border-radius:8px;border:1px solid #30363d}
#dg::-webkit-scrollbar{width:8px}
#dg::-webkit-scrollbar-track{background:#0d1117;border-radius:4px}
#dg::-webkit-scrollbar-thumb{background:#30363d;border-radius:4px}
.di{position:relative;width:110px;height:110px;flex-shrink:0;border-radius:6px;overflow:hidden;border:1px solid #30363d}
.di img{width:100%;height:100%;object-fit:cover;display:block;image-rendering:pixelated}
.di span{position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,.85);color:#fff;font-size:11px;text-align:center;padding:3px 0}
.di span.happy{color:#3fb950}
.di span.calm{color:#58a6ff}
.di span.upset{color:#f85149}
button{padding:10px 20px;margin:8px;border:none;border-radius:6px;font-size:15px;cursor:pointer;color:#fff}
#bi{background:#ff7a22}#bl{background:#2299ff}
button:disabled{opacity:.35}
</style>
</head>
<body>
<h2>v5 全修复：大画布 · 几何姿态 · 原始预处理</h2>
<div>
<button id="bi" onclick="sw('ip')">IP Camera</button>
<button id="bl" onclick="sw('local')">Local Camera</button>
</div>
<div class="box"><img id="live" src="/video_feed"></div>
<div id="ed" class="calm">加载中...</div>
<div id="pose">姿态: 等待检测...</div>
<div id="warn"></div>
<div id="dt">Debug 模型真实输入 (64x64)</div>
<div id="dg"></div>
<script>
var Z={calm:"平静",happy:"高兴",upset:"不高兴"};
setInterval(function(){
  fetch("/get_emotion").then(r=>r.json()).then(function(d){
    var ed=document.getElementById("ed");
    var p=(d.confidence*100).toFixed(0);
    ed.className=d.emotion;
    ed.innerHTML=Z[d.emotion]+'<span class="cf">置信度: '+p+'%</span>';
    var poseEl=document.getElementById("pose");
    var warnEl=document.getElementById("warn");
    if(d.pose){
      poseEl.textContent="姿态: P:"+d.pose.pitch+"°  Y:"+d.pose.yaw+"°  R:"+d.pose.roll+"°";
      var w=[];
      if(d.pose.pitch<-45) w.push("低头角度过大");
      if(d.pose.pitch>35) w.push("抬头角度过大");
      if(Math.abs(d.pose.yaw)>55) w.push("侧脸角度过大");
      if(Math.abs(d.pose.roll)>30) w.push("头部倾斜");
      warnEl.textContent=w.join("  |  ");
    }else{
      poseEl.textContent="姿态: 未检测到人脸";
      warnEl.textContent="";
    }
  }).catch(function(){});
},300);
setInterval(function(){
  fetch("/debug_images").then(r=>r.json()).then(function(arr){
    var dg=document.getElementById("dg");
    dg.innerHTML="";
    for(var i=arr.length-1;i>=0;i--){
      var d=document.createElement("div");d.className="di";
      var im=document.createElement("img");
      im.src="data:image/jpeg;base64,"+arr[i].b64;
      var sp=document.createElement("span");
      var parts=arr[i].name.replace(".jpg","").split("_");
      sp.className=parts[1];
      sp.textContent=parts[0]+" "+Z[parts[1]];
      d.appendChild(im);d.appendChild(sp);dg.appendChild(d);
    }
  }).catch(function(){});
},1000);
function sw(c){
  document.querySelectorAll("button").forEach(function(b){b.disabled=true});
  fetch("/switch_camera",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({cam:c})})
    .then(function(){}).catch(function(){})
    .finally(function(){document.querySelectorAll("button").forEach(function(b){b.disabled=false})});
}
</script>
</body>
</html>'''


if __name__ == "__main__":
    print("=" * 65)
    print("  v5 全修复:")
    print("    1. 大画布 1.5x + 黑边填充 -> 绝不截断")
    print("    2. 几何法姿态 -> 无万向锁，不跳 170/-170")
    print("    3. 原始预处理 -> 正脸效果回归 test.py")
    print("    4. Queue=1 | Window=6 | Pose EMA | MP 3帧降频")
    print("=" * 65)
    try:
        init()
        print("[RUN] http://127.0.0.1:5000")
        app.run(host="127.0.0.1", port=5000,
                debug=False, use_reloader=False, threaded=True)
    except:
        tb.print_exc()