"""
app2.py - Debug version with extensive breakpoints to trace hang issues
"""
import os, time, threading, json, base64
import numpy as np
from collections import deque
import sys

print("[DEBUG] ==== 模块加载开始 ====")

os.environ["FLASK_SKIP_DOTENV"] = "1"
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("[DEBUG] import cv2...")
import cv2
print("[DEBUG] import torch...")
import torch
print("[DEBUG] import mediapipe...")
import mediapipe as mp
print("[DEBUG] import flask...")
from flask import Flask, render_template, Response, jsonify, request
print("[DEBUG] import sixdrepnet...")
from sixdrepnet import SixDRepNet
print("[DEBUG] import MEFARG...")
from au_net.MEFL import MEFARG

print("[DEBUG] ==== 所有 import 完成 ====")

# ── Constants ──────────────────────────────────────────────
CALIB_N = 30
AU_MAIN = ['AU1','AU2','AU4','AU5','AU6','AU7','AU9','AU10',
           'AU11','AU12','AU13','AU14','AU15','AU16','AU17','AU18',
           'AU19','AU20','AU22','AU23','AU24','AU25','AU26','AU27',
           'AU32','AU38','AU39']
AU_SUB = ['AUL1','AUR1','AUL2','AUR2','AUL4','AUR4','AUL6','AUR6',
          'AUL10','AUR10','AUL12','AUR12','AUL14','AUR14']
AU_SHOW = ['AU12','AU6','AU25','AU7','AU5','AU15','AU4','AU17','AU1','AU9']
AU_LABEL = {'AU12':'嘴角上拉','AU6':'颧骨提升','AU25':'嘴唇分开','AU7':'眼睑收紧',
            'AU5':'上睑抬起','AU15':'嘴角下拉','AU4':'皱眉','AU17':'下巴上提',
            'AU1':'内眉上抬','AU9':'鼻皱'}

_s = 224.0 / 96.0
ALIGN_DST = np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],
                       [41.5493,92.3655],[70.7299,92.2041]], dtype=np.float32) * _s
_MEAN = np.array([0.485,0.456,0.406], dtype=np.float32)
_STD  = np.array([0.229,0.224,0.225], dtype=np.float32)
MP5 = [33, 263, 1, 61, 291]
KP_IDX = [1,33,133,159,145,263,362,386,374,61,291,13,14,152,105,334,55,285]

POSES = ['front', 'up', 'down', 'side']
EMOTIONS = ['calm', 'happy', 'sad']
AU_HAPPY = ['AU12', 'AU6', 'AU25']
AU_SAD = ['AU15', 'AU4', 'AU1', 'AU17']

# ── FaceDetector ──────────────────────────────────────
class FaceDetector:
    def __init__(self):
        print("[DEBUG] FaceDetector.__init__ 开始...")
        self.fm = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=5, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        print("[DEBUG] FaceDetector.__init__ 完成")
    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        r = self.fm.process(rgb)
        if not r.multi_face_landmarks:
            return []
        h, w = frame.shape[:2]
        return [np.array([[p.x*w, p.y*h, p.z*w] for p in fl.landmark])
                for fl in r.multi_face_landmarks]
    def release(self):
        self.fm.close()

# ── SpeechDetector ────────────────────────────────────
class SpeechDetector:
    def __init__(self):
        print("[DEBUG] SpeechDetector.__init__ 开始...")
        self.history = deque(maxlen=20)
        self.speaking = False
        self._spk_cnt = 0
        self._quiet_cnt = 0
        print("[DEBUG] SpeechDetector.__init__ 完成")

    def update(self, lm):
        eye_dist = max(np.linalg.norm(lm[33][:2] - lm[263][:2]), 1.0)
        lip_open = abs(lm[14][1] - lm[13][1]) / eye_dist
        self.history.append(lip_open)
        if len(self.history) < 6:
            return False
        arr = np.array(self.history)
        diffs = np.abs(np.diff(arr))
        speed = np.mean(diffs[-8:])
        amplitude = np.max(arr[-12:]) - np.min(arr[-12:])
        raw = (speed > 0.008) or (amplitude > 0.06)
        if raw:
            self._spk_cnt += 1; self._quiet_cnt = 0
        else:
            self._quiet_cnt += 1; self._spk_cnt = 0
        if self._spk_cnt >= 3:
            self.speaking = True
        elif self._quiet_cnt >= 6:
            self.speaking = False
        return self.speaking

