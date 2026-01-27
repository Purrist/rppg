import time
import random

class WhackAMole:
    def __init__(self, socketio):
        self.socketio = socketio
        self.status = "SLEEP"  # SLEEP, READY, PLAYING
        self.score = 0
        self.current_mole = -1
        self.last_mole_time = 0
        self.difficulty = "正常"
        self.stay_duration = 2.0 
        
    def set_ready(self):
        """进入预备状态，显示白圈"""
        self.status = "READY"
        self.score = 0
        self.current_mole = -1

    def start_game(self):
        """正式开始游戏"""
        self.status = "PLAYING"
        self.score = 0
        self.last_mole_time = time.time()

    def stop(self):
        """回到休眠状态"""
        self.status = "SLEEP"
        self.current_mole = -1

    def handle_hit(self, index):
        if self.status == "PLAYING" and index == self.current_mole:
            self.score += 10
            self.current_mole = -1 
            self.last_mole_time = time.time()

    def update(self, health_data=None):
        """动态逻辑与数据评估"""
        if self.status != "PLAYING":
            # 即使不运行，也要持续推送状态
            self._emit_update()
            return

        # 难度调节逻辑
        if health_data:
            bpm = health_data.get("bpm", 0)
            if isinstance(bpm, int) and bpm > 100:
                self.difficulty = "简单"
                self.stay_duration = 3.0
            else:
                self.difficulty = "正常"
                self.stay_duration = 2.0

        now = time.time()
        if self.current_mole == -1:
            if now - self.last_mole_time > 0.5:
                self.current_mole = random.randint(0, 2)
                self.last_mole_time = now
        else:
            if now - self.last_mole_time > self.stay_duration:
                self.current_mole = -1
                self.last_mole_time = now

        self._emit_update()

    def _emit_update(self):
        # 综合计算参与意愿
        engagement = "高" if self.score > 20 else "中"
        self.socketio.emit('game_update', {
            "status": self.status,
            "score": self.score,
            "current_mole": self.current_mole,
            "difficulty": self.difficulty,
            "engagement": engagement,
            "load": "中等"
        })