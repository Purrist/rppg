# emotion.py
import os, time, threading, json, base64
import numpy as np
from collections import deque
import sys

os.environ["FLASK_SKIP_DOTENV"] = "1"
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import torch
import mediapipe as mp
from flask import Flask, Response, jsonify, request
from sixdrepnet import SixDRepNet
from au_net.MEFL import MEFARG

POSES = ['front', 'up', 'down', 'side']
EMOTIONS = ['neutral', 'positive', 'negative']

POSE_AU_SUBSET = {
    'front': ['AU1', 'AU2', 'AU4', 'AU5', 'AU6', 'AU7', 'AU9', 'AU10', 'AU12', 'AU15', 'AU17', 'AU25'],
    'up': ['AU1', 'AU2', 'AU4', 'AU5', 'AU7', 'AU15', 'AU17'],
    'down': ['AU1', 'AU2', 'AU4', 'AU5', 'AU7', 'AU15'],
    'side': ['AUL1', 'AUR1', 'AUL2', 'AUR2', 'AUL6', 'AUR6', 'AU5', 'AU7', 'AU25']
}

class ProfileMatcher:
    def __init__(self, profile_path=None):
        self.profiles = {}
        self.history = deque(maxlen=5)
        self.last_emotion = 'neutral'
        self.switch_counter = 0
        self.profile_path = profile_path or os.path.join(os.path.dirname(__file__), 'data', 'emotion_profiles.json')
        self._load_profiles()
        self.pose_confidence_thresholds = {
            'front': {'min_pitch': -15, 'max_pitch': 15, 'max_yaw': 20},
            'up': {'min_pitch': 10, 'max_pitch': 45, 'max_yaw': 25},
            'down': {'min_pitch': -45, 'max_pitch': -15, 'max_yaw': 25},
            'side': {'min_yaw': 30, 'max_yaw': 60}
        }
    
    def _load_profiles(self):
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, 'r', encoding='utf-8') as f:
                    self.profiles = json.load(f)
                print(f"[ProfileMatcher] 已加载轮廓模板: {self.profile_path}")
            except Exception as e:
                print(f"[ProfileMatcher] 加载失败: {e}")
        else:
            print(f"[ProfileMatcher] 模板文件不存在: {self.profile_path}")
    
    def normalize_profile(self, au_dict, au_subset):
        values = [au_dict.get(au, 0.0) for au in au_subset]
        arr = np.array(values, dtype=np.float32)
        mean_val = np.mean(arr)
        centered = arr - mean_val
        std_val = np.std(arr)
        if std_val < 1e-6:
            std_val = 1.0
        normalized = centered / std_val
        result = {}
        for i, au in enumerate(au_subset):
            result[au] = float(normalized[i])
        return result, float(mean_val), float(std_val)
    
    def cosine_similarity(self, vec1, vec2, keys):
        arr1 = np.array([vec1.get(k, 0.0) for k in keys], dtype=np.float32)
        arr2 = np.array([vec2.get(k, 0.0) for k in keys], dtype=np.float32)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        if norm1 < 1e-6 or norm2 < 1e-6:
            return 0.0
        return float(np.dot(arr1, arr2) / (norm1 * norm2))
    
    def get_pose(self, pitch, yaw):
        pitch = float(pitch)
        yaw = abs(float(yaw))
        if yaw > 35: return 'side'
        if pitch > 15: return 'up'
        if pitch < -20: return 'down'
        return 'front'
    
    def get_pose_confidence(self, pose, pitch, yaw):
        pitch = float(pitch)
        yaw = abs(float(yaw))
        thresholds = self.pose_confidence_thresholds.get(pose, {})
        if pose == 'front':
            pitch_ok = thresholds.get('min_pitch', -90) <= pitch <= thresholds.get('max_pitch', 90)
            yaw_ok = yaw <= thresholds.get('max_yaw', 90)
            return float(pitch_ok and yaw_ok)
        elif pose == 'up':
            pitch_ok = thresholds.get('min_pitch', -90) <= pitch <= thresholds.get('max_pitch', 90)
            yaw_ok = yaw <= thresholds.get('max_yaw', 90)
            return float(pitch_ok and yaw_ok)
        elif pose == 'down':
            pitch_ok = thresholds.get('min_pitch', -90) <= pitch <= thresholds.get('max_pitch', 90)
            yaw_ok = yaw <= thresholds.get('max_yaw', 90)
            return float(pitch_ok and yaw_ok)
        elif pose == 'side':
            yaw_ok = thresholds.get('min_yaw', 0) <= yaw <= thresholds.get('max_yaw', 90)
            return float(yaw_ok)
        return 1.0
    
    def predict(self, au_dict, pitch, yaw, speaking=False):
        if au_dict is None:
            return 'unknown', 'no_face', 0.0, {'neutral': 1, 'positive': 0, 'negative': 0}
        if speaking:
            return 'unknown', 'speaking', 0.0, {e: 0.5 if e == self.last_emotion else 0.05 for e in EMOTIONS}
        pose = self.get_pose(pitch, yaw)
        pose_confidence = self.get_pose_confidence(pose, pitch, yaw)
        if pose_confidence < 0.5:
            return pose, 'out_of_range', 0.0, {'neutral': 0, 'positive': 0, 'negative': 0}
        if pose not in self.profiles:
            return pose, 'uncalibrated', 0.0, {'neutral': 1, 'positive': 0, 'negative': 0}
        pose_profiles = self.profiles[pose]
        available_emotions = [e for e in EMOTIONS if pose_profiles.get(e) is not None]
        if not available_emotions:
            return pose, 'uncalibrated', 0.0, {'neutral': 1, 'positive': 0, 'negative': 0}
        au_subset = POSE_AU_SUBSET.get(pose, list(au_dict.keys()))
        current_profile, mean_val, std_val = self.normalize_profile(au_dict, au_subset)

        if std_val < 3.0:
            return pose, 'neutral', 0.8, {'neutral': 0.9, 'positive': 0.05, 'negative': 0.05}

        similarities = {}
        for emotion in available_emotions:
            template = pose_profiles.get(emotion)
            if template is None:
                similarities[emotion] = -1.0
                continue
            template_mean = template.get('mean', {})
            similarity = self.cosine_similarity(current_profile, template_mean, au_subset)
            similarities[emotion] = similarity
        max_sim = max(similarities.values())
        min_sim = min(similarities.values())
        range_sim = max_sim - min_sim if max_sim != min_sim else 1.0
        scores = {}
        for emotion in EMOTIONS:
            if emotion in similarities:
                scores[emotion] = (similarities[emotion] - min_sim) / range_sim
            else:
                scores[emotion] = 0.0
        total = sum(scores.values()) + 1e-6
        scores = {e: v / total for e, v in scores.items()}
        best_emotion = max(scores, key=scores.get)
        confidence = scores[best_emotion]
        confidence = confidence * pose_confidence
        self.history.append(best_emotion)
        if len(self.history) >= 3:
            emotion_counts = {}
            for e in self.history:
                emotion_counts[e] = emotion_counts.get(e, 0) + 1
            voted_emotion = max(emotion_counts, key=emotion_counts.get)
            vote_ratio = emotion_counts[voted_emotion] / len(self.history)
            if vote_ratio >= 0.5:
                best_emotion = voted_emotion
            else:
                best_emotion = self.last_emotion
        if best_emotion != self.last_emotion:
            self.switch_counter += 1
            if self.switch_counter < 1:
                best_emotion = self.last_emotion
            else:
                self.last_emotion = best_emotion
                self.switch_counter = 0
        else:
            self.switch_counter = 0
        return pose, best_emotion, confidence, scores
    
    def get_available_profiles(self):
        result = {}
        for pose in POSES:
            if pose in self.profiles:
                result[pose] = [e for e in EMOTIONS if self.profiles[pose].get(e) is not None]
            else:
                result[pose] = []
        return result

