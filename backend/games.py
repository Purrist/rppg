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

    def set_ready(self):
        self.status = "READY"
        self.score = 0
        self.current_mole = -1

    def start_game(self):
        self.status = "PLAYING"
        self.start_time = time.time()
        self.timer = 60
        self.last_mole_time = time.time()

    def stop(self):
        self.status = "SLEEP"

    def handle_hit(self, index):
        if self.status == "PLAYING" and index == self.current_mole:
            self.score += 10
            self.current_mole = -1
            self.last_mole_time = time.time()

    def update(self, health_state=None):
        if self.status == "PLAYING":
            now = time.time()
            self.timer = max(0, int(60 - (now - self.start_time)))
            if self.timer <= 0: self.set_ready()
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