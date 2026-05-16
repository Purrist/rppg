# games/game_whack_a_mole.py
# 打地鼠游戏

from .games_base import GameBase, GameConfig
from typing import Dict, Optional
import random
import time


# 打地鼠配置
WHACK_A_MOLE_CONFIG = GameConfig(
    game_id="whack_a_mole",
    game_name="趣味打地鼠",
    description="站在投影区域内，用脚踩地鼠获得分数",
    duration=60,
    interaction_type="foot",
    zones=[
        {"id": 0, "x": 160, "y": 240, "radius": 60},
        {"id": 1, "x": 320, "y": 240, "radius": 60},
        {"id": 2, "x": 480, "y": 240, "radius": 60},
    ],
    difficulty_levels=["easy", "normal", "hard"],
    default_difficulty="normal",
    settling_duration=5.0,
    ui_type="whack_a_mole",
    show_timer=True,
    show_score=True,
)


class WhackAMoleGame(GameBase):
    """打地鼠游戏"""
    
    def __init__(self, socketio, config: GameConfig = None, system_core=None):
        config = config or WHACK_A_MOLE_CONFIG
        super().__init__(socketio, config, system_core)
        
        self.current_mole = -1
        self.mole_appear_time = 0
        self.last_mole_time = 0
        
        self._difficulty_params = {
            "easy": {"mole_stay": 7.0, "mole_interval": 2.0},
            "normal": {"mole_stay": 5.0, "mole_interval": 1.5},
            "hard": {"mole_stay": 3.0, "mole_interval": 1.0},
        }
        
        self.mole_stay = 5.0
        self.mole_interval = 1.5
        
        self.total_hits = 0
        self.success_hits = 0
        self.missed_moles = 0
    
    def _on_ready(self):
        self.current_mole = -1
        self.total_hits = 0
        self.success_hits = 0
        self.missed_moles = 0
        self.state.extra = {"current_mole": -1}
        print("[打地鼠] 进入准备状态")
    
    def _on_start(self):
        self.last_mole_time = time.time()
        self.current_mole = -1
        self.state.extra["current_mole"] = -1
        print("[打地鼠] 游戏开始！")
    
    def _on_update(self, perception_data: Optional[Dict]):
        now = time.time()
        
        if self.current_mole == -1:
            if now - self.last_mole_time >= self.mole_interval:
                self._spawn_mole()
        else:
            if now - self.mole_appear_time >= self.mole_stay:
                self._miss_mole()
    
    def _on_action(self, action: str, data: Dict):
        if action == "hit":
            self._handle_hit(data.get("zone", -1), data.get("success", False))
        elif action == "zone_enter":
            self._handle_zone_enter(data.get("zone", -1))
    
    def _on_stop(self):
        self.current_mole = -1
        self.state.extra["current_mole"] = -1
        print("[打地鼠] 游戏结束")
    
    def _on_settling(self):
        accuracy = (self.success_hits / self.total_hits * 100) if self.total_hits > 0 else 0
        self.state.stats = {
            "total_hits": self.total_hits,
            "success_hits": self.success_hits,
            "missed_moles": self.missed_moles,
            "accuracy": round(accuracy, 1),
        }
        print(f"[打地鼠] 结算: 得分={self.state.score}, 命中率={accuracy:.1f}%")
    
    def _on_difficulty_change(self, difficulty: str):
        params = self._difficulty_params.get(difficulty, self._difficulty_params["normal"])
        self.mole_interval = params["mole_interval"]
        # 根据地鼠停留时间 = 确认时间 + 额外时间
        extra_times = {"easy": 4.0, "normal": 3.0, "hard": 2.0}
        extra_time = extra_times.get(difficulty, 3.0)
        dwell_time_s = getattr(self, '_dwell_time_s', 2.0)
        self.mole_stay = dwell_time_s + extra_time
        print(f"[打地鼠] 难度设置为: {difficulty}, 地鼠停留时间: {self.mole_stay}s")
    
    def update_params(self, params: Dict):
        """更新游戏参数 - 接收统一的确认时间"""
        if 'dwell_time' in params:
            # 打地鼠使用确认时间作为停留判定时间
            self._dwell_time_ms = params['dwell_time']
            self._dwell_time_s = self._dwell_time_ms / 1000
            # 更新地鼠停留时间，使其与确认时间相关
            # 地鼠停留时间 = 确认时间 + 额外时间（根据难度）
            difficulty = self.state.difficulty
            extra_times = {"easy": 4.0, "normal": 3.0, "hard": 2.0}
            extra_time = extra_times.get(difficulty, 3.0)
            self.mole_stay = self._dwell_time_s + extra_time
            print(f"[打地鼠] 更新确认时间: {self._dwell_time_ms}ms, 地鼠停留时间: {self.mole_stay}s")
    
    def get_dwell_time(self) -> int:
        """获取确认时间（毫秒）"""
        return getattr(self, '_dwell_time_ms', 2000)
    
    def _spawn_mole(self):
        """生成地鼠 - 不发送状态，由 update() 统一发送"""
        self.current_mole = random.randint(0, 2)
        self.mole_appear_time = time.time()
        self.state.extra["current_mole"] = self.current_mole
        # ⭐ 不调用 _emit_state()，由 update() 统一发送
    
    def _miss_mole(self):
        """地鼠逃跑 - 不发送状态，由 update() 统一发送"""
        self.state.score = max(0, self.state.score - 5)
        self.missed_moles += 1
        self.current_mole = -1
        self.state.extra["current_mole"] = -1
        self.last_mole_time = time.time()
        # ⭐ 不调用 _emit_state()，由 update() 统一发送
    
    def _handle_hit(self, zone: int, success: bool):
        """处理踩踏 - 立即发送状态（用户交互需要即时反馈）"""
        # 防止重复处理同一个地鼠
        if zone != self.current_mole:
            return
        
        self.total_hits += 1
        if success:
            self.state.score += 10
            self.success_hits += 1
            self.current_mole = -1
            self.state.extra["current_mole"] = -1
            self.last_mole_time = time.time()
            self._emit_state()  # ⭐ 用户交互需要即时反馈
    
    def _handle_zone_enter(self, zone: int):
        if self.current_mole != -1 and zone == self.current_mole:
            self._handle_hit(zone, True)
    
    # 兼容旧接口
    def handle_hit(self, hole_index: int, hit: bool):
        self._handle_hit(hole_index, hit)
    
    @property
    def status(self):
        return self.state.status
    
    @property
    def score(self):
        return self.state.score
    
    @property
    def timer(self):
        return self.state.timer