# ── Constants ──────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CALIB_N = 30
AU_MAIN = ['AU1','AU2','AU4','AU5','AU6','AU7','AU9','AU10','AU11','AU12','AU13','AU14','AU15','AU16','AU17','AU18','AU19','AU20','AU22','AU23','AU24','AU25','AU26','AU27','AU32','AU38','AU39']
AU_SUB = ['AUL1','AUR1','AUL2','AUR2','AUL4','AUR4','AUL6','AUR6','AUL10','AUR10','AUL12','AUR12','AUL14','AUR14']
AU_SHOW = ['AU12','AU6','AU25','AU7','AU5','AU15','AU4','AU17','AU1','AU9']
AU_LABEL = {'AU12':'嘴角上拉','AU6':'颧骨提升','AU25':'嘴唇分开','AU7':'眼睑收紧','AU5':'上睑抬起','AU15':'嘴角下拉','AU4':'皱眉','AU17':'下巴上提','AU1':'内眉上抬','AU9':'鼻皱'}
_s = 224.0 / 96.0
ALIGN_DST = np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]], dtype=np.float32) * _s
_MEAN = np.array([0.485,0.456,0.406], dtype=np.float32)
_STD = np.array([0.229,0.224,0.225], dtype=np.float32)
MP5 = [33, 263, 1, 61, 291]
KP_IDX = [1,33,133,159,145,263,362,386,374,61,291,13,14,152,105,334,55,285]
POSES = ['front', 'up', 'down', 'side']
EMOTIONS = ['neutral', 'positive', 'negative']
AU_HAPPY = ['AU12', 'AU6', 'AU25']
AU_SAD = ['AU15', 'AU4', 'AU1', 'AU17']

FER_MODEL_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), "backend", "core", "models", "emotion-ferplus-8.onnx")
FER_LABELS_8 = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]
DEFAULT_FER_BIAS = {label: 0.0 for label in FER_LABELS_8}

def softmax(x):
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-10)

# ── [保持不变] AU 原有组件 ──────────────────────────────
class FaceDetector:
    def __init__(self):
        self.fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=5, refine_landmarks=True, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        r = self.fm.process(rgb)
        if not r.multi_face_landmarks: return []
        h, w = frame.shape[:2]
        return [np.array([[p.x*w, p.y*h, p.z*w] for p in fl.landmark]) for fl in r.multi_face_landmarks]
    def release(self): self.fm.close()

class SpeechDetector:
    def __init__(self):
        self.lip_open_history = deque(maxlen=20)
        self.lip_width_history = deque(maxlen=20)
        self.speaking = False
        self._spk_cnt = 0
        self._quiet_cnt = 0
        self._last_lip_open = 0.0

    def update(self, lm):
        eye_dist = max(np.linalg.norm(lm[33][:2] - lm[263][:2]), 1.0)
        lip_open = abs(lm[14][1] - lm[13][1]) / eye_dist
        lip_width = abs(lm[61][0] - lm[291][0]) / eye_dist
        
        # 唇速在开头就算，每帧都更新 _last_lip_open
        lip_velocity = abs(lip_open - self._last_lip_open)
        self._last_lip_open = lip_open
        
        self.lip_open_history.append(lip_open)
        self.lip_width_history.append(lip_width)
        
        if len(self.lip_open_history) < 10:
            return False
        
        open_arr = np.array(self.lip_open_history)
        width_arr = np.array(self.lip_width_history)
        
        recent_open = open_arr[-10:]
        recent_width = width_arr[-10:]
        
        kernel = np.ones(3) / 3
        smooth_open = np.convolve(recent_open, kernel, mode='valid')
        smooth_width = np.convolve(recent_width, kernel, mode='valid')
        
        open_range = np.max(smooth_open) - np.min(smooth_open)
        
        if open_range < 0.025:
            raw = False
        else:
            open_mean = np.mean(smooth_open)
            open_centered = smooth_open - open_mean
            crossings = 0
            for i in range(1, len(open_centered)):
                if open_centered[i] * open_centered[i-1] < 0:
                    crossings += 1
            
            open_energy = np.mean(np.abs(open_centered))
            
            raw = (crossings >= 2 and open_energy > 0.012)
        
        if raw and lip_velocity > 0.003:
            self._spk_cnt += 1
            self._quiet_cnt = 0
        else:
            self._quiet_cnt += 1
            self._spk_cnt = 0
        
        if self._spk_cnt >= 3:
            self.speaking = True
        elif self._quiet_cnt >= 5:
            self.speaking = False
        
        return self.speaking

