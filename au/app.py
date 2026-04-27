import os, sys, time, threading, json
import numpy as np
from collections import deque
import yaml

os.environ["FLASK_SKIP_DOTENV"] = "1"
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import torch
import mediapipe as mp
from flask import Flask, render_template, Response, jsonify, request
from sixdrepnet import SixDRepNet
from au_net.MEFL import MEFARG
#from au_net.ANFL import MEFARG
# ── 常量 ──────────────────────────────────────────────
AU_MAIN = ['AU1','AU2','AU4','AU5','AU6','AU7','AU9','AU10',
           'AU11','AU12','AU13','AU14','AU15','AU16','AU17','AU18',
           'AU19','AU20','AU22','AU23','AU24','AU25','AU26','AU27',
           'AU32','AU38','AU39']
AU_SUB  = ['AUL1','AUR1','AUL2','AUR2','AUL4','AUR4','AUL6','AUR6',
           'AUL10','AUR10','AUL12','AUR12','AUL14','AUR14']
# 显示哪些 AU
AU_SHOW = ['AU12','AU6','AU25','AU7','AU5','AU15','AU4','AU17','AU1','AU9']
AU_LABEL = {'AU12':'嘴角上拉','AU6':'颧骨提升','AU25':'嘴唇分开','AU7':'眼睑收紧',
            'AU5':'上睑抬起','AU15':'嘴角下拉','AU4':'皱眉','AU17':'下巴上提',
            'AU1':'内眉上抬','AU9':'鼻皱'}
# 5 点对齐目标（face_alignment 标准 96→224）
_s = 224.0 / 96.0
ALIGN_DST = np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],
                       [41.5493,92.3655],[70.7299,92.2041]], dtype=np.float32) * _s
_MEAN = np.array([0.485,0.456,0.406], dtype=np.float32)
_STD  = np.array([0.229,0.224,0.225], dtype=np.float32)
# MediaPipe 5 点索引：左眼外 右眼外 鼻尖 左嘴角 右嘴角
MP5 = [33, 263, 1, 61, 291]
# 帧上画关键点的索引
KP_IDX = [1,33,133,159,145,263,362,386,374,61,291,13,14,152,105,334,55,285]

# ── FaceDetector ──────────────────────────────────────
class FaceDetector:
    def __init__(self):
        self.fm = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        r = self.fm.process(rgb)
        if not r.multi_face_landmarks:
            return None
        h, w = frame.shape[:2]
        return np.array([[p.x*w, p.y*h, p.z*w] for p in r.multi_face_landmarks[0].landmark])
    def release(self):
        self.fm.close()

# ── PoseEstimator ─────────────────────────────────────
class PoseEstimator:
    def __init__(self):
        self.model = SixDRepNet()
    def estimate(self, frame, lm):
        if lm is None: return 0.,0.,0.
        h, w = frame.shape[:2]
        xs, ys = lm[:,0], lm[:,1]
        x0,x1 = int(xs.min()),int(xs.max())
        y0,y1 = int(ys.min()),int(ys.max())
        m=0.3; bw=max(x1-x0,1); bh=max(y1-y0,1)
        x0=max(0,int(x0-bw*m)); x1=min(w,int(x1+bw*m))
        y0=max(0,int(y0-bh*m)); y1=min(h,int(y1+bh*m))
        crop = frame[y0:y1, x0:x1]
        if crop.size==0 or crop.shape[0]<20: return 0.,0.,0.
        crop = cv2.resize(crop,(480,480), interpolation=cv2.INTER_LANCZOS4)
        p,y,r = self.model.predict(crop)
        return float(np.asarray(p).item()),float(np.asarray(y).item()),float(np.asarray(r).item())

