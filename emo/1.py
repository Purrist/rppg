"""
engage.py — 参与度感知系统（高精度 · 低频 · 全姿态）

设计哲学:
  不追求"每帧都准"，而是"综合多帧判断后一定准"
  情绪识别 + 头部姿态 融合为 参与度指标

核心策略（解决前面所有文件的痛点）:
  1. 【裁剪】凸包 + 40%padding + 侧脸自适应加宽 → 不截断
  2. 【对齐】2D仿射 + 2.5x画布 + pitch自适应偏移(×3.5) → 下巴不丢
  3. 【分类】二分类 positive/negative + unknown → 不在低质量输入上强行分类
  4. 【姿态融合】大角度自动降权，不丢弃数据
  5. 【规则辅助】极端姿态时用嘴角/眉头几何做辅助
  6. 【三级平滑】EMA → 窗口投票(20帧) → 状态机(3次确认) → 输出极度稳定
  7. 【1Hz输出】满足低频高精度需求
"""

import os, sys, time, threading, traceback as tb
from datetime import datetime
from queue import Queue
from collections import deque
import cv2, numpy as np, mediapipe as mp
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ===================== 配置 =====================
IP_CAMERA_URL = "http://10.215.158.45:8080/video"
LOCAL_CAMERA = 0
g_camera_src = LOCAL_CAMERA
g_processor = None

MODEL_PATH = r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\emotion-ferplus-8.onnx"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_START = datetime.now().strftime("%Y%m%d_%H%M%S")
DEBUG_DIR = os.path.join(SCRIPT_DIR, "debug_engage", RUN_START)
os.makedirs(DEBUG_DIR, exist_ok=True)