class FaceSelector:
    def __init__(self):
        self.tracks = {}; self._next_id = 0; self.primary_id = None; self._lost_cnt = 0
    def select(self, lm_list, shape):
        if not lm_list:
            self._lost_cnt += 1
            if self._lost_cnt > 30: self.primary_id = None
            return None
        h, w = shape[:2]; cx, cy = w / 2, h / 2; faces = []
        for lm in lm_list:
            xs, ys = lm[:, 0], lm[:, 1]; bbox = (xs.min(), ys.min(), xs.max(), ys.max())
            area = (bbox[2]-bbox[0]) * (bbox[3]-bbox[1]); fcx = (bbox[0]+bbox[2]) / 2; fcy = (bbox[1]+bbox[3]) / 2
            dist = np.sqrt((fcx-cx)**2 + (fcy-cy)**2); score = area / (1 + dist * 0.005)
            faces.append({'bbox': bbox, 'area': area, 'score': score, 'lm': lm})
        new_tracks = {}; used = set()
        for tid, trk in self.tracks.items():
            best_iou, best_j = 0.25, -1
            for j, f in enumerate(faces):
                if j in used: continue
                iou = self._iou(trk['bbox'], f['bbox'])
                if iou > best_iou: best_iou, best_j = iou, j
            if best_j >= 0:
                used.add(best_j); new_tracks[tid] = {'bbox': faces[best_j]['bbox'], 'frames': trk['frames']+1, 'area': faces[best_j]['area'], 'score': faces[best_j]['score'], 'lm': faces[best_j]['lm']}
        for j, f in enumerate(faces):
            if j not in used:
                new_tracks[self._next_id] = {'bbox': f['bbox'], 'frames': 1, 'area': f['area'], 'score': f['score'], 'lm': f['lm']}; self._next_id += 1
        self.tracks = new_tracks; self._lost_cnt = 0
        if self.primary_id is None or self.primary_id not in self.tracks:
            best = max(self.tracks.values(), key=lambda t: t['score'])
            for tid, t in self.tracks.items():
                if t is best: self.primary_id = tid; break
        else:
            pri = self.tracks[self.primary_id]
            for tid, t in self.tracks.items():
                if tid != self.primary_id and t['frames'] > 15 and t['score'] > pri['score'] * 1.8: self.primary_id = tid; break
        return self.tracks[self.primary_id]['lm'] if self.primary_id in self.tracks else None
    @staticmethod
    def _iou(a, b):
        x1, y1 = max(a[0],b[0]), max(a[1],b[1]); x2, y2 = min(a[2],b[2]), min(a[3],b[3])
        inter = max(0, x2-x1) * max(0, y2-y1)
        union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
        return inter / max(union, 1)

class PoseEstimator:
    def __init__(self): self.model = SixDRepNet()
    def estimate(self, frame, lm):
        if lm is None: return 0.,0.,0.
        h, w = frame.shape[:2]; xs, ys = lm[:,0], lm[:,1]
        x0,x1 = int(xs.min()),int(xs.max()); y0,y1 = int(ys.min()),int(ys.max())
        m=0.3; bw=max(x1-x0,1); bh=max(y1-y0,1)
        x0=max(0,int(x0-bw*m)); x1=min(w,int(x1+bw*m)); y0=max(0,int(y0-bh*m)); y1=min(h,int(y1+bh*m))
        crop = frame[y0:y1, x0:x1]
        if crop.size==0 or crop.shape[0]<20: return 0.,0.,0.
        crop = cv2.resize(crop,(480,480), interpolation=cv2.INTER_LANCZOS4)
        p,y,r = self.model.predict(crop)
        return float(np.asarray(p).item()),float(np.asarray(y).item()),float(np.asarray(r).item())

class AUExtractor:
    def __init__(self, arc='resnet50', ckpt='checkpoints/OpenGprahAU-ResNet50_second_stage.pth'):
        self.sz = 224; self.dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.net = MEFARG(num_main_classes=27, num_sub_classes=14, backbone=arc)
        if os.path.exists(ckpt):
            d = torch.load(ckpt, map_location=self.dev); sd = {k.replace("module.",""): v for k,v in d["state_dict"].items()}
            self.net.load_state_dict(sd); print(f"[AU] 权重已加载: {ckpt}")
        else: print(f"[AU] 权重缺失: {ckpt}")
        self.net.to(self.dev).eval()
        self._clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
    def _enhance_elderly(self, img):
        lab = cv2.cvtColor((img*255).astype(np.uint8), cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        cl = self._clahe.apply(l)
        enhanced = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2RGB)
        return enhanced.astype(np.float32)/255.0
    def _align(self, frame, lm):
        src = np.array([lm[i][:2] for i in MP5], dtype=np.float32); M = cv2.estimateAffinePartial2D(src, ALIGN_DST)[0]
        if M is None: return None
        return cv2.warpAffine(frame, M, (self.sz, self.sz), flags=cv2.INTER_LANCZOS4)
    def predict(self, frame, lm):
        if lm is None: return None
        aligned = self._align(frame, lm)
        if aligned is None: return None
        img = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
        img = self._enhance_elderly(img)
        img = (img - _MEAN) / _STD; img = np.transpose(img, (2,0,1))[None]
        t = torch.from_numpy(img).float().to(self.dev)
        with torch.no_grad(): out = self.net(t)
        if isinstance(out, (tuple,list)):
            mp_ = torch.sigmoid(out[0]).cpu().numpy()[0]*100; sp_ = torch.sigmoid(out[1]).cpu().numpy()[0]*100 if len(out)>1 else np.zeros(14)
        else: mp_ = torch.sigmoid(out).cpu().numpy()[0]*100; sp_ = np.zeros(14)
        r = {}
        for i,n in enumerate(AU_MAIN): r[n] = float(mp_[i])
        for i,n in enumerate(AU_SUB): r[n] = float(sp_[i])
        return r