# ── AUExtractor ───────────────────────────────────────
class AUExtractor:
    def __init__(self, arc='resnet50', ckpt='checkpoints/OpenGprahAU-ResNet50_second_stage.pth'):
    #def __init__(self, arc='resnet18', ckpt='checkpoints/OpenGprahAU-ResNet18_first_stage.pth'):
        self.sz = 224
        self.dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.net = MEFARG(num_main_classes=27, num_sub_classes=14, backbone=arc)
        if os.path.exists(ckpt):
            ckpt_data = torch.load(ckpt, map_location=self.dev)
            state_dict = {k.replace("module.", ""): v for k, v in ckpt_data["state_dict"].items()}
            self.net.load_state_dict(state_dict)
            print(f"[AU] 权重已加载: {ckpt}")
        else:
            print(f"[AU] ⚠ 权重缺失: {ckpt}")
        self.net.to(self.dev).eval()

    def _align(self, frame, lm):
        src = np.array([lm[i][:2] for i in MP5], dtype=np.float32)
        M = cv2.estimateAffinePartial2D(src, ALIGN_DST)[0]
        if M is None: return None
        return cv2.warpAffine(frame, M, (self.sz, self.sz), flags=cv2.INTER_LANCZOS4)

    def predict(self, frame, lm):
        if lm is None: return None
        aligned = self._align(frame, lm)
        if aligned is None: return None
        img = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
        img = (img - _MEAN) / _STD
        img = np.transpose(img, (2,0,1))[None]
        t = torch.from_numpy(img).float().to(self.dev)
        with torch.no_grad():
            out = self.net(t)
            if isinstance(out, (tuple,list)):
                mp_ = torch.sigmoid(out[0]).cpu().numpy()[0]*100
                sp_ = torch.sigmoid(out[1]).cpu().numpy()[0]*100 if len(out)>1 else np.zeros(14)
            else:
                mp_ = torch.sigmoid(out).cpu().numpy()[0]*100
                sp_ = np.zeros(14)
        r = {}
        for i,n in enumerate(AU_MAIN): r[n] = float(mp_[i])
        for i,n in enumerate(AU_SUB):  r[n] = float(sp_[i])
        return r

