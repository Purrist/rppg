# games/games_base.py
# 游戏基类 - 所有游戏必须继承此类

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
import time


class GameStatus(Enum):
    """游戏状态枚举"""
    IDLE = "IDLE"
    READY = "READY"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    SETTLING = "SETTLING"


@dataclass
class GameConfig:
    """游戏配置"""
    game_id: str
    game_name: str
    description: str = ""
    duration: int = 60
    interaction_type: str = "foot"
    zones: List[Dict] = field(default_factory=list)
    difficulty_levels: List[str] = field(default_factory=lambda: ["easy", "normal", "hard"])
    default_difficulty: str = "normal"
    settling_duration: float = 5.0
    ui_type: str = "default"
    show_timer: bool = True
    show_score: bool = True


@dataclass
class GameState:
    """游戏状态"""
    status: str = "IDLE"
    score: int = 0
    timer: int = 60
    difficulty: str = "normal"
    extra: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "status": self.status,
            "score": self.score,
            "timer": self.timer,
            "difficulty": self.difficulty,
            "extra": self.extra,
            "stats": self.stats,
        }


class GameBase(ABC):
    """游戏基类 - 所有游戏必须继承"""
    
    def __init__(self, socketio, config: GameConfig):
        self.socketio = socketio
        self.config = config
        self.state = GameState(status="IDLE", timer=config.duration)
        
        self._start_time = 0
        self._paused_time = 0
        self._total_paused = 0
        self._settling_start_time = 0
        
        # ⭐ 状态更新节流（每秒最多10次）
        self._last_emit_time = 0
        self._emit_interval = 0.1  # 100ms = 10fps
    
    # 生命周期
    def set_ready(self):
        self.state.status = "READY"
        self.state.score = 0
        self.state.timer = self.config.duration
        self._total_paused = 0
        self._on_ready()
        self._emit_state()
    
    def start_game(self):
        self.state.status = "PLAYING"
        self._start_time = time.time()
        self.state.timer = self.config.duration
        self._on_start()
        self._emit_state()
    
    def toggle_pause(self):
        if self.state.status == "PLAYING":
            self.state.status = "PAUSED"
            self._paused_time = time.time()
            self._on_pause()
        elif self.state.status == "PAUSED":
            self.state.status = "PLAYING"
            self._total_paused += time.time() - self._paused_time
            self._on_resume()
        self._emit_state()
    
    def stop(self):
        self.state.status = "IDLE"
        self._on_stop()
        self._emit_state()
    
    def start_settling(self):
        self.state.status = "SETTLING"
        self._settling_start_time = time.time()
        self._on_settling()
        self._emit_state()
    
    # ⭐ 重置到准备状态（不经过IDLE）
    def restart(self):
        """重新开始 - 直接进入READY状态"""
        self.state.status = "READY"
        self.state.score = 0
        self.state.timer = self.config.duration
        self._total_paused = 0
        self._start_time = 0
        self._paused_time = 0
        self._on_ready()
        self._emit_state()
    
    # 更新
    def update(self, perception_data: Optional[Dict] = None):
        if self.state.status == "SETTLING":
            elapsed = time.time() - self._settling_start_time
            if elapsed >= self.config.settling_duration:
                self.set_ready()
            else:
                # ⭐ 结算期间降低发送频率（每秒2次）
                now = time.time()
                if now - self._last_emit_time >= 0.5:
                    self._emit_state()
            return
        
        if self.state.status == "PLAYING":
            elapsed = time.time() - self._start_time - self._total_paused
            self.state.timer = max(0, int(self.config.duration - elapsed))
            
            if self.state.timer <= 0:
                self.start_settling()
                return
            
            self._on_update(perception_data)
            
            # ⭐ 节流：限制状态更新频率（每秒10次）
            now = time.time()
            if now - self._last_emit_time >= self._emit_interval:
                self._emit_state()
    
    # 交互
    def handle_action(self, action: str, data: Dict):
        if self.state.status != "PLAYING":
            return
        self._on_action(action, data)
    
    # 抽象方法
    @abstractmethod
    def _on_ready(self): pass
    
    @abstractmethod
    def _on_start(self): pass
    
    @abstractmethod
    def _on_update(self, perception_data: Optional[Dict]): pass
    
    @abstractmethod
    def _on_action(self, action: str, data: Dict): pass
    
    # 可选方法
    def _on_pause(self): pass
    def _on_resume(self): pass
    def _on_stop(self): pass
    def _on_settling(self): pass
    
    # 工具
    def _emit_state(self):
        """发送游戏状态（带节流）"""
        self._last_emit_time = time.time()
        self.socketio.emit("game_update", {
            "game_id": self.config.game_id,
            **self.state.to_dict()
        })
    
    def get_config(self) -> Dict:
        return {
            "game_id": self.config.game_id,
            "game_name": self.config.game_name,
            "description": self.config.description,
            "duration": self.config.duration,
            "interaction_type": self.config.interaction_type,
            "zones": self.config.zones,
            "ui_type": self.config.ui_type,
            "show_timer": self.config.show_timer,
            "show_score": self.config.show_score,
        }
    
    def get_state(self) -> Dict:
        return self.state.to_dict()
    
    def set_difficulty(self, difficulty: str):
        if difficulty in self.config.difficulty_levels:
            self.state.difficulty = difficulty
            self._on_difficulty_change(difficulty)
    
    def _on_difficulty_change(self, difficulty: str):
        pass
    
    def update_params(self, params: Dict):
        """更新游戏参数（由GameManager调用）"""
        # 子类可以重写此方法接收动态参数
        pass
