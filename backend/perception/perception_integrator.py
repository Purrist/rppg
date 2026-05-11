
# -*- coding: utf-8 -*-
"""
Perception Integrator - 感知系统整合模块
将 perception.py 中的核心逻辑提取为可导入模块
不启动独立的 Flask 应用，而是集成到 app.py 主系统
"""

import os
import sys
import time
import threading
import atexit
import requests
from collections import deque

# 导入 DDA 系统
from .dda import DDASystem

# ========================================
# 常量配置
# ========================================
AU_EMOTION_API = "http://127.0.0.1:5010/api/fusion"
AU_STATUS_API = "http://127.0.0.1:5010/api/status"
HLKK_DATA_API = "http://127.0.0.1:5020/data"


# ========================================
# EmotionProcessor - 情绪与生理数据处理
# ========================================
class EmotionProcessor:
    def __init__(self):
        self.emotion_data = {
            "neutral": 0.0,
            "positive": 0.0,
            "negative": 0.0,
            "confidence": 0.0,
            "emotion": "neutral",
            "engagement": "None",
            "timestamp": 0
        }
        self.physio_data = {
            "heart": 0,
            "breath": 0,
            "human": False,
            "timestamp": 0,
            "hr_valid": False,
            "hr_valid_since": 0,
            "hrr_pct": 0,
            "hr_slope": 0
        }
        self.face_data = {
            "face_detected": False,
            "face_count": 0,
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "pose": "-",
            "is_front_face": False
        }
        self.processed_emotion = {
            "label": "neutral",
            "confidence": 0.0,
            "value": 0,
            "timestamp": 0
        }
        self.lock = threading.Lock()
        self.enabled = True
        self.gate_enabled = True
        self.history = []
        self.history_max = 300
        self.start_time = time.time()
        self.startup_grace_period = 30

    def fetch_au_emotion(self):
        try:
            resp = requests.get(AU_EMOTION_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                scores = d.get("scores", {})
                return {
                    "neutral": scores.get("neutral", 0),
                    "positive": scores.get("positive", 0),
                    "negative": scores.get("negative", 0),
                    "confidence": d.get("confidence", 0),
                    "emotion": d.get("emotion", "neutral"),
                    "engagement": d.get("tag", "None"),
                    "timestamp": time.time()
                }
        except Exception:
            pass
        return None

    def fetch_face_status(self):
        try:
            resp = requests.get(AU_STATUS_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "face_detected": d.get("face_detected", False),
                    "face_count": d.get("face_count", 0),
                    "pitch": d.get("pitch", 0.0),
                    "yaw": d.get("yaw", 0.0),
                    "roll": d.get("roll", 0.0),
                    "pose": d.get("pose", "-"),
                    "is_front_face": abs(d.get("yaw", 0)) < 35 and abs(d.get("pitch", 0)) < 25
                }
        except Exception:
            pass
        return None

    def fetch_physio_data(self):
        try:
            resp = requests.get(HLKK_DATA_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                raw = d.get("raw", {})
                physiology = d.get("physiology", {})
                return {
                    "heart": raw.get("hr", 0),
                    "breath": raw.get("br", 0),
                    "human": raw.get("is_human", 0) == 1,
                    "timestamp": time.time(),
                    "hr_valid": raw.get("hr_valid", False),
                    "hrr_pct": physiology.get("hrr_pct", 0),
                    "hr_slope": physiology.get("hr_slope", 0)
                }
        except Exception as e:
            pass
        return None

    def apply_gate(self, emotion_data):
        if not self.gate_enabled:
            return {
                "label": emotion_data.get("emotion", "neutral"),
                "confidence": emotion_data.get("confidence", 0),
                "value": self.emotion_to_value(emotion_data.get("emotion", "neutral")),
                "timestamp": emotion_data.get("timestamp", time.time())
            }

        emotion = emotion_data.get("emotion", "neutral")

        special_states = {'no_face', 'out_of_range', 'speaking', 'uncalibrated'}
        if emotion in special_states:
            return {
                "label": emotion,
                "confidence": 0,
                "value": 0,
                "timestamp": emotion_data.get("timestamp", time.time())
            }

        scores = {
            'positive': emotion_data.get("positive", 0),
            'neutral': emotion_data.get("neutral", 0),
            'negative': emotion_data.get("negative", 0)
        }
        conf = emotion_data.get("confidence", 0)

        label_cn = self.classify_confidence(scores)
        label = self.cn_label_to_en(label_cn)
        value = self.emotion_to_value(label)

        p1 = max(scores.values())
        confidence = min(p1 * conf * 1.5, 1.0)

        return {
            "label": label,
            "confidence": confidence,
            "value": value,
            "timestamp": emotion_data.get("timestamp", time.time())
        }

    def classify_confidence(self, scores):
        p_pos = scores['positive']
        p_neu = scores['neutral']
        p_neg = scores['negative']

        items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        (e1, p1), (e2, p2), (e3, p3) = items

        mu = p_pos - p_neg

        if p1 >= 0.70 and (p1 - p2) >= 0.20:
            if e1 == 'positive' and p_neg <= 0.15:
                return '积极高信度'
            if e1 == 'negative' and p_pos <= 0.15:
                return '消极高信度'
            if e1 == 'neutral' and max(p_pos, p_neg) <= 0.15:
                return '中性高信度'

        if p_pos > 0.10 and p_neg > 0.10 and abs(mu) < 0.25:
            return '中性'

        if p1 - p3 <= 0.20:
            return '中性'

        if e1 == 'neutral' and p_neu >= 0.50:
            if abs(mu) >= 0.30:
                return '积极低信度' if mu > 0 else '消极低信度'
            return '中性'

        if e1 == 'positive':
            if mu < 0.20:
                return '中性'
            return '积极低信度'

        if e1 == 'negative':
            if -mu < 0.20:
                return '中性'
            return '消极低信度'

        if abs(mu) >= 0.25:
            return '积极低信度' if mu > 0 else '消极低信度'

        return '中性'

    def cn_label_to_en(self, label_cn):
        mapping = {
            '积极高信度': 'positive_high',
            '消极高信度': 'negative_high',
            '中性高信度': 'neutral_high',
            '积极低信度': 'positive_low',
            '消极低信度': 'negative_low',
            '中性': 'neutral'
        }
        return mapping.get(label_cn, 'neutral')

    def emotion_to_value(self, label):
        mapping = {
            'positive_high': 1,
            'positive_low': 0.5,
            'neutral': 0,
            'neutral_high': 0,
            'negative_low': -0.5,
            'negative_high': -1,
            'positive': 1,
            'negative': -1
        }
        return mapping.get(label, 0)

    def update(self):
        au_data = self.fetch_au_emotion()
        physio = self.fetch_physio_data()
        face = self.fetch_face_status()

        with self.lock:
            if au_data:
                self.emotion_data = au_data
                self.processed_emotion = self.apply_gate(au_data)
                self.history.append({
                    "emotion": self.emotion_data.copy(),
                    "processed": self.processed_emotion.copy(),
                    "timestamp": time.time()
                })
                if len(self.history) > self.history_max:
                    self.history.pop(0)

            if physio:
                if physio.get("hr_valid", False):
                    physio["hr_valid_since"] = time.time()
                else:
                    physio["hr_valid_since"] = self.physio_data.get("hr_valid_since", 0)
                self.physio_data = physio

            if face:
                self.face_data = face

    def get_current(self):
        with self.lock:
            return {
                "emotion": self.emotion_data.copy(),
                "processed": self.processed_emotion.copy(),
                "physio": self.physio_data.copy(),
                "face": self.face_data.copy(),
                "history": list(self.history)
            }


# ========================================
# PerceptionIntegrator - 主整合类
# ========================================
class PerceptionIntegrator:
    def __init__(self, socketio=None, system_core=None):
        self.socketio = socketio
        self.system_core = system_core

        # 初始化组件
        self.emotion_processor = EmotionProcessor()

        # 子进程管理
        self.child_processes = []
        self.running = False

        # 注册退出清理
        atexit.register(self.cleanup)

    def start_child_processes(self):
        """启动子进程（au/emotion.py, hlkk.py）"""
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # 启动 AU 情绪模块
        au_emotion_script = os.path.join(script_dir, "au", "emotion.py")
        if os.path.exists(au_emotion_script):
            print(f"[PerceptionIntegrator] 启动 AU 情绪模块: {au_emotion_script}")
            import subprocess
            au_proc = subprocess.Popen([sys.executable, au_emotion_script],
                                        cwd=os.path.join(script_dir, "au"))
            self.child_processes.append(au_proc)

        # 启动 HLKK 生理模块
        hlkk_script = os.path.join(script_dir, "hlkk.py")
        if os.path.exists(hlkk_script):
            print(f"[PerceptionIntegrator] 启动 HLKK 生理模块: {hlkk_script}")
            import subprocess
            hlkk_proc = subprocess.Popen([sys.executable, hlkk_script],
                                          cwd=script_dir)
            self.child_processes.append(hlkk_proc)

    def cleanup(self):
        """清理子进程"""
        print("[PerceptionIntegrator] 正在停止子进程...")
        for proc in self.child_processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in self.child_processes:
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        print("[PerceptionIntegrator] 所有子进程已停止")

    def update_perception_to_system_core(self):
        """将感知数据更新到 system_core"""
        try:
            with self.emotion_processor.lock:
                physio = self.emotion_processor.physio_data
                emotion = self.emotion_processor.processed_emotion
                face_data = self.emotion_processor.face_data

            # 获取数据
            hr_valid = physio.get('hr_valid', False)
            hrr_pct = physio.get('hrr_pct', 0)
            hr_slope = physio.get('hr_slope', 0)
            heart_rate = physio.get('heart', 0)

            face_detected = face_data.get('face_detected', True)
            face_count = face_data.get('face_count', 1)

            label = emotion.get('label', 'neutral')
            confidence = emotion.get('confidence', 0)

            # 将情绪标签转换为 system_core 能用的格式
            emotion_map = {
                'positive_high': 'happy',
                'positive_low': 'happy',
                'negative_high': 'sad',
                'negative_low': 'sad',
                'neutral_high': 'neutral',
                'neutral': 'neutral'
            }
            simple_emotion = emotion_map.get(label, 'neutral')

            if self.system_core:
                # 调用 system_core 的 update_perception 方法
                self.system_core.update_perception({
                    'personDetected': face_detected,
                    'personCount': face_count,
                    'faceCount': face_count,
                    'bodyDetected': face_detected,
                    'emotion': simple_emotion,
                    'attention': confidence if confidence else 0.5,
                    'fatigue': 0,  # 暂时由其他模块处理
                    'heartRate': heart_rate if hr_valid else None,
                    'activity': 'standing' if face_detected else 'unknown',
                })

                # 同时保存 DDA 专用的完整感知数据
                self.system_core.set_dda_perception_data({
                    'hr_valid': hr_valid,
                    'hrr_pct': hrr_pct,
                    'hr_slope': hr_slope,
                    'emotion': label,
                    'confidence': confidence,
                    'face_detected': face_detected,
                    'face_count': face_count
                })

        except Exception as e:
            print(f"[PerceptionIntegrator] 更新感知数据失败: {e}")

    def update_loop(self):
        """主更新循环"""
        last_processor_update = time.time()
        last_core_update = time.time()

        while self.running:
            current_time = time.time()

            # 更新情绪与生理数据
            if current_time - last_processor_update >= 0.5:
                last_processor_update = current_time
                self.emotion_processor.update()

            # 定期更新到 system_core
            if current_time - last_core_update >= 1.0:
                last_core_update = current_time
                self.update_perception_to_system_core()

            time.sleep(0.1)

    def start(self):
        """启动整合器"""
        print("[PerceptionIntegrator] 正在启动...")
        self.running = True

        # 启动子进程
        self.start_child_processes()

        # 等待子进程启动
        time.sleep(3)

        # 启动更新循环
        threading.Thread(target=self.update_loop, daemon=True).start()
        print("[PerceptionIntegrator] 已启动")

    def stop(self):
        """停止整合器"""
        self.running = False
        self.cleanup()