# ── EmotionMapper ────────────────────────────────────
class EmotionMapper:
    POSES = ['front', 'up', 'down', 'side']
    EMOTIONS = ['calm', 'happy', 'sad']

    def __init__(self, history=8, persist_path=None):
        self.baselines = {p: None for p in self.POSES}
        self.buffers = {p: [] for p in self.POSES}
        self.calibrating = None
        self.hist = deque(maxlen=history)
        # 每种姿态的激活阈值（z-score 单位）
        self.config = {
            'front': {'h_thresh': 1.5, 's_thresh': 1.5},
            'up':    {'h_thresh': 1.5, 's_thresh': 1.5},
            'down':  {'h_thresh': 1.2, 's_thresh': 1.2},
            'side':  {'h_thresh': 1.2, 's_thresh': 1.2},
        }
        self.last_emotion = 'calm'
        self.switch_cnt = 0
        self.persist_path = persist_path or os.path.join(
            os.path.dirname(__file__), 'data', 'baselines.json')
        self._load()

    # ── 持久化（均值 + 标准差）──
    def _load(self):
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                for p in self.POSES:
                    if p in d and d[p]:
                        self.baselines[p] = {
                            'mu':    {k: float(v) for k, v in d[p]['mu'].items()},
                            'sigma': {k: max(float(v), 0.1) for k, v in d[p]['sigma'].items()},
                        }
                print(f"[Mapper] 基线已加载: {list(k for k,v in self.baselines.items() if v)}")
            except Exception as e:
                print(f"[Mapper] 加载失败（将重新校准）: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            d = {}
            for p in self.POSES:
                if self.baselines[p]:
                    d[p] = {
                        'mu': self.baselines[p]['mu'],
                        'sigma': self.baselines[p]['sigma'],
                    }
            with open(self.persist_path, 'w', encoding='utf-8') as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Mapper] 保存失败: {e}")

    # ── 校准 ──
    def start_calib(self, pose):
        if pose not in self.POSES:
            return False
        self.calibrating = pose
        self.buffers[pose] = []
        return True

    def finish_calib(self, pose):
        buf = self.buffers.get(pose, [])
        if len(buf) < 20:
            self.calibrating = None
            return False
        keys = list(buf[0].keys())
        mu    = {k: float(np.mean([f[k] for f in buf])) for k in keys}
        sigma = {k: max(float(np.std([f[k] for f in buf])), 0.1) for k in keys}
        self.baselines[pose] = {'mu': mu, 'sigma': sigma}
        self.calibrating = None
        self._save()
        # 打印关键 AU 的基线，方便调试
        for au in ['AU12', 'AU6', 'AU15', 'AU4', 'AU25']:
            print(f"  {au}: μ={mu.get(au,0):.1f}  σ={sigma.get(au,0):.1f}")
        return True

    def feed_calib(self, au):
        if self.calibrating and self.calibrating in self.buffers:
            self.buffers[self.calibrating].append(au)
            return len(self.buffers[self.calibrating])
        return 0

    # ── 姿态 ──
    @staticmethod
    def get_pose(pitch, yaw):
        if abs(yaw) > 35: return 'side'
        if pitch >  15:    return 'up'
        if pitch < -20:    return 'down'
        return 'front'

    # ── 核心：AU → 情绪（z-score）──
    def predict(self, au, pitch, yaw):
        if au is None:
            return 'unknown', 'no_face', 0., {'calm':1,'happy':0,'sad':0}

        pose = self.get_pose(pitch, yaw)
        bl = self.baselines[pose]

        # 未校准
        if bl is None:
            return pose, 'uncalibrated', 0., {'calm':1,'happy':0,'sad':0}

        mu, sigma = bl['mu'], bl['sigma']
        thr = self.config[pose]

        # z-score：正值 = 比基线高，负值 = 比基线低
        def z(name):
            if name not in mu or name not in sigma:
                return 0.0
            return (au.get(name, 0.0) - mu[name]) / sigma[name]

        # ── 高兴：AU12（嘴角上拉）主导，AU6（颧骨）辅助 ──
        z12 = z('AU12');  z6 = z('AU6');  z25 = z('AU25')
        h_act = 0.0
        if z12 > 0.8 and z6 > -0.5:
            h_act = max(0, z12) * 0.55 + max(0, z6) * 0.30 + max(0, z25) * 0.15

        # ── 沮丧：AU15（嘴角下拉）主导，AU4/AU1 辅助 ──
        z15 = z('AU15');  z4 = z('AU4');  z1 = z('AU1');  z17 = z('AU17')
        s_act = 0.0
        if z15 > 0.8:
            s_act = max(0, z15) * 0.50 + max(0, z4) * 0.20 + max(0, z1) * 0.15 + max(0, z17) * 0.15

        # ── 平静 = 默认态，只有强激活才能切换走 ──
        c_act = 1.0
        if h_act > thr['h_thresh']:
            c_act = max(0.0, 1.0 - (h_act - thr['h_thresh']) * 0.4)
        elif s_act > thr['s_thresh']:
            c_act = max(0.0, 1.0 - (s_act - thr['s_thresh']) * 0.4)

        # 归一化
        total = h_act + s_act + c_act + 1e-6
        scores = {'happy': h_act/total, 'sad': s_act/total, 'calm': c_act/total}

        # ── 状态机（5 帧迟滞 ≈ 0.5 秒）──
        raw = max(scores, key=scores.get)
        if self.last_emotion == 'calm':
            if raw == 'happy' and h_act < thr['h_thresh']:
                raw = 'calm'
            elif raw == 'sad' and s_act < thr['s_thresh']:
                raw = 'calm'
        else:
            if raw == 'calm':
                if self.last_emotion == 'happy' and h_act > thr['h_thresh'] * 0.6:
                    raw = 'happy'
                elif self.last_emotion == 'sad' and s_act > thr['s_thresh'] * 0.6:
                    raw = 'sad'

        if raw != self.last_emotion:
            self.switch_cnt += 1
            if self.switch_cnt < 5:
                best = self.last_emotion
            else:
                best = raw; self.last_emotion = raw; self.switch_cnt = 0
        else:
            self.switch_cnt = 0; best = raw

        # 时序平滑
        self.hist.append(scores)
        smooth = {e: float(np.mean([x[e] for x in self.hist])) for e in self.EMOTIONS}
        conf = smooth[best]

        return pose, best, float(conf), smooth

