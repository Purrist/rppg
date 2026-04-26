"""
 test3.py — 终极最优解（全姿态精准版）
   核心突破:
     1. 纯 2D 仿射对齐: 解决低头时下巴消失、侧脸五官歪斜的问题
     2. EfficientNet 模型: 提供更准确的情绪识别
     3. 时序平滑滤波: 解决文字闪烁问题
     4. 侧脸过滤: 提高稳定性
     5. 架构优化: Frame Queue + 推理节流
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

# 模型路径
ONNX_MODEL_PATH = r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\emotion_classifier.onnx"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_START = datetime.now().strftime("%Y%m%d_%H%M%S")
DEBUG_DIR = os.path.join(SCRIPT_DIR, "debug_aligned", RUN_START)
os.makedirs(DEBUG_DIR, exist_ok=True)
MAX_DBG = 30


class EmotionDetector:
    """使用 EfficientNet 模型进行情绪识别"""
    def __init__(self, path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
        self.input_name = self.sess.get_inputs()[0].name
        # 模型输出顺序
        self.labels = ["angry","disgust","fear","happy","sad","surprise","neutral"]
        print("[OK] EfficientNet Emotion Loaded")

    def predict(self, bgr):
        face = cv2.resize(bgr, (224, 224))
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        face = face.astype(np.float32) / 255.0

        face = np.transpose(face, (2, 0, 1))
        face = np.expand_dims(face, axis=0)

        outputs = self.sess.run(None, {self.input_name: face})[0][0]
        probs = self._softmax(outputs)

        # 三分类映射（优化）
        p_happy = probs[3]
        p_calm = probs[6] + probs[5] * 0.3
        p_upset = probs[0] + probs[1] + probs[2] + probs[4] + probs[5] * 0.7

        total = p_happy + p_calm + p_upset + 1e-6
        final_probs = [p_calm/total, p_happy/total, p_upset/total]

        labels = ["calm", "happy", "upset"]
        idx = int(np.argmax(final_probs))
        return labels[idx], final_probs

    def _softmax(self, x):
        e = np.exp(x - np.max(x))
        return e / e.sum()


class SmartAligner:
    """最优解核心：基于 Mesh 的纯 2D 仿射对齐"""
    def __init__(self):
        print("[INIT] MediaPipe FaceMesh (2D Alignment) ...")
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        # 预热
        _ = self.mesh.process(np.zeros((480, 640, 3), dtype=np.uint8))
        print("[OK] FaceMesh ready")

    def detect(self, frame):
        h, w = frame.shape[:2]
        try:
            res = self.mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        except:
            return None, None, None
            
        if not res.multi_face_landmarks:
            return None, None, None

        lm = res.multi_face_landmarks[0]
        pts = np.array([[p.x * w, p.y * h] for p in lm.landmark], dtype=np.float32)

        # 关键点：左眼外角(33)，右眼外角(263)
        le = pts[33]
        re = pts[263]

        # 计算两眼中心与旋转角度
        eye_center = ((le + re) / 2.0).astype(np.float32)
        dY = re[1] - le[1]
        dX = re[0] - le[0]
        angle = np.degrees(np.arctan2(dY, dX))

        # 计算两眼距离，决定输出框大小
        dist = np.linalg.norm(re - le)
        # 放大系数 2.8 确保低头时下巴不被裁掉，抬头时额头不被裁掉
        size = int(dist * 2.8)
        size = max(100, min(size, 500)) # 安全限制

        # 构造 2D 仿射矩阵（只旋转不平移）
        M = cv2.getRotationMatrix2D(tuple(eye_center), angle, scale=1.0)

        # 计算平移量：让 eye_center 在输出图的正中偏上 (留出下巴空间)
        target_x = size / 2.0
        target_y = size * 0.35  # 0.35 是黄金比例，上方留少，下方留多给下巴
        M[0, 2] += target_x - eye_center[0]
        M[1, 2] += target_y - eye_center[1]

        # 执行 2D 仿射变换 (绝对不会产生透视拉伸畸变)
        aligned = cv2.warpAffine(frame, M, (size, size), flags=cv2.INTER_LINEAR)

        # 简单 yaw 估计
        nose = pts[1]
        dx = (nose[0] - eye_center[0]) / dist
        yaw = -dx * 55

        # 返回对齐后的图，以及原画面上的外接矩形用于画框
        xs, ys = pts[:, 0], pts[:, 1]
        box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        
        return aligned, box, (0, yaw, 0)


class TemporalSmoother:
    """时序平滑滤波器，解决文字闪烁问题"""
    def __init__(self, window_size=10):
        self.window = deque(maxlen=window_size)
        self.state = "calm"
        self.conf = 0

    def update(self, label, probs):
        self.window.append((label, probs))
        if not self.window:
            return "calm", 0.0
        
        # majority vote（计票）
        counts = {}
        for lbl, _ in self.window:
            counts[lbl] = counts.get(lbl, 0) + 1
        
        # 选得票最多的
        sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
        best_label = sorted_counts[0][0]
        
        # 对这个标签求平均置信度
        best_confs = []
        for l, p in self.window:
            if l == best_label:
                if best_label == "calm":
                    best_confs.append(p[0])
                elif best_label == "happy":
                    best_confs.append(p[1])
                else:  # upset
                    best_confs.append(p[2])
        
        avg_conf = np.mean(best_confs) if best_confs else 0.0
        
        return best_label, float(avg_conf)


class Processor:
    def __init__(self, src):
        self.src = src
        self.cap = None
        self._open_cam(src)
        print(f"[OK] cam: {src}")
        print(f"[DEBUG] 对齐后视角 -> {DEBUG_DIR}")
        
        self.det = SmartAligner()
        self.fer = EmotionDetector(ONNX_MODEL_PATH)
        self.smoother = TemporalSmoother(window_size=10)
        
        # 架构：Queue + 锁
        self.frame_queue = Queue(maxsize=3)
        self.lock = threading.Lock()
        self.jpeg = None
        self.box = None
        self.label = "calm"
        self.conf = 0.0
        
        self._nf = 0
        self._zz = False
        self._zc = 0
        self._dbg_b64 = []
        self.running = True
        
        # 启动线程
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
        """采集线程：只负责拿帧，不做推理"""
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
            if self.frame_queue.full():
                try: self.frame_queue.get_nowait()
                except: pass
            self.frame_queue.put(f)
            time.sleep(0.01)

    def _work(self):
        """推理线程：从队列拿帧，每3帧推理一次"""
        frame_counter = 0
        while self.running:
            try: frame = self.frame_queue.get(timeout=0.5)
            except: continue
            frame_counter += 1
            
            try:
                if self._zz:
                    self._zc += 1
                    if self._zc >= 5:
                        self._zc = 0
                        crop, box, pose = self.det.detect(frame)
                        if crop is not None:
                            # 侧脸过滤
                            if pose and abs(pose[1]) <= 45:
                                self._zz = False; self._nf = 0
                                lb, pr = self.fer.predict(crop)
                                lb, cf = self.smoother.update(lb, pr)
                                self.label = lb; self.conf = cf; self.box = box
                                self._save(crop, lb)
                    time.sleep(0.2)
                    self._render(frame)
                    continue

                # 每3帧推理一次，节流！
                should_infer = (frame_counter % 3 == 0)
                
                crop = None
                box = None
                pose = None
                
                if should_infer:
                    crop, box, pose = self.det.detect(frame)
                else:
                    # 只检测人脸位置，不做对齐和推理
                    _, box, _ = self.det.detect(frame)
                
                if crop is None:
                    self._nf += 1
                    self.label = "calm"; self.conf = 0; self.box = box
                    self.smoother.window.clear() # 丢脸时清空历史，避免恢复时拖泥带水
                    if self._nf >= 5: self._zz = True
                else:
                    self._nf = 0
                    if self._zz: self._zz = False
                    
                    # 侧脸过滤（关键稳定）
                    if pose and abs(pose[1]) <= 45:
                        lb, pr = self.fer.predict(crop)
                        lb, cf = self.smoother.update(lb, pr)
                        self.label = lb; self.conf = cf; self.box = box
                        self._save(crop, lb)
                    else:
                        self.box = box
            except Exception as e:
                print(f"[ERR] {e}"); tb.print_exc()
                
            self._render(frame)

    def _save(self, crop, label):
        try:
            # 关键：这里保存的是对齐后、送入模型前的图，方便你直观验证
            debug_crop = cv2.resize(crop, (224, 224))
            ts = datetime.now().strftime("%H%M%S")
            fname = f"{ts}_{label}.jpg"
            cv2.imwrite(os.path.join(DEBUG_DIR, fname), debug_crop)
            
            _, buf = cv2.imencode(".jpg", debug_crop, [cv2.IMWRITE_JPEG_QUALITY, 60])
            b64 = base64.b64encode(buf.tobytes()).decode()
            self._dbg_b64.append({"name": fname, "b64": b64})
            if len(self._dbg_b64) > MAX_DBG:
                self._dbg_b64 = self._dbg_b64[-MAX_DBG:]
        except: pass

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
            
            ok, buf = cv2.imencode(".jpg", d, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                with self.lock:
                    self.jpeg = buf.tobytes()
        except: pass

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
            return jsonify(emotion=g_processor.label,
                           confidence=g_processor.conf)
    return jsonify(emotion="calm", confidence=0)


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

#ed{
  margin-top:20px; font-size:2.2em; font-weight:bold; min-height:50px;
  padding:10px; border-radius:8px;
  transition: all 0.3s;
}
#ed.happy{color:#3fb950; background:rgba(63,185,80,0.1); border:1px solid #3fb950}
#ed.calm{color:#58a6ff; background:rgba(88,166,255,0.1); border:1px solid #58a6ff}
#ed.upset{color:#f85149; background:rgba(248,81,73,0.1); border:1px solid #f85149}

.cf{color:#8b949e;font-size:.4em;display:block;margin-top:4px}

#dt{margin-top:20px;color:#58a6ff;font-size:1em}
#dg{
  display:flex; flex-wrap:wrap; justify-content:center; gap:10px;
  margin-top:8px; padding:10px;
  max-height:300px; overflow-y:auto;
  background:#161b22; border-radius:8px; border:1px solid #30363d;
}
#dg::-webkit-scrollbar{width:8px}
#dg::-webkit-scrollbar-track{background:#0d1117;border-radius:4px}
#dg::-webkit-scrollbar-thumb{background:#30363d;border-radius:4px}

.di{position:relative;width:110px;height:110px;flex-shrink:0;border-radius:6px;overflow:hidden;border:1px solid #30363d}
.di img{width:100%;height:100%;object-fit:cover;display:block;image-rendering:pixelated}
.di span{
  position:absolute;bottom:0;left:0;right:0;
  background:rgba(0,0,0,0.85); color:#fff;
  font-size:11px; text-align:center; padding:3px 0;
}
.di span.happy{color:#3fb950}
.di span.calm{color:#58a6ff}
.di span.upset{color:#f85149}

button{padding:10px 20px;margin:8px;border:none;border-radius:6px;font-size:15px;cursor:pointer;color:#fff}
#bi{background:#ff7a22}#bl{background:#2299ff}
button:disabled{opacity:.35}
</style>
</head>
<body>
<h2>全姿态精准 3 分类 (基于 2D 仿射对齐 + EfficientNet)</h2>
<div>
<button id="bi" onclick="sw('ip')">IP Camera</button>
<button id="bl" onclick="sw('local')">Local Camera</button>
</div>
<div class="box"><img id="live" src="/video_feed"></div>

<div id="ed" class="calm">加载中...</div>

<div id="dt">Debug 模型真实视角 (已对齐拉平 224x224)</div>
<div id="dg"></div>

<script>
var Z={calm:"平静",happy:"高兴",upset:"不高兴"};
var ed=document.getElementById("ed");
var dg=document.getElementById("dg");

setInterval(function(){
  fetch("/get_emotion").then(function(r){return r.json()}).then(function(d){
    var p=(d.confidence*100).toFixed(0);
    ed.className = d.emotion;
    ed.innerHTML = Z[d.emotion] + '<span class="cf">置信度: '+p+'%</span>';
  }).catch(function(){})
},300);

setInterval(function(){
  fetch("/debug_images").then(function(r){return r.json()}).then(function(arr){
    dg.innerHTML="";
    for(var i=arr.length-1;i>=0;i--){
      var d=document.createElement("div"); d.className="di";
      var im=document.createElement("img");
      im.src="data:image/jpeg;base64,"+arr[i].b64;
      var sp=document.createElement("span");
      var parts=arr[i].name.replace(".jpg","").split("_");
      sp.className = parts[1];
      sp.textContent=parts[0]+" "+Z[parts[1]];
      d.appendChild(im); d.appendChild(sp); dg.appendChild(d);
    }
  }).catch(function(){})
},1000);

function sw(c){
  document.querySelectorAll("button").forEach(function(b){b.disabled=true});
  fetch("/switch_camera",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({cam:c})}).then(function(){})
    .finally(function(){document.querySelectorAll("button").forEach(function(b){b.disabled=false})});
}
</script>
</body>
</html>'''


if __name__ == "__main__":
    print("=" * 60)
    print("  策略升级: 纯2D仿射对齐(不变形) + EfficientNet + 时序平滑防抖")
    print("  效果: 低头/抬头/侧脸时，眼睛被强制拉平，下巴不丢失")
    print("  验证: 查看 debug_aligned 目录，眼睛必定在同一水平线")
    print("=" * 60)
    try:
        init()
        print("[RUN] http://127.0.0.1:5000")
        app.run(host="127.0.0.1", port=5000,
                debug=False, use_reloader=False, threaded=True)
    except:
        tb.print_exc()