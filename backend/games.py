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
        self.mole_appear_time = 0  # 地鼠出现时间
        self.paused_time = 0
        self.total_paused = 0
        
        # 游戏参数（调整后）
        self.mole_stay = 5.0       # 地鼠停留时间 4秒
        self.mole_interval = 1.5   # 地鼠出现间隔 1.5秒
        
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
    
    def handle_hit(self, hole_index, hit):
        """处理击中判定"""
        if self.status != "PLAYING":
            return
        
        self.total_hits += 1
        
        if hit and hole_index == self.current_mole:
            # 击中地鼠
            self.score += 10
            self.success_hits += 1
            self.current_mole = -1
            self.last_mole_time = time.time()  # 立即开始计时下一只
            print(f"[打地鼠] 击中！+10分，总分：{self.score}")
        else:
            # 击中错误
            self.score = max(0, self.score - 5)
            print(f"[打地鼠] 未击中，-5分，总分：{self.score}")
        
        self._emit_state()
    
    def update(self, health_state=None):
        """更新游戏状态"""
        if self.status == "PLAYING":
            now = time.time()
            
            # 计算有效时间
            elapsed = now - self.start_time - self.total_paused
            self.timer = max(0, int(60 - elapsed))
            
            # 时间结束
            if self.timer <= 0:
                print(f"[打地鼠] 时间到！最终得分：{self.score}")
                self.status = "READY"
                self.current_mole = -1
                self._emit_state()
                return
            
            # 地鼠逻辑
            if self.current_mole == -1:
                # 没有地鼠，等待后出现
                if now - self.last_mole_time > self.mole_interval:
                    self.current_mole = random.randint(0, 2)
                    self.mole_appear_time = now
                    self.last_mole_time = now
                    print(f"[打地鼠] 地鼠出现在洞 {self.current_mole}")
            else:
                # 有地鼠，检查是否超时
                if now - self.mole_appear_time > self.mole_stay:
                    self.current_mole = -1
                    self.last_mole_time = now
                    print("[打地鼠] 地鼠消失（超时）")
            
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