# ── FaceSelector ─────────────────────────────────────
class FaceSelector:
    def __init__(self):
        print("[DEBUG] FaceSelector.__init__ 开始...")
        self.tracks = {}
        self._next_id = 0
        self.primary_id = None
        self._lost_cnt = 0
        print("[DEBUG] FaceSelector.__init__ 完成")

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
            bbox = (xs.min(), ys.min(), xs.max(), ys.max())
            area = (bbox[2]-bbox[0]) * (bbox[3]-bbox[1])
            fcx = (bbox[0]+bbox[2]) / 2
            fcy = (bbox[1]+bbox[3]) / 2
            dist = np.sqrt((fcx-cx)**2 + (fcy-cy)**2)
            score = area / (1 + dist * 0.005)
            faces.append({'bbox': bbox, 'area': area, 'score': score, 'lm': lm})

        new_tracks = {}
        used = set()
        for tid, trk in self.tracks.items():
            best_iou, best_j = 0.25, -1
            for j, f in enumerate(faces):
                if j in used: continue
                iou = self._iou(trk['bbox'], f['bbox'])
                if iou > best_iou:
                    best_iou, best_j = iou, j
            if best_j >= 0:
                used.add(best_j)
                new_tracks[tid] = {
                    'bbox': faces[best_j]['bbox'], 'frames': trk['frames']+1,
                    'area': faces[best_j]['area'], 'score': faces[best_j]['score'],
                    'lm': faces[best_j]['lm']}

        for j, f in enumerate(faces):
            if j not in used:
                new_tracks[self._next_id] = {
                    'bbox': f['bbox'], 'frames': 1,
                    'area': f['area'], 'score': f['score'], 'lm': f['lm']}
                self._next_id += 1

        self.tracks = new_tracks
        self._lost_cnt = 0

        if self.primary_id is None or self.primary_id not in self.tracks:
            best = max(self.tracks.values(), key=lambda t: t['score'])
            for tid, t in self.tracks.items():
                if t is best: self.primary_id = tid; break
        else:
            pri = self.tracks[self.primary_id]
            for tid, t in self.tracks.items():
                if tid != self.primary_id and t['frames'] > 15 and t['score'] > pri['score'] * 1.8:
                    self.primary_id = tid; break

        return self.tracks[self.primary_id]['lm'] if self.primary_id in self.tracks else None

    @staticmethod
    def _iou(a, b):
        x1, y1 = max(a[0],b[0]), max(a[1],b[1])
        x2, y2 = min(a[2],b[2]), min(a[3],b[3])
        inter = max(0, x2-x1) * max(0, y2-y1)
        union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
        return inter / max(union, 1)

# ── PoseEstimator ─────────────────────────────────────
class PoseEstimator:
    def __init__(self):
        print("[DEBUG] PoseEstimator.__init__ 开始...")
        print("[DEBUG] 加载 SixDRepNet...")
        self.model = SixDRepNet()
        print("[DEBUG] PoseEstimator.__init__ 完成")

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
        print("[DEBUG] PoseEstimator.predict 调用...")
        p,y,r = self.model.predict(crop)
        print("[DEBUG] PoseEstimator.predict 完成")
        return float(np.asarray(p).item()),float(np.asarray(y).item()),float(np.asarray(r).item())

# ── AUExtractor ───────────────────────────────────────
class AUExtractor:
    def __init__(self, arc='resnet50', ckpt='checkpoints/OpenGprahAU-ResNet50_second_stage.pth'):
        print("[DEBUG] AUExtractor.__init__ 开始...")
        self.sz = 224
        # 强制使用 CPU 避免 CUDA 问题
        self.dev = torch.device('cpu')
        print(f"[DEBUG] AUExtractor 强制使用 device: {self.dev}")
        print("[DEBUG] 创建 MEFARG 网络...")
        try:
            self.net = MEFARG(num_main_classes=27, num_sub_classes=14, backbone=arc)
            print("[DEBUG] MEFARG 网络创建成功!")
        except Exception as e:
            print(f"[DEBUG] MEFARG 创建失败: {e}")
            import traceback; traceback.print_exc()
            raise
        print(f"[DEBUG] MEFARG 网络创建完成，检查 checkpoint: {ckpt}")
        if os.path.exists(ckpt):
            print(f"[DEBUG] 开始加载权重: {ckpt}")
            d = torch.load(ckpt, map_location=self.dev)
            sd = {k.replace("module.",""): v for k,v in d["state_dict"].items()}
            self.net.load_state_dict(sd)
            print(f"[AU] 权重已加载: {ckpt}")
        else:
            print(f"[AU] 权重缺失: {ckpt}")
        self.net.to(self.dev).eval()
        print("[DEBUG] AUExtractor.__init__ 完成")

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
        for i,n in enumerate(AU_SUB): r[n] = float(sp_[i])
        return r

