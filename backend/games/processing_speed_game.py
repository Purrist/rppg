# games/processing_speed_game.py
# 处理速度训练游戏 - 基于用户定义重新设计
#
# 核心概念：
# - 确认时间（dwell_time）：进度圈0-100%的时间，在setting.vue设置，范围1.5-4s
# - 作答时间（answer_time）：题目显示到消失的时间，必须 >= 确认时间 + 1s
# - 作答间隔（interval）：两题之间的休息时间
# - 干扰项：No-Go就是干扰项

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from .games_base import GameBase, GameConfig


class TrainingModule(Enum):
    """训练模块"""
    GO_NO_GO = "go_no_go"
    CHOICE_REACTION = "choice_reaction"


@dataclass
class ProcessingSpeedConfig(GameConfig):
    """处理速度训练配置"""
    game_id: str = "processing_speed"
    game_name: str = "处理速度训练"
    description: str = "提高反应速度和认知灵活性"
    duration: int = 180  # 总游戏时长3分钟
    interaction_type: str = "foot"
    ui_type: str = "processing_speed"

    # 确认时间（从设置读取，默认2秒，范围1.5-4s）
    dwell_time: int = 2000  # 毫秒

    # 作答间隔（两题之间的休息时间）
    interval_time: int = 2000  # 毫秒（增加到2秒，让用户有感知）

    # 颜色配置
    colors: Dict[str, str] = field(default_factory=lambda: {
        "go": "#33B555",      # 绿色 - 正确/Go
        "no_go": "#FF4444",   # 红色 - 错误/No-Go/干扰
        "blue": "#2196F3",
        "yellow": "#FFD111",
        "purple": "#9C27B0",
        "orange": "#FF7222",
        "default": "#D9D9D9", # 灰色 - 未激活
    })


