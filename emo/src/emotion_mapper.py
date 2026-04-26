import os
import json
import numpy as np
from collections import deque

class EmotionMapper:
    POSES = ['front', 'up', 'down', 'side']
    EMOTIONS = ['calm', 'happy', 'sad']

    def __init__(self, history=5, persist_path=None):
        self.baselines = {p: None for p in self.POSES}
        self.buffers = {p: [] for p in self.POSES}
        self.calibrating = None
        self.hist = deque(maxlen=history)
        self.config = self._default_config()

        # 状态机
        self.last_emotion = 'calm'
        self.switch_counter = 0

        # 持久化路径
        if persist_path is None:
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
            persist_path = os.path.join(base, 'data', 'baselines.json')
        self.persist_path = persist_path
        self.load_baselines()

    def _default_config(self):
        return {
            'front': {
                'happy_thresh': 0.5, 'sad_thresh': 0.5,
                'weights': {'mouth': 1.0, 'eyes': 1.0, 'eyebrows': 1.0}
            },
            'up': {
                'happy_thresh': 0.5, 'sad_thresh': 0.5,
                'weights': {'mouth': 1.0, 'eyes': 1.0, 'eyebrows': 1.0}
            },
            'down': {
                'happy_thresh': 0.5, 'sad_thresh': 0.5,
                'weights': {'mouth': 0.1, 'eyes': 1.8, 'eyebrows': 1.8}
            },
            'side': {
                'happy_thresh': 0.5, 'sad_thresh': 0.5,
                'weights': {'mouth': 0.2, 'eyes': 1.5, 'eyebrows': 1.5}
            }
        }

    def load_baselines(self):
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for pose in self.POSES:
                    if pose in data and data[pose] is not None:
                        self.baselines[pose] = {
                            'mu': {k: float(v) for k, v in data[pose]['mu'].items()},
                            'sigma': {k: float(v) for k, v in data[pose]['sigma'].items()}
                        }
                print(f"[EmotionMapper] 已加载基线: {self.persist_path}")
            except Exception as e:
                print(f"[EmotionMapper] 加载基线失败: {e}")

    def save_baselines(self):
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            data = {}
            for pose in self.POSES:
                if self.baselines[pose] is not None:
                    data[pose] = {
                        'mu': {k: float(v) for k, v in self.baselines[pose]['mu'].items()},
                        'sigma': {k: float(v) for k, v in self.baselines[pose]['sigma'].items()}
                    }
            with open(self.persist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[EmotionMapper] 基线已保存: {self.persist_path}")
        except Exception as e:
            print(f"[EmotionMapper] 保存基线失败: {e}")

    def start_calib(self, pose):
        if pose not in self.POSES:
            return False
        self.calibrating = pose
        self.buffers[pose] = []
        print(f"[校准] 开始采集「{pose}」基线，请保持平静...")
        return True

    def finish_calib(self, pose):
        buf = self.buffers.get(pose, [])
        if len(buf) < 15:
            self.calibrating = None
            print(f"[校准] 样本不足 ({len(buf)} < 15)，取消")
            return False

        keys = list(buf[0].keys())
        mu = {k: float(np.mean([f[k] for f in buf])) for k in keys}
        sigma = {k: float(np.std([f[k] for f in buf])) for k in keys}
        sigma = {k: max(v, 1e-6) for k, v in sigma.items()}

        self.baselines[pose] = {'mu': mu, 'sigma': sigma}
        self.calibrating = None
        self.save_baselines()
        print(f"[校准] 「{pose}」基线已建立 (样本{len(buf)})，已持久化")
        return True

    def feed_calib(self, features):
        if self.calibrating and self.calibrating in self.buffers:
            self.buffers[self.calibrating].append(features)
            return len(self.buffers[self.calibrating])
        return 0

    def get_pose(self, pitch, yaw):
        # 用户反馈：抬头低头符号反了，已互换
        if abs(yaw) > 35:
            return 'side'
        if pitch > 15:        # 抬头为正
            return 'up'
        if pitch < -20:       # 低头为负
            return 'down'
        return 'front'

    def predict(self, features, pitch, yaw):
        pose = self.get_pose(pitch, yaw)
        baseline = self.baselines[pose]
        if baseline is None:
            return pose, 'uncalibrated', 0.0, {'calm': 1.0, 'happy': 0.0, 'sad': 0.0}

        mu, sigma = baseline['mu'], baseline['sigma']
        cfg = self.config[pose]
        w = cfg['weights']

        # z-score 归一化（消除不同特征尺度差异）
        z = {}
        for k in ['eye_open_avg', 'brow_height_avg', 'brow_inner_dist', 'mouth_ar', 'mouth_corner_lift']:
            if k in mu and k in sigma:
                z[k] = (features[k] - mu[k]) / sigma[k]
            else:
                z[k] = 0.0

        # ---- 高兴激活度 ----
        h_act = 0.0
        if z.get('mouth_corner_lift', 0) > 1.0:
            h_act += 0.4 * w['mouth']
        if z.get('mouth_corner_lift', 0) > 2.0:
            h_act += 0.3 * w['mouth']
        if z.get('eye_open_avg', 0) < -0.5:
            h_act += 0.2 * w['eyes']
        if z.get('eye_open_avg', 0) < -1.5:
            h_act += 0.15 * w['eyes']
        if z.get('mouth_ar', 0) > 0.5:
            h_act += 0.05 * w['mouth']

        # ---- 沮丧激活度 ----
        s_act = 0.0
        if z.get('mouth_corner_lift', 0) < -1.0:
            s_act += 0.4 * w['mouth']
        if z.get('mouth_corner_lift', 0) < -2.0:
            s_act += 0.3 * w['mouth']
        if z.get('brow_height_avg', 0) > 1.0:
            s_act += 0.2 * w['eyebrows']
        if z.get('brow_inner_dist', 0) < -0.5:
            s_act += 0.15 * w['eyebrows']
        if z.get('eye_open_avg', 0) < -0.3:
            s_act += 0.05 * w['eyes']

        # ---- 平静 = 默认态 ----
        max_act = max(h_act, s_act)
        c_act = max(0.0, 1.0 - max_act * 1.5)

        total = h_act + s_act + c_act + 1e-6
        scores = {
            'happy': h_act / total,
            'sad': s_act / total,
            'calm': c_act / total
        }

        # ---- 状态机 + 迟滞（防止跳变）----
        raw_best = max(scores, key=scores.get)

        # 从平静切换出去需要强证据（激活度 > 0.5）
        if self.last_emotion == 'calm':
            if raw_best == 'happy' and h_act < 0.5:
                raw_best = 'calm'
            elif raw_best == 'sad' and s_act < 0.5:
                raw_best = 'calm'
        else:
            # 从情绪切回平静需要激活度大幅下降
            if raw_best == 'calm' and max_act > 0.25:
                raw_best = self.last_emotion

        # 最小持续帧数锁定（连续3帧才切换）
        if raw_best != self.last_emotion:
            self.switch_counter += 1
            if self.switch_counter < 3:
                best = self.last_emotion
            else:
                best = raw_best
                self.last_emotion = raw_best
                self.switch_counter = 0
        else:
            self.switch_counter = 0
            best = raw_best

        # 时序平滑（仅用于显示）
        self.hist.append(scores)
        smooth = {e: float(np.mean([h[e] for h in self.hist])) for e in self.EMOTIONS}
        conf = smooth[best]

        return pose, best, float(conf), smooth