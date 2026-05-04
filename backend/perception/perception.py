# -*- coding: utf-8 -*-
"""
Perception - 情绪与生理数据综合展示模块
整合 AU+FER 情绪数据与心率呼吸率数据，提供进一步的情感分析
"""
import os
import json
import time
import threading
import requests
import subprocess
import atexit
import sys
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

AU_EMOTION_API = "http://127.0.0.1:5000/api/fusion"
COM_DATA_API = "http://127.0.0.1:5001/data"

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "au", "config.json")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emodata")

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
            "timestamp": 0
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

    def fetch_au_emotion(self):
        try:
            resp = requests.get(AU_EMOTION_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "neutral": d.get("scores", {}).get("neutral", 0),
                    "positive": d.get("scores", {}).get("positive", 0),
                    "negative": d.get("scores", {}).get("negative", 0),
                    "confidence": d.get("confidence", 0),
                    "emotion": d.get("emotion", "neutral"),
                    "engagement": d.get("engagement", "None"),
                    "timestamp": time.time()
                }
        except:
            pass
        return None

    def fetch_physio_data(self):
        try:
            resp = requests.get(COM_DATA_API, timeout=0.5)
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "heart": d.get("heart", 0),
                    "breath": d.get("breath", 0),
                    "human": d.get("human", False),
                    "timestamp": time.time()
                }
        except:
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
        
        # 基于势场深度计算置信度
        p1 = max(scores.values())
        confidence = min(p1 * conf * 1.5, 1.0)
        
        return {
            "label": label,
            "confidence": confidence,
            "value": value,
            "timestamp": emotion_data.get("timestamp", time.time())
        }

    def classify_confidence(self, scores):
        """
        基于多稳态势场理论的实时情绪状态分类器。
        核心思想：分类不取决于单一概率的最大值，而取决于该状态在势场中形成的“势阱深度”是否足以抵抗帧间噪声扰动。
        """
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
                self.physio_data = physio

    def get_current(self):
        with self.lock:
            return {
                "emotion": self.emotion_data.copy(),
                "processed": self.processed_emotion.copy(),
                "physio": self.physio_data.copy(),
                "history": list(self.history)
            }

processor = EmotionProcessor()

child_processes = []

def start_child_processes():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    au_emotion_script = os.path.join(script_dir, "au", "emotion.py")
    if os.path.exists(au_emotion_script):
        print(f"启动 AU 情绪模块: {au_emotion_script}")
        au_proc = subprocess.Popen([sys.executable, au_emotion_script], 
                                  cwd=os.path.join(script_dir, "au"))
        child_processes.append(au_proc)
    else:
        print(f"警告: AU 情绪模块未找到: {au_emotion_script}")
    
    com_script = os.path.join(script_dir, "com.py")
    if os.path.exists(com_script):
        print(f"启动 COM 生理模块: {com_script}")
        com_proc = subprocess.Popen([sys.executable, com_script], 
                                  cwd=script_dir)
        child_processes.append(com_proc)
    else:
        print(f"警告: COM 生理模块未找到: {com_script}")

def cleanup():
    print("正在停止子进程...")
    for proc in child_processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in child_processes:
        try:
            proc.wait(timeout=2)
        except:
            proc.kill()
    print("所有子进程已停止")

atexit.register(cleanup)

def update_loop():
    while True:
        processor.update()
        time.sleep(0.1)

@app.route("/")
def index():
    return render_template("perception.html")

@app.route("/api/current")
def api_current():
    return jsonify(processor.get_current())

@app.route("/api/gate", methods=["POST"])
def api_gate():
    enabled = request.json.get("enabled", True)
    processor.gate_enabled = enabled
    return jsonify({"ok": True, "gate_enabled": enabled})

if __name__ == "__main__":
    start_child_processes()
    time.sleep(2)  # 等待子进程启动
    threading.Thread(target=update_loop, daemon=True).start()
    print("\n================================================")
    print("Perception 服务已启动!")
    print("访问: http://127.0.0.1:6002")
    print("================================================")
    app.run(host="127.0.0.1", port=6002, debug=False, use_reloader=False)