# ===================== FER+ 二分类 =====================
class FERPlusBinary:
    """
    FER+ 8类 → 二分类: positive(happiness) / negative(sad+angry+disgust+fear) / unknown
    不做任何概率操纵，纯合并
    """
    def __init__(self, model_path):
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 2
            opts.intra_op_num_threads = 2
            self.sess = ort.InferenceSession(model_path, opts, providers=['CPUExecutionProvider'])
            self.in_name = self.sess.get_inputs()[0].name
            self._use_ort = True
            print(f"[OK] FER+ ONNXRuntime: {os.path.basename(model_path)}")
        except Exception:
            self.net = cv2.dnn.readNetFromONNX(model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self._use_ort = False
            print(f"[OK] FER+ OpenCV DNN: {os.path.basename(model_path)}")

    def predict(self, aligned_bgr):
        """返回: {'positive': float, 'negative': float, 'unknown': float}"""
        try:
            gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
            blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
            if self._use_ort:
                scores = self.sess.run(None, {self.in_name: blob})[0][0]
            else:
                self.net.setInput(blob)
                scores = self.net.forward()[0]
            probs = self._softmax(scores)
            # 二分类映射 — 干净、对称
            positive = probs[1]                                  # happiness
            negative = probs[3] + probs[4] + probs[5] + probs[6]  # sad+angry+disgust+fear
            unknown  = probs[0] + probs[2] + probs[7]            # neutral+surprise+contempt
            return {
                'positive': float(positive),
                'negative': float(negative),
                'unknown':  float(unknown)
            }
        except Exception as e:
            print(f"[ERR] FER+ predict: {e}")
            return {'positive': 0.0, 'negative': 0.0, 'unknown': 1.0}

    @staticmethod
    def _softmax(x):
        e = np.exp(x - np.max(x))
        return e / (e.sum() + 1e-10)


# ===================== 凸包裁剪 + 2D仿射对齐 =====================
class FaceAligner:
    """
    改进点（vs 所有旧方案）:
    - 凸包确定人脸区域，而非 bbox → 侧脸时轮廓完整
    - 画布 2.5x（vs test2.py 的 1.5x）→ 低头时下巴不截断
    - pitch 偏移 ×3.5（vs test2.py 的 1.8）→ 低头 25° 时偏移 87px，够用
    - 侧脸时额外加宽 padding → 脸颊不截断
    """
    def __init__(self):
        print("[INIT] MediaPipe FaceMesh (凸包对齐)...")
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _ = self.mesh.process(np.zeros((480, 640, 3), dtype=np.uint8))
        print("[OK] FaceMesh")
        self.frame_cnt = 0
        self.last_pts = None

    def process(self, frame):
        """返回: (aligned_256x256, bbox, pose, pts)  bbox=None表示无人脸"""
        h, w = frame.shape[:2]
        self.frame_cnt += 1

        # MediaPipe 3帧降频
        need_process = (self.frame_cnt % 3 == 0) or (self.last_pts is None)
        if need_process:
            try:
                small = cv2.resize(frame, (w // 2, h // 2))
                res = self.mesh.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
            except Exception:
                res = None
            if not res or not res.multi_face_landmarks:
                self.last_pts = None
                return None, None, None, None
            lm = res.multi_face_landmarks[0]
            pts = np.array([[p.x * w, p.y * h] for p in lm.landmark], dtype=np.float32)
            self.last_pts = pts
        else:
            pts = self.last_pts

        if pts is None:
            return None, None, None, None

        pose = self._estimate_pose(pts)

        # ---- 凸包裁剪（核心改进 vs bbox）----
        hull = cv2.convexHull(pts.astype(np.int32))
        hull_pts = hull.reshape(-1, 2).astype(np.float32)
        x0, y0 = hull_pts.min(axis=0)
        x1, y1 = hull_pts.max(axis=0)
        fw, fh = x1 - x0, y1 - y0

        # 40% 基础 padding（vs 旧方案 30%）
        pad = max(fw, fh) * 0.4
        # 侧脸时额外加宽
        if pose:
            side_pad = abs(pose[1]) * 1.8  # yaw越大侧面padding越大
            pad = max(pad, fw * 0.4 + side_pad)

        cx1 = max(0, int(x0 - pad))
        cy1 = max(0, int(y0 - pad))
        cx2 = min(w, int(x1 + pad))
        cy2 = min(h, int(y1 + pad))
        crop_region = frame[cy1:cy2, cx1:cx2]
        if crop_region.size == 0:
            return None, None, pose, pts

        # ---- 2D仿射对齐（双眼水平）----
        le, re = pts[33], pts[263]
        eye_c = ((le + re) / 2.0).astype(np.float32)
        eye_dist = np.linalg.norm(re - le)
        if eye_dist < 5:
            return None, None, pose, pts

        angle = np.degrees(np.arctan2(re[1] - le[1], re[0] - le[0]))

        # 目标: 两眼在 256x256 中占 40% 宽度
        target_eye_dist = 256 * 0.40
        scale = target_eye_dist / eye_dist

        # 画布 2.5x（vs test2.py 的 1.5x）
        ch_crop, cw_crop = crop_region.shape[:2]
        canvas_w = max(int(cw_crop * scale * 2.5), 512)
        canvas_h = max(int(ch_crop * scale * 2.5), 512)

        eye_in_crop = eye_c - np.array([cx1, cy1], dtype=np.float32)
        M = cv2.getRotationMatrix2D(tuple(eye_in_crop), angle, scale)
        M[0, 2] += canvas_w / 2 - eye_in_crop[0]
        M[1, 2] += canvas_h / 2 - eye_in_crop[1]

        big = cv2.warpAffine(crop_region, M, (canvas_w, canvas_h), flags=cv2.INTER_CUBIC)

        # pitch 自适应偏移（系数 3.5 vs test2.py 的 1.8）
        pitch_offset = 0
        if pose:
            pitch_offset = int(np.clip(pose[0] * 3.5, -80, 80))

        cx = canvas_w // 2
        cy = canvas_h // 2 + pitch_offset
        x1a, y1a = cx - 128, cy - 128
        x2a, y2a = x1a + 256, y1a + 256

        # 黑边填充（绝不截断）
        pad_l = max(0, -x1a)
        pad_t = max(0, -y1a)
        pad_r = max(0, x2a - canvas_w)
        pad_b = max(0, y2a - canvas_h)
        x1a, y1a = max(0, x1a), max(0, y1a)
        x2a, y2a = min(canvas_w, x2a), min(canvas_h, y2a)

        crop_aligned = big[y1a:y2a, x1a:x2a]
        if crop_aligned.size == 0:
            return None, None, pose, pts

        aligned = np.zeros((256, 256, 3), dtype=np.uint8)
        sh, sw = crop_aligned.shape[:2]
        aligned[pad_t:pad_t + sh, pad_l:pad_l + sw] = crop_aligned

        # 原图 bbox
        margin = int(max(fw, fh) * 0.15)
        bbox = (max(0, int(x0) - margin), max(0, int(y0) - margin),
                min(w, int(x1) + margin), min(h, int(y1) + margin))

        return aligned, bbox, pose, pts

    @staticmethod
    def _estimate_pose(pts):
        """几何法: 无 solvePnP，不跳变"""
        le, re = pts[33], pts[263]
        nose, chin = pts[1], pts[152]
        eye_c = (le + re) / 2.0
        eye_dist = np.linalg.norm(re - le)
        if eye_dist < 1:
            return None
        roll = np.degrees(np.arctan2(re[1] - le[1], re[0] - le[0]))
        yaw = -((nose[0] - eye_c[0]) / eye_dist) * 55
        dy_nose = (nose[1] - eye_c[1]) / eye_dist
        dy_chin = (chin[1] - nose[1]) / eye_dist
        pitch = -(dy_nose * 35 + (dy_chin - 0.9) * 25)
        return (float(pitch), float(yaw), float(roll))


# ===================== 规则辅助（极端姿态时） =====================
class RuleHelper:
    """极端姿态时，用嘴角/眉头几何做辅助判断"""
    def analyze(self, pts):
        if pts is None or len(pts) < 300:
            return {'smile_hint': 0.5, 'frown_hint': 0.5}
        fh = np.linalg.norm(pts[10][:2] - pts[152][:2])
        if fh < 1:
            return {'smile_hint': 0.5, 'frown_hint': 0.5}
        mouth_l, mouth_r = pts[61], pts[291]
        mouth_c = pts[13]
        corner_avg_y = (mouth_l[1] + mouth_r[1]) / 2
        mouth_w = np.linalg.norm(mouth_r - mouth_l) + 1e-6
        smile_lift = (corner_avg_y - mouth_c[1]) / fh
        smile_width = mouth_w / fh
        smile = np.clip(0.5 + (-smile_lift * 20 + (smile_width - 0.35) * 5), 0, 1)
        brow_dist = np.linalg.norm(pts[296] - pts[66])
        brow_ref = np.linalg.norm(pts[9] - pts[6])
        frown = np.clip(1.0 - (brow_dist / (brow_ref + 1e-6) - 0.8) * 3, 0, 1)
        return {'smile_hint': float(smile), 'frown_hint': float(frown)}


# ===================== 姿态权重 =====================
def pose_weight(pose):
    """正脸±20°: 1.0 | 20-35°: 0.8 | 35-50°: 0.5 | >50°: 0.2"""
    if pose is None:
        return 0.3
    max_angle = max(abs(pose[0]), abs(pose[1]), abs(pose[2]))
    if max_angle <= 20:   return 1.0
    elif max_angle <= 35: return 0.8
    elif max_angle <= 50: return 0.5
    else:                 return 0.2


# ===================== 三级平滑管线 =====================
class SmoothPipeline:
    """
    L1: EMA(α=0.3) → 消除单帧噪声
    L2: 滑动窗口majority vote(window=20帧≈0.66秒) → 消除短时抖动
    L3: 状态机(连续3次L2确认才切换) → 消除跳变
    输出频率: 1Hz
    """
    def __init__(self):
        self.alpha = 0.3
        self.ema_pos = 0.0
        self.ema_neg = 0.0
        self._ema_init = False

        self.window = deque(maxlen=20)

        self.state = 'unknown'
        self.confirm_count = 0
        self.CONFIRM_NEED = 3

        self.output_label = 'unknown'
        self.output_confidence = 0.0
        self.output_engagement = 0.0
        self.output_pose = None
        self.output_pose_weight = 0.3

        self._last_output = 0
        self._interval = 1.0

    def update(self, scores, pose, has_face):
        now = time.time()
        pw = pose_weight(pose)

        if not has_face:
            self.ema_pos *= 0.95
            self.ema_neg *= 0.95
            self._interval = 2.0
            self._emit(now, pw, pose)
            return

        self._interval = 1.0

        # L1: EMA
        if not self._ema_init:
            self.ema_pos = scores['positive']
            self.ema_neg = scores['negative']
            self._ema_init = True
        else:
            self.ema_pos = self.alpha * scores['positive'] + (1 - self.alpha) * self.ema_pos
            self.ema_neg = self.alpha * scores['negative'] + (1 - self.alpha) * self.ema_neg

        # L2: 窗口投票
        current = 'positive' if self.ema_pos > self.ema_neg else (
            'negative' if self.ema_neg > self.ema_pos else 'unknown')
        self.window.append(current)
        counts = {'positive': 0, 'negative': 0, 'unknown': 0}
        for c in self.window:
            counts[c] += 1
        l2 = max(counts, key=counts.get)

        # L3: 状态机
        if l2 == self.state:
            self.confirm_count += 1
        else:
            if self.confirm_count >= self.CONFIRM_NEED:
                self.state = l2
                self.confirm_count = 1
            else:
                self.confirm_count = 0

        self._emit(now, pw, pose)

    def _emit(self, now, pw, pose):
        if now - self._last_output < self._interval:
            return
        self._last_output = now

        total = self.ema_pos + self.ema_neg + 1e-10
        if self.state == 'positive':
            conf = self.ema_pos / total
        elif self.state == 'negative':
            conf = self.ema_neg / total
        else:
            conf = max(self.ema_pos, self.ema_neg) / total * 0.5

        adj_conf = conf * pw

        if self.state == 'positive':
            engagement = adj_conf * 100
        elif self.state == 'negative':
            engagement = -adj_conf * 100
        else:
            engagement = 0.0

        self.output_label = self.state
        self.output_confidence = round(adj_conf, 3)
        self.output_engagement = round(engagement, 1)
        self.output_pose = pose
        self.output_pose_weight = pw


# ===================== 主处理器 =====================
class Processor:
    def __init__(self, src):
        self.src = src
        self.cap = None
        self._open_cam(src)
        print(f"[OK] cam: {src}")

        self.aligner = FaceAligner()
        self.fer = FERPlusBinary(MODEL_PATH)
        self.rule = RuleHelper()
        self.smoother = SmoothPipeline()

        self.q = Queue(maxsize=2)
        self.lock = threading.Lock()
        self.jpeg = None
        self.bbox = None
        self.running = True
        self._nf = 0
        self._dbg_cnt = 0

        threading.Thread(target=self._grab, daemon=True).start()
        threading.Thread(target=self._work, daemon=True).start()

    def _open_cam(self, src):
        try:
            self.cap.release()
        except Exception:
            pass
        try:
            self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if self.cap.isOpened():
                return
        except Exception:
            pass
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _switch_cam(self):
        old = self.src
        self.src = LOCAL_CAMERA if old == IP_CAMERA_URL else IP_CAMERA_URL
        tag = "本地" if self.src == LOCAL_CAMERA else "IP"
        print(f"[WARN] {old} 失败, 切到{tag}")
        self._open_cam(self.src)

    def _grab(self):
        rt = 0
        while self.running:
            ok, f = self.cap.read()
            if not ok:
                self.cap.release()
                now = time.time()
                if rt == 0:
                    rt = now
                elif now - rt >= 3:
                    rt = 0
                    self._switch_cam()
                    time.sleep(0.5)
                else:
                    time.sleep(0.5)
                continue
            rt = 0
            if self.q.full():
                try:
                    self.q.get_nowait()
                except Exception:
                    pass
            self.q.put(f)
            time.sleep(0.01)

    def _work(self):
        fc = 0
        while self.running:
            try:
                frame = self.q.get(timeout=0.5)
            except Exception:
                continue
            fc += 1

            # 每4帧推理一次（~7.5fps推理，足够低频高精度）
            should_infer = (fc % 4 == 0)

            if should_infer:
                aligned, bbox, pose, pts = self.aligner.process(frame)

                if aligned is None:
                    self._nf += 1
                    self.smoother.update(
                        {'positive': 0, 'negative': 0, 'unknown': 1},
                        pose, False
                    )
                    with self.lock:
                        self.bbox = None
                else:
                    self._nf = 0
                    scores = self.fer.predict(aligned)
                    pw = pose_weight(pose)

                    # 极端姿态: 混入规则信号
                    if pw < 0.5 and pts is not None:
                        r = self.rule.analyze(pts)
                        scores['positive'] = scores['positive'] * pw + r['smile_hint'] * (1 - pw) * 0.3
                        scores['negative'] = scores['negative'] * pw + r['frown_hint'] * (1 - pw) * 0.3

                    self.smoother.update(scores, pose, True)

                    self._dbg_cnt += 1
                    if self._dbg_cnt % 50 == 0:
                        self._save_debug(aligned)

                    with self.lock:
                        self.bbox = bbox

            self._render(frame)

    def _save_debug(self, aligned):
        try:
            ts = datetime.now().strftime("%H%M%S")
            state = self.smoother.output_label
            pw = self.smoother.output_pose_weight
            fname = f"{ts}_{state}_pw{pw:.1f}.jpg"
            model_in = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
            model_in = cv2.resize(model_in, (64, 64))
            cv2.imwrite(os.path.join(DEBUG_DIR, fname), model_in)
        except Exception:
            pass

    def _render(self, frame):
        try:
            if frame is None:
                return
            d = frame.copy()
            with self.lock:
                bbox = self.bbox
                s = self.smoother

            if bbox:
                x1, y1, x2, y2 = bbox
                eng = s.output_engagement
                color = (0, 220, 100) if eng > 20 else (0, 80, 255) if eng < -20 else (200, 200, 200)
                cv2.rectangle(d, (x1, y1), (x2, y2), color, 2)

                LABEL_CN = {'positive': 'POSITIVE', 'negative': 'NEGATIVE', 'unknown': 'UNKNOWN'}
                label_text = LABEL_CN.get(s.output_label, '?')
                pw_text = f"pw:{s.output_pose_weight:.0%}"
                eng_text = f"eng:{eng:+.0f}"
                text = f"{label_text} | {eng_text} | {pw_text}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(d, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
                cv2.putText(d, text, (x1 + 3, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

                if s.output_pose:
                    p, ya, r = s.output_pose
                    cv2.putText(d, f"P:{p:+.0f} Y:{ya:+.0f} R:{r:+.0f}",
                                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 200), 1)

                # 参与度条
                bar_y = d.shape[0] - 14
                bar_total = d.shape[1] - 20
                cv2.rectangle(d, (10, bar_y), (10 + bar_total, bar_y + 10), (50, 50, 50), -1)
                center = 10 + bar_total // 2
                bar_w = int(eng / 100 * (bar_total // 2))
                if eng >= 0:
                    cv2.rectangle(d, (center, bar_y), (center + bar_w, bar_y + 10), color, -1)
                else:
                    cv2.rectangle(d, (center + bar_w, bar_y), (center, bar_y + 10), color, -1)
                cv2.line(d, (center, bar_y - 2), (center, bar_y + 12), (255, 255, 255), 1)

            ok, buf = cv2.imencode(".jpg", d, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                self.jpeg = buf.tobytes()
        except Exception as e:
            print(f"[ERR] render: {e}")

    def stop(self):
        self.running = False
        try:
            self.cap.release()
        except Exception:
            pass


# ===================== Flask =====================
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
    if c == "ip":
        g_camera_src = IP_CAMERA_URL
    elif c == "local":
        g_camera_src = LOCAL_CAMERA
    else:
        return jsonify(code=400)
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
    return Response(g(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/get_engagement")
def ge():
    if g_processor:
        s = g_processor.smoother
        pose = s.output_pose
        return jsonify(
            label=s.output_label,
            confidence=s.output_confidence,
            engagement=s.output_engagement,
            pose_weight=s.output_pose_weight,
            pose={
                'pitch': round(pose[0], 1) if pose else 0,
                'yaw':   round(pose[1], 1) if pose else 0,
                'roll':  round(pose[2], 1) if pose else 0,
            } if pose else None,
        )
    return jsonify(label="unknown", confidence=0, engagement=0, pose_weight=0)


@app.route("/")
def idx():
    return HTML_CONTENT


# ===================== HTML =====================
HTML_CONTENT = (
    '<!DOCTYPE html>'
    '<html lang="zh-CN"><head><meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
    '<title>Engagement</title>'
    '<style>'
    '*{margin:0;padding:0;box-sizing:border-box}'
    'body{background:#0d1117;color:#c9d1d9;font-family:Segoe UI,system-ui,sans-serif;'
    'min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:20px}'
    'h1{color:#58a6ff;margin-bottom:6px;font-size:1.5em}'
    '.sub{color:#8b949e;margin-bottom:16px;font-size:0.85em}'
    '.cam-btns{margin-bottom:12px}'
    '.cam-btns button{padding:7px 18px;margin:0 4px;border:none;border-radius:5px;'
    'font-size:13px;cursor:pointer;color:#fff}'
    '.cam-btns button:disabled{opacity:.35;cursor:not-allowed}'
    '#btn-ip{background:#ff7a22}#btn-local{background:#2299ff}'
    '.video-wrap{border:2px solid #30363d;border-radius:10px;overflow:hidden;'
    'background:#000;max-width:800px;width:100%}'
    '#stream{width:100%;display:block}'
    '.dash{max-width:800px;width:100%;margin-top:16px;display:grid;'
    'grid-template-columns:1fr 1fr;gap:14px}'
    '.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}'
    '.card h3{color:#58a6ff;margin-bottom:10px;font-size:0.9em}'
    '.ev{font-size:2.8em;font-weight:bold;text-align:center;line-height:1.2;transition:color .5s}'
    '.ev.pos{color:#3fb950}.ev.neg{color:#f85149}.ev.neu{color:#8b949e}'
    '.ebar{margin-top:10px;height:8px;background:#21262d;border-radius:4px;position:relative}'
    '.ebar-c{position:absolute;left:50%;top:-2px;width:2px;height:12px;background:#fff;transform:translateX(-1px)}'
    '.ebar-f{position:absolute;top:0;height:100%;border-radius:4px;transition:all .5s}'
    '.dr{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #21262d;font-size:.85em}'
    '.dr:last-child{border:none}.dl{color:#8b949e}.dv{font-weight:600}'
    '.pg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;text-align:center}'
    '.pi{background:#21262d;padding:8px;border-radius:5px}'
    '.pi .v{font-size:1.3em;font-weight:bold;color:#58a6ff}'
    '.pi .l{font-size:.7em;color:#8b949e;margin-top:2px}'
    '@media(max-width:600px){.dash{grid-template-columns:1fr}}'
    '</style></head><body>'
    '<h1>Engagement Tracker</h1>'
    '<p class="sub">Low Freq (1Hz) High Precision | FER+ + FaceMesh + Pose Fusion</p>'
    '<div class="cam-btns">'
    '<button id="btn-ip" onclick="sw(\'ip\')">IP Camera</button>'
    '<button id="btn-local" onclick="sw(\'local\')">Local Camera</button>'
    '</div>'
    '<div class="video-wrap"><img id="stream" src="/video_feed"></div>'
    '<div class="dash">'
    '<div class="card"><h3>Engagement</h3>'
    '<div class="ev neu" id="ev">0</div>'
    '<div class="ebar"><div class="ebar-c"></div>'
    '<div class="ebar-f" id="ebar" style="left:50%;width:0;background:#8b949e"></div></div>'
    '</div>'
    '<div class="card"><h3>Details</h3>'
    '<div class="dr"><span class="dl">State</span><span class="dv" id="d-l">--</span></div>'
    '<div class="dr"><span class="dl">Adj. Confidence</span><span class="dv" id="d-c">--</span></div>'
    '<div class="dr"><span class="dl">Pose Trust</span><span class="dv" id="d-pw">--</span></div>'
    '</div>'
    '<div class="card" style="grid-column:1/-1"><h3>Head Pose</h3>'
    '<div class="pg">'
    '<div class="pi"><div class="v" id="p-p">--</div><div class="l">Pitch</div></div>'
    '<div class="pi"><div class="v" id="p-y">--</div><div class="l">Yaw</div></div>'
    '<div class="pi"><div class="v" id="p-r">--</div><div class="l">Roll</div></div>'
    '</div></div></div>'
    '<script>'
    'var LC={positive:"POSITIVE",negative:"NEGATIVE",unknown:"UNKNOWN"};'
    'function u(d){'
    'var e=d.engagement||0,el=document.getElementById("ev");'
    'el.textContent=(e>=0?"+":"")+e;'
    'el.className="ev "+(e>20?"pos":e<-20?"neg":"neu");'
    'var b=document.getElementById("ebar"),p=(e+100)/200*100;'
    'if(e>=0){b.style.left="50%";b.style.width=(p-50)+"%";b.style.background=e>20?"#3fb950":"#8b949e"}'
    'else{b.style.width=(50-p)+"%";b.style.left=p+"%";b.style.background=e<-20?"#f85149":"#8b949e"}'
    'document.getElementById("d-l").textContent=LC[d.label]||d.label;'
    'document.getElementById("d-c").textContent=(d.confidence*100).toFixed(1)+"%";'
    'document.getElementById("d-pw").textContent=(d.pose_weight*100).toFixed(0)+"%";'
    'if(d.pose){document.getElementById("p-p").textContent=d.pose.pitch+"\u00b0";'
    'document.getElementById("p-y").textContent=d.pose.yaw+"\u00b0";'
    'document.getElementById("p-r").textContent=d.pose.roll+"\u00b0"}'
    'else{document.getElementById("p-p").textContent="--";'
    'document.getElementById("p-y").textContent="--";'
    'document.getElementById("p-r").textContent="--"}}'
    'setInterval(function(){fetch("/get_engagement").then(function(r){return r.json()}).then(u).catch(function(){})},1000);'
    'function sw(t){document.querySelectorAll("button").forEach(function(b){b.disabled=true});'
    'fetch("/switch_camera",{method:"POST",headers:{"Content-Type":"application/json"},'
    'body:JSON.stringify({cam:t})}).finally(function(){document.querySelectorAll("button").forEach(function(b){b.disabled=false})})}'
    '</script></body></html>'
)


if __name__ == "__main__":
    print("=" * 60)
    print("  Engagement Tracker")
    print("  " + "-" * 56)
    print("  [1] Convex hull + 2.5x canvas + pitch offset x3.5")
    print("  [2] Binary: positive / negative / unknown")
    print("  [3] Pose decay: no data discard, only weight adjust")
    print("  [4] Rule assist: mouth/brow geometry at extreme pose")
    print("  [5] 3-level smooth: EMA -> window(20) -> state machine(3)")
    print("  [6] 1Hz output")
    print("  " + "-" * 56)
    print(f"  Model: {os.path.basename(MODEL_PATH)}")
    print(f"  Debug: {DEBUG_DIR}")
    print("=" * 60)
    try:
        init()
        print("[RUN] http://127.0.0.1:5000")
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)
    except Exception:
        tb.print_exc()
