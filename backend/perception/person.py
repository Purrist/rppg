# -*- coding: utf-8 -*-
"""
Person Analyzer - 人脸年龄、性别和身份识别模块
使用DeepFace对检测的人脸进行年龄、性别分析和身份识别
新增：头部姿态识别
"""
import os
import sys
import json
import cv2
import numpy as np
import threading
import time
from collections import deque
from flask import Flask, render_template, jsonify, Response, request

# 关键！先导入关键第三方库，然后临时移除当前目录，导入sixdrepnet！
import mediapipe as mp
from deepface import DeepFace

# 保存当前sys.path
original_sys_path = sys.path.copy()
# 移除当前目录，防止sixdrepnet导入错误的utils.py
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if p != current_dir and p != '']

try:
    from sixdrepnet import SixDRepNet
finally:
    # 恢复原始sys.path
    sys.path = original_sys_path

# 关键！设置DeepFace去正确的父目录，因为它会自动加一层.deepface！
os.environ['DEEPFACE_HOME'] = "C:\\Users\\purriste"

app = Flask(__name__)

HTTP_PORT = 5030
IP_CAMERA_URL = "http://10.158.7.180:8080/video"
LOCAL_CAMERA_ID = 0

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core", "models")
FACE_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'face_database')

os.makedirs(FACE_DB_DIR, exist_ok=True)

AGE_RANGES = ['0-20', '20-40', '40-60', '60-80', '80-100']
RECOGNITION_THRESHOLD = 0.3  # 人脸匹配阈值，调小一点，让匹配更宽松！


# 第三方库已经提前导入了，这个函数保持兼容但实际不再重新导入
def import_libraries():
    pass


# ── 人脸检测和姿态估计组件 ──
class FaceDetector:
    def __init__(self):
        self.fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=5, refine_landmarks=True, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    
    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.fm.process(rgb)
        if not res.multi_face_landmarks:
            return []
        h, w = frame.shape[:2]
        return [np.array([[p.x*w, p.y*h, p.z*w] for p in fl.landmark]) for fl in res.multi_face_landmarks]
    
    def release(self):
        self.fm.close()


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
                if j in used:
                    continue
                iou = self._iou(trk['bbox'], f['bbox'])
                if iou > best_iou:
                    best_iou, best_j = iou, j
            if best_j >= 0:
                used.add(best_j)
                new_tracks[tid] = {'bbox': faces[best_j]['bbox'], 'frames': trk['frames']+1, 'area': faces[best_j]['area'], 'score': faces[best_j]['score'], 'lm': faces[best_j]['lm']}
        for j, f in enumerate(faces):
            if j not in used:
                new_tracks[self._next_id] = {'bbox': f['bbox'], 'frames': 1, 'area': f['area'], 'score': f['score'], 'lm': f['lm']}
                self._next_id += 1
        self.tracks = new_tracks
        self._lost_cnt = 0
        if self.primary_id is None or self.primary_id not in self.tracks:
            best = max(self.tracks.values(), key=lambda t: t['score'])
            for tid, t in self.tracks.items():
                if t is best:
                    self.primary_id = tid
                    break
        else:
            pri = self.tracks[self.primary_id]
            for tid, t in self.tracks.items():
                if tid != self.primary_id and t['frames'] > 15 and t['score'] > pri['score'] * 1.8:
                    self.primary_id = tid
                    break
        return self.tracks[self.primary_id]['lm'] if self.primary_id in self.tracks else None
    
    @staticmethod
    def _iou(a, b):
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        x2, y2 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x2-x1) * max(0, y2-y1)
        union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
        return inter / max(union, 1)


class PoseEstimator:
    def __init__(self):
        self.model = None
        try:
            self.model = SixDRepNet()
        except Exception:
            pass
    
    def estimate(self, frame, lm):
        if lm is None or self.model is None:
            return 0., 0., 0.
        try:
            h, w = frame.shape[:2]
            xs, ys = lm[:, 0], lm[:, 1]
            x0, x1 = int(xs.min()), int(xs.max())
            y0, y1 = int(ys.min()), int(ys.max())
            m = 0.3
            bw = max(x1-x0, 1)
            bh = max(y1-y0, 1)
            x0 = max(0, int(x0-bw*m))
            x1 = min(w, int(x1+bw*m))
            y0 = max(0, int(y0-bh*m))
            y1 = min(h, int(y1+bh*m))
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0 or crop.shape[0] < 20:
                return 0., 0., 0.
            crop = cv2.resize(crop, (480, 480), interpolation=cv2.INTER_LANCZOS4)
            p, y, r = self.model.predict(crop)
            return float(np.asarray(p).item()), float(np.asarray(y).item()), float(np.asarray(r).item())
        except Exception:
            return 0., 0., 0.
    
    @staticmethod
    def get_pose(pitch, yaw):
        if abs(yaw) > 35:
            return 'side_left' if yaw < 0 else 'side_right'
        elif pitch > 15:
            return 'up'
        elif pitch < -20:
            return 'down'
        else:
            return 'front'
    
    @staticmethod
    def is_front_face(pitch, yaw):
        return abs(yaw) < 35 and abs(pitch) < 25


