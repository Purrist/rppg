# games/__init__.py
# 游戏系统入口

from .games_base import GameBase, GameConfig, GameState, GameStatus
from .games_manager import GameManager
from .game_whack_a_mole import WhackAMoleGame, WHACK_A_MOLE_CONFIG
from .processing_speed_game import ProcessingSpeedGame, ProcessingSpeedConfig

# 游戏配置
PROCESSING_SPEED_CONFIG = ProcessingSpeedConfig()

# 游戏注册表
GAME_REGISTRY = {
    "whack_a_mole": WhackAMoleGame,
    "processing_speed": ProcessingSpeedGame,
}

# 游戏配置表
GAME_CONFIGS = {
    "whack_a_mole": WHACK_A_MOLE_CONFIG,
    "processing_speed": PROCESSING_SPEED_CONFIG,
}

__all__ = [
    "GameBase",
    "GameConfig",
    "GameState",
    "GameStatus",
    "GameManager",
    "WhackAMoleGame",
    "WHACK_A_MOLE_CONFIG",
    "ProcessingSpeedGame",
    "ProcessingSpeedConfig",
    "PROCESSING_SPEED_CONFIG",
    "GAME_REGISTRY",
    "GAME_CONFIGS",
]
