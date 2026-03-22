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


class GoNoGoType(Enum):
    """Go/No-Go 四种指令类型"""
    STEP_ON_GREEN = "step_on_green"      # 踩绿色
    STEP_ON_RED = "step_on_red"          # 踩红色
    DONT_STEP_ON_GREEN = "dont_step_on_green"  # 别踩绿色
    DONT_STEP_ON_RED = "dont_step_on_red"      # 别踩红色


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

    # 颜色配置 - 基于认知训练文献设计
    # Go/No-Go只使用红绿两种颜色（符合文献要求）
    # 选择反应使用高对比度颜色，确保老人能区分
    colors: Dict[str, str] = field(default_factory=lambda: {
        "green": "#33B555",      # 绿色 - Go/目标
        "red": "#FF4444",        # 红色 - No-Go/干扰
        "blue": "#1976D2",       # 深蓝色（高对比度）
        "yellow": "#FFC107",     # 金黄色（高对比度）
        "purple": "#7B1FA2",     # 深紫色（高对比度）
        "orange": "#E65100",     # 深橙色（高对比度）
        "cyan": "#00838F",       # 深青色（高对比度）
        "pink": "#C2185B",       # 深粉色（高对比度）
        "default": "#555555",    # 深灰色 - 未激活
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
    # zones: 激活的区域数量（根据UI参考：圈半径70px，左右间距15px，上下间距8px）
    DIFFICULTY_LEVELS = {
        1: {"extra_time": 3.0, "zones": 2},  # 最简单：2个区域
        2: {"extra_time": 2.5, "zones": 3},
        3: {"extra_time": 2.0, "zones": 4},
        4: {"extra_time": 1.5, "zones": 5},
        5: {"extra_time": 1.0, "zones": 6},
        6: {"extra_time": 0.8, "zones": 6},
        7: {"extra_time": 0.5, "zones": 7},
        8: {"extra_time": 0.3, "zones": 8},  # 最难：8个区域
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
        
        # ⭐ 自动切换模块计数器
        self.module_switch_counter = 0
        self.questions_per_module = 10  # 每10题切换一次模块

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
        
        # ⭐ 支持切换游戏模块
        if 'module' in params:
            module_name = params['module']
            if module_name == 'choice_reaction':
                self.current_module = TrainingModule.CHOICE_REACTION
                print(f"[ProcessingSpeedGame] 切换到选择反应模块")
            elif module_name == 'go_no_go':
                self.current_module = TrainingModule.GO_NO_GO
                print(f"[ProcessingSpeedGame] 切换到Go/No-Go模块")
            else:
                print(f"[ProcessingSpeedGame] 未知模块: {module_name}")

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
        
        # ⭐ 自动切换模块
        self.module_switch_counter += 1
        if self.module_switch_counter >= self.questions_per_module:
            self.module_switch_counter = 0
            if self.current_module == TrainingModule.GO_NO_GO:
                self.current_module = TrainingModule.CHOICE_REACTION
                print(f"[ProcessingSpeedGame] 自动切换到选择反应模块")
            else:
                self.current_module = TrainingModule.GO_NO_GO
                print(f"[ProcessingSpeedGame] 自动切换到Go/No-Go模块")
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
        """生成Go/No-Go题目 - 四种指令类型"""
        params = self.get_difficulty_params()

        # 随机选择四种指令类型之一
        go_no_go_type = random.choice(list(GoNoGoType))

        # 选择激活的区域数
        num_zones = params["zones"]
        active_zones = random.sample(range(1, 9), num_zones)

        # Go/No-Go只有红绿两个颜色
        # 根据指令类型设置目标颜色
        if go_no_go_type == GoNoGoType.STEP_ON_GREEN:
            # 踩绿色：必须踩绿色，踩红色扣分
            target_color = "green"
            other_color = "red"
            instruction = "踩绿色！"
            correct_action = "step_on_target"
        elif go_no_go_type == GoNoGoType.STEP_ON_RED:
            # 踩红色：必须踩红色，踩绿色扣分
            target_color = "red"
            other_color = "green"
            instruction = "踩红色！"
            correct_action = "step_on_target"
        elif go_no_go_type == GoNoGoType.DONT_STEP_ON_GREEN:
            # 别踩绿色：只有绿色区域，没有红色
            target_color = "green"
            other_color = None  # 没有其他颜色
            instruction = "别踩绿色！"
            correct_action = "avoid_target"
        else:  # DONT_STEP_ON_RED
            # 别踩红色：只有红色区域，没有绿色
            target_color = "red"
            other_color = None  # 没有其他颜色
            instruction = "别踩红色！"
            correct_action = "avoid_target"

        # 确保至少有一个目标颜色区域
        target_zone = random.choice(active_zones)
        other_zones = [z for z in active_zones if z != target_zone]

        # 构建区域状态
        zones = {}
        for z in range(1, 9):
            if z == target_zone:
                # 目标颜色区域（要避开或要踩的）
                zones[z] = {
                    "active": True,
                    "color": self.config.colors[target_color],
                    "color_name": target_color,
                    "is_target": True
                }
            elif z in other_zones:
                # 其他激活区域
                if other_color:
                    # "踩X"类型：分配另一个颜色
                    zones[z] = {
                        "active": True,
                        "color": self.config.colors[other_color],
                        "color_name": other_color,
                        "is_target": False
                    }
                else:
                    # "别踩X"类型：其他区域也用目标颜色（全是目标颜色）
                    zones[z] = {
                        "active": True,
                        "color": self.config.colors[target_color],
                        "color_name": target_color,
                        "is_target": True
                    }
            else:
                # 未激活区域
                zones[z] = {
                    "active": False,
                    "color": self.config.colors["default"],
                    "color_name": "default",
                    "is_target": False
                }

        self.current_question = {
            "trial_id": self.trial_id,
            "module": "go_no_go",
            "go_no_go_type": go_no_go_type.value,
            "target_color": target_color,
            "target_zone": target_zone,
            "correct_action": correct_action,
            "zones": zones,
            "instruction": instruction,
            "answer_time": self.get_answer_time(),
            "dwell_time": self.dwell_time_s,
        }

    def _generate_choice_reaction_question(self):
        """生成选择反应题目 - 基于认知训练文献设计"""
        params = self.get_difficulty_params()

        # 颜色列表 - 8种颜色，根据难度选择使用数量
        # 基于Hick's Law：选择数量影响反应时间
        all_colors = ["red", "green", "blue", "yellow", "purple", "orange", "cyan", "pink"]
        
        # 根据难度决定使用多少种颜色
        # 难度1-2：2-3种颜色
        # 难度3-5：4-5种颜色
        # 难度6-8：6-8种颜色
        if self.difficulty_level <= 2:
            num_colors = min(3, len(all_colors))
        elif self.difficulty_level <= 5:
            num_colors = min(5, len(all_colors))
        else:
            num_colors = min(8, len(all_colors))
        
        colors = all_colors[:num_colors]

        # 选择激活的区域数
        num_zones = params["zones"]
        active_zones = random.sample(range(1, 9), num_zones)

        # 随机选择目标颜色
        target_color = random.choice(colors)

        # 为每个激活区域分配颜色
        # 确保至少有一个目标颜色区域
        target_zone = random.choice(active_zones)

        other_zones = [z for z in active_zones if z != target_zone]
        other_colors = [c for c in colors if c != target_color]
        random.shuffle(other_colors)

        # 构建区域状态
        zones = {}
        for z in range(1, 9):
            if z == target_zone:
                # 目标颜色区域
                zones[z] = {
                    "active": True,
                    "color": self.config.colors[target_color],
                    "color_name": target_color,
                    "is_target": True
                }
            elif z in other_zones:
                # 其他激活区域 - 分配其他颜色
                color_idx = other_zones.index(z) % len(other_colors)
                color_name = other_colors[color_idx]
                zones[z] = {
                    "active": True,
                    "color": self.config.colors[color_name],
                    "color_name": color_name,
                    "is_target": False
                }
            else:
                # 未激活区域
                zones[z] = {
                    "active": False,
                    "color": self.config.colors["default"],
                    "color_name": "default",
                    "is_target": False
                }

        color_names = {
            "red": "红色", "green": "绿色", "blue": "蓝色", "yellow": "黄色",
            "purple": "紫色", "orange": "橙色", "cyan": "青色", "pink": "粉色"
        }

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
            # ⭐ 修复：使用 correct_action 判断是 Go 还是 No-Go
            correct_action = self.current_question.get("correct_action", "step_on_target")
            is_go = correct_action == "step_on_target"
            if is_go:
                self.stats["go_total"] += 1
                if correct:
                    self.stats["go_correct"] += 1
            else:
                self.stats["no_go_total"] += 1
                if correct:
                    self.stats["no_go_correct"] += 1

        # 计分 - 新规则：错了扣5分，对了根据剩余时间加分（剩余时间/100，四舍五入）
        if correct:
            # 计算剩余时间（毫秒转秒）
            remaining_time_ms = (answer_time - elapsed) * 1000
            # 加分 = 剩余时间(毫秒) / 100，四舍五入
            points = round(remaining_time_ms / 100)
            self.state.score += max(0, points)
        else:
            # 错误扣5分
            self.state.score = max(0, self.state.score - 5)

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
            correct_action = self.current_question.get("correct_action")
            if correct_action == "step_on_target":
                # "踩X"试次超时 = 错误（没有踩到目标）
                self.stats["go_total"] += 1
            else:
                # "别踩X"试次超时 = 正确（成功避开了）
                self.stats["no_go_total"] += 1
                self.stats["no_go_correct"] += 1
                self.stats["correct"] += 1
                # 正确加分（超时情况下剩余时间为0，只给基础分）
                self.state.score += 5  # 基础分5分
                self._emit_feedback(correct=True, zone_id=None, is_timeout=True)
                self._start_interval()
                return

        # 超时扣分（与错误一致，扣5分）
        self.state.score = max(0, self.state.score - 5)

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
        """评估答案是否正确 - 支持四种Go/No-Go指令类型"""
        if not self.current_question:
            return False

        target_zone = self.current_question.get("target_zone")
        target_color = self.current_question.get("target_color")
        zones = self.current_question.get("zones", {})
        zone_state = zones.get(zone_id, {})

        if self.current_question["module"] == "go_no_go":
            correct_action = self.current_question.get("correct_action")
            zone_color = zone_state.get("color_name", "")

            if correct_action == "step_on_target":
                # "踩绿色"或"踩红色"：必须踩目标颜色区域
                return zone_id == target_zone and zone_color == target_color
            else:  # "avoid_target"
                # "别踩绿色"或"别踩红色"：只有踩目标颜色才错误，其他都正确
                # 踩了目标颜色 = 错误，踩非目标颜色或不踩 = 正确
                return zone_color != target_color
        else:
            # 选择反应：踩目标颜色区域
            zone_color = zone_state.get("color_name", "")
            return zone_color == target_color

    def _adjust_difficulty(self):
        """动态难度调整 - 基于答题情况调整区域数量"""
        if len(self.recent_trials) < 5:
            return

        correct_count = sum(1 for t in self.recent_trials if t["correct"])
        accuracy = correct_count / len(self.recent_trials)

        # 调整规则
        if accuracy < 0.5:
            # 正确率过低，降低难度（减少区域数量）
            if self.difficulty_level > 1:
                self.difficulty_level -= 1
                print(f"[ProcessingSpeed] 难度降低至 {self.difficulty_level} 级")
        elif accuracy > 0.85:
            # 正确率过高，提高难度（增加区域数量）
            if self.difficulty_level < 8:
                self.difficulty_level += 1
                print(f"[ProcessingSpeed] 难度提高至 {self.difficulty_level} 级")

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

        # 如果是"别踩X"正确（成功抑制）
        if (self.current_question and
            self.current_question["module"] == "go_no_go" and
            self.current_question.get("correct_action") == "avoid_target" and
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
