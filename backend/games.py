import time
import random

class WhackAMole:
    def __init__(self, socketio):
        self.socketio = socketio
        self.status = "SLEEP"  # SLEEP(纯黑), READY(白圈), PLAYING(进行中)
        self.score = 0
        self.start_time = 0
        self.current_mole = -1
        self.last_mole_time = 0
        self.difficulty = "正常"
        self.stay_duration = 2.0 
        
    def start_ready(self):
        """进入预备状态，显示白圈"""
        self.status = "READY"
        self.score = 0

    def start_game(self):
        """正式开始游戏"""
        self.status = "PLAYING"
        self.start_time = time.time()
        self.score = 0

    def stop(self):
        self.status = "SLEEP"
        self.current_mole = -1

    def handle_hit(self, index):
        if self.status == "PLAYING" and index == self.current_mole:
            self.score += 10
            self.current_mole = -1 # 击中立刻消失
            self.last_mole_time = time.time()

    def update(self, health_data=None):
        """根据生理状态感知的反馈，动态调整难度"""
        if self.status != "PLAYING":
            return

        # 动态难度逻辑 (简单示例：基于心率或情绪调节停留时间)
        if health_data:
            bpm = health_data.get("bpm", 0)
            # 这里的计算逻辑应避开敏感词，视为“负荷调节”
            if isinstance(bpm, int) and bpm > 100:
                self.difficulty = "简单"
                self.stay_duration = 3.0
            else:
                self.difficulty = "正常"
                self.stay_duration = 2.0

        now = time.time()
        # 地鼠出现逻辑
        if self.current_mole == -1:
            if now - self.last_mole_time > 0.5:
                self.current_mole = random.randint(0, 2)
                self.last_mole_time = now
        else:
            if now - self.last_mole_time > self.stay_duration:
                self.current_mole = -1
                self.last_mole_time = now

        # 计算参与意愿 (综合评估)
        engagement = "高" if self.score > 20 else "中"
        
        self.socketio.emit('game_update', {
            "status": self.status,
            "score": self.score,
            "current_mole": self.current_mole,
            "difficulty": self.difficulty,
            "engagement": engagement,
            "load": "正常" # 运动负荷
        })