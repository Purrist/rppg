import time
import random
import threading

class BaseGame:
    """游戏基类，方便以后扩展其他游戏"""
    def __init__(self, socketio):
        self.socketio = socketio
        self.playing = False
        self.score = 0
        self.timer = 120
        self.start_time = 0

    def start(self):
        self.playing = True
        self.score = 0
        self.timer = 120
        self.start_time = time.time()

    def stop(self):
        self.playing = False

class WhackAMole(BaseGame):
    """打地鼠游戏逻辑类"""
    def __init__(self, socketio):
        super().__init__(socketio)
        self.current_mole = -1
        self.last_mole_time = 0
        self.stay_duration = 2.5 # 地鼠停留2.5秒

    def update(self):
        """由主循环调用，负责逻辑状态切换"""
        if not self.playing: return

        now = time.time()
        # 更新倒计时
        elapsed = int(now - self.start_time)
        self.timer = max(0, 120 - elapsed)
        if self.timer <= 0: self.stop()

        # 地鼠出现逻辑
        if self.current_mole == -1: # 如果当前没地鼠
            if now - self.last_mole_time > 0.5: # 冷却0.5秒后出新的
                self.current_mole = random.randint(0, 2)
                self.last_mole_time = now
        else: # 如果有地鼠
            if now - self.last_mole_time > self.stay_duration:
                self.current_mole = -1
                self.last_mole_time = now

        # 推送给前端
        self.socketio.emit('game_update', {
            "playing": self.playing,
            "score": self.score,
            "timer": self.timer,
            "current_mole": self.current_mole
        })

    def handle_hit(self, hit_index):
        if not self.playing or self.current_mole == -1: return
        
        if hit_index == self.current_mole:
            self.score += 10
            self.current_mole = -1 # 击中立即消失
            self.last_mole_time = time.time()
        else:
            self.score -= 5