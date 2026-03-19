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


class TrialType(Enum):
    """试次类型"""
    GO = "go"
    NO_GO = "no_go"
    CHOICE = "choice"
    SERIAL = "serial"


@dataclass
class Trial:
    """试次数据"""
    trial_id: int
    trial_type: TrialType
    stimulus: Dict[str, Any]  # 刺激信息
    correct_response: Any  # 正确反应
    response: Optional[Any] = None  # 用户反应
    reaction_time: Optional[float] = None  # 反应时间
    correct: Optional[bool] = None  # 是否正确
    timestamp: float = 0


@dataclass
class ProcessingSpeedConfig(GameConfig):
    """处理速度训练配置"""
    game_id: str = "processing_speed"
    game_name: str = "处理速度训练"
    description: str = "提高反应速度和认知灵活性"
    duration: int = 300  # 5分钟
    interaction_type: str = "foot"
    ui_type: str = "processing_speed"
    
    # 训练模块
    modules: List[str] = field(default_factory=lambda: ["go_no_go", "choice_reaction", "serial_reaction"])
    module_duration: int = 60  # 每个模块60秒
    
    # 区域配置
    zones: List[Dict] = field(default_factory=lambda: [
        {"id": 1, "x": 54, "y": 150, "width": 420, "height": 420},
        {"id": 2, "x": 518, "y": 150, "width": 420, "height": 420},
        {"id": 3, "x": 982, "y": 150, "width": 420, "height": 420},
        {"id": 4, "x": 1446, "y": 150, "width": 420, "height": 420},
        {"id": 5, "x": 54, "y": 597, "width": 420, "height": 419},
        {"id": 6, "x": 518, "y": 597, "width": 420, "height": 419},
        {"id": 7, "x": 982, "y": 597, "width": 420, "height": 419},
        {"id": 8, "x": 1446, "y": 597, "width": 420, "height": 419},
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
    
    # 停留时间
    dwell_time: int = 3000  # 3秒
    
    # 难度参数
    difficulty_params: Dict = field(default_factory=dict)


class ProcessingSpeedGame(GameBase):
    """
    处理速度认知训练游戏
    
    训练模块：
    1. Go/No-Go：反应控制训练
    2. 选择反应：决策速度训练
    3. 序列反应：序列学习训练
    
    参考文献：
    - Ball et al. (2002) ACTIVE研究
    - Nissen & Bullemer (1987) SRTT
    - Nielson et al. (2002) Go/No-Go
    """
    
    def __init__(self, socketio, config: ProcessingSpeedConfig = None):
        super().__init__(socketio, config or ProcessingSpeedConfig())
        
        # 当前训练模块
        self.current_module = TrainingModule.GO_NO_GO
        self.module_index = 0
        
        # 试次数据
        self.trials: List[Trial] = []
        self.current_trial: Optional[Trial] = None
        self.trial_id = 0
        
        # 模块统计
        self.module_stats = {
            "go_no_go": {"correct": 0, "total": 0, "go_rt": [], "no_go_correct": 0, "no_go_total": 0},
            "choice_reaction": {"correct": 0, "total": 0, "rt_list": []},
            "serial_reaction": {"correct": 0, "total": 0, "sequences": []},
        }
        
        # 当前刺激
        self.current_stimulus = None
        self.stimulus_start_time = 0
        
        # 序列反应
        self.current_sequence = []
        self.sequence_index = 0
        
        # 难度参数
        self.difficulty_params = self._get_difficulty_params()
        
        # 模块计时
        self.module_start_time = 0
        self.module_duration = self.config.module_duration
    
    def _get_difficulty_params(self) -> Dict:
        """获取当前难度的参数"""
        # 基于当前难度等级设置参数
        level = self.state.difficulty
        
        params = {
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
        
        return params
    
    def set_difficulty_params(self, params: Dict):
        """设置难度参数（由难度调整器调用）"""
        self.difficulty_params.update(params)
    
    # ==================== 实现抽象方法 ====================
    def _on_ready(self):
        """准备状态回调"""
        self.module_index = 0
        self.current_module = TrainingModule.GO_NO_GO
        self.trials = []
        self.current_trial = None
        self.trial_id = 0
        self.current_stimulus = None
        self.module_stats = {
            "go_no_go": {"correct": 0, "total": 0, "go_rt": [], "no_go_correct": 0, "no_go_total": 0},
            "choice_reaction": {"correct": 0, "total": 0, "rt_list": []},
            "serial_reaction": {"correct": 0, "total": 0, "sequences": []},
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
            params = self.difficulty_params.get(self.current_module.value, {})
            display_time = params.get("display_time", 5000) / 1000
            
            if time.time() - self.stimulus_start_time > display_time:
                self._handle_timeout()
    
    def _on_action(self, action: str, data: Dict):
        """动作回调"""
        if action == "zone_entered":
            self._handle_zone_entered(data.get("zone_id"))
        elif action == "zone_exited":
            self._handle_zone_exited(data.get("zone_id"))
        elif action == "zone_dwell_completed":
            self._handle_dwell_completed(data.get("zone_id"), data.get("dwell_time"))
    
    def _on_pause(self):
        """暂停回调"""
        pass
    
    def _on_resume(self):
        """恢复回调"""
        pass
    
    def _on_stop(self):
        """停止回调"""
        self.current_stimulus = None
        self.current_trial = None
    
    def _on_settling(self):
        """结算回调"""
        pass
    
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
        params = self.difficulty_params["go_no_go"]
        
        # 决定是Go还是No-Go
        is_go = random.random() < params["go_ratio"]
        
        # 选择区域
        num_zones = params["zones"]
        available_zones = list(range(1, num_zones + 1))
        target_zone = random.choice(available_zones)
        
        trial_type = TrialType.GO if is_go else TrialType.NO_GO
        
        self.current_trial = Trial(
            trial_id=self.trial_id,
            trial_type=trial_type,
            stimulus={
                "type": "go" if is_go else "no_go",
                "color": self.config.colors["go"] if is_go else self.config.colors["no_go"],
                "zone": target_zone,
                "zones": available_zones,
            },
            correct_response=target_zone if is_go else None,
            timestamp=time.time()
        )
        
        self.current_stimulus = {
            "module": "go_no_go",
            "trial_type": trial_type.value,
            "zones": {
                z: {"active": True, "color": self.current_trial.stimulus["color"] if z == target_zone else self.config.colors["default"]}
                for z in available_zones
            },
            "target_zone": target_zone if is_go else None,
            "is_go": is_go,
        }
    
    def _generate_choice_reaction_trial(self):
        """生成选择反应试次"""
        params = self.difficulty_params["choice_reaction"]
        
        # 选择刺激数量和颜色
        num_stimuli = params["stimuli"]
        num_colors = params["colors"]
        
        # 可用颜色
        color_names = ["blue", "yellow", "purple", "orange"][:num_colors]
        colors = {name: self.config.colors[name] for name in color_names}
        
        # 选择区域
        zones = random.sample(range(1, 9), num_stimuli)
        
        # 为每个区域分配颜色
        zone_colors = {}
        target_color = random.choice(color_names)
        target_zone = None
        
        for zone in zones:
            color = random.choice(color_names)
            zone_colors[zone] = {"color": colors[color], "color_name": color}
            if color == target_color and target_zone is None:
                target_zone = zone
        
        # 确保至少有一个目标
        if target_zone is None:
            target_zone = zones[0]
            zone_colors[target_zone] = {"color": colors[target_color], "color_name": target_color}
        
        self.current_trial = Trial(
            trial_id=self.trial_id,
            trial_type=TrialType.CHOICE,
            stimulus={
                "type": "choice",
                "zones": zones,
                "zone_colors": zone_colors,
                "target_color": target_color,
            },
            correct_response=target_zone,
            timestamp=time.time()
        )
        
        self.current_stimulus = {
            "module": "choice_reaction",
            "trial_type": "choice",
            "zones": {
                z: {"active": True, "color": zone_colors[z]["color"]}
                for z in zones
            },
            "target_color": target_color,
            "target_zone": target_zone,
            "instruction": f"踩{self._color_name_cn(target_color)}",
        }
    
    def _generate_serial_reaction_trial(self):
        """生成序列反应试次"""
        params = self.difficulty_params["serial_reaction"]
        
        # 如果是新序列，生成序列
        if self.sequence_index == 0 or self.sequence_index >= len(self.current_sequence):
            sequence_length = params["sequence_length"]
            self.current_sequence = random.sample(range(1, 9), min(sequence_length, 8))
            self.sequence_index = 0
        
        # 当前目标
        target_zone = self.current_sequence[self.sequence_index]
        
        self.current_trial = Trial(
            trial_id=self.trial_id,
            trial_type=TrialType.SERIAL,
            stimulus={
                "type": "serial",
                "sequence": self.current_sequence,
                "current_index": self.sequence_index,
                "target_zone": target_zone,
            },
            correct_response=target_zone,
            timestamp=time.time()
        )
        
        self.current_stimulus = {
            "module": "serial_reaction",
            "trial_type": "serial",
            "zones": {
                z: {"active": True, "color": self.config.colors["go"] if z == target_zone else self.config.colors["default"]}
                for z in range(1, 9)
            },
            "target_zone": target_zone,
            "sequence_progress": f"{self.sequence_index + 1}/{len(self.current_sequence)}",
        }
    
    def _handle_zone_entered(self, zone_id: int):
        """处理进入区域"""
        pass
    
    def _handle_zone_exited(self, zone_id: int):
        """处理离开区域"""
        pass
    
    def _handle_dwell_completed(self, zone_id: int, dwell_time: float):
        """处理停留完成"""
        if not self.current_trial:
            return
        
        # 记录反应
        self.current_trial.response = zone_id
        self.current_trial.reaction_time = (time.time() - self.stimulus_start_time) * 1000  # 毫秒
        
        # 判断正确性
        if self.current_module == TrainingModule.GO_NO_GO:
            self._evaluate_go_no_go(zone_id)
        elif self.current_module == TrainingModule.CHOICE_REACTION:
            self._evaluate_choice_reaction(zone_id)
        elif self.current_module == TrainingModule.SERIAL_REACTION:
            self._evaluate_serial_reaction(zone_id)
        
        # 记录试次
        self.trials.append(self.current_trial)
        
        # 发送反馈
        self._emit_feedback()
        
        # 开始下一个试次
        self._start_next_trial()
    
    def _handle_timeout(self):
        """处理超时"""
        if not self.current_trial:
            return
        
        self.current_trial.response = None
        self.current_trial.correct = False
        self.current_trial.reaction_time = (time.time() - self.stimulus_start_time) * 1000
        
        self.trials.append(self.current_trial)
        
        # 更新统计
        stats = self.module_stats[self.current_module.value]
        stats["total"] += 1
        
        # 发送超时反馈
        self.socketio.emit("game_update", {
            "status": self.state.status,
            "feedback": {"type": "timeout", "message": "超时"},
            "score": self.state.score,
        })
        
        # 开始下一个试次
        self._start_next_trial()
    
    def _evaluate_go_no_go(self, zone_id: int):
        """评估Go/No-Go反应"""
        stats = self.module_stats["go_no_go"]
        stats["total"] += 1
        
        if self.current_trial.trial_type == TrialType.GO:
            # Go试次：应该踩
            if zone_id == self.current_trial.correct_response:
                self.current_trial.correct = True
                stats["correct"] += 1
                stats["go_rt"].append(self.current_trial.reaction_time)
                self.state.score += int(100 * (1 + (5000 - self.current_trial.reaction_time) / 5000))
            else:
                self.current_trial.correct = False
        else:
            # No-Go试次：不应该踩
            stats["no_go_total"] += 1
            self.current_trial.correct = False  # 踩了就是错误
            # 如果没踩（超时），会在_handle_timeout处理
    
    def _evaluate_choice_reaction(self, zone_id: int):
        """评估选择反应"""
        stats = self.module_stats["choice_reaction"]
        stats["total"] += 1
        
        if zone_id == self.current_trial.correct_response:
            self.current_trial.correct = True
            stats["correct"] += 1
            stats["rt_list"].append(self.current_trial.reaction_time)
            self.state.score += int(100 * (1 + (5000 - self.current_trial.reaction_time) / 5000))
        else:
            self.current_trial.correct = False
    
    def _evaluate_serial_reaction(self, zone_id: int):
        """评估序列反应"""
        stats = self.module_stats["serial_reaction"]
        stats["total"] += 1
        
        if zone_id == self.current_trial.correct_response:
            self.current_trial.correct = True
            stats["correct"] += 1
            self.sequence_index += 1
            
            # 序列完成奖励
            if self.sequence_index >= len(self.current_sequence):
                self.state.score += 500
                stats["sequences"].append(self.current_sequence.copy())
                self.sequence_index = 0
            
            self.state.score += 50
        else:
            self.current_trial.correct = False
            # 序列错误，重新开始
            self.sequence_index = 0
    
    def _next_module(self):
        """切换到下一个模块"""
        self.module_index += 1
        
        if self.module_index >= len(self.config.modules):
            # 所有模块完成，结束游戏
            self._finish_game()
        else:
            # 切换模块
            module_name = self.config.modules[self.module_index]
            self.current_module = TrainingModule(module_name)
            self.module_start_time = time.time()
            
            # 发送模块切换通知
            self.socketio.emit("game_update", {
                "status": self.state.status,
                "module_changed": True,
                "current_module": self.current_module.value,
                "module_name": self._module_name_cn(self.current_module),
            })
    
    def _finish_game(self):
        """结束游戏"""
        self.state.status = "SETTLING"
        
        # 计算最终统计
        summary = self._calculate_summary()
        
        self.socketio.emit("game_update", {
            "status": "SETTLING",
            "score": self.state.score,
            "summary": summary,
        })
    
    def _calculate_summary(self) -> Dict:
        """计算训练总结"""
        summary = {}
        
        # Go/No-Go统计
        go_no_go = self.module_stats["go_no_go"]
        if go_no_go["total"] > 0:
            summary["go_no_go"] = {
                "accuracy": go_no_go["correct"] / go_no_go["total"],
                "avg_go_rt": sum(go_no_go["go_rt"]) / len(go_no_go["go_rt"]) if go_no_go["go_rt"] else 0,
                "no_go_accuracy": go_no_go["no_go_correct"] / go_no_go["no_go_total"] if go_no_go["no_go_total"] > 0 else 0,
            }
        
        # 选择反应统计
        choice = self.module_stats["choice_reaction"]
        if choice["total"] > 0:
            summary["choice_reaction"] = {
                "accuracy": choice["correct"] / choice["total"],
                "avg_rt": sum(choice["rt_list"]) / len(choice["rt_list"]) if choice["rt_list"] else 0,
            }
        
        # 序列反应统计
        serial = self.module_stats["serial_reaction"]
        if serial["total"] > 0:
            summary["serial_reaction"] = {
                "accuracy": serial["correct"] / serial["total"],
                "sequences_completed": len(serial["sequences"]),
            }
        
        return summary
    
    def _emit_stimulus(self):
        """发送刺激"""
        self.socketio.emit("game_update", {
            "status": self.state.status,
            "stimulus": self.current_stimulus,
            "trial_id": self.trial_id,
            "module": self.current_module.value,
            "score": self.state.score,
            "timer": int(self.module_duration - (time.time() - self.module_start_time)),
        })
    
    def _emit_feedback(self):
        """发送反馈"""
        feedback = {
            "correct": self.current_trial.correct,
            "reaction_time": self.current_trial.reaction_time,
            "score": self.state.score,
        }
        
        if self.current_trial.correct:
            feedback["message"] = "正确！"
            feedback["type"] = "correct"
        else:
            feedback["message"] = "错误"
            feedback["type"] = "error"
        
        self.socketio.emit("game_update", {
            "status": self.state.status,
            "feedback": feedback,
            "score": self.state.score,
        })
    
    def _emit_game_state(self):
        """发送游戏状态"""
        self.socketio.emit("game_update", {
            "status": self.state.status,
            "score": self.state.score,
            "timer": self.state.timer,
            "module": self.current_module.value,
            "module_name": self._module_name_cn(self.current_module),
            "difficulty": self.state.difficulty,
        })
    
    def _module_name_cn(self, module: TrainingModule) -> str:
        """获取模块中文名"""
        names = {
            TrainingModule.GO_NO_GO: "反应控制",
            TrainingModule.CHOICE_REACTION: "选择反应",
            TrainingModule.SERIAL_REACTION: "序列学习",
        }
        return names.get(module, module.value)
    
    def _color_name_cn(self, color: str) -> str:
        """获取颜色中文名"""
        names = {
            "blue": "蓝色",
            "yellow": "黄色",
            "purple": "紫色",
            "orange": "橙色",
            "green": "绿色",
            "red": "红色",
        }
        return names.get(color, color)
    
    def get_state(self) -> Dict:
        """获取游戏状态"""
        state = super().get_state()
        state.update({
            "module": self.current_module.value,
            "module_name": self._module_name_cn(self.current_module),
            "trial_id": self.trial_id,
            "difficulty_params": self.difficulty_params,
        })
        return state
