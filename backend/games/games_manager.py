# games/games_manager.py
# 游戏管理器

from typing import Dict, Optional, Type
from .games_base import GameBase, GameConfig
from .difficulty_adjuster import DifficultyAdjuster


class GameManager:
    """游戏管理器 - 集成动态难度调整"""
    
    def __init__(self, socketio):
        self.socketio = socketio
        self._registry: Dict[str, Type[GameBase]] = {}
        self._current_game: Optional[GameBase] = None
        self._current_game_id: Optional[str] = None
        self._configs: Dict[str, GameConfig] = {}
        
        # ⭐ 难度调整器
        # 参考: Csikszentmihalyi (1990), Shute (2008)
        self.difficulty_adjuster = DifficultyAdjuster(initial_level=5, max_level=8)
        
        # 感知管理器引用（由外部设置）
        self.perception_manager = None
    
    def set_perception_manager(self, perception_manager):
        """设置感知管理器引用"""
        self.perception_manager = perception_manager
    
    def register(self, game_id: str, game_class: Type[GameBase], config: GameConfig = None):
        self._registry[game_id] = game_class
        if config:
            self._configs[game_id] = config
        print(f"[GameManager] 注册游戏: {game_id}")
    
    def create_game(self, game_id: str, config: GameConfig = None) -> Optional[GameBase]:
        if game_id not in self._registry:
            print(f"[GameManager] 错误: 游戏 {game_id} 未注册")
            return None
        
        if self._current_game and self._current_game.state.status != "IDLE":
            self._current_game.stop()
        
        game_class = self._registry[game_id]
        game_config = config or self._configs.get(game_id)
        
        game = game_class(self.socketio, game_config) if game_config else game_class(self.socketio)
        
        self._current_game = game
        self._current_game_id = game_id
        print(f"[GameManager] 创建游戏: {game_id}")
        return game
    
    # 控制接口
    def set_ready(self, game_id: str = None):
        if game_id and game_id != self._current_game_id:
            self.create_game(game_id)
        if self._current_game:
            self._current_game.set_ready()
            self._emit_system_state()
    
    def start_game(self):
        if self._current_game:
            self._current_game.start_game()
            self._emit_system_state()
    
    def toggle_pause(self):
        if self._current_game:
            self._current_game.toggle_pause()
            self._emit_system_state()
    
    def stop_game(self):
        if self._current_game:
            self._current_game.stop()
            self._current_game_id = None
            self._emit_system_state()
    
    # ⭐ 新增：重新开始（直接进入READY）
    def restart_game(self, game_id: str = None):
        """重新开始游戏 - 直接进入READY状态，不经过IDLE"""
        if game_id and game_id != self._current_game_id:
            self.create_game(game_id)
        if self._current_game:
            # ⭐ 直接调用 restart，不调用 stop
            self._current_game.restart()
            # ⭐ 发送 system_state，但此时 is_game_active() 返回 True（因为 READY 算激活）
            self._emit_system_state()
    
    def handle_action(self, action: str, data: Dict):
        if self._current_game:
            self._current_game.handle_action(action, data)
    
    def update(self, perception_data: Dict = None):
        """更新游戏状态，包括难度调整"""
        if self._current_game:
            self._current_game.update(perception_data)
            
            # ⭐ 检查是否需要调整难度
            if self._current_game.state.status == "PLAYING":
                self._check_difficulty_adjustment()
    
    def _check_difficulty_adjustment(self):
        """检查并执行难度调整"""
        if not self.perception_manager:
            return
        
        # 获取用户状态
        user_state = self.perception_manager.get_state()
        
        # 安全检查
        safety = self.perception_manager.safety_check()
        if safety.get("action") == "pause":
            print(f"[GameManager] 安全检查: {safety.get('reason')}")
            self._current_game.toggle_pause()
            self.socketio.emit("safety_alert", safety)
            return
        
        # 检查是否应该调整
        if self.difficulty_adjuster.should_adjust():
            physical = user_state.get("physical_load", {}).get("value", 0)
            cognitive = user_state.get("cognitive_load", {}).get("value", 0)
            engagement = user_state.get("engagement", {}).get("value", 0.5)
            
            # 执行调整
            result = self.difficulty_adjuster.adjust(physical, cognitive, engagement)
            
            if result["adjustment"] != 0:
                print(f"[GameManager] 难度调整: {result['old_level']} -> {result['new_level']}, 原因: {result['reason']}")
                
                # 应用新难度参数
                self._apply_difficulty_params(result["params"])
                
                # 通知前端
                self.socketio.emit("difficulty_changed", {
                    "old_level": result["old_level"],
                    "new_level": result["new_level"],
                    "params": result["params"],
                    "reason": result["reason"],
                })
    
    def _apply_difficulty_params(self, params: Dict):
        """应用难度参数到当前游戏"""
        if not self._current_game:
            return
        
        # 更新游戏配置
        if hasattr(self._current_game, 'config'):
            self._current_game.config.reaction_time = params.get("reaction_time", 1500)
            self._current_game.config.target_count = params.get("targets", 2)
        
        # 更新游戏状态
        if hasattr(self._current_game, 'set_difficulty_params'):
            self._current_game.set_difficulty_params(params)
    
    def get_difficulty_params(self) -> Dict:
        """获取当前难度参数"""
        return self.difficulty_adjuster.get_params()
    
    def get_difficulty_level(self) -> int:
        """获取当前难度等级"""
        return self.difficulty_adjuster.current_level
    
    def set_difficulty_level(self, level: int) -> Dict:
        """手动设置难度等级"""
        result = self.difficulty_adjuster.set_level(level)
        self._apply_difficulty_params(result["params"])
        return result
    
    def get_difficulty_adjuster_state(self) -> Dict:
        """获取难度调整器状态"""
        return self.difficulty_adjuster.get_state()
    
    # 状态查询
    def get_game_status(self) -> str:
        return self._current_game.state.status if self._current_game else "IDLE"
    
    def is_game_active(self) -> bool:
        """游戏是否激活 - READY/PLAYING/PAUSED/SETTLING 都算激活"""
        if not self._current_game:
            return False
        status = self._current_game.state.status
        # ⭐ READY 和 PAUSED 也算激活，这样 restart 不会导致平板返回游戏列表
        return status in ["READY", "PLAYING", "PAUSED", "SETTLING"]
    
    def get_current_game_id(self) -> Optional[str]:
        return self._current_game_id
    
    def get_game_state(self) -> Optional[Dict]:
        return self._current_game.get_state() if self._current_game else None
    
    def get_game_list(self) -> Dict:
        result = {}
        for game_id in self._registry:
            config = self._configs.get(game_id)
            result[game_id] = {
                "game_id": config.game_id if config else game_id,
                "game_name": config.game_name if config else game_id,
                "description": config.description if config else "",
                "duration": config.duration if config else 60,
                "interaction_type": config.interaction_type if config else "foot",
                "ui_type": config.ui_type if config else "default",
            }
        return result
    
    def get_game_config(self, game_id: str = None) -> Optional[Dict]:
        target_id = game_id or self._current_game_id
        if target_id and target_id in self._configs:
            return self._configs[target_id].__dict__
        if self._current_game:
            return self._current_game.get_config()
        return None
    
    def _emit_system_state(self):
        self.socketio.emit("system_state", {
            "state": {
                "mode": "game" if self.is_game_active() else "normal",
                "game": {
                    "active": self.is_game_active(),
                    "name": self._current_game_id,
                    "status": self.get_game_status(),
                    "score": self._current_game.state.score if self._current_game else 0,
                    "timer": self._current_game.state.timer if self._current_game else 0,
                }
            }
        })
