# games/processing_speed_game.py
# 处理速度认知训练游戏
# 基于文献：Ball et al. (2002), Nissen & Bullemer (1987), Nielson et al. (2002)

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from .games_base import GameBase, GameState, GameConfig


class TrainingModule(Enum):
    """训练模块"""
    GO_NO_GO = "go_no_go"
    CHOICE_REACTION = "choice_reaction"
    SERIAL_REACTION = "serial_reaction"


@dataclass
class ProcessingSpeedConfig(GameConfig):
    """处理速度训练配置"""
    game_id: str = "processing_speed"
    game_name: str = "处理速度训练"
    description: str = "提高反应速度和认知灵活性"
    duration: int = 180  # 3分钟
    interaction_type: str = "foot"
    ui_type: str = "processing_speed"
    
    # 训练模块
    modules: List[str] = field(default_factory=lambda: ["go_no_go", "choice_reaction", "serial_reaction"])
    module_duration: int = 60  # 每个模块60秒
    
    # 区域配置（8个圆形区域）
    zones: List[Dict] = field(default_factory=lambda: [
        {"id": 1, "x": 159, "y": 255},   # 区域1中心
        {"id": 2, "x": 623, "y": 255},   # 区域2中心
        {"id": 3, "x": 1087, "y": 255},  # 区域3中心
        {"id": 4, "x": 1551, "y": 255},  # 区域4中心
        {"id": 5, "x": 159, "y": 702},   # 区域5中心
        {"id": 6, "x": 623, "y": 702},   # 区域6中心
        {"id": 7, "x": 1087, "y": 702},  # 区域7中心
        {"id": 8, "x": 1551, "y": 702},  # 区域8中心
    ])
    
    # 颜色配置
    colors: Dict[str, str] = field(default_factory=lambda: {
        "go": "#33B555",      # 绿色
        "no_go": "#FF4444",   # 红色
        "blue": "#2196F3",
        "yellow": "#FFD111",
        "purple": "#9C27B0",
        "orange": "#FF7222",
        "default": "#D9D9D9",
    })