class EmotionMapper:
    def __init__(self, history=8, persist_path=None):
        self.baselines = {p: {e: None for e in EMOTIONS} for p in POSES}
        self.buffers = {}; self.calibrating = None; self.hist = deque(maxlen=history)
        self.stability_hist = deque(maxlen=5)
        self.config = {
            'front': {'h_thresh': 2.0, 's_thresh': 2.0}, 'up': {'h_thresh': 2.0, 's_thresh': 2.0},
            'down': {'h_thresh': 1.5, 's_thresh': 1.5}, 'side': {'h_thresh': 1.5, 's_thresh': 1.5},
            'pitch_limit': 45, 'fusion_weights': {'front': 0.4, 'up': 0.4, 'down': 0.4, 'side': 0.4},
            'stability_thresh': 0.6
        }
        self.last_emotion = 'neutral'; self.switch_cnt = 0
        self.persist_path = persist_path or os.path.join(os.path.dirname(__file__),'data','baselines.json')
        self._load()
    def _load(self):
        if not os.path.exists(self.persist_path): return
        try:
            with open(self.persist_path, 'r', encoding='utf-8') as f: d = json.load(f)
            for p in POSES:
                if p not in d: continue
                # 新格式：直接检查每种情绪
                for e in EMOTIONS:
                    if e in d[p] and d[p][e] and 'mu' in d[p][e] and 'sigma' in d[p][e]:
                        self.baselines[p][e] = {'mu': {k:float(v) for k,v in d[p][e]['mu'].items()}, 'sigma': {k:max(float(v),0.1) for k,v in d[p][e]['sigma'].items()}}
                # 旧格式兼容：'calm' 或直接在姿态下有 mu/sigma
                if 'calm' in d[p] and d[p]['calm']:
                    if 'mu' in d[p]['calm'] and 'sigma' in d[p]['calm']:
                        self.baselines[p]['neutral'] = {'mu': {k:float(v) for k,v in d[p]['calm']['mu'].items()}, 'sigma': {k:max(float(v),0.1) for k,v in d[p]['calm']['sigma'].items()}}
                elif 'mu' in d[p] and 'sigma' in d[p]:
                    self.baselines[p]['neutral'] = {'mu': {k:float(v) for k,v in d[p]['mu'].items()}, 'sigma': {k:max(float(v),0.1) for k,v in d[p]['sigma'].items()}}
        except Exception as ex: print(f"[Mapper] 加载失败: {ex}")
    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True); d = {}
            for p in POSES:
                d[p] = {}
                for e in EMOTIONS:
                    if self.baselines[p][e]: d[p][e] = {'mu': self.baselines[p][e]['mu'], 'sigma': self.baselines[p][e]['sigma']}
            with open(self.persist_path, 'w', encoding='utf-8') as f: json.dump(d, f, indent=2, ensure_ascii=False)
        except Exception as ex: print(f"[Mapper] 保存失败: {ex}")
    def start_calib(self, pose, emotion):
        if pose not in POSES or emotion not in EMOTIONS: return False
        self.calibrating = (pose, emotion); self.buffers[f"{pose}_{emotion}"] = []; return True
    def finish_calib(self, pose, emotion):
        key = f"{pose}_{emotion}"; buf = self.buffers.get(key, [])
        if len(buf) < 20: self.calibrating = None; return False
        keys = list(buf[0].keys())
        mu = {k: float(np.mean([f[k] for f in buf])) for k in keys}
        sigma = {k: max(float(np.std([f[k] for f in buf])), 0.1) for k in keys}
        self.baselines[pose][emotion] = {'mu': mu, 'sigma': sigma}; self.calibrating = None; self._save(); return True
    def feed_calib(self, au):
        if not self.calibrating: return 0
        pose, emotion = self.calibrating; key = f"{pose}_{emotion}"
        if key not in self.buffers: self.buffers[key] = []
        self.buffers[key].append(au); return len(self.buffers[key])
    def get_calibrated(self): return {p: [e for e in EMOTIONS if self.baselines[p][e]] for p in POSES}
    def delete_baseline(self, pose, emotion):
        if pose in self.baselines and emotion in self.baselines[pose]: self.baselines[pose][emotion] = None; self._save(); return True
        return False
    def delete_all_baselines(self):
        for p in POSES:
            for e in EMOTIONS: self.baselines[p][e] = None
        self._save(); return True
    @staticmethod
    def get_pose(pitch, yaw):
        if abs(yaw) > 35: return 'side'
        if pitch > 15: return 'up'
        if pitch < -20: return 'down'
        return 'front'
    def _is_stable(self, raw):
        self.stability_hist.append(raw)
        if len(self.stability_hist) < 3: return True
        recent = list(self.stability_hist)[-3:]
        most_common = max(set(recent), key=recent.count)
        stability_ratio = recent.count(most_common) / len(recent)
        return stability_ratio >= self.config.get('stability_thresh', 0.6)
    def predict(self, au, pitch, yaw, speaking=False):
        if au is None: return 'unknown', 'no_face', 0., {'neutral':1,'positive':0,'negative':0}
        pose = self.get_pose(pitch, yaw)
        if abs(pitch) > self.config.get('pitch_limit', 30): return pose, 'out_of_range', 0., {'neutral':0,'positive':0,'negative':0}
        if speaking: return pose, 'speaking', 0., {e: (0.5 if e == self.last_emotion else 0.05) for e in EMOTIONS}
        neutral_bl = self.baselines[pose]['neutral']
        if neutral_bl is None: return pose, 'uncalibrated', 0., {'neutral':1,'positive':0,'negative':0}
        mu, sig = neutral_bl['mu'], neutral_bl['sigma']; thr = self.config[pose]
        def z(n): return (au.get(n,0.) - mu[n]) / sig[n] if n in mu else 0.
        z12,z6,z25 = z('AU12'),z('AU6'),z('AU25')
        h_act = 0.
        if z12 > 0.5: h_act = max(0,z12)*.55 + max(0,z6)*.30 + max(0,z25)*.15
        z15,z4,z17 = z('AU15'),z('AU4'),z('AU17')
        s_act = 0.
        if z15 > 1.0: s_act = max(0,z15)*.55 + max(0,z4)*.30 + max(0,z17)*.15
        if h_act > 0 and s_act > 0:
            if h_act >= s_act: s_act = 0
            else: h_act = 0
        positive_bl = self.baselines[pose]['positive']
        if positive_bl and h_act > 0:
            hm, hs = positive_bl['mu'], positive_bl['sigma']
            dist = np.mean([abs(au.get(a,0)-hm.get(a,0))/hs.get(a,1) for a in AU_HAPPY if a in hm])
            if dist > 2.5: h_act *= max(0, 1.-(dist-2.5)*.4)
        negative_bl = self.baselines[pose]['negative']
        if negative_bl and s_act > 0:
            sm, ss = negative_bl['mu'], negative_bl['sigma']
            dist = np.mean([abs(au.get(a,0)-sm.get(a,0))/ss.get(a,1) for a in AU_SAD if a in sm])
            if dist > 2.5: s_act *= max(0, 1.-(dist-2.5)*.4)
        c_act = 1.0
        if h_act > thr['h_thresh']: c_act = max(0., 1.-(h_act-thr['h_thresh'])*1.2)
        elif s_act > thr['s_thresh']: c_act = max(0., 1.-(s_act-thr['s_thresh'])*1.2)
        total = h_act + s_act + c_act + 1e-6
        scores = {'positive': h_act/total, 'negative': s_act/total, 'neutral': c_act/total}
        if self.last_emotion == 'neutral':
            if h_act >= thr['h_thresh'] and s_act < thr['s_thresh']*.6: raw = 'positive'
            elif s_act >= thr['s_thresh'] and h_act < thr['h_thresh']*.6: raw = 'negative'
            else: raw = 'neutral'
        elif self.last_emotion == 'positive': raw = 'neutral' if h_act < thr['h_thresh']*.35 else 'positive'
        elif self.last_emotion == 'negative': raw = 'neutral' if s_act < thr['s_thresh']*.35 else 'negative'
        else: raw = 'neutral'
        if raw != self.last_emotion:
            self.switch_cnt += 1
            if self.switch_cnt < 2: best = self.last_emotion
            elif not self._is_stable(raw): best = self.last_emotion
            else: best = raw; self.last_emotion = raw; self.switch_cnt = 0
        else: self.switch_cnt = 0; best = raw
        self.hist.append(scores)
        smooth = {e: float(np.mean([x[e] for x in self.hist])) for e in EMOTIONS}
        return pose, best, smooth[best], smooth