# ── InferenceEngine ──────────────────────────────────
class Engine:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        print(f"[Engine] 摄像头状态 opened={self.cap.isOpened()}, idx=0")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.det = FaceDetector()
        self.pose_est = PoseEstimator()
        #self.au_ext = AUExtractor()
        self.au_ext = AUExtractor(arc='resnet50',ckpt='checkpoints/OpenGprahAU-ResNet50_second_stage.pth')
        persist = os.path.join(os.path.dirname(__file__),'data','baselines.json')
        self.mapper = EmotionMapper(history=5, persist_path=persist)
        self.annotated = None
        self.lock = threading.Lock()
        self.running = False
        self.status = dict(pose='-',emotion='uncalibrated',confidence=0.,
                           pitch=0.,yaw=0.,roll=0.,
                           calibrating=False,calib_pose=None,calib_count=0,
                           scores={'calm':0,'happy':0,'sad':0},
                           au={}, features={})

    def loop(self):
        try:
            if not self.cap.isOpened():
                print("[Engine] ❌ 摄像头打不开！检查是否被其他程序占用，或换个摄像头索引")
                return
            print("[Engine] ✅ 摄像头已打开，推理线程启动")
            self.running = True
            while self.running:
                try:
                    ret, frame = self.cap.read()
                    if not ret: time.sleep(.01); continue
                    ann = frame.copy()
                    lm = self.det.process(frame)
                    if lm is not None:
                        pitch,yaw,roll = self.pose_est.estimate(frame, lm)
                        au = self.au_ext.predict(frame, lm)
                        # 每 30 帧打印一次 AU 原始值，方便调试
                        if hasattr(self, '_dbg_cnt'):
                            self._dbg_cnt += 1
                        else:
                            self._dbg_cnt = 0
                        if au and self._dbg_cnt % 30 == 0:
                            print(f"[AU值] 12={au.get('AU12',0):.1f}  6={au.get('AU6',0):.1f}  "
                                f"15={au.get('AU15',0):.1f}  4={au.get('AU4',0):.1f}  "
                                f"25={au.get('AU25',0):.1f}  1={au.get('AU1',0):.1f}")                        
                        # 校准采集
                        if self.mapper.calibrating and au:
                            cnt = self.mapper.feed_calib(au)
                            with self.lock: self.status['calib_count'] = cnt
                            cv2.putText(ann, f"CALIB {self.mapper.calibrating.upper()}: {cnt}/30",
                                        (20,40), cv2.FONT_HERSHEY_SIMPLEX, .7, (0,255,0), 2)
                            if cnt >= 30:
                                self.mapper.finish_calib(self.mapper.calibrating)
                                with self.lock:
                                    self.status['calibrating']=False
                                    self.status['calib_pose']=None
                                    self.status['calib_count']=0

                        pose, emotion, conf, scores = self.mapper.predict(au, pitch, yaw)

                        # 绘制关键点
                        for i in KP_IDX:
                            cv2.circle(ann,(int(lm[i][0]),int(lm[i][1])),2,(0,255,0),-1)
                        # 姿态
                        cv2.putText(ann,f"P:{pitch:5.1f} Y:{yaw:5.1f} R:{roll:5.1f}",
                                    (10,30), cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
                        # 情绪
                        clr = {'happy':(0,255,0),'sad':(0,0,255),'calm':(128,128,128),
                               'uncalibrated':(0,255,255),'no_face':(0,0,255)}
                        c = clr.get(emotion,(128,128,128))
                        cv2.putText(ann,f"{emotion.upper()} {conf:.2f}",
                                    (10,65), cv2.FONT_HERSHEY_SIMPLEX,.9,c,2)
                        # 关键 AU
                        if au:
                            txt = "  ".join(f"{n}:{au[n]:.0f}" for n in AU_SHOW[:5])
                            cv2.putText(ann, txt, (10,95), cv2.FONT_HERSHEY_SIMPLEX,.45,(200,200,200),1)
                            txt2 = "  ".join(f"{n}:{au[n]:.0f}" for n in AU_SHOW[5:])
                            cv2.putText(ann, txt2, (10,115), cv2.FONT_HERSHEY_SIMPLEX,.45,(200,200,200),1)

                        with self.lock:
                            self.status.update(
                                pose=pose, emotion=emotion, confidence=round(conf,3),
                                pitch=round(pitch,1), yaw=round(yaw,1), roll=round(roll,1),
                                scores={k:round(v,3) for k,v in scores.items()},
                                au={k:round(v,1) for k,v in au.items()} if au else {})
                    else:
                        cv2.putText(ann,"NO FACE",(20,80),cv2.FONT_HERSHEY_SIMPLEX,1.,(0,0,255),2)
                        with self.lock:
                            self.status['emotion']='no_face'
                            self.status['au']={}
                            self.status['scores']={'calm':0,'happy':0,'sad':0}
                    with self.lock:
                        self.annotated = ann
                    time.sleep(.03)
                except Exception as e:
                    print(f"[Engine] 推理异常: {e}")
                    import traceback; traceback.print_exc()
                    time.sleep(1)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.running = False

    def get_frame(self):
        with self.lock:
            if self.annotated is None: return None
            r,buf = cv2.imencode('.jpg',self.annotated)
            return buf.tobytes() if r else None

    def get_status(self):
        with self.lock:
            s = dict(self.status); s['config']=self.mapper.config; return s

    def start_calib(self, pose):
        ok = self.mapper.start_calib(pose)
        if ok:
            with self.lock: self.status['calibrating']=True; self.status['calib_pose']=pose; self.status['calib_count']=0
        return ok

    def stop_calib(self, pose):
        ok = self.mapper.finish_calib(pose)
        with self.lock: self.status['calibrating']=False; self.status['calib_pose']=None
        return ok

    def update_config(self, cfg):
        for p,c in cfg.items():
            if p in self.mapper.config: self.mapper.config[p].update(c)

    def shutdown(self):
        self.running = False; self.cap.release(); self.det.release()

# ── Flask ────────────────────────────────────────────
app = Flask(__name__)
engine = Engine()
threading.Thread(target=engine.loop, daemon=True).start()

@app.route("/")
def index():
    return render_template("index.html")

def gen():
    while True:
        f = engine.get_frame()
        if f: yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"+f+b"\r\n"
        time.sleep(.03)

@app.route("/video_feed")
def video_feed():
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/status")
def api_status():
    return jsonify(engine.get_status())

@app.route("/api/calibrate/start", methods=["POST"])
def calib_start():
    d = request.get_json() or {}
    return jsonify({"ok": engine.start_calib(d.get("pose","front")), "pose": d.get("pose","front")})

@app.route("/api/calibrate/stop", methods=["POST"])
def calib_stop():
    d = request.get_json() or {}
    return jsonify({"ok": engine.stop_calib(d.get("pose","front")), "pose": d.get("pose","front")})

@app.route("/api/config", methods=["GET","POST"])
def api_config():
    if request.method == "POST":
        engine.update_config(request.get_json() or {})
        return jsonify({"ok": True})
    return jsonify(engine.mapper.config)

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, threaded=True, use_reloader=False)
    finally:
        engine.shutdown()