class ProcessingSpeedGame(GameBase):
    """
    处理速度认知训练游戏
    
    训练模块：
    1. Go/No-Go：反应控制训练
    2. 选择反应：决策速度训练
    3. 序列反应：序列学习训练
    """
    
    def __init__(self, socketio, config: ProcessingSpeedConfig = None):
        super().__init__(socketio, config or ProcessingSpeedConfig())
        
        # 当前训练模块
        self.current_module = TrainingModule.GO_NO_GO
        self.module_index = 0
        
        # 试次数据
        self.trial_id = 0
        self.current_stimulus = None
        self.stimulus_start_time = 0
        
        # 序列反应
        self.current_sequence = []
        self.sequence_index = 0
        
        # 模块计时
        self.module_start_time = 0
        self.module_duration = self.config.module_duration
        
        # 难度等级（1-10）
        self.difficulty_level = 5
        
        # 模块统计
        self.module_stats = {
            "go_no_go": {"correct": 0, "total": 0, "go_rt": []},
            "choice_reaction": {"correct": 0, "total": 0, "rt_list": []},
            "serial_reaction": {"correct": 0, "total": 0, "sequences_completed": 0},
        }
    
    def _get_difficulty_params(self) -> Dict:
        """获取当前难度的参数"""
        level = self.difficulty_level
        
        return {
            "go_no_go": {
                "go_ratio": max(0.4, 0.9 - level * 0.05),
                "display_time": max(3000, 8000 - level * 500),
                "dwell_time": max(1500, 3000 - level * 150),
                "zones": min(4, 1 + level // 2),
            },
            "choice_reaction": {
                "stimuli": min(8, 2 + level // 2),
                "colors": min(5, 2 + level // 3),
                "display_time": max(3000, 8000 - level * 500),
                "dwell_time": max(1500, 3000 - level * 150),
            },
            "serial_reaction": {
                "sequence_length": min(8, 3 + level // 2),
                "display_time": max(2000, 6000 - level * 400),
                "dwell_time": max(1500, 3000 - level * 150),
            }
        }
    
    # ==================== 实现抽象方法 ====================
    def _on_ready(self):
        """准备状态回调"""
        self.module_index = 0
        self.current_module = TrainingModule.GO_NO_GO
        self.trial_id = 0
        self.current_stimulus = None
        self.current_sequence = []
        self.sequence_index = 0
        self.module_stats = {
            "go_no_go": {"correct": 0, "total": 0, "go_rt": []},
            "choice_reaction": {"correct": 0, "total": 0, "rt_list": []},
            "serial_reaction": {"correct": 0, "total": 0, "sequences_completed": 0},
        }
    
    def _on_start(self):
        """开始游戏回调"""
        self.module_start_time = time.time()
        self._start_next_trial()
    
    def _on_update(self, perception_data: Optional[Dict]):
        """更新回调"""
        # 检查模块时间
        elapsed = time.time() - self.module_start_time
        if elapsed >= self.module_duration:
            self._next_module()
            return
        
        # 检查刺激超时
        if self.current_stimulus:
            params = self._get_difficulty_params().get(self.current_module.value, {})
            display_time = params.get("display_time", 5000) / 1000
            
            if time.time() - self.stimulus_start_time > display_time:
                self._handle_timeout()
    
    def _on_action(self, action: str, data: Dict):
        """动作回调"""
        if action == "zone_dwell_completed":
            self._handle_dwell_completed(data.get("zone_id"), data.get("dwell_time"))
    
    def _on_pause(self):
        pass
    
    def _on_resume(self):
        pass
    
    def _on_stop(self):
        self.current_stimulus = None
    
    def _on_settling(self):
        """结算回调 - 计算统计数据"""
        self.state.stats = {
            "modules": self.module_stats,
            "total_trials": sum(m["total"] for m in self.module_stats.values()),
            "total_correct": sum(m["correct"] for m in self.module_stats.values()),
        }
    
    # ==================== 游戏逻辑 ====================
    def _start_next_trial(self):
        """开始下一个试次"""
        self.trial_id += 1
        self.current_stimulus = None
        
        # 根据当前模块生成刺激
        if self.current_module == TrainingModule.GO_NO_GO:
            self._generate_go_no_go_trial()
        elif self.current_module == TrainingModule.CHOICE_REACTION:
            self._generate_choice_reaction_trial()
        elif self.current_module == TrainingModule.SERIAL_REACTION:
            self._generate_serial_reaction_trial()
        
        self.stimulus_start_time = time.time()
        self._emit_stimulus()
    
    def _generate_go_no_go_trial(self):
        """生成Go/No-Go试次"""
        params = self._get_difficulty_params()["go_no_go"]
        
        is_go = random.random() < params["go_ratio"]
        num_zones = params["zones"]
        target_zone = random.randint(1, num_zones)
        
        self.current_stimulus = {
            "module": "go_no_go",
            "is_go": is_go,
            "target_zone": target_zone if is_go else None,
            "zones": {
                z: {
                    "active": z <= num_zones,
                    "color": self.config.colors["go"] if is_go and z == target_zone 
                             else self.config.colors["no_go"] if not is_go and z == target_zone
                             else self.config.colors["default"]
                }
                for z in range(1, 9)
            }
        }
    
    def _generate_choice_reaction_trial(self):
        """生成选择反应试次"""
        params = self._get_difficulty_params()["choice_reaction"]
        
        num_stimuli = params["stimuli"]
        color_names = ["blue", "yellow", "purple", "orange"]
        target_color = random.choice(color_names[:params["colors"]])
        
        zones = random.sample(range(1, 9), num_stimuli)
        zone_colors = {}
        target_zone = None
        
        for zone in zones:
            color = random.choice(color_names[:params["colors"]])
            zone_colors[zone] = color
            if color == target_color and target_zone is None:
                target_zone = zone
        
        if target_zone is None:
            target_zone = zones[0]
            zone_colors[target_zone] = target_color
        
        self.current_stimulus = {
            "module": "choice_reaction",
            "target_color": target_color,
            "target_zone": target_zone,
            "instruction": f"踩{self._color_name_cn(target_color)}",
            "zones": {
                z: {
                    "active": z in zones,
                    "color": self.config.colors.get(zone_colors.get(z, "default"), self.config.colors["default"])
                }
                for z in range(1, 9)
            }
        }
    
    def _generate_serial_reaction_trial(self):
        """生成序列反应试次"""
        params = self._get_difficulty_params()["serial_reaction"]
        
        if self.sequence_index == 0 or self.sequence_index >= len(self.current_sequence):
            self.current_sequence = random.sample(range(1, 9), params["sequence_length"])
            self.sequence_index = 0
        
        target_zone = self.current_sequence[self.sequence_index]
        
        self.current_stimulus = {
            "module": "serial_reaction",
            "target_zone": target_zone,
            "sequence_progress": f"{self.sequence_index + 1}/{len(self.current_sequence)}",
            "zones": {
                z: {
                    "active": True,
                    "color": self.config.colors["go"] if z == target_zone else self.config.colors["default"]
                }
                for z in range(1, 9)
            }
        }
    
    def _handle_dwell_completed(self, zone_id: int, dwell_time: float):
        """处理停留完成"""
        if not self.current_stimulus:
            return
        
        rt = (time.time() - self.stimulus_start_time) * 1000
        correct = False
        
        if self.current_module == TrainingModule.GO_NO_GO:
            correct = self._evaluate_go_no_go(zone_id, rt)
        elif self.current_module == TrainingModule.CHOICE_REACTION:
            correct = self._evaluate_choice_reaction(zone_id, rt)
        elif self.current_module == TrainingModule.SERIAL_REACTION:
            correct = self._evaluate_serial_reaction(zone_id)
        
        # 发送反馈
        self._emit_feedback(correct, rt)
        
        # 开始下一个试次
        self._start_next_trial()
    
    def _handle_timeout(self):
        """处理超时"""
        stats = self.module_stats[self.current_module.value]
        stats["total"] += 1
        
        self._emit_feedback(False, 0, timeout=True)
        self._start_next_trial()
    
    def _evaluate_go_no_go(self, zone_id: int, rt: float) -> bool:
        """评估Go/No-Go反应"""
        stats = self.module_stats["go_no_go"]
        stats["total"] += 1
        
        is_go = self.current_stimulus["is_go"]
        target_zone = self.current_stimulus["target_zone"]
        
        if is_go:
            if zone_id == target_zone:
                stats["correct"] += 1
                stats["go_rt"].append(rt)
                self.state.score += int(100 * (1 + (5000 - rt) / 5000))
                return True
        # No-Go时不应该踩，踩了就是错误
        return False
    
    def _evaluate_choice_reaction(self, zone_id: int, rt: float) -> bool:
        """评估选择反应"""
        stats = self.module_stats["choice_reaction"]
        stats["total"] += 1
        
        if zone_id == self.current_stimulus["target_zone"]:
            stats["correct"] += 1
            stats["rt_list"].append(rt)
            self.state.score += int(100 * (1 + (5000 - rt) / 5000))
            return True
        return False
    
    def _evaluate_serial_reaction(self, zone_id: int) -> bool:
        """评估序列反应"""
        stats = self.module_stats["serial_reaction"]
        stats["total"] += 1
        
        if zone_id == self.current_stimulus["target_zone"]:
            stats["correct"] += 1
            self.sequence_index += 1
            self.state.score += 50
            
            if self.sequence_index >= len(self.current_sequence):
                stats["sequences_completed"] += 1
                self.state.score += 500
                self.sequence_index = 0
            
            return True
        else:
            self.sequence_index = 0
            return False
    
    def _next_module(self):
        """切换到下一个模块"""
        self.module_index += 1
        
        if self.module_index >= len(self.config.modules):
            # 所有模块完成
            self.start_settling()
        else:
            module_name = self.config.modules[self.module_index]
            self.current_module = TrainingModule(module_name)
            self.module_start_time = time.time()
            self._start_next_trial()
    
    def _emit_stimulus(self):
        """发送刺激"""
        self.socketio.emit("game_update", {
            "status": self.state.status,
            "score": self.state.score,
            "timer": self.state.timer,
            "module": self.current_module.value,
            "trial_id": self.trial_id,
            "stimulus": self.current_stimulus,
        })
    
    def _emit_feedback(self, correct: bool, rt: float, timeout: bool = False):
        """发送反馈"""
        self.socketio.emit("game_update", {
            "status": self.state.status,
            "score": self.state.score,
            "feedback": {
                "correct": correct,
                "rt": rt,
                "timeout": timeout,
                "message": "正确！" if correct else ("超时" if timeout else "错误")
            }
        })
    
    def _color_name_cn(self, color: str) -> str:
        """获取颜色中文名"""
        names = {"blue": "蓝色", "yellow": "黄色", "purple": "紫色", "orange": "橙色"}
        return names.get(color, color)
    
    def set_difficulty_level(self, level: int):
        """设置难度等级"""
        self.difficulty_level = max(1, min(10, level))
