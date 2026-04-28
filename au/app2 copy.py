"""
app2.py — 结合app.py的多人脸/说话检测 + nemo.py的FER+情绪识别
✅ 保留：多人脸检测、人脸选择、说话检测、完整web界面
✅ 替换：用FER+模型做情绪识别，不需要校准
"""
import os, time, threading, json, base64
import numpy as np
from collections import deque
import sys

os.environ["FLASK_SKIP_DOTENV"] = "1"
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import mediapipe as mp
from flask import Flask, render_template, Response, jsonify, request

app = Flask(__name__)

# ========== 配置 ==========
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\emotion-ferplus-8.onnx"
FER_LABELS = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]

# 把FER+的8个标签映射到app.py的3个标签
EMOTION_MAP = {
    "neutral": "calm",
    "happiness": "happy",
    "sadness": "sad",
    "anger": "sad",
    "surprise": "calm",
    "disgust": "sad",
    "fear": "sad",
    "contempt": "sad"
}

POSES = ["front", "up", "down", "side"]
EMOTIONS = ["calm", "happy", "sad"]
CALIB_N = 30


def softmax(x):
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-10)


# ========== FaceDetector（多人脸） ==========
class FaceDetector:
    def __init__(self):
        self.fm = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=5, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
    
    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.fm.process(rgb)
        if not res.multi_face_landmarks:
            return []
        h, w = frame.shape[:2]
        return [np.array([[p.x*w, p.y*h, p.z*w] for p in fl.landmark])
                for fl in res.multi_face_landmarks]
    
    def release(self):
        self.fm.close()


# ========== SpeechDetector（说话检测） ==========
class SpeechDetector:
    def __init__(self):
        self.history = deque(maxlen=30)
        self.width_history = deque(maxlen=30)
        self.speaking = False
        self._spk_cnt = 0
        self._quiet_cnt = 0

    def update(self, lm):
        eye_dist = max(np.linalg.norm(lm[33][:2] - lm[263][:2]), 1.0)
        lip_open = abs(lm[14][1] - lm[13][1]) / eye_dist
        lip_width = abs(lm[61][0] - lm[291][0]) / eye_dist

        self.history.append(lip_open)
        self.width_history.append(lip_width)

        if len(self.history) < 12:
            return False

        arr = np.array(self.history)
        arr_w = np.array(self.width_history)
        diffs = np.abs(np.diff(arr))

        speed = np.mean(diffs[-10:])
        amplitude = np.max(arr[-15:]) - np.min(arr[-15:])
        width_var = np.var(arr_w[-10:])

        if len(arr) >= 20:
            recent = arr[-20:]
            peaks = 0
            troughs = 0
            for i in range(2, len(recent)-2):
                if recent[i] > recent[i-1] and recent[i] > recent[i+1] and recent[i] - recent[i-2] > 0.005:
                    peaks += 1
                if recent[i] < recent[i-1] and recent[i] < recent[i+1] and recent[i-2] - recent[i] > 0.005:
                    troughs += 1
            has_periodic = (peaks >= 2 and troughs >= 1) or (troughs >= 2 and peaks >= 1)
        else:
            has_periodic = False

        raw = (speed > 0.012 and amplitude > 0.04 and has_periodic and width_var > 0.00005)

        if raw:
            self._spk_cnt += 1
            self._quiet_cnt = 0
        else:
            self._quiet_cnt += 1
            self._spk_cnt = 0

        if self._spk_cnt >= 5:
            self.speaking = True
        elif self._quiet_cnt >= 8:
            self.speaking = False
        return self.speaking


