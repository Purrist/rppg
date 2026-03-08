# -*- coding: utf-8 -*-
"""
游戏逻辑 - 打地鼠
"""
import time
import random

class WhackAMole:
    """打地鼠游戏"""
    
    def __init__(self, socketio):
        self.socketio = socketio
        
        # 游戏状态
        self.status = "IDLE"
        
        # 游戏数据
        self.score = 0
        self.timer = 60
        self.current_mole = -1
        
        # 时间控制
        self.start_time = 0
        self.last_mole_time = 0
        self.mole_appear_time = 0
        self.paused_time = 0
        self.total_paused = 0
        
        # ⭐ 结算时间
        self.settling_start_time = 0
        self.SETTLING_DURATION = 5.0  # 结算阶段5秒
        
        # 游戏参数
        self.mole_stay = 5.0
        self.mole_interval = 1.5
        
        # 统计
        self.total_hits = 0
        self.success_hits = 0
    
    def set_ready(self):
        """设置准备状态"""
        self.status = "READY"
        self.score = 0
        self.timer = 60
        self.current_mole = -1
        self.total_paused = 0
        self.total_hits = 0
        self.success_hits = 0
        self._emit_state()
        print("[打地鼠] 进入准备状态")
    
    def start_game(self):
        """开始游戏"""
        self.status = "PLAYING"
        self.start_time = time.time()
        self.timer = 60
        self.last_mole_time = time.time()
        self.mole_appear_time = 0
        self.current_mole = -1
        self._emit_state()
        print("[打地鼠] 游戏开始！")
    
    def toggle_pause(self):
        """暂停/继续"""
        if self.status == "PLAYING":
            self.status = "PAUSED"
            self.paused_time = time.time()
            print("[打地鼠] 游戏暂停")
        elif self.status == "PAUSED":
            self.status = "PLAYING"
            self.total_paused += time.time() - self.paused_time
            print("[打地鼠] 游戏继续")
        self._emit_state()
    
    def stop(self):
        """停止游戏"""
        self.status = "IDLE"
        self.current_mole = -1
        self._emit_state()
        print("[打地鼠] 游戏结束")
    
    def start_settling(self):
        """进入结算状态"""
        self.status = "SETTLING"
        self.settling_start_time = time.time()
        self._emit_state()
        print("[打地鼠] 进入结算状态")
    
    def handle_hit(self, hole_index, hit):
        """处理击中判定"""
        if self.status != "PLAYING":
            return
        
        self.total_hits += 1
        
        if hit and hole_index == self.current_mole:
            self.score += 10
            self.success_hits += 1
            self.current_mole = -1
            self.last_mole_time = time.time()
            print(f"[打地鼠] 击中！+10分，总分：{self.score}")
        else:
            self.score = max(0, self.score - 5)
            print(f"[打地鼠] 未击中，-5分，总分：{self.score}")
        
        self._emit_state()
    
    def update(self, health_state=None):
        """更新游戏状态"""
        # ⭐ 结算状态处理
        if self.status == "SETTLING":
            elapsed = time.time() - self.settling_start_time
            if elapsed >= self.SETTLING_DURATION:
                print("[打地鼠] 结算结束，回到准备状态")
                self.set_ready()
            return
        
        if self.status == "PLAYING":
            now = time.time()
            
            elapsed = now - self.start_time - self.total_paused
            self.timer = max(0, int(60 - elapsed))
            
            # 时间结束 -> 进入结算状态
            if self.timer <= 0:
                print(f"[打地鼠] 时间到！最终得分：{self.score}")
                self.start_settling()
                return
            
            # 地鼠逻辑
            if self.current_mole == -1:
                if now - self.last_mole_time > self.mole_interval:
                    self.current_mole = random.randint(0, 2)
                    self.mole_appear_time = now
                    self.last_mole_time = now
                    print(f"[打地鼠] 地鼠出现在洞 {self.current_mole}")
            else:
                if now - self.mole_appear_time > self.mole_stay:
                    self.score = max(0, self.score - 5)
                    self.current_mole = -1
                    self.last_mole_time = now
                    print(f"[打地鼠] 地鼠逃走！-5分，总分：{self.score}")
            
            self._emit_state()
    
    def _emit_state(self):
        """发送游戏状态"""
        accuracy = 0
        if self.total_hits > 0:
            accuracy = int((self.success_hits / self.total_hits) * 100)
        
        self.socketio.emit('game_update', {
            "status": self.status,
            "score": self.score,
            "timer": self.timer,
            "current_mole": self.current_mole,
            "accuracy": accuracy
        })
    
    def get_state(self):
        """获取当前状态"""
        return {
            "status": self.status,
            "score": self.score,
            "timer": self.timer,
            "current_mole": self.current_mole
        }