# ── FER+ 组件 ──────────────────────────────────────────
class FERDetector:
    def __init__(self, model_path=FER_MODEL_PATH):
        self.net = None
        if os.path.exists(model_path):
            self.net = cv2.dnn.readNetFromONNX(model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            print(f"[FER+] 权重已加载: {model_path}")
        else: print(f"[FER+] 权重缺失: {model_path}")

    def predict(self, aligned_64):
        if self.net is None: return "calm", 0.0, np.zeros(8)
        try:
            gray = cv2.cvtColor(aligned_64, cv2.COLOR_BGR2GRAY)
            blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
            self.net.setInput(blob); scores = self.net.forward()[0]; probs = softmax(scores)
            
            # 概率池化：直接把8类概率按语义合并成3类
            probs_3 = {
                'positive': probs[1],                                             # happiness
                'negative': probs[3] + probs[4] + probs[5] + probs[6],           # sadness + anger + disgust + fear
                'neutral':  probs[0] + probs[2] + probs[7]                       # neutral + surprise + contempt
            }
            
            # 归一化
            total = sum(probs_3.values()) + 1e-8
            probs_3 = {k: v/total for k, v in probs_3.items()}
            
            label_3 = max(probs_3, key=probs_3.get)
            conf_3 = probs_3[label_3]
            
            return label_3, float(conf_3), probs
        except Exception as e: return "neutral", 0.0, np.zeros(8)

class FERAligner:
    def __init__(self):
        self.mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=False, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    def align(self, frame):
        h, w = frame.shape[:2]; rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try: res = self.mesh.process(rgb)
        except Exception: return None
        if not res.multi_face_landmarks: return None
        lm = res.multi_face_landmarks[0].landmark
        left = np.array([lm[33].x * w, lm[33].y * h]); right = np.array([lm[263].x * w, lm[263].y * h])
        angle = np.degrees(np.arctan2(right[1]-left[1], right[0]-left[0]))
        center = ((left[0]+right[0])/2, (left[1]+right[1])/2)
        rot = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(frame, rot, (w, h), borderValue=(0,0,0))
        xs = [p.x * w for p in lm]; ys = [p.y * h for p in lm]
        bx1, by1 = min(xs), min(ys); bx2, by2 = max(xs), max(ys)
        pad = int(max(bx2-bx1, by2-by1) * 0.3)
        cx1, cy1 = max(0, int(bx1 - pad)), max(0, int(by1 - pad))
        cx2, cy2 = min(w, int(bx2 + pad)), min(h, int(by2 + pad))
        crop = rotated[cy1:cy2, cx1:cx2]
        if crop.size == 0: return None
        return cv2.resize(crop, (64, 64))

class FERSmoother:
    def __init__(self, window=5): self.window = deque(maxlen=window)
    def update(self, label, probs_3):
        self.window.append((label, probs_3))
        if not self.window: return "calm", 0.0, {'calm':0, 'happy':0, 'sad':0}
        counts = {}
        for l, _ in self.window: counts[l] = counts.get(l, 0) + 1
        best = max(counts, key=counts.get)
        avg_probs = {e: float(np.mean([p[e] for _, p in self.window])) for e in EMOTIONS}
        return best, avg_probs[best], avg_probs

# ── 全局配置管理 ──────────────────────────────────────
class GlobalConfig:
    def __init__(self):
        self.path = os.path.join(os.path.dirname(__file__), 'data', 'config.json')
        self.data = {}
        self._load()
    
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except:
                self.data = {}
        if not self.data:
            self.data = {
                'mode': 'profiles',
                'fusion_weights': {p: 0.4 for p in POSES},
                'pitch_limit': 45,
                'thresholds': {
                    'front': {'h_thresh': 2.0, 's_thresh': 2.0},
                    'up': {'h_thresh': 2.0, 's_thresh': 2.0},
                    'down': {'h_thresh': 1.5, 's_thresh': 1.5},
                    'side': {'h_thresh': 1.5, 's_thresh': 1.5}
                },
                'fer_bias': DEFAULT_FER_BIAS.copy()
            }
    
    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as ex:
            print(f"[GlobalConfig] 保存失败: {ex}")
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def set(self, key, value):
        self.data[key] = value
        self._save()

# ── 核心引擎 ──────────────────────────────────────────
class EmotionEngine:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # AU 组件
        self.det = FaceDetector()
        self.face_sel = FaceSelector()
        self.speech_det = SpeechDetector()
        self.pose_est = PoseEstimator()
        self.au_ext = AUExtractor()
        persist = os.path.join(os.path.dirname(__file__),'data','baselines.json')
        self.mapper = EmotionMapper(history=50, persist_path=persist)
        
        # 轮廓向量匹配器
        self.profile_matcher = ProfileMatcher()
        
        # 全局配置
        self.gcfg = GlobalConfig()
        
        # 从 gcfg 同步配置到 mapper.config
        gcfg_fusion_weights = self.gcfg.get('fusion_weights')
        if gcfg_fusion_weights:
            self.mapper.config['fusion_weights'] = gcfg_fusion_weights
        gcfg_thresholds = self.gcfg.get('thresholds')
        if gcfg_thresholds:
            for p in POSES:
                if p in gcfg_thresholds:
                    self.mapper.config[p] = gcfg_thresholds[p]
        gcfg_pitch_limit = self.gcfg.get('pitch_limit')
        if gcfg_pitch_limit is not None:
            self.mapper.config['pitch_limit'] = gcfg_pitch_limit
        
        # FER+ 组件
        self.fer_det = FERDetector(); self.fer_align = FERAligner(); self.fer_smoother = FERSmoother(window=5)
        # FER+ 配置（从全局配置加载）
        self.fer_bias = self.gcfg.get('fer_bias', DEFAULT_FER_BIAS.copy())
        
        # Intentionally lock-free: CPython reference assignment is atomic.
        # Both threads may process slightly different frames (≤1 frame drift).
        # Acceptable because each channel has its own smoothing window.
        self.raw_frame = None
        self.last_landmarks = None  # 保存最新的人脸关键点
        
        self.lock = threading.Lock(); self.running = False
        self.annotated = None
        self.t0 = time.time(); self._fc_au = 0; self._fc_fer = 2
        
        self.au_result = {'emotion':'no_face','confidence':0.,'scores':{'calm':0,'happy':0,'sad':0},'pose':'-','pitch':0,'yaw':0,'roll':0,'au':{},'speaking':False,'calibrating':False,'calib_pose':None,'calib_emotion':None,'calib_count':0}
        self.fer_result = {'label':'calm','conf':0.0,'probs_3':{'calm':0,'happy':0,'sad':0},'has_face':False}
        
        # 画面快照缓存（最近20次）
        self.snapshots = deque(maxlen=20)
        self.prev_emotion = None
        self.last_snap_time = 0  # 上次快照时间

    def grab_loop(self):
        if not self.cap.isOpened(): return
        self.running = True
        
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                
                # 直接保存原始帧，不做任何绘制
                self.raw_frame = frame
                
                # 视频流直接传输原始画面（无任何绘制）
                r, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if r:
                    with self.lock:
                        self.annotated = buf.tobytes()
                
                # 快照逻辑：情绪变化立即捕捉，否则0.5s捕捉一次（快照带标注）
                now = time.time()
                should_snap = False
                
                # 读取au_result和prev_emotion
                try:
                    with self.lock:
                        au_em = self.au_result.get('emotion', 'no_face')
                        fer_lb = self.fer_result.get('label', '-')
                        current_prev_emotion = self.prev_emotion
                except:
                    au_em = 'no_face'
                    fer_lb = '-'
                    current_prev_emotion = None
                
                # 情绪变化立即捕捉（排除无效情绪）
                if au_em != current_prev_emotion and au_em not in ('no_face', 'uncalibrated', 'out_of_range', 'speaking'):
                    should_snap = True
                # 情绪不变时，每0.5秒捕捉一次
                elif now - self.last_snap_time >= 0.5 and au_em not in ('no_face', 'uncalibrated', 'out_of_range'):
                    should_snap = True
                
                if should_snap:
                    # 快照直接用原图，不做任何绘制
                    # 只保存原始bytes，Base64编码留到API请求时做（惰性计算）
                    snap_buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
                    elapsed = round(now - self.t0, 1)
                    local_time = time.localtime(now)
                    time_str = time.strftime("%H:%M:%S", local_time)
                    
                    # 使用融合结果而不是AU结果
                    fusion_em = self.get_fusion().get('emotion', au_em)
                    
                    with self.lock:
                        self.snapshots.append({
                            'img_raw': snap_buf,  # 保存原始bytes，不立即编码
                            'emotion': fusion_em,
                            'time': elapsed,
                            'time_str': time_str,
                            'timestamp': now
                        })
                        self.prev_emotion = fusion_em
                    
                    self.last_snap_time = now
                
                time.sleep(0.01)
            except Exception as e:
                print(f"[Grab Loop Error]: {e}")
                time.sleep(0.1)

    def au_loop(self):
        lm_cache = None
        
        while self.running:
            frame = self.raw_frame
            if frame is not None:
                self._fc_au += 1
                
                if self._fc_au % 2 == 0 and lm_cache is not None:
                    self.speech_det.update(lm_cache)
                
                if self._fc_au % 4 == 1:
                    lm_list = self.det.process(frame)
                    lm = self.face_sel.select(lm_list, frame.shape) if lm_list else None
                    lm_cache = lm
                    self.last_landmarks = lm
                    res = dict(self.au_result)
                    if lm is not None:
                        speaking = self.speech_det.update(lm)
                        pitch, yaw, roll = self.pose_est.estimate(frame, lm)
                        au = self.au_ext.predict(frame, lm)
                        
                        if self.mapper.calibrating and au:
                            cp, ce = self.mapper.calibrating; cnt = self.mapper.feed_calib(au)
                            res.update(calibrating=True, calib_pose=cp, calib_emotion=ce, calib_count=cnt)
                            if cnt >= CALIB_N: self.mapper.finish_calib(cp, ce); res['calibrating']=False
                        
                        has_profiles = bool(self.profile_matcher.profiles)
                        mode = self.gcfg.get('mode', 'profiles')
                        if mode == 'profiles' and has_profiles and au:
                            pose, emotion, conf, scores = self.profile_matcher.predict(au, pitch, yaw, speaking=speaking)
                            res['matching_method'] = 'profile'
                        else:
                            pose, emotion, conf, scores = self.mapper.predict(au, pitch, yaw, speaking=speaking)
                            res['matching_method'] = 'zscore' if mode == 'base' else 'profile_no_data'
                        
                        res.update(pose=pose, emotion=emotion, confidence=round(conf,3), pitch=round(pitch,1), yaw=round(yaw,1), roll=round(roll,1), scores={k:round(v,3) for k,v in scores.items()}, au={k:round(v,1) for k,v in au.items()} if au else {}, speaking=speaking)
                    else:
                        res.update(emotion='no_face', au={}, scores={'neutral':0,'positive':0,'negative':0}, speaking=False)
                    self.au_result = res
            time.sleep(0.01)

    def fer_loop(self):
        while self.running:
            frame = self.raw_frame
            if frame is not None:
                self._fc_fer += 1
                # 低频推理（每15帧一次，降低CPU占用）
                if self._fc_fer % 15 == 3:
                    aligned = self.fer_align.align(frame)
                    if aligned is not None:
                        s_label, s_conf, probs_8 = self.fer_det.predict(aligned)
                        
                        # 对原始8种概率应用 bias
                        biased_probs_8 = probs_8.copy()
                        for i, label in enumerate(FER_LABELS_8):
                            biased_probs_8[i] += self.fer_bias.get(label, 0.0)
                        
                        # 合并成3类
                        probs_3 = {
                            'positive': biased_probs_8[1],
                            'negative': biased_probs_8[3] + biased_probs_8[4] + biased_probs_8[5] + biased_probs_8[6],
                            'neutral': biased_probs_8[0] + biased_probs_8[2] + biased_probs_8[7]
                        }
                        
                        # 归一化
                        total = sum(probs_3.values()) + 1e-8
                        for e in EMOTIONS:
                            probs_3[e] /= total
                        
                        # 找到合并后概率最高的标签
                        final_label_3 = max(probs_3, key=probs_3.get)
                        
                        # 同时保存原始8种情绪的概率，用于显示
                        probs_8_dict = {FER_LABELS_8[i]: float(probs_8[i]) for i in range(8)}
                        biased_probs_8_dict = {FER_LABELS_8[i]: float(biased_probs_8[i]) for i in range(8)}
                        # 找到原始最高的情绪
                        original_best_idx = int(np.argmax(biased_probs_8))
                        original_label = FER_LABELS_8[original_best_idx]
                        
                        final_label, final_conf, final_probs = self.fer_smoother.update(final_label_3, probs_3)
                        self.fer_result = {
                            'label': final_label,
                            'conf': round(final_conf, 3),
                            'probs_3': {k: round(v, 3) for k, v in final_probs.items()},
                            'has_face': True,
                            'original_label': original_label,
                            'probs_8': probs_8_dict,
                            'biased_probs_8': biased_probs_8_dict
                        }
                    else:
                        self.fer_result = {
                            'label':'neutral',
                            'conf':0.0,
                            'probs_3':{'neutral':0,'positive':0,'negative':0},
                            'has_face':False,
                            'original_label': None,
                            'probs_8': {},
                            'biased_probs_8': {}
                        }
            time.sleep(0.01)

    def get_fusion(self):
        au = self.au_result; fer = self.fer_result
        em = au.get('emotion')
        if em in ('no_face', 'out_of_range', 'speaking', 'uncalibrated'):
            return {**au, 'tag': em, 'au_raw': em, 'fer_raw': fer.get('label', '-')}
        if not fer.get('has_face'):
            return {**au, 'tag': 'au_only', 'au_raw': em, 'fer_raw': '-'}
        
        pose = au.get('pose', 'front')
        w_au = self.mapper.config.get('fusion_weights', {}).get(pose, 0.4)
        w_fer = 1.0 - w_au
        au_scores = au.get('scores', {'calm':0,'happy':0,'sad':0})
        fer_probs = fer.get('probs_3', {'calm':0,'happy':0,'sad':0})
        
        fused_raw = {e: au_scores[e]*w_au + fer_probs[e]*w_fer for e in EMOTIONS}
        total = sum(fused_raw.values()) + 1e-8
        fused_norm = {e: v/total for e, v in fused_raw.items()}
        
        best = max(fused_norm, key=fused_norm.get)
        conf = fused_norm[best]
        au_best = max(au_scores, key=au_scores.get)
        fer_best = fer.get('label', 'calm')
        
        tag = 'agree' if au_best == fer_best else 'disagree'
        if tag == 'agree': conf = min(conf * 1.15, 0.98)
        else: conf = conf * 0.65
            
        return {
            'emotion': best, 'confidence': round(conf, 3),
            'scores': {e: round(v, 3) for e, v in fused_norm.items()},
            'pose': au.get('pose', '-'), 'pitch': au.get('pitch', 0), 'yaw': au.get('yaw', 0),
            'tag': tag, 'au_raw': au_best, 'fer_raw': fer_best
        }

    def start_calib(self, pose, emotion): return self.mapper.start_calib(pose, emotion)
    def update_config(self, cfg):
        mc = self.mapper.config
        for k, v in cfg.items():
            if k in mc:
                if isinstance(mc[k], dict) and isinstance(v, dict): mc[k].update(v)
                else: mc[k] = v
            elif k == 'mode':
                self.gcfg.set('mode', v)
            elif k == 'fusion_weights':
                self.gcfg.set('fusion_weights', v)
                self.mapper.config['fusion_weights'] = v
            elif k == 'pitch_limit':
                self.gcfg.set('pitch_limit', v)
                self.mapper.config['pitch_limit'] = v
            elif k == 'thresholds':
                self.gcfg.set('thresholds', v)
                for p in POSES:
                    if p in v:
                        self.mapper.config[p] = v[p]
            elif k == 'fer_bias':
                self.gcfg.set('fer_bias', v)
                self.fer_bias = v
        self.gcfg._save()
    def shutdown(self): self.running = False; self.cap.release(); self.det.release()

# ── Flask ────────────────────────────────────────────
app = Flask(__name__)
engine = EmotionEngine()
threading.Thread(target=engine.grab_loop, daemon=True).start()
threading.Thread(target=engine.au_loop, daemon=True).start()
threading.Thread(target=engine.fer_loop, daemon=True).start()

@app.route("/")
def index(): return open(os.path.join(SCRIPT_DIR, "emo.html"), encoding="utf-8").read()

def gen():
    last_frame = None
    frame_timeout = 0
    consecutive_errors = 0
    while True:
        try:
            current_frame = None
            # 使用超时机制获取帧
            with engine.lock:
                current_frame = engine.annotated
            
            if current_frame:
                last_frame = current_frame
                frame_timeout = 0
                consecutive_errors = 0
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + current_frame + b"\r\n"
            elif last_frame:
                frame_timeout += 1
                if frame_timeout < 30:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + last_frame + b"\r\n"
                else:
                    # 超时30帧后仍yield旧帧，但间隔拉大，减少CPU空转
                    time.sleep(0.1)
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + last_frame + b"\r\n"
                    time.sleep(0.2)
            else:
                # 等待帧准备
                time.sleep(0.05)
                
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors < 10:
                print(f"[Video Feed Error {consecutive_errors}]: {e}")
            time.sleep(0.05)
            if last_frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + last_frame + b"\r\n"
            continue
        time.sleep(0.02)  # 约50fps，减少CPU占用
@app.route("/video_feed")
def video_feed(): return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/status")
def api_status():
    s = dict(engine.au_result); s['config'] = engine.mapper.config; s['calibrated'] = engine.mapper.get_calibrated()
    return jsonify(s)

@app.route("/api/profile")
def api_profile():
    pm = engine.profile_matcher
    has_profiles = bool(pm.profiles)
    profile_info = {}
    if has_profiles:
        for pose in pm.profiles:
            profile_info[pose] = {}
            for emo in pm.profiles[pose]:
                if pm.profiles[pose][emo]:
                    profile_info[pose][emo] = {'count': pm.profiles[pose][emo].get('sample_count', 0), 'loaded': True}
                else:
                    profile_info[pose][emo] = {'count': 0, 'loaded': False}
    return jsonify({
        'has_profiles': has_profiles,
        'profiles': profile_info,
        'mode': engine.gcfg.get('mode', 'profiles')
    })

@app.route("/api/fer")
def api_fer(): return jsonify(engine.fer_result)

@app.route("/api/fusion")
def api_fusion(): return jsonify(engine.get_fusion())

@app.route("/api/profile/realtime")
def api_profile_realtime():
    au_result = engine.au_result
    pose = au_result.get('pose', 'front')
    confidence = au_result.get('confidence', 0.0)
    return jsonify({
        'emotion': au_result.get('emotion', 'unknown'),
        'confidence': confidence,
        'pose': pose,
        'available_profiles': engine.profile_matcher.get_available_profiles()
    })

@app.route("/api/calibrate/start", methods=["POST"])
def calib_start():
    d = request.get_json() or {}; return jsonify({"ok": engine.start_calib(d.get("pose","front"), d.get("emotion","calm"))})

@app.route("/api/config", methods=["GET","POST"])
def api_config():
    if request.method == "POST":
        engine.update_config(request.get_json() or {}); return jsonify({"ok": True})
    # 从 gcfg 构建配置响应
    cfg = {}
    # 复制 thresholds
    thresholds = engine.gcfg.get('thresholds', {p: {'h_thresh': 2.0, 's_thresh': 2.0} for p in POSES})
    for p in POSES:
        if p in thresholds:
            cfg[p] = thresholds[p]
    # 添加其他配置
    cfg['mode'] = engine.gcfg.get('mode', 'profiles')
    cfg['fusion_weights'] = engine.gcfg.get('fusion_weights', {p: 0.4 for p in POSES})
    cfg['pitch_limit'] = engine.gcfg.get('pitch_limit', 45)
    cfg['thresholds'] = thresholds
    cfg['fer_bias'] = engine.gcfg.get('fer_bias', DEFAULT_FER_BIAS.copy())
    return jsonify(cfg)

@app.route("/api/calibrate/delete", methods=["POST"])
def calib_delete():
    d = request.get_json() or {}; return jsonify({"ok": engine.mapper.delete_baseline(d.get("pose","front"), d.get("emotion","calm"))})

@app.route("/api/calibrate/delete_all", methods=["POST"])
def calib_delete_all():
    engine.mapper.delete_all_baselines(); return jsonify({"ok": True})

@app.route("/api/snapshots")
def api_snapshots():
    with engine.lock:
        # 惰性编码：只在API请求时才进行Base64编码
        result = []
        for snap in engine.snapshots:
            item = dict(snap)
            if 'img_raw' in item:
                item['img'] = base64.b64encode(item['img_raw']).decode()
                del item['img_raw']
            result.append(item)
        return jsonify(result)

@app.route("/api/all")
def api_all():
    au = dict(engine.au_result)
    au['config'] = engine.mapper.config
    au['calibrated'] = engine.mapper.get_calibrated()
    return jsonify({
        'au': au,
        'fer': engine.fer_result,
        'fusion': engine.get_fusion()
    })

if __name__ == "__main__":
    try: app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)
    finally: engine.shutdown()