# ========== FaceSelector（人脸选择） ==========
class FaceSelector:
    def __init__(self):
        self.tracks = {}
        self._next_id = 0
        self.primary_id = None
        self._lost_cnt = 0

    def select(self, lm_list, shape):
        if not lm_list:
            self._lost_cnt += 1
            if self._lost_cnt > 30:
                self.primary_id = None
            return None
        h, w = shape[:2]
        cx, cy = w / 2, h / 2
        faces = []
        for lm in lm_list:
            xs, ys = lm[:, 0], lm[:, 1]
            bx1, by1 = min(xs), min(ys)
            bx2, by2 = max(xs), max(ys)
            area = (bx2 - bx1) * (by2 - by1)
            fcx = (bx1 + bx2) / 2
            fcy = (by1 + by2) / 2
            dist = np.sqrt((fcx - cx) ** 2 + (fcy - cy) ** 2)
            score = area / (1 + dist * 0.005)
            faces.append({"box": (bx1, by1, bx2, by2), "area": area, "score": score, "lm": lm})

        new_tracks = {}
        used = set()
        for tid, trk in self.tracks.items():
            best_iou, best_j = 0.25, -1
            for j, f in enumerate(faces):
                if j in used:
                    continue
                iou = self._iou(trk["box"], f["box"])
                if iou > best_iou:
                    best_iou, best_j = iou, j
            if best_j >= 0:
                used.add(best_j)
                new_tracks[tid] = {
                    "box": faces[best_j]["box"], "frames": trk["frames"] + 1,
                    "area": faces[best_j]["area"], "score": faces[best_j]["score"],
                    "lm": faces[best_j]["lm"]
                }

        for j, f in enumerate(faces):
            if j not in used:
                new_tracks[self._next_id] = {
                    "box": f["box"], "frames": 1,
                    "area": f["area"], "score": f["score"],
                    "lm": f["lm"]
                }
                self._next_id += 1

        self.tracks = new_tracks
        self._lost_cnt = 0

        if self.primary_id is None or self.primary_id not in self.tracks:
            best = max(self.tracks.values(), key=lambda x: x["score"])
            for tid, trk in self.tracks.items():
                if trk is best:
                    self.primary_id = tid
                    break
        else:
            pri = self.tracks[self.primary_id]
            for tid, trk in self.tracks.items():
                if tid != self.primary_id and trk["frames"] > 15 and trk["score"] > pri["score"] * 1.8:
                    self.primary_id = tid
                    break

        return self.tracks[self.primary_id]["lm"] if self.primary_id in self.tracks else None

    @staticmethod
    def _iou(a, b):
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        x2, y2 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        return inter / max(union, 1)


# ========== FaceAligner（人脸对齐） ==========
class FaceAligner:
    def __init__(self):
        pass

    def align(self, frame, lm):
        """用MediaPipe的关键点对齐"""
        h, w = frame.shape[:2]
        
        left_eye = np.array([lm[33][0], lm[33][1]])
        right_eye = np.array([lm[263][0], lm[263][1]])
        
        dy = right_eye[1] - left_eye[1]
        dx = right_eye[0] - left_eye[0]
        angle = np.degrees(np.arctan2(dy, dx))
        
        eye_center = ((left_eye[0] + right_eye[0]) / 2, (left_eye[1] + right_eye[1]) / 2)
        
        xs, ys = lm[:, 0], lm[:, 1]
        bx1, by1 = min(xs), min(ys)
        bx2, by2 = max(xs), max(ys)
        bw, bh = bx2 - bx1, by2 - by1
        
        rot_mat = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
        rotated = cv2.warpAffine(frame, rot_mat, (w, h), borderValue=(0, 0, 0))
        
        pad = int(max(bw, bh) * 0.3)
        cx1 = max(0, int(bx1 - pad))
        cy1 = max(0, int(by1 - pad))
        cx2 = min(w, int(bx2 + pad))
        cy2 = min(h, int(by2 + pad))
        
        crop = rotated[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None
        
        aligned = cv2.resize(crop, (64, 64))
        return aligned


# ========== EmotionDetector（FER+推理） ==========
class EmotionDetector:
    def __init__(self, model_path):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        print(f"[OK] FER+ loaded: {os.path.basename(model_path)}")

    def predict(self, aligned_bgr):
        try:
            gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)
            blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
            self.net.setInput(blob)
            scores = self.net.forward()[0]
            probs = softmax(scores)
            
            # 返回所有8个标签的概率
            return {label: float(p) for label, p in zip(FER_LABELS, probs)}
        except Exception as e:
            print(f"[ERR] predict: {e}")
            return {label: 0.0 for label in FER_LABELS}


