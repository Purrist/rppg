import time, random

class WhackAMole:
    def __init__(self, socketio):
        self.socketio = socketio
        self.status = "SLEEP"  # SLEEP, READY, PLAYING
        self.score = 0
        self.timer = 60
        self.start_time = 0
        self.current_mole = -1
        self.last_mole_time = 0

    def set_ready(self):
        """进入待机状态：黑底白圈"""
        self.status = "READY"
        self.score = 0
        self.current_mole = -1

    def start_game(self):
        """进入游戏状态：白底地鼠"""
        self.status = "PLAYING"
        self.start_time = time.time()
        self.timer = 60

    def stop(self):
        """退出到休眠状态：全黑"""
        self.status = "SLEEP"

    def handle_hit(self, index):
        if self.status == "PLAYING" and index == self.current_mole:
            self.score += 10
            self.current_mole = -1 

    def update(self, health_state=None):
        if self.status == "PLAYING":
            now = time.time()
            self.timer = max(0, int(60 - (now - self.start_time)))
            
            if self.timer <= 0:
                self.set_ready() # 游戏结束回到待机
                
            if self.current_mole == -1 and now - self.last_mole_time > 0.8:
                self.current_mole = random.randint(0, 2)
                self.last_mole_time = now
            elif self.current_mole != -1 and now - self.last_mole_time > 2.0:
                self.current_mole = -1
                self.last_mole_time = now
        
        # 持续推送状态
        self.socketio.emit('game_update', {
            "status": self.status,
            "score": self.score,
            "timer": self.timer,
            "current_mole": self.current_mole,
            "difficulty": "正常"
        })