# ── EmotionMapper (4x3 baselines + fixed state machine) ──
class EmotionMapper:
    def __init__(self, history=30, persist_path=None):
        print("[DEBUG] EmotionMapper.__init__ 开始...")
        self.baselines = {p: {e: None for e in EMOTIONS} for p in POSES}
        self.buffers = {}
        self.calibrating = None
        self.hist = deque(maxlen=history)
        self.config = {
            'front': {'h_thresh': 1.2, 's_thresh': 1.2},
            'up':    {'h_thresh': 1.2, 's_thresh': 1.2},
            'down':  {'h_thresh': 1.0, 's_thresh': 1.0},
            'side':  {'h_thresh': 1.0, 's_thresh': 1.0},
            'pitch_limit': 30,
        }
        self.last_emotion = 'calm'
        self.switch_cnt = 0
        self.persist_path = persist_path or os.path.join(os.path.dirname(__file__),'data','baselines.json')
        print(f"[DEBUG] EmotionMapper 加载基线: {self.persist_path}")
        self._load()
        print("[DEBUG] EmotionMapper.__init__ 完成")

    def _load(self):
        if not os.path.exists(self.persist_path): return
        try:
            with open(self.persist_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            for p in POSES:
                if p not in d: continue
                if 'calm' in d[p]:
                    for e in EMOTIONS:
                        if e in d[p] and d[p][e]:
                            self.baselines[p][e] = {
                                'mu': {k:float(v) for k,v in d[p][e]['mu'].items()},
                                'sigma': {k:max(float(v),0.1) for k,v in d[p][e]['sigma'].items()},
                            }
                else:
                    self.baselines[p]['calm'] = {
                        'mu': {k:float(v) for k,v in d[p]['mu'].items()},
                        'sigma': {k:max(float(v),0.1) for k,v in d[p]['sigma'].items()},
                    }
            loaded = [f"{p}/{e}" for p in POSES for e in EMOTIONS if self.baselines[p][e]]
            if loaded: print(f"[Mapper] 已加载基线: {loaded}")
            if '_config' in d:
                for k, v in d['_config'].items():
                    if k in self.config:
                        if isinstance(self.config[k], dict) and isinstance(v, dict):
                            self.config[k].update(v)
                        else:
                            self.config[k] = v
                print(f"[Mapper] 已加载阈值配置")
        except Exception as ex:
            print(f"[Mapper] 加载失败: {ex}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            d = {}
            for p in POSES:
                d[p] = {}
                for e in EMOTIONS:
                    if self.baselines[p][e]:
                        d[p][e] = {'mu': self.baselines[p][e]['mu'], 'sigma': self.baselines[p][e]['sigma']}
            d['_config'] = self.config
            with open(self.persist_path, 'w', encoding='utf-8') as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
        except Exception as ex:
            print(f"[Mapper] 保存失败: {ex}")

    def start_calib(self, pose, emotion):
        if pose not in POSES or emotion not in EMOTIONS: return False
        self.calibrating = (pose, emotion)
        self.buffers[f"{pose}_{emotion}"] = []
        return True

    def finish_calib(self, pose, emotion):
        key = f"{pose}_{emotion}"
        buf = self.buffers.get(key, [])
        if len(buf) < 20:
            self.calibrating = None; return False
        keys = list(buf[0].keys())
        mu = {k: float(np.mean([f[k] for f in buf])) for k in keys}
        sigma = {k: max(float(np.std([f[k] for f in buf])), 0.1) for k in keys}
        self.baselines[pose][emotion] = {'mu': mu, 'sigma': sigma}
        self.calibrating = None
        print(f"[Mapper] 完成校准: {pose}/{emotion}")
        self._save()
        for au in ['AU12','AU6','AU15','AU4','AU25']:
            print(f"  {pose}/{emotion} {au}: mu={mu.get(au,0):.1f} sigma={sigma.get(au,0):.1f}")
        return True

    def feed_calib(self, au):
        if not self.calibrating: return 0
        pose, emotion = self.calibrating
        key = f"{pose}_{emotion}"
        if key not in self.buffers: self.buffers[key] = []
        self.buffers[key].append(au)
        return len(self.buffers[key])

    def get_calibrated(self):
        return {p: [e for e in EMOTIONS if self.baselines[p][e]] for p in POSES}

    def delete_baseline(self, pose, emotion):
        if pose in self.baselines and emotion in self.baselines[pose]:
            self.baselines[pose][emotion] = None
            self._save()
            return True
        return False

    def delete_all_baselines(self):
        for p in POSES:
            for e in EMOTIONS:
                self.baselines[p][e] = None
        self._save()
        return True

    @staticmethod
    def get_pose(pitch, yaw):
        if abs(yaw) > 35: return 'side'
        if pitch > 15: return 'up'
        if pitch < -20: return 'down'
        return 'front'

    def predict(self, au, pitch, yaw, speaking=False):
        if au is None:
            return 'unknown', 'no_face', 0., {'calm':1,'happy':0,'sad':0}
        pose = self.get_pose(pitch, yaw)
        if abs(pitch) > self.config.get('pitch_limit', 30):
            return pose, 'out_of_range', 0., {'calm':0,'happy':0,'sad':0}
        if speaking:
            self.last_emotion = 'calm'
            self.switch_cnt = 0
            return pose, 'speaking', 0., {'calm':0.6,'happy':0,'sad':0}
        calm_bl = self.baselines[pose]['calm']
        if calm_bl is None:
            return pose, 'uncalibrated', 0., {'calm':1,'happy':0,'sad':0}

        mu, sig = calm_bl['mu'], calm_bl['sigma']
        thr = self.config[pose]

        def z(n):
            return (au.get(n,0.) - mu[n]) / sig[n] if n in mu else 0.

        z12,z6,z25 = z('AU12'),z('AU6'),z('AU25')
        h_act = 0.
        if z12 > 0.5:
            h_act = max(0,z12)*.55 + max(0,z6)*.30 + max(0,z25)*.15

        z15,z4,z1,z17 = z('AU15'),z('AU4'),z('AU1'),z('AU17')
        s_act = 0.
        if z15 > 0.5:
            s_act = max(0,z15)*.50 + max(0,z4)*.20 + max(0,z1)*.15 + max(0,z17)*.15

        happy_bl = self.baselines[pose]['happy']
        if happy_bl and h_act > 0:
            hm, hs = happy_bl['mu'], happy_bl['sigma']
            dist = np.mean([abs(au.get(a,0)-hm.get(a,0))/hs.get(a,1) for a in AU_HAPPY if a in hm])
            if dist > 2.5: h_act *= max(0, 1.-(dist-2.5)*.4)

        sad_bl = self.baselines[pose]['sad']
        if sad_bl and s_act > 0:
            sm, ss = sad_bl['mu'], sad_bl['sigma']
            dist = np.mean([abs(au.get(a,0)-sm.get(a,0))/ss.get(a,1) for a in AU_SAD if a in sm])
            if dist > 2.5: s_act *= max(0, 1.-(dist-2.5)*.4)

        c_act = 1.0
        if h_act > thr['h_thresh']:
            c_act = max(0., 1.-(h_act-thr['h_thresh'])*.4)
        elif s_act > thr['s_thresh']:
            c_act = max(0., 1.-(s_act-thr['s_thresh'])*.4)

        total = h_act + s_act + c_act + 1e-6
        scores = {'happy': h_act/total, 'sad': s_act/total, 'calm': c_act/total}

        if self.last_emotion == 'calm':
            if h_act >= thr['h_thresh'] and s_act < thr['s_thresh']*.8:
                raw = 'happy'
            elif s_act >= thr['s_thresh'] and h_act < thr['h_thresh']*.8:
                raw = 'sad'
            else:
                raw = 'calm'
        elif self.last_emotion == 'happy':
            raw = 'calm' if h_act < thr['h_thresh']*.4 else 'happy'
        elif self.last_emotion == 'sad':
            raw = 'calm' if s_act < thr['s_thresh']*.4 else 'sad'
        else:
            raw = 'calm'

        if raw != self.last_emotion:
            self.switch_cnt += 1
            if self.switch_cnt < 8:
                best = self.last_emotion
            else:
                best = raw; self.last_emotion = raw; self.switch_cnt = 0
        else:
            self.switch_cnt = 0; best = raw

        self.hist.append(scores)
        smooth = {e: float(np.mean([x[e] for x in self.hist])) for e in EMOTIONS}
        return pose, best, smooth[best], smooth

# ── InferenceEngine ──────────────────────────────────
class Engine:
    def __init__(self):
        print("[DEBUG] Engine.__init__ 开始...")
        print("[DEBUG] 打开摄像头...")
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        print(f"[Engine] 摄像头 opened={self.cap.isOpened()}")
        print("[DEBUG] 设置摄像头分辨率...")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("[DEBUG] 创建 FaceDetector...")
        self.det = FaceDetector()
        print("[DEBUG] 创建 FaceSelector...")
        self.face_sel = FaceSelector()
        print("[DEBUG] 创建 SpeechDetector...")
        self.speech_det = SpeechDetector()
        print("[DEBUG] 创建 PoseEstimator...")
        self.pose_est = PoseEstimator()
        print("[DEBUG] 创建 AUExtractor...")
        self.au_ext = AUExtractor()
        print("[DEBUG] 创建 EmotionMapper...")
        persist = os.path.join(os.path.dirname(__file__),'data','baselines.json')
        self.mapper = EmotionMapper(history=30, persist_path=persist)
        self.annotated = None
        self.lock = threading.Lock()
        self.running = False
        self.snapshots = deque(maxlen=5)
        self.timeline = deque(maxlen=1800)
        self.prev_emotion = None
        self.t0 = time.time()
        self._fc = 0
        self.status = dict(
            pose='-',emotion='uncalibrated',confidence=0.,
            pitch=0.,yaw=0.,roll=0.,
            calibrating=False,calib_pose=None,calib_emotion=None,calib_count=0,
            scores={'calm':0,'happy':0,'sad':0},au={})
        print("[DEBUG] Engine.__init__ 完成!")

    def loop(self):
        print("[DEBUG] Engine.loop 开始...")
        try:
            if not self.cap.isOpened():
                print("[Engine] 摄像头打不开"); return
            print("[Engine] 推理线程启动"); self.running = True
            while self.running:
                try:
                    t0 = time.time()
                    ret, frame = self.cap.read()
                    if not ret: time.sleep(.01); continue

                    ann = frame.copy()
                    lm_list = self.det.process(frame)
                    lm = self.face_sel.select(lm_list, frame.shape)

                    if len(lm_list) > 1:
                        cv2.putText(ann, f"FACES:{len(lm_list)}",
                                    (ann.shape[1]-100, 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, .5, (100,100,100), 1)

                    if lm is not None:
                        speaking = self.speech_det.update(lm)
                        pitch, yaw, roll = self.pose_est.estimate(frame, lm)
                        au = self.au_ext.predict(frame, lm)
                        self._fc += 1

                        if self.mapper.calibrating and au:
                            cp, ce = self.mapper.calibrating
                            cnt = self.mapper.feed_calib(au)
                            with self.lock:
                                self.status['calib_pose'] = cp
                                self.status['calib_emotion'] = ce
                                self.status['calib_count'] = cnt
                            cv2.putText(ann, f"CALIB {cp}/{ce}: {cnt}/{CALIB_N}",
                                        (20,40), cv2.FONT_HERSHEY_SIMPLEX, .7, (0,255,0), 2)
                            if cnt >= CALIB_N:
                                self.mapper.finish_calib(cp, ce)
                                with self.lock: self.status['calibrating'] = False

                        pose, emotion, conf, scores = self.mapper.predict(au, pitch, yaw, speaking=speaking)

                        if self._fc % 3 == 0:
                            self.timeline.append({
                                't': round(time.time()-self.t0, 2),
                                'e': emotion,
                                's': {k: round(v,3) for k,v in scores.items()}})

                        if emotion != self.prev_emotion and emotion not in ('no_face','uncalibrated','out_of_range','speaking'):
                            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                            self.snapshots.append({
                                'img': base64.b64encode(buf).decode(),
                                'e': emotion, 't': round(time.time()-self.t0, 1)})
                            self.prev_emotion = emotion

                        for i in KP_IDX:
                            cv2.circle(ann,(int(lm[i][0]),int(lm[i][1])),2,(0,255,0),-1)
                        cv2.putText(ann,f"P:{pitch:5.1f} Y:{yaw:5.1f} R:{roll:5.1f}",
                                    (10,30), cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
                        clr = {'happy':(0,255,0),'sad':(0,0,255),'calm':(128,128,128),
                               'uncalibrated':(0,255,255),'out_of_range':(0,165,255),
                               'no_face':(0,0,255),'speaking':(0,200,255)}
                        c = clr.get(emotion,(128,128,128))
                        cv2.putText(ann,f"{emotion.upper()} {conf:.2f}",
                                    (10,65), cv2.FONT_HERSHEY_SIMPLEX,.9,c,2)
                        if au:
                            cv2.putText(ann," ".join(f"{n}:{au[n]:.0f}" for n in AU_SHOW[:5]),
                                        (10,95), cv2.FONT_HERSHEY_SIMPLEX,.45,(200,200,200),1)
                            cv2.putText(ann," ".join(f"{n}:{au[n]:.0f}" for n in AU_SHOW[5:]),
                                        (10,115), cv2.FONT_HERSHEY_SIMPLEX,.45,(200,200,200),1)
                        with self.lock:
                            self.status.update(pose=pose,emotion=emotion,confidence=round(conf,3),
                                pitch=round(pitch,1),yaw=round(yaw,1),roll=round(roll,1),
                                scores={k:round(v,3) for k,v in scores.items()},
                                au={k:round(v,1) for k,v in au.items()} if au else {})
                    else:
                        cv2.putText(ann,"NO FACE",(20,80),cv2.FONT_HERSHEY_SIMPLEX,1.,(0,0,255),2)
                        with self.lock:
                            self.status.update(emotion='no_face',au={},scores={'calm':0,'happy':0,'sad':0})

                    with self.lock: self.annotated = ann
                    elapsed = time.time() - t0
                    time.sleep(max(0, 0.033 - elapsed))
                except Exception as e:
                    print(f"[Engine] 异常: {e}")
                    import traceback; traceback.print_exc()
                    time.sleep(1)
        except Exception as e:
            import traceback; traceback.print_exc()
        self.running = False
        print("[DEBUG] Engine.loop 结束")

    def get_frame(self):
        with self.lock:
            if self.annotated is None: return None
            r, buf = cv2.imencode('.jpg', self.annotated)
            return buf.tobytes() if r else None

    def get_status(self):
        with self.lock:
            s = dict(self.status)
            s['config'] = self.mapper.config
            s['calibrated'] = self.mapper.get_calibrated()
            return s

    def start_calib(self, pose, emotion):
        ok = self.mapper.start_calib(pose, emotion)
        if ok:
            with self.lock:
                self.status.update(calibrating=True, calib_pose=pose, calib_emotion=emotion, calib_count=0)
        return ok

    def update_config(self, cfg):
        mc = self.mapper.config
        for k, v in cfg.items():
            if k in mc:
                if isinstance(mc[k], dict) and isinstance(v, dict):
                    mc[k].update(v)
                else:
                    mc[k] = v
        self.mapper._save()

    def shutdown(self):
        self.running = False; self.cap.release(); self.det.release()

# ── Flask ────────────────────────────────────────────
print("[DEBUG] 创建 Flask app...")
app = Flask(__name__)
print("[DEBUG] 创建 Engine 实例...")
engine = Engine()
print("[DEBUG] 启动推理线程...")
threading.Thread(target=engine.loop, daemon=True).start()
print("[DEBUG] Flask 路由定义...")

@app.route("/")
def index():
    return render_template("index.html")

def gen():
    while True:
        f = engine.get_frame()
        if f:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"+f+b"\r\n"
        time.sleep(.03)

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
    d = request.get_json() or {}
    return jsonify({"ok": engine.start_calib(d.get("pose","front"), d.get("emotion","calm"))})

@app.route("/api/config", methods=["GET","POST"])
def api_config():
    if request.method == "POST":
        engine.update_config(request.get_json() or {})
        return jsonify({"ok": True})
    return jsonify(engine.mapper.config)

@app.route("/api/calibrate/delete", methods=["POST"])
def calib_delete():
    d = request.get_json() or {}
    ok = engine.mapper.delete_baseline(d.get("pose","front"), d.get("emotion","calm"))
    return jsonify({"ok": ok})

@app.route("/api/calibrate/delete_all", methods=["POST"])
def calib_delete_all():
    engine.mapper.delete_all_baselines()
    return jsonify({"ok": True})

print("[DEBUG] 所有路由定义完成，准备启动 Flask...")

if __name__ == "__main__":
    print("[DEBUG] 进入 app.run()...")
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)
    finally:
        engine.shutdown()
    print("[DEBUG] app.run() 退出")