class ProcessingSpeedGame(GameBase):
    """
    处理速度训练游戏

    基于用户定义的核心概念：
    1. 每道题有多个选项（8个圈/识别区域）
    2. 玩家站在圈中，进度圈0-100%表示确认
    3. 确认时间固定（setting.vue设置），不参与难度调整
    4. 作答时间（题目显示时长）是动态难度的主要方式
    5. No-Go是干扰项

    游戏流程：
    1. 作答间隔（interval）- 无题状态
    2. 呈现题目（answer_time）- 显示刺激，等待回答
    3. 玩家确认（dwell_time）- 站在圈中等待进度满
    4. 反馈（feedback_time）- 显示正确/错误
    5. 回到步骤1
    """

    # 难度参数表
    # 作答时间 = 确认时间 + 额外时间（动态难度调整）
    DIFFICULTY_LEVELS = {
        1: {"extra_time": 3.0, "go_ratio": 0.90, "zones": 1},  # 最简单
        2: {"extra_time": 2.5, "go_ratio": 0.85, "zones": 2},
        3: {"extra_time": 2.0, "go_ratio": 0.80, "zones": 2},
        4: {"extra_time": 1.5, "go_ratio": 0.70, "zones": 3},
        5: {"extra_time": 1.0, "go_ratio": 0.60, "zones": 3},
        6: {"extra_time": 0.8, "go_ratio": 0.55, "zones": 4},
        7: {"extra_time": 0.5, "go_ratio": 0.50, "zones": 4},
        8: {"extra_time": 0.3, "go_ratio": 0.45, "zones": 4},  # 最难
    }

    def __init__(self, socketio, config: ProcessingSpeedConfig = None):
        super().__init__(socketio, config or ProcessingSpeedConfig())

        # 难度等级（1-8级）
        self.difficulty_level = 3

        # 当前模块
        self.current_module = TrainingModule.GO_NO_GO

        # 游戏状态
        self.trial_id = 0
        self.current_question = None  # 当前题目
        self.question_start_time = 0  # 题目开始时间
        self.question_answered = False  # 题目是否已回答

        # 作答间隔状态
        self.in_interval = True  # 是否在作答间隔期
        self.interval_start_time = 0

        # 统计
        self.stats = {
            "correct": 0,
            "total": 0,
            "go_correct": 0,
            "go_total": 0,
            "no_go_correct": 0,
            "no_go_total": 0,
        }

        # 最近表现（用于动态难度）
        self.recent_trials = []

        # 确认时间（从配置读取）
        self.dwell_time_ms = self.config.dwell_time
        self.dwell_time_s = self.dwell_time_ms / 1000

    def get_difficulty_params(self) -> Dict:
        """获取当前难度参数"""
        level = max(1, min(8, self.difficulty_level))
        return self.DIFFICULTY_LEVELS[level]

    def get_answer_time(self) -> float:
        """
        计算作答时间
        作答时间 = 确认时间 + 额外时间（根据难度）
        必须 >= 确认时间 + 1s
        """
        params = self.get_difficulty_params()
        extra_time = params["extra_time"]
        answer_time = self.dwell_time_s + extra_time
        # 确保至少比确认时间多1秒
        min_answer_time = self.dwell_time_s + 1.0
        return max(answer_time, min_answer_time)

    # ==================== 实现抽象方法 ====================
    def _on_ready(self):
        """准备状态回调"""
        self.difficulty_level = 3
        self.current_module = TrainingModule.GO_NO_GO
        self.trial_id = 0
        self.current_question = None
        self.question_answered = False
        self.in_interval = True
        self.stats = {
            "correct": 0, "total": 0,
            "go_correct": 0, "go_total": 0,
            "no_go_correct": 0, "no_go_total": 0,
        }
        self.recent_trials = []
        # ⭐ 只有在没有通过 update_params 设置时才读取配置
        if not getattr(self, '_dwell_time_custom', False):
            self.dwell_time_ms = self.config.dwell_time
            self.dwell_time_s = self.dwell_time_ms / 1000
            print(f"[ProcessingSpeedGame] 使用配置确认时间: {self.dwell_time_ms}ms")
        else:
            print(f"[ProcessingSpeedGame] 保持自定义确认时间: {self.dwell_time_ms}ms")

    def _on_start(self):
        """开始游戏回调"""
        self._start_interval()

    def _on_update(self, perception_data: Optional[Dict]):
        """更新回调 - 每50ms调用一次"""
        current_time = time.time()

        if self.in_interval:
            # 作答间隔期 - 检查是否结束
            elapsed = current_time - self.interval_start_time
            interval_s = self.config.interval_time / 1000

            if elapsed >= interval_s:
                # 间隔结束，开始新题目
                self._start_question()
        else:
            # 作答期 - 检查是否超时
            if not self.question_answered and self.current_question:
                elapsed = current_time - self.question_start_time
                answer_time = self.get_answer_time()

                if elapsed >= answer_time:
                    # 作答时间到，题目超时
                    self._handle_timeout()

        # ⭐ 持续发送状态更新（确保前端实时同步 remaining_time）
        self._emit_state()

    def _on_action(self, action: str, data: Dict):
        """动作回调 - 玩家完成停留确认"""
        if action == "zone_dwell_completed":
            zone_id = data.get("zone_id")
            self._handle_answer(zone_id)

    def _on_pause(self):
        pass

    def _on_resume(self):
        pass

    def _on_stop(self):
        self.current_question = None
        self.in_interval = True

    def update_params(self, params: Dict):
        """更新游戏参数"""
        if 'dwell_time' in params:
            self.dwell_time_ms = params['dwell_time']
            self.dwell_time_s = self.dwell_time_ms / 1000
            self._dwell_time_custom = True  # 标记为已自定义
            print(f"[ProcessingSpeedGame] 更新确认时间: {self.dwell_time_ms}ms ({self.dwell_time_s}s)")

    def _on_settling(self):
        """结算回调"""
        self.state.stats = {
            "total_trials": self.stats["total"],
            "total_correct": self.stats["correct"],
            "accuracy": self.stats["correct"] / max(1, self.stats["total"]),
            "go_accuracy": self.stats["go_correct"] / max(1, self.stats["go_total"]),
            "no_go_accuracy": self.stats["no_go_correct"] / max(1, self.stats["no_go_total"]),
        }

    # ==================== 游戏流程控制 ====================
    def _start_interval(self):
        """开始作答间隔"""
        self.in_interval = True
        self.interval_start_time = time.time()
        self.current_question = None
        self.question_answered = False

        # 发送间隔状态（无题目）
        self._emit_state()

    def _start_question(self):
        """开始新题目"""
        self.in_interval = False
        self.trial_id += 1
        self.question_answered = False
        self.question_start_time = time.time()

        # 生成题目
        if self.current_module == TrainingModule.GO_NO_GO:
            self._generate_go_no_go_question()
        else:
            self._generate_choice_reaction_question()

        # 发送题目
        self._emit_question()

    def _generate_go_no_go_question(self):
        """生成Go/No-Go题目"""
        params = self.get_difficulty_params()

        # 根据Go比例决定是Go还是No-Go
        is_go = random.random() < params["go_ratio"]

        # 选择激活的区域数
        num_zones = params["zones"]
        active_zones = random.sample(range(1, 9), num_zones)

        # 选择目标区域（如果是Go）
        target_zone = random.choice(active_zones) if is_go else None

        # 构建区域状态
        zones = {}
        for z in range(1, 9):
            if z in active_zones:
                if is_go and z == target_zone:
                    # Go目标 - 绿色
                    zones[z] = {"active": True, "color": self.config.colors["go"], "is_target": True}
                elif not is_go and z == random.choice(active_zones):
                    # No-Go干扰项 - 红色（只有一个红色）
                    zones[z] = {"active": True, "color": self.config.colors["no_go"], "is_target": False}
                    target_zone = z  # 记录这个干扰项位置
                else:
                    # 其他激活区域 - 灰色
                    zones[z] = {"active": True, "color": self.config.colors["default"], "is_target": False}
            else:
                # 未激活区域
                zones[z] = {"active": False, "color": self.config.colors["default"], "is_target": False}

        self.current_question = {
            "trial_id": self.trial_id,
            "module": "go_no_go",
            "is_go": is_go,
            "target_zone": target_zone,  # Go时需要踩，No-Go时不能踩
            "zones": zones,
            "instruction": "踩绿色！" if is_go else "不要踩红色！",
            "answer_time": self.get_answer_time(),
            "dwell_time": self.dwell_time_s,
        }

    def _generate_choice_reaction_question(self):
        """生成选择反应题目"""
        params = self.get_difficulty_params()

        # 颜色列表
        colors = ["blue", "yellow", "purple", "orange"]
        num_colors = min(params["zones"], len(colors))

        # 选择激活的区域数和颜色
        num_zones = params["zones"]
        active_zones = random.sample(range(1, 9), num_zones)
        zone_colors = random.sample(colors[:num_colors], num_zones)

        # 随机选择一个作为目标
        target_idx = random.randint(0, num_zones - 1)
        target_zone = active_zones[target_idx]
        target_color = zone_colors[target_idx]

        # 构建区域状态
        zones = {}
        for z in range(1, 9):
            if z in active_zones:
                idx = active_zones.index(z)
                color = zone_colors[idx]
                zones[z] = {
                    "active": True,
                    "color": self.config.colors[color],
                    "is_target": (z == target_zone)
                }
            else:
                zones[z] = {"active": False, "color": self.config.colors["default"], "is_target": False}

        color_names = {"blue": "蓝色", "yellow": "黄色", "purple": "紫色", "orange": "橙色"}

        self.current_question = {
            "trial_id": self.trial_id,
            "module": "choice_reaction",
            "target_zone": target_zone,
            "target_color": target_color,
            "zones": zones,
            "instruction": f"踩{color_names[target_color]}！",
            "answer_time": self.get_answer_time(),
            "dwell_time": self.dwell_time_s,
        }

    def _handle_answer(self, zone_id: int):
        """处理玩家答案"""
        if not self.current_question or self.question_answered:
            return

        # 检查是否在作答时间内
        elapsed = time.time() - self.question_start_time
        answer_time = self.get_answer_time()

        if elapsed >= answer_time:
            # 已经超时，忽略这个答案
            return

        self.question_answered = True

        # 判断对错
        correct = self._evaluate_answer(zone_id)

        # 更新统计
        self.stats["total"] += 1
        if correct:
            self.stats["correct"] += 1

        # Go/No-Go统计
        if self.current_question["module"] == "go_no_go":
            is_go = self.current_question["is_go"]
            if is_go:
                self.stats["go_total"] += 1
                if correct:
                    self.stats["go_correct"] += 1
            else:
                self.stats["no_go_total"] += 1
                if correct:
                    self.stats["no_go_correct"] += 1

        # 计分
        if correct:
            # 基础分100，根据难度和速度加分
            base_score = 100
            difficulty_bonus = self.difficulty_level * 10
            speed_bonus = int((answer_time - elapsed) * 10)  # 剩余时间奖励
            self.state.score += base_score + difficulty_bonus + max(0, speed_bonus)
        else:
            # 错误扣分
            self.state.score = max(0, self.state.score - 50)

        # 记录最近表现
        self.recent_trials.append({"correct": correct})
        if len(self.recent_trials) > 5:
            self.recent_trials.pop(0)

        # 发送反馈
        self._emit_feedback(correct, zone_id)

        # 动态难度调整
        if len(self.recent_trials) >= 5:
            self._adjust_difficulty()

        # 开始间隔
        self._start_interval()

    def _handle_timeout(self):
        """处理超时（作答时间到但玩家未回答）"""
        if not self.current_question or self.question_answered:
            return

        self.question_answered = True

        # 更新统计
        self.stats["total"] += 1

        # Go/No-Go统计
        if self.current_question["module"] == "go_no_go":
            if self.current_question["is_go"]:
                # Go试次超时 = 错误
                self.stats["go_total"] += 1
            else:
                # No-Go试次超时 = 正确（忍住了）
                self.stats["no_go_total"] += 1
                self.stats["no_go_correct"] += 1
                self.stats["correct"] += 1
                # No-Go正确加分
                self.state.score += 150
                self._emit_feedback(correct=True, zone_id=None, is_timeout=True)
                self._start_interval()
                return

        # 扣分
        self.state.score = max(0, self.state.score - 30)

        # 记录
        self.recent_trials.append({"correct": False})
        if len(self.recent_trials) > 5:
            self.recent_trials.pop(0)

        # 发送超时反馈
        self._emit_feedback(correct=False, zone_id=None, is_timeout=True)

        # 动态难度调整
        if len(self.recent_trials) >= 5:
            self._adjust_difficulty()

        # 开始间隔
        self._start_interval()

    def _evaluate_answer(self, zone_id: int) -> bool:
        """评估答案是否正确"""
        if not self.current_question:
            return False

        target_zone = self.current_question.get("target_zone")

        if self.current_question["module"] == "go_no_go":
            is_go = self.current_question["is_go"]
            if is_go:
                # Go试次：必须踩目标区域
                return zone_id == target_zone
            else:
                # No-Go试次：不能踩任何区域（但玩家已经踩了，所以是错误）
                return False
        else:
            # 选择反应：踩目标区域
            return zone_id == target_zone

    def _adjust_difficulty(self):
        """动态难度调整"""
        if len(self.recent_trials) < 5:
            return

        correct_count = sum(1 for t in self.recent_trials if t["correct"])
        accuracy = correct_count / len(self.recent_trials)

        # 调整规则
        if accuracy < 0.5:
            # 正确率过低，降低难度
            self.difficulty_level = max(1, self.difficulty_level - 1)
        elif accuracy > 0.85:
            # 正确率过高，提高难度
            self.difficulty_level = min(8, self.difficulty_level + 1)

    # ==================== 状态发送 ====================
    def _emit_state(self):
        """发送当前状态"""
        data = {
            "status": self.state.status,
            "score": self.state.score,
            "timer": self.state.timer,
            "game_id": "processing_speed",
            "module": self.current_module.value,
            "difficulty_level": self.difficulty_level,
            "dwell_time": self.dwell_time_s,  # 确认时间
        }

        if self.in_interval:
            # 间隔期 - 不显示题目
            data["in_interval"] = True
            data["question"] = None
        elif self.current_question:
            # 作答期 - 显示题目
            data["in_interval"] = False
            data["question"] = self.current_question
            # 计算剩余作答时间
            elapsed = time.time() - self.question_start_time
            answer_time = self.get_answer_time()
            data["remaining_time"] = max(0, answer_time - elapsed)
            data["progress"] = min(100, (elapsed / answer_time) * 100)  # 0-100，用于进度条

        self.socketio.emit("game_update", data)

    def _emit_question(self):
        """发送题目"""
        self._emit_state()

    def _emit_feedback(self, correct: bool, zone_id: Optional[int], is_timeout: bool = False):
        """发送反馈"""
        message = "正确！"
        if is_timeout:
            message = "时间到！"
        elif not correct:
            message = "错误！"

        # 如果是No-Go正确（忍住了）
        if (self.current_question and
            self.current_question["module"] == "go_no_go" and
            not self.current_question["is_go"] and
            correct):
            message = "很好，忍住了！"

        # ⭐ 发送反馈时也要包含完整的游戏状态，包括 game_id
        self.socketio.emit("game_update", {
            "status": self.state.status,
            "score": self.state.score,
            "timer": self.state.timer,
            "game_id": "processing_speed",
            "module": self.current_module.value,
            "difficulty_level": self.difficulty_level,
            "dwell_time": self.dwell_time_s,
            "in_interval": self.in_interval,
            "question": self.current_question if not self.in_interval else None,
            "feedback": {
                "correct": correct,
                "zone_id": zone_id,
                "is_timeout": is_timeout,
                "message": message,
                "timestamp": int(time.time() * 1000),  # ⭐ 添加时间戳用于去重
            }
        })

    def get_state(self) -> Dict:
        """获取游戏状态"""
        state = super().get_state()
        state.update({
            "game_id": "processing_speed",
            "module": self.current_module.value,
            "difficulty_level": self.difficulty_level,
            "dwell_time": self.dwell_time_s,
        })
        return state
