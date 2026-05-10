# -*- coding: utf-8 -*-
"""
Dynamic Difficulty Adjustment (DDA) System
基于 Hierarchical State Estimation 与 Evidence Fusion 的动态难度调整系统

系统架构：
Level 0: Perception Layer (生理 + 情绪 + 认知)
Level 1: Reliability Gate (信号可靠性门控)
Level 2A: Can Continue (能力状态估计)
Level 2B: Want Continue (意愿状态估计)
Level 3: Flow State Estimation (心流状态估计)
Level 4: Difficulty Policy Engine (难度策略引擎)
Level 5: Anti-Oscillation (防抖机制)
Level 6: Safety Override (安全保护机制)
"""

import time
import math
from collections import deque


class DDASystem:
    def __init__(self):
        # 滑动窗口（最近5题）
        self.window_size = 5
        self.question_history = deque(maxlen=self.window_size)
        
        # 当前状态
        self.current_difficulty = 4  # 开局默认难度4
        self.min_difficulty = 1
        self.max_difficulty = 8
        
        # 状态计数器（用于防抖）
        self.flow_state_history = deque(maxlen=5)  # 更长的历史窗口
        self.consecutive_same_state = 0
        self.last_state = None
        
        # HR 斜率 EMA 平滑
        self.hr_slope_ema = 0
        self.ema_alpha = 0.2
        
        # 时间窗口
        self.last_decision_time = time.time()
        self.decision_interval = 10  # 增加决策间隔到10秒
        self.last_adjust_time = time.time()  # 上次调整时间
        self.min_adjust_interval = 30  # 最小调整间隔30秒
        
        # 安全状态
        self.hr_abnormal_count = 0
        self.negative_high_conf_count = 0
        self.high_hrr_duration = 0
        self.last_hr_check_time = time.time()
        
        # 当前情绪（用于安全规则检查）
        self._current_emotion = 'neutral'
        
        # 上一个心流状态（用于防抖）
        self._last_flow_state = 'flow'
        
        # 统计数据
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.total_bombs = 0
        
        # 可靠性门控参数
        self.hr_max_age = 10.0  # HR数据最大有效年龄（秒）
        self.hr_decay_half_life = 5.0  # HR数据折损半衰期（秒）
        
        # 难度平滑 - EMA参数
        self.ema_difficulty = 4.0  # EMA平滑后的难度
        self.difficulty_ema_alpha = 0.15  # EMA系数，降低让变化更慢
        self.max_single_adjustment = 1  # 单次最大调整幅度
    
    def _calculate_hr_reliability(self, hr_valid, hr_age):
        """计算HR信号的可靠性权重（证据折损）
        
        Args:
            hr_valid: HR是否有效
            hr_age: HR数据的年龄（秒）
        
        Returns:
            reliability: 0.0 ~ 1.0 的可靠性权重
        """
        if not hr_valid:
            return 0.0
        
        if hr_age is None or hr_age <= 0:
            return 1.0
        
        # 指数衰减折损
        reliability = max(0.0, min(1.0, 
            math.exp(-math.log(2) * hr_age / self.hr_decay_half_life)))
        
        # 如果数据太旧，强制设为0
        if hr_age > self.hr_max_age:
            reliability = 0.0
        
        return reliability
    
    def _calculate_emotion_reliability(self, confidence, face_detected=True, face_count=1):
        """计算情绪数据的可靠性权重
        
        Args:
            confidence: 情绪置信度
            face_detected: 是否检测到人脸
            face_count: 人脸数量
        
        Returns:
            reliability: 0.0 ~ 1.0 的可靠性权重
        """
        if not face_detected:
            return 0.2  # 无人脸时可靠性很低
        
        if face_count != 1:
            return 0.5  # 多人场景可靠性降低
        
        return min(1.0, confidence)
    
    def _calculate_accuracy_from_history(self):
        """从题目历史计算准确率"""
        if not self.question_history:
            return 0.5
        
        total = len(self.question_history)
        hits = sum(1 for q in self.question_history if q.get('type') == 'hit')
        return hits / total if total > 0 else 0.5
    
    def _calculate_rt_stats(self):
        """计算反应时间统计"""
        rts = []
        for q in self.question_history:
            t = q.get('time', 0)
            if isinstance(t, int) and t > 0:
                rts.append(t)
        
        if not rts:
            return {'avg': 2000, 'trend': 0, 'ratio': 1.0}
        
        avg_rt = sum(rts) / len(rts)
        
        if len(rts) >= 3:
            recent_rts = rts[-3:]
            earlier_rts = rts[:-3] if len(rts) > 3 else recent_rts
            
            recent_avg = sum(recent_rts) / len(recent_rts)
            earlier_avg = sum(earlier_rts) / len(earlier_rts) if earlier_rts else recent_avg
            
            trend = recent_avg - earlier_avg
            ratio = recent_avg / earlier_avg if earlier_avg > 0 else 1.0
        else:
            trend = 0
            ratio = 1.0
        
        return {'avg': avg_rt, 'trend': trend, 'ratio': ratio}
    
    def _calculate_hit_ratio(self):
        """计算击中率"""
        recent = list(self.question_history)[-3:] if len(self.question_history) >= 3 else self.question_history
        
        if not recent:
            return 0.5
        
        hits = sum(1 for q in recent if q.get('type') == 'hit')
        return hits / len(recent)
    
    def _calculate_error_rate(self):
        """计算错误率（打错+炸弹）"""
        recent = list(self.question_history)[-3:] if len(self.question_history) >= 3 else self.question_history
        
        if not recent:
            return 0
        
        errors = sum(1 for q in recent if q.get('type') in ['error', 'bomb'])
        return errors / len(recent)
    
    def _calculate_difficulty_tolerance(self):
        """计算难度耐受性：评估玩家适应当前难度的能力趋势"""
        if len(self.question_history) < 3:
            return 10
        
        recent = list(self.question_history)[-5:]
        recent_types = [q.get('type') for q in recent]
        recent_difficulties = [q.get('difficulty', 1) for q in recent]
        
        # 计算近期命中率
        hits = sum(1 for t in recent_types if t == 'hit')
        recent_accuracy = hits / len(recent) if len(recent) > 0 else 0.5
        
        # 检查表现趋势（比较前半部分和后半部分）
        if len(recent) >= 4:
            first_half = recent_types[:len(recent)//2]
            second_half = recent_types[len(recent)//2:]
            first_hits = sum(1 for t in first_half if t == 'hit')
            second_hits = sum(1 for t in second_half if t == 'hit')
            first_acc = first_hits / len(first_half) if len(first_half) > 0 else 0.5
            second_acc = second_hits / len(second_half) if len(second_half) > 0 else 0.5
            trend = second_acc - first_acc
        else:
            trend = 0
        
        # 检查难度变化后的表现
        tolerance_score = 10  # 基准分
        
        # 如果近期准确率很高，给予奖励
        if recent_accuracy >= 0.8:
            tolerance_score += 10
        elif recent_accuracy >= 0.6:
            tolerance_score += 5
        
        # 如果表现正在改善，给予奖励
        if trend > 0.2:
            tolerance_score += 5
        # 如果表现正在恶化，给予惩罚
        elif trend < -0.2:
            tolerance_score -= 5
        
        # 检查难度提升后的适应情况
        if len(recent_difficulties) >= 2:
            last_diff = recent_difficulties[-1]
            prev_diff = recent_difficulties[-2]
            if last_diff > prev_diff:
                # 难度刚提升
                recent_hits_after = sum(1 for t in recent_types[-2:] if t == 'hit')
                if recent_hits_after >= 2:
                    tolerance_score += 10
                elif recent_hits_after == 0:
                    tolerance_score -= 5
        
        return max(0, min(20, tolerance_score))

    def _calculate_hrr_score(self, hrr, for_can_continue=True):
        """计算 HRR 得分"""
        if hrr is None:
            hrr = "medium"
        hrr = hrr.lower() if isinstance(hrr, str) else "medium"
        
        if for_can_continue:
            if hrr == "中等强度":
                return 15
            elif hrr == "低强度":
                return 8
            else:
                return 0
        else:
            if hrr == "中等强度":
                return 20
            elif hrr == "低强度":
                return 10
            else:
                return -15

    def _calculate_hr_slope_score(self, hr_slope_raw):
        """计算 HR 斜率得分"""
        if hr_slope_raw is None:
            hr_slope_raw = 0
        self.hr_slope_ema = self.ema_alpha * hr_slope_raw + (1 - self.ema_alpha) * self.hr_slope_ema
        
        slope = self.hr_slope_ema
        
        if -0.5 <= slope <= 0.5:
            return 10
        elif -1 <= slope <= 1:
            return 8
        elif slope > 2:
            return -5
        elif slope < -2:
            return -5
        else:
            return 5

    def estimate_can_continue(self, hr_valid, hrr_pct, hr_slope, hr_age=0):
        """估计能力状态（Can Continue）
        
        Args:
            hr_valid: HR是否有效
            hrr_pct: HRR百分比
            hr_slope: HR斜率
            hr_age: HR数据的年龄（秒）
        """
        # 确保数值类型正确
        if hrr_pct is None:
            hrr_pct = 0
        if hr_slope is None:
            hr_slope = 0
        if hr_age is None:
            hr_age = float('inf')
        
        # 计算HR可靠性权重（证据折损）
        hr_reliability = self._calculate_hr_reliability(hr_valid, hr_age)
        
        hr_signal = '正常' if hr_valid else '异常'
        
        if hrr_pct < 40:
            hrr = '低强度'
        elif hrr_pct <= 60:
            hrr = '中强度'
        else:
            hrr = '高强度'
        
        accuracy = self._calculate_accuracy_from_history()
        rt_stats = self._calculate_rt_stats()
        tolerance_score = self._calculate_difficulty_tolerance()
        error_rate = self._calculate_error_rate()
        
        if accuracy >= 0.9:
            acc_score = 30
        elif accuracy >= 0.7:
            acc_score = 20
        elif accuracy >= 0.5:
            acc_score = 10
        else:
            acc_score = 0
        
        rt_ratio = rt_stats['ratio']
        if rt_ratio < 0.8:
            rt_score = 25
        elif rt_ratio <= 1.2:
            rt_score = 20
        elif rt_ratio <= 1.5:
            rt_score = 10
        else:
            rt_score = 0
        
        # 移除Error Penalty，因为accuracy已经反映了错误率
        error_penalty = 0
        
        # 使用可靠性权重对折损HR相关得分
        hrr_score = self._calculate_hrr_score(hrr) * hr_reliability
        hr_slope_score = self._calculate_hr_slope_score(hr_slope) * hr_reliability
        
        # 计算理论满分和实际得分
        cognitive_score = acc_score + rt_score + tolerance_score
        hr_score = hrr_score + hr_slope_score
        
        # 当HR不可靠时，认知特征自动获得更高权重
        # 基础权重分配：认知65%，HR35%
        total = cognitive_score * 0.65 + hr_score * 0.35 + cognitive_score * 0.35 * (1 - hr_reliability)
        total = max(0, min(100, total))
        
        if total > 75:
            state = "Strong"
        elif total >= 55:
            state = "Capable"
        elif total >= 35:
            state = "Struggling"
        else:
            state = "Overloaded"
        
        return {
            'score': total,
            'state': state,
            'components': {
                'accuracy': acc_score,
                'rt_trend': rt_score,
                'tolerance': tolerance_score,
                'hrr': hrr_score,
                'hr_slope': hr_slope_score,
                'error_penalty': error_penalty,
                'hr_valid': hr_valid,
                'hr_reliability': hr_reliability,
                'accuracy_value': accuracy,
                'rt_ms': rt_stats['avg'],
                'error_rate': error_rate
            }
        }

    def _calculate_emotion_score(self, emotion):
        """计算情绪得分"""
        emotion_map = {
            '积极高信度': 35, 'positive_high': 35,
            '积极低信度': 15, 'positive_low': 15,
            '中性高信度': 10, 'neutral_high': 10,
            '中性': 5, 'neutral': 5,
            '消极低信度': -15, 'negative_low': -15,
            '消极高信度': -40, 'negative_high': -40
        }
        return emotion_map.get(emotion, 0)

    def _calculate_rt_engagement(self):
        """计算 RT 参与度得分 - 根据文档使用 slope（趋势）而不是 ratio"""
        rt_stats = self._calculate_rt_stats()
        slope = rt_stats['trend']  # 使用趋势而不是比率
        
        # slope = recent_avg - earlier_avg
        # 更快（斜率为负，反应时间在缩短）: +15
        # 稳定（斜率接近0）: +10
        # 略慢（斜率为正但不大）: -5
        # 明显慢（斜率为正且较大）: -15
        
        if slope < -100:
            return 15
        elif -100 <= slope <= 100:
            return 10
        elif slope <= 300:
            return -5
        else:
            return -15

    def _calculate_accuracy_confidence(self):
        """计算准确率信心得分"""
        accuracy = self._calculate_accuracy_from_history()
        
        if accuracy > 0.85:
            return 15
        elif accuracy >= 0.65:
            return 10
        elif accuracy >= 0.5:
            return 0
        else:
            return -10

    def estimate_want_continue(self, hr_valid, hrr_pct, emotion_confidence=0, face_detected=True, face_count=1):
        """估计意愿状态（Want Continue）
        
        Args:
            hr_valid: HR是否有效
            hrr_pct: HRR百分比
            emotion_confidence: 情绪置信度（用于计算情绪可靠性）
            face_detected: 是否检测到人脸（用于情绪可靠性计算）
            face_count: 人脸数量（用于情绪可靠性计算）
        """
        # 确保数值类型正确
        if hrr_pct is None:
            hrr_pct = 0
        if emotion_confidence is None:
            emotion_confidence = 0
        
        use_hr = hr_valid
        
        # 当 HR 无效时，跳过 HRR 计算
        if use_hr:
            if hrr_pct < 40:
                hrr = '低强度'
            elif hrr_pct <= 60:
                hrr = '中强度'
            else:
                hrr = '高强度'
            hrr_score = self._calculate_hrr_score(hrr, for_can_continue=False)
        else:
            hrr_score = 0
        
        emotion = self._current_emotion
        
        emotion_score = self._calculate_emotion_score(emotion)
        
        # 计算情绪可靠性并折损情绪得分 - 使用 face_detected 和 face_count
        emotion_reliability = self._calculate_emotion_reliability(emotion_confidence, face_detected, face_count)
        emotion_score = emotion_score * emotion_reliability
        rt_engagement_score = self._calculate_rt_engagement()
        acc_conf_score = self._calculate_accuracy_confidence()
        
        hit_ratio = self._calculate_hit_ratio()
        hit_boost = (hit_ratio - 0.5) * 20
        
        # 评分公式：情绪40%，HRR20%，RT参与度20%，准确率信心15%，hit boost5%
        # 理论满分：35*1.2 + 20*0.8 + 15*0.8 + 15*0.6 + 10*0.4 = 42+16+12+9+4 = 83
        total = emotion_score * 1.2 + hrr_score * 0.8 + rt_engagement_score * 0.8 + acc_conf_score * 0.6 + hit_boost * 0.4
        
        # 归一化到0-100范围（使用tanh压缩曲线，让极端情绪更敏感）
        total = max(0, min(100, total))
        
        if total > 75:
            state = "Highly Engaged"
        elif total >= 55:
            state = "Engaged"
        elif total >= 35:
            state = "Passive"
        else:
            state = "Withdrawal Risk"
        
        return {
            'score': total,
            'state': state,
            'components': {
                'emotion': emotion_score,
                'hrr': hrr_score,
                'rt_engagement': rt_engagement_score,
                'accuracy_confidence': acc_conf_score,
                'hit_boost': hit_boost,
                'hit_ratio': hit_ratio
            }
        }

    def estimate_flow_state(self, can_continue_state, want_continue_state):
        """估计心流状态"""
        state_matrix = {
            ('Strong', 'Highly Engaged'): 'boredom',
            ('Strong', 'Engaged'): 'flow',
            ('Capable', 'Engaged'): 'flow',
            ('Struggling', 'Engaged'): 'challenge',
            ('Struggling', 'Passive'): 'anxiety',
            ('Overloaded', 'Passive'): 'fatigue',
            ('Overloaded', 'Withdrawal Risk'): 'fatigue'
        }
        
        return state_matrix.get((can_continue_state, want_continue_state), 'flow')

    def _check_safety_rules(self, hr_valid, hrr_pct):
        """检查安全规则"""
        current_time = time.time()
        
        hr_signal = '正常' if hr_valid else '异常'
        
        # 确保 hrr_pct 不是 None
        if hrr_pct is None:
            hrr_pct = 0
        
        # 使用指数衰减代替清零，处理间歇性异常
        if not hr_valid:
            self.hr_abnormal_count = min(10, self.hr_abnormal_count + 1)
        else:
            # 正常时缓慢衰减
            self.hr_abnormal_count = max(0, self.hr_abnormal_count - 0.3)
        
        if hrr_pct > 50:
            self.high_hrr_duration += current_time - self.last_hr_check_time
        else:
            # 高HRR结束时缓慢衰减
            self.high_hrr_duration = max(0, self.high_hrr_duration - (current_time - self.last_hr_check_time) * 0.5)
        
        emotion = self._current_emotion
        if emotion in ["消极高信度", "negative_high"]:
            self.negative_high_conf_count += 1
        else:
            # 消极情绪结束时缓慢衰减
            self.negative_high_conf_count = max(0, self.negative_high_conf_count - 0.5)
        
        accuracy_collapse = False
        if len(self.question_history) >= 3:
            recent_accuracy = self._calculate_accuracy_from_history()
            # 阈值从0.2调整为0.4，更早检测准确率崩塌
            accuracy_collapse = recent_accuracy <= 0.4
        
        self.last_hr_check_time = current_time
        
        return {
            'hr_abnormal': self.hr_abnormal_count > 3,
            'sustained_high_hrr': self.high_hrr_duration > 60,
            'negative_consecutive': self.negative_high_conf_count >= 5,
            'accuracy_collapse': accuracy_collapse
        }

    def get_difficulty_adjustment(self, flow_state, safety_rules, can_continue_components=None):
        """获取难度调整量
        
        Args:
            flow_state: 心流状态
            safety_rules: 安全规则
            can_continue_components: Can Continue的组件数据（包含accuracy_value）
        """
        if safety_rules['accuracy_collapse']:
            return -1, "安全规则: 准确率崩塌"
        if safety_rules['sustained_high_hrr']:
            return -1, "安全规则: 持续高负荷"
        if safety_rules['negative_consecutive']:
            return 0, "安全规则: 消极情绪连续，禁止升难度"
        
        # 检查是否"太简单了"：高准确率 + 不是Overloaded + 至少有5题数据
        if can_continue_components:
            accuracy = can_continue_components.get('accuracy_value', 0)
            state = can_continue_components.get('state', 'Struggling')
            # 只有至少有5题数据且准确率非常高时才触发
            has_enough_data = len(self.question_history) >= 5
            if has_enough_data and accuracy >= 0.95 and state != 'Overloaded':
                return 1, "表现优异: 准确率过高"
        
        policy = {
            'boredom': 1,
            'flow': 0,
            'challenge': 0,
            'anxiety': -1,
            'fatigue': -1  # 减小疲劳时的调整幅度
        }
        
        return policy.get(flow_state, 0), f"策略: {flow_state}"

    def _apply_difficulty_adjustment(self, adjustment, reason, safety_rules, is_game_running):
        """应用难度调整（抽象的通用方法）"""
        current_time = time.time()
        time_since_last_adjust = current_time - self.last_adjust_time
        within_cooldown = time_since_last_adjust < self.min_adjust_interval
        
        should_adjust = is_game_running and (
            (self.consecutive_same_state >= 3 or safety_rules['accuracy_collapse']) 
            and not within_cooldown
        )
        
        if not is_game_running:
            adjustment = 0
            reason = "游戏未进行中"
        elif within_cooldown:
            adjustment = 0
            reason = f"冷却中: 还需{int(self.min_adjust_interval - time_since_last_adjust)}秒"
        
        adjustment_made = False
        if should_adjust:
            # 使用EMA平滑调整
            target_difficulty = self.current_difficulty + adjustment
            target_difficulty = max(self.min_difficulty, min(self.max_difficulty, target_difficulty))
            
            # EMA平滑: new = alpha * target + (1-alpha) * current
            self.ema_difficulty = (self.difficulty_ema_alpha * target_difficulty + 
                                   (1 - self.difficulty_ema_alpha) * self.ema_difficulty)
            
            # 四舍五入到最近整数
            new_difficulty = int(round(self.ema_difficulty))
            new_difficulty = max(self.min_difficulty, min(self.max_difficulty, new_difficulty))
            
            # 限制单次调整幅度不超过±1
            diff = new_difficulty - self.current_difficulty
            if abs(diff) > self.max_single_adjustment:
                if diff > 0:
                    new_difficulty = self.current_difficulty + self.max_single_adjustment
                else:
                    new_difficulty = self.current_difficulty - self.max_single_adjustment
            
            if new_difficulty != self.current_difficulty:
                self.current_difficulty = new_difficulty
                self.last_adjust_time = current_time
                adjustment_made = True
        
        return adjustment, reason, adjustment_made, should_adjust

    def update(self, physiology_data, emotion_data, game_data):
        """更新 DDA 状态"""
        hr_valid = physiology_data.get('hr_valid', False)
        hrr_pct = physiology_data.get('hrr_pct', 0) or 0
        hr_slope = physiology_data.get('hr_slope', 0) or 0
        hr_age = physiology_data.get('hr_age', 0) or float('inf')
        
        emotion = emotion_data.get('emotion', 'neutral')
        emotion_confidence = emotion_data.get('confidence', 0) or 0
        self._current_emotion = emotion
        
        game_status = game_data.get('status', 'idle')
        results = game_data.get('results', [])
        
        if results:
            for result in results:
                time_val = result.get('time', 0)
                if not isinstance(time_val, int):
                    time_val = 0
                q_data = {
                    'type': result.get('type', 'miss'),
                    'time': time_val,
                    'difficulty': result.get('difficulty', 1),
                    'score': result.get('score', 0)
                }
                self.question_history.append(q_data)
                
                if q_data['type'] == 'hit':
                    self.total_hits += 1
                elif q_data['type'] == 'miss':
                    self.total_misses += 1
                elif q_data['type'] == 'error':
                    self.total_errors += 1
                elif q_data['type'] == 'bomb':
                    self.total_bombs += 1
        
        can_continue = self.estimate_can_continue(hr_valid, hrr_pct, hr_slope, hr_age)
        want_continue = self.estimate_want_continue(hr_valid, hrr_pct, emotion_confidence)
        flow_state = self.estimate_flow_state(can_continue['state'], want_continue['state'])
        
        safety_rules = self._check_safety_rules(hr_valid, hrr_pct)
        
        self.flow_state_history.append(flow_state)
        if flow_state == self.last_state:
            self.consecutive_same_state += 1
        else:
            self.consecutive_same_state = 1
        self.last_state = flow_state
        
        adjustment, reason = self.get_difficulty_adjustment(flow_state, safety_rules, can_continue['components'])
        
        is_game_running = game_status == 'playing'
        adjustment, reason, adjustment_made, should_adjust = self._apply_difficulty_adjustment(adjustment, reason, safety_rules, is_game_running)
        
        return {
            'current_difficulty': self.current_difficulty,
            'adjustment': adjustment if should_adjust else 0,
            'adjustment_made': adjustment_made,
            'reason': reason,
            'can_continue': can_continue,
            'want_continue': want_continue,
            'flow_state': flow_state,
            'safety_rules': safety_rules,
            'consecutive_state_count': self.consecutive_same_state,
            'window_size': len(self.question_history),
            'stats': {
                'total_hits': self.total_hits,
                'total_misses': self.total_misses,
                'total_errors': self.total_errors,
                'total_bombs': self.total_bombs,
                'overall_accuracy': (self.total_hits / (self.total_hits + self.total_misses + self.total_errors + self.total_bombs)) if (self.total_hits + self.total_misses + self.total_errors + self.total_bombs) > 0 else 0
            }
        }
    
    def update_from_unified(self, unified):
        """从统一的 JSON 数据更新 DDA 状态"""
        hr_valid = unified.get('hr_valid', False)
        hrr_pct = unified.get('hrr_pct', 0) or 0
        hr_slope = unified.get('hr_slope', 0) or 0
        hr_age = unified.get('hr_age', 0) or float('inf')
        
        emotion = unified.get('emotion', 'neutral')
        emotion_confidence = unified.get('confidence', 0) or 0
        self._current_emotion = emotion
        
        difficulty = unified.get('difficulty', 1)
        game_status = unified.get('game_status', 'idle')
        
        results = unified.get('results', [])
        if results:
            for result in results:
                time_val = result.get('time', 0)
                if not isinstance(time_val, int):
                    time_val = 0
                q_data = {
                    'type': result.get('type', 'miss'),
                    'time': time_val,
                    'difficulty': result.get('difficulty', difficulty),
                    'score': result.get('score', 0)
                }
                if q_data['type'] in ['hit', 'miss', 'error', 'bomb']:
                    # 检查是否已经存在（避免重复）
                    exists = any(h['type'] == q_data['type'] and h['time'] == q_data['time'] 
                                for h in self.question_history)
                    if not exists:
                        self.question_history.append(q_data)
                        
                        if q_data['type'] == 'hit':
                            self.total_hits += 1
                        elif q_data['type'] == 'miss':
                            self.total_misses += 1
                        elif q_data['type'] == 'error':
                            self.total_errors += 1
                        elif q_data['type'] == 'bomb':
                            self.total_bombs += 1
        
        can_continue = self.estimate_can_continue(hr_valid, hrr_pct, hr_slope, hr_age)
        want_continue = self.estimate_want_continue(hr_valid, hrr_pct, emotion_confidence)
        flow_state = self.estimate_flow_state(can_continue['state'], want_continue['state'])
        
        safety_rules = self._check_safety_rules(hr_valid, hrr_pct)
        
        if flow_state == self._last_flow_state:
            self.consecutive_same_state += 1
        else:
            self.consecutive_same_state = 1
        self._last_flow_state = flow_state
        
        adjustment, reason = self.get_difficulty_adjustment(flow_state, safety_rules, can_continue['components'])
        
        # 额外的安全规则检查（update_from_unified 特有）
        if safety_rules['hr_abnormal']:
            adjustment = 0
            reason = "安全: HR异常"
        
        if safety_rules['negative_consecutive']:
            adjustment = min(adjustment, 0)
            if adjustment > 0:
                adjustment = 0
                reason = "安全: 消极情绪连续"
        
        if safety_rules['accuracy_collapse']:
            adjustment = -1
            reason = "安全: 准确率崩塌"
        
        if safety_rules['sustained_high_hrr']:
            adjustment = min(adjustment, -1)
            if adjustment > -1:
                adjustment = -1
                reason = "安全: 高负荷持续"
        
        is_game_running = game_status == 'playing'
        adjustment, reason, adjustment_made, should_adjust = self._apply_difficulty_adjustment(adjustment, reason, safety_rules, is_game_running)
        
        return {
            'current_difficulty': self.current_difficulty,
            'adjustment': adjustment if should_adjust else 0,
            'adjustment_made': adjustment_made,
            'reason': reason,
            'can_continue': can_continue,
            'want_continue': want_continue,
            'flow_state': flow_state,
            'safety_rules': safety_rules,
            'consecutive_state_count': self.consecutive_same_state,
            'window_size': len(self.question_history),
            'stats': {
                'total_hits': self.total_hits,
                'total_misses': self.total_misses,
                'total_errors': self.total_errors,
                'total_bombs': self.total_bombs,
                'overall_accuracy': (self.total_hits / (self.total_hits + self.total_misses + self.total_errors + self.total_bombs)) if (self.total_hits + self.total_misses + self.total_errors + self.total_bombs) > 0 else 0
            }
        }