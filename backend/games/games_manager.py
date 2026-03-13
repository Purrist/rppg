# games/games_manager.py
# 游戏管理器

from typing import Dict, Optional, Type
from .games_base import GameBase, GameConfig


class GameManager:
    """游戏管理器"""
    
    def __init__(self, socketio):
        self.socketio = socketio
        self._registry: Dict[str, Type[GameBase]] = {}
        self._current_game: Optional[GameBase] = None
        self._current_game_id: Optional[str] = None
        self._configs: Dict[str, GameConfig] = {}
    
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
        return self._current_game.state.status not in ["IDLE"] if self._current_game else False
    
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
