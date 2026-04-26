import os, time, threading, json
import numpy as np
from collections import deque

os.environ["FLASK_SKIP_DOTENV"] = "1"

import cv2
import torch
import mediapipe as mp
from flask import Flask, Response, jsonify, request
from au_net.ANFL import MEFARG

AU_MAIN = ['AU1','AU2','AU4','AU5','AU6','AU7','AU9','AU10',
           'AU11','AU12','AU13','AU14','AU15','AU16','AU17','AU18',
           'AU19','AU20','AU22','AU23','AU24','AU25','AU26','AU27',
           'AU32','AU38','AU39']
AU_SUB  = ['AUL1','AUR1','AUL2','AUR2','AUL4','AUR4','AUL6','AUR6',
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
            print(f"[AU] 权重缺失: {ckpt}")
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

    @staticmethod
    def get_pose(pitch, yaw):
        if abs(yaw) > 35: return 'side'
        if pitch > 15:  return 'up'
        if pitch < -20: return 'down'
        return 'front'

    def predict(self, au, pitch, yaw):
        if au is None:
            return 'unknown','no_face',0.,{'calm':0.,'happy':0.,'sad':0.}
        g = lambda n: au.get(n, 0.)
        h = (g('AU12')/100)*.40 + (g('AU6')/100)*.30 + (g('AU25')/100)*.15 + (g('AU7')/100)*.15
        s = (g('AU15')/100)*.40 + (g('AU4')/100)*.30 + (g('AU17')/100)*.20 + (g('AU1')/100)*.10
        mx = max(h, s)
        c = max(0., 1. - mx*1.5)
        t = h + s + c + 1e-6
        scores = {'happy': h/t, 'sad': s/t, 'calm': c/t}
        raw = max(scores, key=scores.get)
        if self.last_emotion == 'calm':
            if raw == 'happy' and h < .5: raw = 'calm'
            elif raw == 'sad' and s < .5: raw = 'calm'
        else:
            if raw == 'calm' and mx > .25: raw = self.last_emotion
        if raw != self.last_emotion:
            self.switch_cnt += 1
            if self.switch_cnt < 3: best = self.last_emotion
            else: best = raw; self.last_emotion = raw; self.switch_cnt = 0
        else:
            self.switch_cnt = 0; best = raw
        self.hist.append(scores)
        smooth = {e: float(np.mean([x[e] for x in self.hist])) for e in self.EMOTIONS}
        conf = smooth[best]
        return 'front', best, float(conf), smooth

class Engine:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        print(f"[Engine] 摄像头状态 opened={self.cap.isOpened()}, idx=0")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.det = FaceDetector()
        self.au_ext = AUExtractor()
        persist = os.path.join(os.path.dirname(__file__),'data','baselines.json')
        self.mapper = EmotionMapper(history=5, persist_path=persist)
        self.annotated = None
        self.lock = threading.Lock()
        self.running = False
        self.status = dict(pose='-',emotion='uncalibrated',confidence=0.,
                           pitch=0.,yaw=0.,roll=0.,
                           calibrating=False,calib_pose=None,calib_count=0,
                           scores={'calm':0.,'happy':0.,'sad':0.},
                           au={}, features={})

    def loop(self):
        if not self.cap.isOpened():
            print("[Engine] 摄像头打不开！")
            return
        print("[Engine] 摄像头已打开，推理线程启动")
        self.running = True
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret: time.sleep(.01); continue
                ann = frame.copy()
                lm = self.det.process(frame)
                if lm is not None:
                    pitch, yaw, roll = 0., 0., 0.
                    au = self.au_ext.predict(frame, lm)
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
                    for i in KP_IDX:
                        cv2.circle(ann,(int(lm[i][0]),int(lm[i][1])),2,(0,255,0),-1)
                    clr = {'happy':(0,255,0),'sad':(0,0,255),'calm':(128,128,128),
                           'uncalibrated':(0,255,255),'no_face':(0,0,255)}
                    c = clr.get(emotion,(128,128,128))
                    cv2.putText(ann,f"{emotion.upper()} {conf:.2f}",
                                (10,65), cv2.FONT_HERSHEY_SIMPLEX,.9,c,2)
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
                        self.status['scores']={'calm':0.,'happy':0.,'sad':0.}
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

def get_html_page():
    au_labels_json = json.dumps(AU_LABEL)
    au_show_json = json.dumps(AU_SHOW)
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AU 情绪识别演示</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 20px; color: #00d4ff; }
        .main-content { display: flex; gap: 20px; flex-wrap: wrap; }
        .video-section { flex: 1; min-width: 400px; }
        .video-container { background: #0f0f23; border-radius: 12px; overflow: hidden; }
        .video-container img { width: 100%; display: block; }
        .info-section { flex: 0 0 300px; display: flex; flex-direction: column; gap: 15px; }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 15px;
            backdrop-filter: blur(10px);
        }
        .card h3 { color: #00d4ff; margin-bottom: 10px; font-size: 14px; }
        .emotion-display { text-align: center; }
        .emotion-value { font-size: 48px; font-weight: bold; text-transform: uppercase; }
        .emotion-happy { color: #00ff88; }
        .emotion-sad { color: #ff4757; }
        .emotion-calm { color: #ffa502; }
        .emotion-uncalibrated { color: #00d4ff; }
        .confidence { font-size: 18px; color: #888; margin-top: 5px; }
        .scores { display: flex; justify-content: space-around; margin-top: 15px; }
        .score-item { text-align: center; }
        .score-label { font-size: 12px; color: #888; }
        .score-value { font-size: 20px; font-weight: bold; }
        .au-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
        .au-item { background: rgba(0,212,255,0.1); padding: 8px; border-radius: 6px; text-align: center; }
        .au-name { font-size: 12px; color: #00d4ff; }
        .au-value { font-size: 18px; font-weight: bold; }
        .calib-buttons { display: flex; gap: 10px; margin-top: 10px; }
        .calib-btn { flex: 1; padding: 10px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
        .calib-btn.start { background: #00d4ff; color: #000; }
        .calib-btn.stop { background: #ff4757; color: #fff; }
        .calib-btn:hover { transform: scale(1.02); }
        .status-bar { background: rgba(0,212,255,0.1); padding: 10px; border-radius: 6px; text-align: center; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>AU 实时情绪识别</h1>
        <div class="main-content">
            <div class="video-section">
                <div class="video-container">
                    <img id="videoFeed" src="/video_feed" alt="Video Feed">
                </div>
            </div>
            <div class="info-section">
                <div class="card">
                    <h3>情绪识别</h3>
                    <div class="emotion-display">
                        <div id="emotionValue" class="emotion-value emotion-uncalibrated">--</div>
                        <div id="confidence" class="confidence">置信度: 0%</div>
                    </div>
                    <div class="scores">
                        <div class="score-item"><div class="score-label">平静</div><div id="scoreCalm" class="score-value">0%</div></div>
                        <div class="score-item"><div class="score-label">高兴</div><div id="scoreHappy" class="score-value">0%</div></div>
                        <div class="score-item"><div class="score-label">沮丧</div><div id="scoreSad" class="score-value">0%</div></div>
                    </div>
                </div>
                <div class="card">
                    <h3>主要 AU</h3>
                    <div class="au-list" id="auList"></div>
                </div>
                <div class="card">
                    <h3>校准</h3>
                    <div id="calibStatus" class="status-bar">姿态: <span id="poseStatus">-</span> | 计数: <span id="calibCount">0</span>/30</div>
                    <div class="calib-buttons">
                        <button class="calib-btn start" onclick="startCalib()">开始校准</button>
                        <button class="calib-btn stop" onclick="stopCalib()">停止校准</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script>
        const auLabels = AU_LABELS_JSON;
        const auShow = AU_SHOW_JSON;

        async function updateStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                const emo = data.emotion || 'unknown';
                const conf = (data.confidence || 0) * 100;

                const emotionEl = document.getElementById('emotionValue');
                emotionEl.textContent = emo.toUpperCase();
                emotionEl.className = 'emotion-value emotion-' + emo;

                document.getElementById('confidence').textContent = '置信度: ' + conf.toFixed(1) + '%';

                const scores = data.scores || {calm: 0, happy: 0, sad: 0};
                document.getElementById('scoreCalm').textContent = ((scores.calm || 0) * 100).toFixed(0) + '%';
                document.getElementById('scoreHappy').textContent = ((scores.happy || 0) * 100).toFixed(0) + '%';
                document.getElementById('scoreSad').textContent = ((scores.sad || 0) * 100).toFixed(0) + '%';

                const calibEl = document.getElementById('calibStatus');
                if (data.calibrating) {
                    calibEl.innerHTML = '校准中: ' + (data.calib_pose || '') + ' | 计数: ' + (data.calib_count || 0) + '/30';
                } else {
                    calibEl.innerHTML = '姿态: ' + (data.pose || '-') + ' | 计数: 0/30';
                }

                const auListEl = document.getElementById('auList');
                const auData = data.au || {};
                let auHtml = '';
                for (const au of auShow) {
                    const val = auData[au] || 0;
                    const label = auLabels[au] || au;
                    auHtml += '<div class="au-item"><div class="au-name">' + label + '</div><div class="au-value">' + val.toFixed(0) + '</div></div>';
                }
                auListEl.innerHTML = auHtml;
            } catch (e) { console.error('Status error:', e); }
        }

        async function startCalib() {
            await fetch('/api/calibrate/start', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({pose: 'front'})});
        }

        async function stopCalib() {
            await fetch('/api/calibrate/stop', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({pose: 'front'})});
        }

        setInterval(updateStatus, 200);
    </script>
</body>
</html>'''
    html = html.replace('AU_LABELS_JSON', au_labels_json)
    html = html.replace('AU_SHOW_JSON', au_show_json)
    return html

app = Flask(__name__)
engine = Engine()
threading.Thread(target=engine.loop, daemon=True).start()

@app.route("/")
def index():
    return get_html_page()

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

if __name__ == "__main__":
    try: app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
    finally: engine.shutdown()
