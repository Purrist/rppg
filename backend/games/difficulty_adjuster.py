# games/difficulty_adjuster.py
# 难度调整器
# 基于文献调研的动态难度调整系统
# 参考: Csikszentmihalyi (1990), Shute (2008), Hunicke (2005)

from typing import Dict, Any, Optional, List
import time
from collections import deque


class DifficultyAdjuster:
    """
    难度调整器
    
    理论基础:
    - 心流理论 (Csikszentmihalyi, 1990)
    - 自适应学习系统 (Shute, 2008)
    - 动态难度调整 (Hunicke, 2005)
    
    难度分级:
    - 10级难度系统
    - 基于 Bloom 认知分类法 (Bloom, 1956)
    - 基于 IRT 项目反应理论 (Hambleton et al., 1991)
    
    调整策略:
    - 单题调整: 每答题后评估
    - 单次训练调整: 每训练结束后评估
    - 短期趋势调整: 基于最近5次训练
    - 长期趋势调整: 基于最近30次训练
    - 调整幅度: ±1级
    - 老年人限制: 最高8级
    """
    
    # ==================== 难度参数 ====================
    # 基于 Bloom 认知分类法和 IRT 理论
    DIFFICULTY_PARAMS = {
        1: {
            "level": 1,
            "name": "极易",
            "reaction_time": 3000,    # 反应时间 (ms)
            "targets": 1,             # 目标数量
            "duration": 5000,         # 持续时间 (ms)
            "interval": 3000,         # 出现间隔 (ms)
            "score_multiplier": 1.0,  # 得分倍率
            "description": "适合初学者或疲劳状态"
        },
        2: {
            "level": 2,
            "name": "很易",
            "reaction_time": 2500,
            "targets": 1,
            "duration": 4500,
            "interval": 2800,
            "score_multiplier": 1.1,
            "description": "适合热身阶段"
        },
        3: {
            "level": 3,
            "name": "较易",
            "reaction_time": 2000,
            "targets": 1,
            "duration": 4000,
            "interval": 2600,
            "score_multiplier": 1.2,
            "description": "适合轻度训练"
        },
        4: {
            "level": 4,
            "name": "稍易",
            "reaction_time": 1800,
            "targets": 2,
            "duration": 3500,
            "interval": 2400,
            "score_multiplier": 1.3,
            "description": "适合中等训练"
        },
        5: {
            "level": 5,
            "name": "适中",
            "reaction_time": 1500,
            "targets": 2,
            "duration": 3000,
            "interval": 2200,
            "score_multiplier": 1.5,
            "description": "最佳训练难度"
        },
        6: {
            "level": 6,
            "name": "稍难",
            "reaction_time": 1200,
            "targets": 3,
            "duration": 2500,
            "interval": 2000,
            "score_multiplier": 1.7,
            "description": "适合进阶训练"
        },
        7: {
            "level": 7,
            "name": "较难",
            "reaction_time": 1000,
            "targets": 3,
            "duration": 2000,
            "interval": 1800,
            "score_multiplier": 2.0,
            "description": "适合高强度训练"
        },
        8: {
            "level": 8,
            "name": "很难",
            "reaction_time": 800,
            "targets": 4,
            "duration": 1800,
            "interval": 1600,
            "score_multiplier": 2.5,
            "description": "老年人最高难度"
        },
        9: {
            "level": 9,
            "name": "极难",
            "reaction_time": 600,
            "targets": 4,
            "duration": 1500,
            "interval": 1400,
            "score_multiplier": 3.0,
            "description": "专家级难度"
        },
        10: {
            "level": 10,
            "name": "最难",
            "reaction_time": 500,
            "targets": 5,
            "duration": 1200,
            "interval": 1200,
            "score_multiplier": 4.0,
            "description": "挑战极限"
        },
    }
    
    def __init__(self, initial_level: int = 5, max_level: int = 8):
        """
        初始化难度调整器
        
        参数:
            initial_level: 初始难度等级 (默认5)
            max_level: 最高难度等级 (老年人默认8)
        """
        self.current_level = initial_level
        self.max_level = min(max_level, 10)  # 老年人最高8级
        self.min_level = 1
        
        # 调整间隔 (每N次操作调整一次)
        self.adjustment_interval = 5
        self.action_count = 0
        
        # 历史记录
        self.adjustment_history = []
        self.last_adjustment_time = time.time()
        
        # 单题历史记录（最近50题）
        self.trial_history = deque(maxlen=50)
        
        # 单次训练历史记录（最近30次训练）
        self.session_history = deque(maxlen=30)
        
        # 难度表现记录（每个难度等级的准确率）
        self.difficulty_performance = {}
        for level in range(1, max_level + 1):
            self.difficulty_performance[level] = {
                'total': 0,
                'correct': 0,
                'accuracy': 0
            }
        
        # 最佳难度记录
        self.best_difficulty = initial_level
        self.best_accuracy = 0
    
    def record_trial(self, difficulty: int, correct: bool, reaction_time: float):
        """
        记录单题数据
        
        参数:
            difficulty: 难度等级
            correct: 是否正确
            reaction_time: 反应时间 (ms)
        """
        # 记录单题历史
        self.trial_history.append({
            'time': time.time(),
            'difficulty': difficulty,
            'correct': correct,
            'reaction_time': reaction_time
        })
        
        # 更新难度表现记录
        if difficulty in self.difficulty_performance:
            perf = self.difficulty_performance[difficulty]
            perf['total'] += 1
            if correct:
                perf['correct'] += 1
            perf['accuracy'] = perf['correct'] / perf['total'] if perf['total'] > 0 else 0
            
            # 更新最佳难度
            if perf['accuracy'] > self.best_accuracy and perf['total'] >= 10:
                self.best_accuracy = perf['accuracy']
                self.best_difficulty = difficulty
    
    def record_session(self, final_difficulty: int, accuracy: float, duration: int):
        """
        记录单次训练数据
        
        参数:
            final_difficulty: 最终难度等级
            accuracy: 准确率
            duration: 训练时长 (秒)
        """
        self.session_history.append({
            'time': time.time(),
            'final_difficulty': final_difficulty,
            'accuracy': accuracy,
            'duration': duration
        })
    
    def should_adjust(self) -> bool:
        """
        判断是否应该调整难度
        
        返回:
            是否应该调整
        """
        self.action_count += 1
        return self.action_count >= self.adjustment_interval
    
    def calculate_adjustment(self, physical_load: float, cognitive_load: float, 
                            engagement: float) -> int:
        """
        计算难度调整幅度
        
        参数:
            physical_load: 身体负荷 (0-1)
            cognitive_load: 认知负荷 (0-1)
            engagement: 参与意愿 (0-1)
        
        返回:
            调整幅度 (正数增加难度，负数降低难度)
        
        参考:
            - Csikszentmihalyi (1990): 心流理论
            - Hunicke (2005): 动态难度调整
        """
        adjustment = 0
        
        # ========== 身体负荷判断 ==========
        # 身体负荷过高 -> 降低难度
        if physical_load > 0.7:
            adjustment -= 1
        elif physical_load > 0.5:
            adjustment -= 0.5
        
        # ========== 认知负荷判断 ==========
        # 认知负荷过高 -> 降低难度
        if cognitive_load > 0.7:
            adjustment -= 1
        elif cognitive_load > 0.5:
            adjustment -= 0.5
        
        # ========== 参与意愿判断 ==========
        # 参与意愿过低 -> 可能需要调整
        if engagement < 0.3:
            adjustment -= 0.5
        
        # ========== 最佳状态判断 ==========
        # 心流状态: 身体负荷适中 + 认知负荷适中 + 参与意愿高
        if physical_load < 0.4 and cognitive_load < 0.4 and engagement > 0.7:
            adjustment += 1
        
        # 限制调整幅度
        adjustment = max(-1, min(1, int(round(adjustment))))
        
        return adjustment
    
    def adjust(self, physical_load: float, cognitive_load: float, 
               engagement: float) -> Dict[str, Any]:
        """
        执行难度调整
        
        参数:
            physical_load: 身体负荷
            cognitive_load: 认知负荷
            engagement: 参与意愿
        
        返回:
            调整结果字典
        """
        # 计算调整幅度
        adjustment = self.calculate_adjustment(physical_load, cognitive_load, engagement)
        
        # 计算新难度
        old_level = self.current_level
        new_level = self.current_level + adjustment
        
        # 限制难度范围
        new_level = max(self.min_level, min(self.max_level, new_level))
        
        # 更新当前难度
        self.current_level = new_level
        
        # 重置计数
        self.action_count = 0
        
        # 记录历史
        self.adjustment_history.append({
            "time": time.time(),
            "old_level": old_level,
            "new_level": new_level,
            "adjustment": adjustment,
            "physical_load": physical_load,
            "cognitive_load": cognitive_load,
            "engagement": engagement,
        })
        
        # 保留最近20条记录
        if len(self.adjustment_history) > 20:
            self.adjustment_history = self.adjustment_history[-20:]
        
        return {
            "old_level": old_level,
            "new_level": new_level,
            "adjustment": adjustment,
            "params": self.get_params(),
            "reason": self._get_adjustment_reason(adjustment, physical_load, cognitive_load, engagement),
        }
    
    def _get_adjustment_reason(self, adjustment: int, physical: float, 
                               cognitive: float, engagement: float) -> str:
        """获取调整原因说明"""
        reasons = []
        
        if physical > 0.7:
            reasons.append("身体负荷过高")
        elif physical > 0.5:
            reasons.append("身体负荷略高")
        
        if cognitive > 0.7:
            reasons.append("认知负荷过高")
        elif cognitive > 0.5:
            reasons.append("认知负荷略高")
        
        if engagement < 0.3:
            reasons.append("参与意愿较低")
        
        if physical < 0.4 and cognitive < 0.4 and engagement > 0.7:
            reasons.append("状态良好")
        
        if not reasons:
            reasons.append("状态正常")
        
        return "，".join(reasons)
    
    def get_params(self) -> Dict[str, Any]:
        """
        获取当前难度参数
        
        返回:
            难度参数字典
        """
        return self.DIFFICULTY_PARAMS.get(self.current_level, self.DIFFICULTY_PARAMS[5])
    
    def set_level(self, level: int) -> Dict[str, Any]:
        """
        直接设置难度等级
        
        参数:
            level: 目标难度等级
        
        返回:
            设置结果
        """
        old_level = self.current_level
        self.current_level = max(self.min_level, min(self.max_level, level))
        
        return {
            "old_level": old_level,
            "new_level": self.current_level,
            "params": self.get_params(),
        }
    
    def get_level_info(self, level: int = None) -> Dict[str, Any]:
        """
        获取难度等级信息
        
        参数:
            level: 难度等级 (默认当前等级)
        
        返回:
            难度等级信息
        """
        if level is None:
            level = self.current_level
        
        return self.DIFFICULTY_PARAMS.get(level, self.DIFFICULTY_PARAMS[5])
    
    def get_all_levels(self) -> Dict[int, Dict]:
        """获取所有难度等级信息"""
        return self.DIFFICULTY_PARAMS.copy()
    
    def get_state(self) -> Dict[str, Any]:
        """获取调整器状态"""
        return {
            "current_level": self.current_level,
            "max_level": self.max_level,
            "min_level": self.min_level,
            "action_count": self.action_count,
            "adjustment_interval": self.adjustment_interval,
            "params": self.get_params(),
            "history_count": len(self.adjustment_history),
        }
