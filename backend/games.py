import time, random

class WhackAMole:
    def __init__(self, socketio):
        self.socketio = socketio
        self.status = "SLEEP" # SLEEP, READY, PLAYING, PAUSED
        self.score = 0
        self.timer = 60
        self.start_time = 0
        self.pause_start = 0
        self.current_mole = -1
        self.last_mole_time = 0
        self.difficulty = "正常"

    def set_ready(self): self.status = "READY"
    
    def start_game(self):
        self.status = "PLAYING"
        self.score = 0
        self.timer = 60
        self.start_time = time.time()

    def toggle_pause(self):
        if self.status == "PLAYING":
            self.status = "PAUSED"
            self.pause_start = time.time()
        elif self.status == "PAUSED":
            self.status = "PLAYING"
            # 补偿暂停消耗的时间
            self.start_time += (time.time() - self.pause_start)

    def stop(self): self.status = "SLEEP"

    def handle_hit(self, index):
        if self.status == "PLAYING" and index == self.current_mole:
            self.score += 10
            self.current_mole = -1 

    def update(self, health_state):
        if self.status != "PLAYING":
            self.socketio.emit('game_update', self._get_state())
            return

        now = time.time()
        self.timer = max(0, int(60 - (now - self.start_time)))
        if self.timer <= 0: self.status = "READY"

        # 地鼠出现逻辑
        if self.current_mole == -1 and now - self.last_mole_time > 0.8:
            self.current_mole = random.randint(0, 2)
            self.last_mole_time = now
        elif self.current_mole != -1 and now - self.last_mole_time > 2.0:
            self.current_mole = -1
            self.last_mole_time = now

        self.socketio.emit('game_update', self._get_state())

    def _get_state(self):
        return {
            "status": self.status, "score": self.score, 
            "timer": self.timer, "current_mole": self.current_mole,
            "difficulty": self.difficulty, "engagement": "高", "load": "正常"
        }