# ========== EmotionSmoother（时间平滑） ==========
class EmotionSmoother:
    def __init__(self, window_size=10):
        self.window = deque(maxlen=window_size)
        
    def update(self, label, conf):
        self.window.append((label, conf))
        if not self.window:
            return "calm", 0.0
        
        counts = {}
        for lbl, _ in self.window:
            counts[lbl] = counts.get(lbl, 0) + 1
        
        sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
        best_label = sorted_counts[0][0]
        
        best_confs = [c for l, c in self.window if l == best_label]
        avg_conf = np.mean(best_confs)
        
        return best_label, float(avg_conf)


# ========== 主Engine ==========
class Engine:
    def __init__(self):
        print("[INIT] Engine...")
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        print(f"[Engine] cam opened: {self.cap.isOpened()}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        self.det = FaceDetector()
        self.face_sel = FaceSelector()
        self.speech_det = SpeechDetector()
        self.aligner = FaceAligner()
        self.emotion_det = EmotionDetector(MODEL_PATH)
        self.smoother = EmotionSmoother(window_size=10)
        
        self.annotated = None
        self.lock = threading.Lock()
        self.running = False
        self.snapshots = deque(maxlen=5)
        self.timeline = deque(maxlen=1800)
        self.prev_emotion = None
        self.t0 = time.time()
        self._fc = 0
        self.status = dict(
            pose="front", emotion="calm", confidence=0.0,
            pitch=0.0, yaw=0.0, roll=0.0,
            calibrating=False, calib_pose=None, calib_emotion=None, calib_count=0,
            scores={"calm": 0, "happy": 0, "sad": 0}, au={}
        )
        print("[INIT] Engine OK!")

    def loop(self):
        try:
            if not self.cap.isOpened():
                return
            print("[Engine] thread started")
            self.running = True
            while self.running:
                try:
                    t0 = time.time()
                    ret, frame = self.cap.read()
                    if not ret:
                        time.sleep(0.01)
                        continue

                    ann = frame.copy()
                    lm_list = self.det.process(frame)
                    lm = self.face_sel.select(lm_list, frame.shape)

                    if len(lm_list) > 1:
                        cv2.putText(ann, f"FACES:{len(lm_list)}", (ann.shape[1] - 100, 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

                    if lm is not None:
                        speaking = self.speech_det.update(lm)
                        self._fc += 1

                        # 对齐并推理
                        aligned = self.aligner.align(frame, lm)
                        fer_probs = None
                        emotion_label = "calm"
                        confidence = 0.0
                        
                        if aligned is not None:
                            fer_probs = self.emotion_det.predict(aligned)
                            
                            if speaking:
                                emotion_label = "speaking"
                                confidence = 0.8
                            else:
                                # 映射到3个标签
                                mapped_probs = {e: 0.0 for e in EMOTIONS}
                                for fer_label, p in fer_probs.items():
                                    mapped_label = EMOTION_MAP[fer_label]
                                    mapped_probs[mapped_label] += p
                                
                                # 归一化
                                total = sum(mapped_probs.values()) + 1e-6
                                for k in mapped_probs:
                                    mapped_probs[k] /= total
                                
                                # 选最大的
                                emotion_label = max(mapped_probs.items(), key=lambda x: x[1])[0]
                                confidence = mapped_probs[emotion_label]
                                
                                # 时间平滑
                                emotion_label, confidence = self.smoother.update(emotion_label, confidence)
                        
                        # 时间线
                        if aligned is not None:
                            self.timeline.append({
                                "t": round(time.time() - self.t0, 2),
                                "e": emotion_label,
                                "s": {"calm": confidence if emotion_label == "calm" else 0,
                                      "happy": confidence if emotion_label == "happy" else 0,
                                      "sad": confidence if emotion_label == "sad" else 0}
                            })
                        
                        # 快照（说话时不拍）
                        if (emotion_label != self.prev_emotion and 
                            emotion_label not in ("no_face", "uncalibrated", "out_of_range", "speaking")):
                            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                            self.snapshots.append({
                                "img": base64.b64encode(buf).decode(),
                                "e": emotion_label, "t": round(time.time() - self.t0, 1)
                            })
                            self.prev_emotion = emotion_label

                        # 绘制
                        for i in [33, 133, 159, 145, 263, 362, 386, 374, 61, 291, 13, 14, 152, 105, 334, 55, 285]:
                            cv2.circle(ann, (int(lm[i][0]), int(lm[i][1])), 2, (0, 255, 0), -1)
                        cv2.putText(ann, f"P:0.0 Y:0.0 R:0.0", (10, 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        clr = {"happy": (0, 255, 0), "sad": (0, 0, 255), "calm": (128, 128, 128),
                               "uncalibrated": (0, 255, 255), "out_of_range": (0, 165, 255),
                               "no_face": (0, 0, 255), "speaking": (0, 200, 255)}
                        c = clr.get(emotion_label, (128, 128, 128))
                        cv2.putText(ann, f"{emotion_label.upper()} {confidence:.2f}",
                                    (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.9, c, 2)
                        
                        with self.lock:
                            self.status.update(
                                pose="front", emotion=emotion_label, confidence=round(confidence, 3),
                                pitch=0.0, yaw=0.0, roll=0.0,
                                scores={"calm": confidence if emotion_label == "calm" else 0,
                                      "happy": confidence if emotion_label == "happy" else 0,
                                      "sad": confidence if emotion_label == "sad" else 0},
                                au={}
                            )
                    else:
                        cv2.putText(ann, "NO FACE", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                        with self.lock:
                            self.status.update(emotion="no_face", au={}, scores={"calm": 0, "happy": 0, "sad": 0})

                    with self.lock:
                        self.annotated = ann
                    elapsed = time.time() - t0
                    time.sleep(max(0, 0.033 - elapsed))
                except Exception as e:
                    print(f"[Engine] error: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(1)
        except Exception as e:
            import traceback
            traceback.print_exc()
        self.running = False
        print("[Engine] thread stopped")

    def get_frame(self):
        with self.lock:
            if self.annotated is None:
                return None
            ret, buf = cv2.imencode(".jpg", self.annotated)
            return buf.tobytes() if ret else None

    def get_status(self):
        with self.lock:
            return dict(self.status)

    def start_calib(self, pose, emotion):
        return False

    def update_config(self, cfg):
        pass

    def stop(self):
        self.running = False
        self.cap.release()
        self.det.release()


# ========== Flask ==========
engine = Engine()
threading.Thread(target=engine.loop, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


def gen():
    while True:
        f = engine.get_frame()
        if f:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + f + b"\r\n"
        time.sleep(0.03)


@app.route("/video_feed")
def video_feed():
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    return jsonify(engine.get_status())


@app.route("/api/timeline")
def api_timeline():
    with engine.lock:
        return jsonify(list(engine.timeline))


@app.route("/api/snapshots")
def api_snapshots():
    with engine.lock:
        return jsonify(list(engine.snapshots))


@app.route("/api/calibrate/start", methods=["POST"])
def calib_start():
    return jsonify({"ok": False})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    return jsonify({"front": {"h_thresh": 1.2, "s_thresh": 1.2},
                   "up": {"h_thresh": 1.2, "s_thresh": 1.2},
                   "down": {"h_thresh": 1.0, "s_thresh": 1.0},
                   "side": {"h_thresh": 1.0, "s_thresh": 1.0},
                   "pitch_limit": 30})


@app.route("/api/calibrate/delete", methods=["POST"])
def calib_delete():
    return jsonify({"ok": False})


@app.route("/api/calibrate/delete_all", methods=["POST"])
def calib_delete_all():
    return jsonify({"ok": False})


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)
    finally:
        engine.stop()
