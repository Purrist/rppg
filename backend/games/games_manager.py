# games/games_manager.py
# 游戏管理器

from typing import Dict, Optional, Type
from .games_base import GameBase, GameConfig


class GameManager:
    """游戏管理器 - 通过SystemCore统一广播状态"""
    
    def __init__(self, socketio, system_core=None):
        self.socketio = socketio
        self._system_core = system_core
        self._registry: Dict[str, Type[GameBase]] = {}
        self._current_game: Optional[GameBase] = None
        self._current_game_id: Optional[str] = None
        self._configs: Dict[str, GameConfig] = {}
    
    def register(self, game_id: str, game_class: Type[GameBase], config: GameConfig = None):
        self._registry[game_id] = game_class
        if config:
            self._configs[game_id] = config
        print(f"[GameManager] 注册游戏: {game_id}")
    
    def create_game(self, game_id: str, config: GameConfig = None, game_params: dict = None) -> Optional[GameBase]:
        if game_id not in self._registry:
            print(f"[GameManager] 错误: 游戏 {game_id} 未注册")
            return None
        
        if self._current_game and self._current_game.state.status != "IDLE":
            self._current_game.stop()
        
        game_class = self._registry[game_id]
        game_config = config or self._configs.get(game_id)
        
        # 创建游戏实例
        game = game_class(self.socketio, game_config) if game_config else game_class(self.socketio)
        
        # 如果有额外参数，更新到游戏实例
        if game_params:
            game.update_params(game_params)
        
        self._current_game = game
        self._current_game_id = game_id
        
        # ⭐ 更新SystemCore
        if self._system_core:
            self._system_core.set_current_game(game_id)
        
        print(f"[GameManager] 创建游戏: {game_id}, 参数: {game_params}")
        return game
    
    # 控制接口
    def set_ready(self, game_id: str = None, game_params: dict = None):
        # 如果传入了game_id，必须创建新游戏（或切换到该游戏）
        if game_id:
            if game_id != self._current_game_id:
                self.create_game(game_id, game_params=game_params)
        
        # 确保有当前游戏实例
        if not self._current_game and game_id:
            self.create_game(game_id, game_params=game_params)
        
        # 如果游戏已存在，更新参数
        if self._current_game and game_params:
            self._current_game.update_params(game_params)
            
        if self._current_game:
            self._current_game.set_ready()
            # ⭐ 通过SystemCore广播状态
            self._sync_to_system_core()
    
    def start_game(self):
        print(f"[GameManager] start_game, current_game_id: {self._current_game_id}")
        if self._current_game:
            print(f"[GameManager] 启动游戏: {self._current_game_id}")
            self._current_game.start_game()
            self._sync_to_system_core()
        else:
            print("[GameManager] 错误: 没有当前游戏实例")
    
    def toggle_pause(self):
        if self._current_game:
            self._current_game.toggle_pause()
            self._sync_to_system_core()
    
    def stop_game(self):
        if self._current_game:
            self._current_game.stop()
            self._current_game_id = None
            # ⭐ 更新SystemCore
            if self._system_core:
                self._system_core.set_current_game(None)
                self._system_core.set_game_status('IDLE')
                self._system_core.reset_game_runtime()
    
    # 新增：重新开始（直接进入READY）
    def restart_game(self, game_id: str = None):
        """重新开始游戏 - 直接进入READY状态，不经过IDLE"""
        if game_id and game_id != self._current_game_id:
            self.create_game(game_id)
        if self._current_game:
            # 直接调用 restart，不调用 stop
            self._current_game.restart()
            self._sync_to_system_core()
    
    def handle_action(self, action: str, data: Dict):
        if self._current_game:
            self._current_game.handle_action(action, data)
    
    def update(self, perception_data: Dict = None):
        if self._current_game:
            self._current_game.update(perception_data)
    
    # 状态查询
    def get_game_status(self) -> str:
        return self._current_game.state.status if self._current_game else "IDLE"
    
    def is_game_active(self) -> bool:
        """游戏是否激活 - READY/PLAYING/PAUSED/SETTLING 都算激活"""
        if not self._current_game:
            return False
        status = self._current_game.state.status
        return status in ["READY", "PLAYING", "PAUSED", "SETTLING"]
    
    def get_current_game_id(self) -> Optional[str]:
        return self._current_game_id
    
    def get_current_game(self) -> Optional[GameBase]:
        """获取当前游戏实例"""
        return self._current_game
    
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
    
    def _sync_to_system_core(self):
        """⭐ 同步游戏状态到SystemCore，由SystemCore统一广播"""
        if not self._system_core:
            return
        
        # 更新游戏状态
        status = self.get_game_status()
        self._system_core.set_game_status(status)
        
        # 更新游戏运行时数据
        if self._current_game:
            self._system_core.update_game_runtime({
                'score': self._current_game.state.score,
                'timer': self._current_game.state.timer,
            })