class FaceDatabase:
    """人脸数据库管理类"""
    
    def __init__(self, db_dir):
        self.db_dir = db_dir
        self.db_file = os.path.join(db_dir, "face_db.json")
        self.face_embeddings_dir = os.path.join(db_dir, "embeddings")
        os.makedirs(self.face_embeddings_dir, exist_ok=True)
        self.db = self._load_db()
    
    def _load_db(self):
        """加载数据库"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"users": [], "next_id": 1}
    
    def _save_db(self):
        """保存数据库"""
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, ensure_ascii=False, indent=2)
    
    def _generate_user_id(self):
        """生成用户ID"""
        user_id = self.db["next_id"]
        self.db["next_id"] += 1
        return user_id
    
    def get_all_embeddings(self):
        """获取所有用户的人脸特征"""
        all_embeddings = []
        all_user_ids = []
        for user in self.db["users"]:
            user_id = user["id"]
            emb_file = os.path.join(self.face_embeddings_dir, f"{user_id}_embedding.npy")
            if os.path.exists(emb_file):
                embedding = np.load(emb_file)
                all_embeddings.append(embedding)
                all_user_ids.append(user_id)
        return np.array(all_embeddings), all_user_ids
    
    def add_new_user(self, embedding):
        """添加新用户"""
        user_id = self._generate_user_id()
        user_name = f"用户{user_id:04d}"
        user = {
            "id": user_id,
            "name": user_name,
            "created_at": time.time()
        }
        self.db["users"].append(user)
        self._save_db()
        
        # 保存特征向量
        emb_file = os.path.join(self.face_embeddings_dir, f"{user_id}_embedding.npy")
        np.save(emb_file, embedding)
        
        return user
    
    def find_user(self, user_id):
        """查找用户"""
        for user in self.db["users"]:
            if user["id"] == user_id:
                return user
        return None


class FaceRecognizer:
    """人脸识别类"""
    
    def __init__(self, db_dir):
        self.db = FaceDatabase(db_dir)
        self.face_buffer = []
        self.buffer_size = 8  # 身份识别平滑缓冲区大小，加大让结果更稳定！
    
    def get_embedding(self, frame):
        """提取人脸特征向量"""
        try:
            result = DeepFace.represent(
                frame,
                model_name="VGG-Face",
                enforce_detection=False,
                detector_backend="opencv"
            )
            if isinstance(result, list) and len(result) > 0:
                embedding = result[0]["embedding"]
                return np.array(embedding)
        except Exception:
            pass
        return None
    
    def cosine_similarity(self, emb1, emb2):
        """计算余弦相似度"""
        dot = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        return dot / (norm1 * norm2)
    
    def recognize(self, frame):
        """识别人脸"""
        embedding = self.get_embedding(frame)
        if embedding is None:
            return None
        
        # 获取数据库中的所有特征
        all_embeddings, all_user_ids = self.db.get_all_embeddings()
        
        if len(all_embeddings) == 0:
            # 数据库为空，添加新用户
            user = self.db.add_new_user(embedding)
            return {
                "user_id": user["id"],
                "user_name": user["name"],
                "confidence": 1.0,
                "is_new": True
            }
        
        # 计算相似度
        similarities = [self.cosine_similarity(embedding, e) for e in all_embeddings]
        best_idx = np.argmax(similarities)
        best_similarity = similarities[best_idx]
        
        if best_similarity >= RECOGNITION_THRESHOLD:
            # 匹配成功
            user_id = all_user_ids[best_idx]
            user = self.db.find_user(user_id)
            if user:
                # 平滑处理
                self.face_buffer.append(user_id)
                if len(self.face_buffer) > self.buffer_size:
                    self.face_buffer.pop(0)
                
                from collections import Counter
                counter = Counter(self.face_buffer)
                most_common_id = counter.most_common(1)[0][0]
                final_user = self.db.find_user(most_common_id)
                
                return {
                    "user_id": final_user["id"],
                    "user_name": final_user["name"],
                    "confidence": float(best_similarity),
                    "is_new": False
                }
        else:
            # 匹配失败，添加新用户
            user = self.db.add_new_user(embedding)
            self.face_buffer = [user["id"]]
            return {
                "user_id": user["id"],
                "user_name": user["name"],
                "confidence": 1.0,
                "is_new": True
            }
        
        return None


class PersonAnalyzer:
    """主分析器"""
    
    def __init__(self):
        # 库已经提前导入
        self.current_camera = 'local'  # 默认为本地摄像头
        self.cap = None
        self._init_camera()
        
        # 初始化组件
        self.face_det = FaceDetector()
        self.face_sel = FaceSelector()
        self.pose_est = PoseEstimator()
        self.face_rec = FaceRecognizer(FACE_DB_DIR)
        
        self.lock = threading.Lock()
        self.running = False
        
        self.raw_frame = None
        self.annotated = None
        self.last_landmarks = None
        
        # 结果
        self.result = {
            "age": 0,
            "age_range": "--",
            "age_confidence": 0.0,
            "gender": "--",
            "gender_confidence": 0.0,
            "face_detected": False,
            "face_count": 0,
            "timestamp": time.time(),
            "age_model": {"available": False},
            "gender_model": {"available": False},
            "user_id": None,
            "user_name": "--",
            "user_confidence": 0.0,
            "is_new_user": False,
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "pose": "-",
            "is_front_face": False
        }
        
        # 平滑缓冲区
        self.age_buffer = []
        self.gender_buffer = []
        self.buffer_size = 5
        
        # 帧计数
        self._fc = 0
    
    def _init_camera(self):
        """初始化摄像头"""
        if self.cap is not None:
            self.cap.release()
        
        if self.current_camera == 'ip':
            self.cap = cv2.VideoCapture(IP_CAMERA_URL)
        else:
            self.cap = cv2.VideoCapture(LOCAL_CAMERA_ID)
        
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
    
    def switch_camera(self, camera_type):
        """切换摄像头"""
        with self.lock:
            self.current_camera = camera_type
            self._init_camera()
    
    def _age_to_range(self, age):
        age = int(age)
        if age < 20:
            return '0-20'
        elif age < 40:
            return '20-40'
        elif age < 60:
            return '40-60'
        elif age < 80:
            return '60-80'
        else:
            return '80-100'
    
    def analyze_face(self, frame):
        try:
            result = DeepFace.analyze(
                frame,
                actions=['age', 'gender'],
                enforce_detection=False,
                silent=True
            )
            if isinstance(result, list):
                result = result[0]
            
            age = result.get('age', 0)
            gender = result.get('dominant_gender', '--')
            gender_conf = result.get('gender', {}).get('Man', 0.5) if isinstance(result.get('gender'), dict) else 0.7
            
            return {
                "age": int(age),
                "age_range": self._age_to_range(age),
                "age_confidence": 0.7,
                "gender": gender,
                "gender_confidence": gender_conf,
                "face_count": 1,
                "age_model": {"available": True},
                "gender_model": {"available": True}
            }
        except Exception:
            return None
    
    def smooth_result(self, result):
        if result["age"] is not None and result["age"] > 0:
            self.age_buffer.append(result["age"])
            if len(self.age_buffer) > self.buffer_size:
                self.age_buffer.pop(0)
            result["age"] = int(np.mean(self.age_buffer))
        
        if result["gender"] in ["Man", "Woman"]:
            self.gender_buffer.append(result["gender"])
            if len(self.gender_buffer) > self.buffer_size:
                self.gender_buffer.pop(0)
            from collections import Counter
            counter = Counter(self.gender_buffer)
            result["gender"] = counter.most_common(1)[0][0]
        
        return result
    
    def grab_loop(self):
        """视频读取循环（独立线程）"""
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                
                self.raw_frame = frame
                
                # 直接编码原始帧，不做任何处理，保证视频流畅
                r, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if r:
                    with self.lock:
                        self.annotated = buf.tobytes()
                
            except Exception:
                pass
            time.sleep(0.01)
    
    def analysis_loop(self):
        """分析循环（独立线程）"""
        lm_cache = None
        last_pitch = 0
        last_yaw = 0
        last_roll = 0
        last_pose = "-"
        last_is_front = False
        
        while self.running:
            frame = self.raw_frame
            if frame is not None:
                self._fc += 1
                
                # 高频更新人脸检测和姿态（每10帧一次）
                if self._fc % 10 == 1:
                    lm_list = self.face_det.process(frame)
                    lm = self.face_sel.select(lm_list, frame.shape) if lm_list else None
                    lm_cache = lm
                    self.last_landmarks = lm
                    
                    res = dict(self.result)
                    
                    if lm is not None:
                        pitch, yaw, roll = self.pose_est.estimate(frame, lm)
                        last_pitch, last_yaw, last_roll = pitch, yaw, roll
                        
                        last_pose = PoseEstimator.get_pose(pitch, yaw)
                        last_is_front = PoseEstimator.is_front_face(pitch, yaw)
                        
                        # 立即更新人脸检测状态！
                        res.update({
                            "face_detected": True,
                            "face_count": len(lm_list),
                            "pitch": round(last_pitch, 1),
                            "yaw": round(last_yaw, 1),
                            "roll": round(last_roll, 1),
                            "pose": last_pose,
                            "is_front_face": last_is_front,
                            "timestamp": time.time()
                        })
                    else:
                        last_pose = "-"
                        last_is_front = False
                        
                        # 无人脸时，清除相关状态
                        res.update({
                            "face_detected": False,
                            "face_count": 0,
                            "pitch": round(last_pitch, 1),
                            "yaw": round(last_yaw, 1),
                            "roll": round(last_roll, 1),
                            "pose": last_pose,
                            "is_front_face": last_is_front,
                            "timestamp": time.time()
                        })
                    
                    with self.lock:
                        self.result = res
                
                # 只在正脸时才进行DeepFace分析（每15帧一次）
                if last_is_front and self._fc % 15 == 3 and lm_cache is not None:
                    analysis = self.analyze_face(frame)
                    face_recognition = self.face_rec.recognize(frame)
                    
                    with self.lock:
                        res = dict(self.result)
                        if analysis:
                            analysis = self.smooth_result(analysis)
                            res.update({
                                "age": analysis["age"],
                                "age_range": analysis["age_range"],
                                "age_confidence": analysis["age_confidence"],
                                "gender": analysis["gender"],
                                "gender_confidence": analysis["gender_confidence"],
                                "age_model": analysis["age_model"],
                                "gender_model": analysis["gender_model"],
                                "user_id": face_recognition["user_id"] if face_recognition else None,
                                "user_name": face_recognition["user_name"] if face_recognition else "--",
                                "user_confidence": face_recognition["confidence"] if face_recognition else 0.0,
                                "is_new_user": face_recognition["is_new"] if face_recognition else False,
                                "timestamp": time.time()
                            })
                        else:
                            res.update({
                                "age": 0,
                                "age_range": "--",
                                "age_confidence": 0.0,
                                "gender": "--",
                                "gender_confidence": 0.0,
                                "age_model": {"available": False},
                                "gender_model": {"available": False},
                                "user_id": None,
                                "user_name": "--",
                                "user_confidence": 0.0,
                                "is_new_user": False,
                                "timestamp": time.time()
                            })
                        self.result = res
            
            time.sleep(0.01)
    
    def get_result(self):
        with self.lock:
            return self.result.copy()
    
    def generate_frame(self):
        while self.running:
            with self.lock:
                if self.annotated is not None:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + self.annotated + b'\r\n')
            time.sleep(0.033)
    
    def start(self):
        self.running = True
        threading.Thread(target=self.grab_loop, daemon=True).start()
        threading.Thread(target=self.analysis_loop, daemon=True).start()
    
    def shutdown(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()
        self.face_det.release()


analyzer = PersonAnalyzer()


@app.route("/")
def index():
    return render_template("person.html")


@app.route("/api/data")
def api_data():
    return jsonify(analyzer.get_result())


@app.route("/api/switch_camera", methods=["POST"])
def switch_camera():
    data = request.get_json()
    camera_type = data.get("camera", "ip")
    analyzer.switch_camera(camera_type)
    return jsonify({"status": "success", "camera": camera_type})


@app.route("/video_feed")
def video_feed():
    return Response(analyzer.generate_frame(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    print("=" * 60)
    print("  人脸年龄性别身份分析器 (DeepFace + 头部姿态识别)")
    print("  初始摄像头: 本地摄像头")
    print("=" * 60)
    
    analyzer.start()
    print(f"\nWeb服务器: http://127.0.0.1:{HTTP_PORT}")
    print("=" * 60 + "\n")
    
    try:
        app.run(host="127.0.0.1", port=HTTP_PORT, debug=False, use_reloader=False)
    finally:
        analyzer.shutdown()
