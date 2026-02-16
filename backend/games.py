import time, random

class WhackAMole:
    def __init__(self, socketio):
        self.socketio = socketio
        self.status = "SLEEP"
        self.score = 0
        self.timer = 60
        self.start_time = 0
        self.current_mole = -1
        self.last_mole_time = 0
        self.paused = False
        self.pause_start_time = 0
        self.total_paused_time = 0

    def set_ready(self):
        self.status = "READY"
        self.score = 0
        self.current_mole = -1
        self.total_paused_time = 0

    def start_game(self):
        self.status = "PLAYING"
        self.start_time = time.time()
        self.timer = 60
        self.last_mole_time = time.time()

    def toggle_pause(self):
        if self.status == "PLAYING":
            self.status = "PAUSED"
            self.pause_start_time = time.time()
        elif self.status == "PAUSED":
            self.status = "PLAYING"
            self.total_paused_time += time.time() - self.pause_start_time

    def stop(self):
        self.status = "SLEEP"

    def handle_hit(self, index):
        if self.status == "PLAYING":
            if index == self.current_mole:
                self.score += 10  # 正确：+10分
                self.current_mole = -1
                self.last_mole_time = time.time()
            else:
                self.score -= 5   # 错误：-5分

    def update(self, health_state=None):
        if self.status == "PLAYING":
            now = time.time()
            # 计算有效游戏时间（扣除暂停时间）
            effective_elapsed = now - self.start_time - self.total_paused_time
            self.timer = max(0, int(60 - effective_elapsed))
            
            if self.timer <= 0:
                self.set_ready()
            
            # 地鼠逻辑：停留4秒
            if self.current_mole == -1 and now - self.last_mole_time > 1.0:
                self.current_mole = random.randint(0, 2)
                self.last_mole_time = now
            elif self.current_mole != -1 and now - self.last_mole_time > 4.0:
                self.current_mole = -1
                self.last_mole_time = now
        
        self.socketio.emit('game_update', {
            "status": self.status,
            "score": self.score,
            "timer": self.timer,
            "current_mole": self.current_mole
        })
