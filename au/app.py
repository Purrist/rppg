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
from au_net.ANFL import MEFARG

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
    def __init__(self, arc='resnet18', ckpt='checkpoints/OpenGprahAU-ResNet18_first_stage.pth'):
        self.sz = 224
        self.dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.net = MEFARG(num_main_classes=27, num_sub_classes=14,
                          backbone=arc, neighbor_num=4, metric='dots')
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
    POSES = ['front','up','down','side']
    EMOTIONS = ['calm','happy','sad']

    def __init__(self, history=5, persist_path=None):
        self.baselines = {p:None for p in self.POSES}
        self.buffers   = {p:[]   for p in self.POSES}
        self.calibrating = None
        self.hist = deque(maxlen=history)
        self.config = {
            'front': {'happy_thresh':.5,'sad_thresh':.5,'weights':{'mouth':1.,'eyes':1.,'eyebrows':1.}},
            'up':    {'happy_thresh':.5,'sad_thresh':.5,'weights':{'mouth':1.,'eyes':1.,'eyebrows':1.}},
            'down':  {'happy_thresh':.5,'sad_thresh':.5,'weights':{'mouth':.1,'eyes':1.8,'eyebrows':1.8}},
            'side':  {'happy_thresh':.5,'sad_thresh':.5,'weights':{'mouth':.2,'eyes':1.5,'eyebrows':1.5}},
        }
        self.last_emotion = 'calm'
        self.switch_cnt = 0
        self.persist_path = persist_path or os.path.join(os.path.dirname(__file__),'data','baselines.json')
        self._load()

    # -- 持久化 --
    def _load(self):
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path,'r',encoding='utf-8') as f:
                    d = json.load(f)
                for p in self.POSES:
                    if p in d and d[p]: self.baselines[p] = {k:float(v) for k,v in d[p].items()}
                print(f"[Mapper] 基线已加载")
            except: pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            d = {p:self.baselines[p] for p in self.POSES if self.baselines[p]}
            with open(self.persist_path,'w',encoding='utf-8') as f: json.dump(d,f,indent=2,ensure_ascii=False)
        except: pass

    # -- 校准 --
    def start_calib(self, pose):
        if pose not in self.POSES: return False
        self.calibrating = pose; self.buffers[pose] = []; return True

    def finish_calib(self, pose):
        buf = self.buffers.get(pose,[])
        if len(buf) < 15:
            self.calibrating = None; return False
        keys = list(buf[0].keys())
        self.baselines[pose] = {k:float(np.mean([f[k] for f in buf])) for k in keys}
        self.calibrating = None; self._save(); return True

    def feed_calib(self, au):
        if self.calibrating and self.calibrating in self.buffers:
            self.buffers[self.calibrating].append(au)
            return len(self.buffers[self.calibrating])
        return 0

    # -- 姿态判断 --
    @staticmethod
    def get_pose(pitch, yaw):
        if abs(yaw) > 35: return 'side'
        if pitch > 15:  return 'up'
        if pitch < -20: return 'down'
        return 'front'

    # -- 核心：AU → 情绪 --
    def predict(self, au, pitch, yaw):
        if au is None:
            return 'unknown','no_face',0.,{'calm':0,'happy':0,'sad':0}
        pose = self.get_pose(pitch, yaw)
        bl = self.baselines[pose]
        w  = self.config[pose]['weights']
        g  = lambda n: au.get(n, 0.)

        # 有基线用相对值，无基线用绝对值
        if bl:
            a = lambda n: max(0., g(n) - bl.get(n, 0.))
        else:
            a = g

        # 高兴激活度
        h = (a('AU12')/100)*.35*w['mouth'] + (a('AU6')/100)*.25*w['eyes'] \
          + (a('AU25')/100)*.10*w['mouth'] + (a('AU7')/100)*.15*w['eyes'] \
          + (a('AU5')/100)*.15*w['eyes']
        # 沮丧激活度
        s = (a('AU15')/100)*.35*w['mouth'] + (a('AU4')/100)*.25*w['eyebrows'] \
          + (a('AU17')/100)*.20*w['mouth'] + (a('AU1')/100)*.20*w['eyebrows']
        # 平静
        mx = max(h, s)
        c = max(0., 1. - mx*1.5)
        t = h+s+c+1e-6
        scores = {'happy':h/t, 'sad':s/t, 'calm':c/t}

        # 状态机 + 迟滞
        raw = max(scores, key=scores.get)
        if self.last_emotion == 'calm':
            if raw=='happy' and h<.5: raw='calm'
            elif raw=='sad' and s<.5: raw='calm'
        else:
            if raw=='calm' and mx>.25: raw=self.last_emotion

        if raw != self.last_emotion:
            self.switch_cnt += 1
            if self.switch_cnt < 3: best = self.last_emotion
            else: best = raw; self.last_emotion = raw; self.switch_cnt = 0
        else:
            self.switch_cnt = 0; best = raw

        self.hist.append(scores)
        smooth = {e:float(np.mean([x[e] for x in self.hist])) for e in self.EMOTIONS}
        conf = smooth[best]

        if bl is None: best = 'uncalibrated'
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
        self.au_ext = AUExtractor()
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
        if not self.cap.isOpened():
            print("[Engine] ❌ 摄像头打不开！检查是否被其他程序占用，或换个摄像头索引")
            return
        print("[Engine] ✅ 摄像头已打开，推理线程启动")
        self.running = True
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret: time.sleep(.01); continue
                if int(time.time()*3) % 3 == 0:  # 每秒只打印一次
                    print(f"[Frame] shape={frame.shape}, mean={frame.mean():.1f}")
                ann = frame.copy()
                lm = self.det.process(frame)
                if int(time.time()*2) % 2 == 0:
                    print(f"[Face] detected={lm is not None}")
                if lm is not None:
                    pitch,yaw,roll = self.pose_est.estimate(frame, lm)
                    au = self.au_ext.predict(frame, lm)

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

