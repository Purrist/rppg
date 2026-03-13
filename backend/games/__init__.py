# games/__init__.py
# 游戏系统入口

from .games_base import GameBase, GameConfig, GameState, GameStatus
from .games_manager import GameManager
from .game_whack_a_mole import WhackAMoleGame, WHACK_A_MOLE_CONFIG

# 游戏注册表
GAME_REGISTRY = {
    "whack_a_mole": WhackAMoleGame,
}

__all__ = [
    "GameBase",
    "GameConfig",
    "GameState",
    "GameStatus",
    "GameManager",
    "WhackAMoleGame",
    "WHACK_A_MOLE_CONFIG",
    "GAME_REGISTRY",
]
