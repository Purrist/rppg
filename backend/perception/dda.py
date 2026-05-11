# -*- coding: utf-8 -*-
"""
Dynamic Difficulty Adjustment (DDA) System
基于 Hierarchical State Estimation 与 Evidence Fusion 的动态难度调整系统

核心原则重定义（V2 架构）：
1. 认知数据（游戏表现）：绝对主导，决定难度升降的大趋势
2. 生理数据（HR/HRR）：安全托底，只用于识别硬撑和疲劳，作为惩罚项而非加分项
3. 情绪数据：调味剂，完全信任情绪势场的输出，不改变认知主导的大趋势
4. 时间窗口：抛弃全局准确率，所有判定基于最近3-5题的滑动窗口，实现真正的实时响应
"""

import time
import math
from collections import deque, Counter


class DDASystem:
    def __init__(self):
        # ── 滑动窗口 ──
        self.window_size = 5  # 核心认知窗口：只看最近5题
        self.question_history = deque(maxlen=self.window_size)

        # ── 批处理周期计数器 ──
        self.question_count_since_last_adjustment = 0

        # ── 难度状态 ──
        self.current_difficulty = 4
        self.min_difficulty = 1
        self.max_difficulty = 8

        # ── 防抖与冷却 ──
        self.flow_state_history = deque(maxlen=5)
        self.consecutive_same_state = 0
        self.last_state = None
        self.last_adjust_time = time.time()
        # 非对称冷却：升难度慢（防超载），降难度快（防挫败）
        self.increase_cooldown = 8
        self.decrease_cooldown = 3

        # ── 生理状态追踪 ──
        self.hr_slope_ema = 0
        self.ema_alpha = 0.2
        self.hr_abnormal_count = 0
        self.negative_high_conf_count = 0
        self.high_hrr_duration = 0
        self.last_hr_check_time = time.time()

        # ── 情绪状态 ──
        self._current_emotion = 'neutral'
        self._last_emotion_score = 20.0  # 默认给中性分数，避免初始状态误判

        # ── 统计与去重 ──
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.total_bombs = 0
        self.processed_seqs = set()

        # ── 状态记录（供API查询）──
        self._last_flow_state = 'flow'
        self._last_can_state = 'Capable'
        self._last_can_score = 50
        self._last_want_state = 'Engaged'
        self._last_want_score = 50
        self._last_safety_rules = {}
        self.last_adjustment = 0

    def reset_for_new_game(self):
        """开始新游戏时重置跨游戏状态"""
        self.question_history.clear()
        self.question_count_since_last_adjustment = 0
        self.flow_state_history.clear()
        self.consecutive_same_state = 0
        self.last_state = None
        self.processed_seqs.clear()
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.total_bombs = 0
        self.hr_abnormal_count = 0
        self.high_hrr_duration = 0
        self.negative_high_conf_count = 0

    # ── 数据计算层 ──

    def _calculate_accuracy_from_history(self):
        """基于滑动窗口的准确率（非全局）"""
        if not self.question_history: return 0.5
        total = len(self.question_history)
        hits = sum(1 for q in self.question_history if q.get('type') == 'hit')
        return hits / total if total > 0 else 0.5

    def _calculate_rt_stats(self):
        """RT趋势：最近3题平均RT / 之前RT，判断是否越打越慢（硬撑前兆）"""
        rts = [q.get('time', 0) for q in self.question_history if isinstance(q.get('time', 0), int) and q.get('time', 0) > 0]
        if not rts: return {'avg': 2000, 'trend': 0, 'ratio': 1.0}
        avg_rt = sum(rts) / len(rts)
        if len(rts) >= 3:
            recent_avg = sum(rts[-3:]) / 3
            earlier_avg = sum(rts[:-3]) / len(rts[:-3]) if len(rts) > 3 else recent_avg
            trend = recent_avg - earlier_avg
            ratio = recent_avg / earlier_avg if earlier_avg > 0 else 1.0
        else:
            trend, ratio = 0, 1.0
        return {'avg': avg_rt, 'trend': trend, 'ratio': ratio}

    def _calculate_difficulty_tolerance(self):
        """难度耐受度：评估难度提升后的存活能力（防震缓冲）"""
        if len(self.question_history) < 3: return 15  # 数据不足给中间分
        recent = list(self.question_history)[-5:]
        types = [q.get('type') for q in recent]
        diffs = [q.get('difficulty', 1) for q in recent]
        hits = sum(1 for t in types if t == 'hit')
        acc = hits / len(types) if types else 0.5

        score = 15
        # 整体窗口准确率极高，说明能力有余量
        if acc >= 0.8: score += 25
        elif acc >= 0.6: score += 15

        # 核心创新：检测到难度提升后的表现
        if len(diffs) >= 2 and diffs[-1] > diffs[-2]:
            if types[-1] == 'hit' and types[-2] == 'hit':
                score += 20  # 升难度后连对，耐受度极高，可以再升
            elif types[-1] != 'hit' and types[-2] != 'hit':
                score -= 10  # 升难度后连错，触碰能力边界，不能再升
        return max(0, min(60, score))

    def _calculate_hit_ratio(self):
        """近期命中率（意愿层用）"""
        recent = list(self.question_history)[-3:] if len(self.question_history) >= 3 else self.question_history
        if not recent: return 0.5
        return sum(1 for q in recent if q.get('type') == 'hit') / len(recent)

    # ── 状态估计层 ──

    def estimate_can_continue(self, hr_valid, hrr_pct, hr_slope, hr_age=0):
        """能力估计：认知定基数，生理做扣减"""
        accuracy = self._calculate_accuracy_from_history()
        rt_stats = self._calculate_rt_stats()
        tolerance = self._calculate_difficulty_tolerance()

        # 1. 认知基础分 (满分 90，绝对主导)
        # 准确率得分 (0-40)
        acc_score = 40 if accuracy >= 0.9 else 25 if accuracy >= 0.7 else 10 if accuracy >= 0.5 else 0
        # RT趋势得分 (0-30)：越打越快说明简单，越打越慢说明吃力
        rt_score = 30 if rt_stats['ratio'] < 0.9 else 20 if rt_stats['ratio'] <= 1.2 else 5 if rt_stats['ratio'] <= 1.5 else 0
        cognitive_score = acc_score + rt_score + tolerance  # 范围 0-90

        # 2. 生理安全惩罚 (只减分，不加分)
        safety_penalty = 0
        if hr_valid:
            self.hr_slope_ema = self.ema_alpha * (hr_slope or 0) + (1 - self.ema_alpha) * self.hr_slope_ema
            if hrr_pct is None: hrr_pct = 0
            # HRR过高说明负荷大，扣分
            if hrr_pct > 70: safety_penalty += 25
            elif hrr_pct > 60: safety_penalty += 15
            # HR斜率飙升说明压力急剧上升，扣分
            if self.hr_slope_ema > 2.0: safety_penalty += 15
            elif self.hr_slope_ema > 1.0: safety_penalty += 5

        total = max(0, cognitive_score - safety_penalty)

        # 阈值划分
        if total > 70: state = "Strong"       # 能力极强，太简单了
        elif total >= 45: state = "Capable"   # 能力匹配
        elif total >= 25: state = "Struggling"# 开始吃力
        else: state = "Overloaded"            # 过载

        return {'score': total, 'state': state, 'components': {
            'accuracy_value': accuracy, 'rt_ratio': rt_stats['ratio'], 'state': state}}

    def estimate_want_continue(self, hr_valid, hrr_pct, emotion_confidence=0, face_detected=True, face_count=1):
        """意愿估计：游戏参与度主干，情绪调味且不乘可靠性"""
        # 1. 游戏参与度基础分 (满分 60，行为不会骗人)
        hit_ratio = self._calculate_hit_ratio()
        rt_stats = self._calculate_rt_stats()

        hit_score = 30 if hit_ratio > 0.8 else 20 if hit_ratio > 0.5 else 5
        rt_engage = 30 if rt_stats['ratio'] < 0.9 else 20 if rt_stats['ratio'] <= 1.1 else 5 if rt_stats['ratio'] <= 1.3 else 0
        game_engagement_score = hit_score + rt_engage

        # 2. 情绪调味分 (满分 40)
        # 完全信任情绪势场输出，不乘以人脸检测可靠性系数（避免双重惩罚）
        # 专注状态（中性）给予及格偏上的保底分数
        emotion = self._current_emotion
        emotion_map = {
            'positive_high': 40, '积极高信度': 40,
            'positive_low': 30, '积极低信度': 30,
            'neutral_high': 25, '中性高信度': 25,
            'neutral': 20, '中性': 20,       # 专注保底分
            'negative_low': 5, '消极低信度': 5,
            'negative_high': -20, '消极高信度': -20
        }
        emotion_score = emotion_map.get(emotion, 20)  # 默认给中性分
        self._last_emotion_score = emotion_score  # 记录以便调试

        total = max(0, game_engagement_score + emotion_score)

        # 阈值划分 (意愿比能力更难量化，区间略宽)
        if total > 70: state = "Highly Engaged"
        elif total >= 40: state = "Engaged"     # 专注打游戏时稳居此处
        elif total >= 20: state = "Passive"
        else: state = "Withdrawal Risk"

        return {'score': total, 'state': state}

    def estimate_flow_state(self, can_continue_state, want_continue_state):
        """心流映射：消灭Challenge死锁，能力强就绝不判为挑战"""
        state_matrix = {
            # 太简单区间 (能力强 -> 应该升)
            ('Strong', 'Highly Engaged'): 'boredom',
            ('Strong', 'Engaged'): 'boredom',
            ('Strong', 'Passive'): 'boredom',      # 修复：强且平淡=太简单
            ('Strong', 'Withdrawal Risk'): 'boredom',
            # 刚好区间 (能力匹配 -> 保持)
            ('Capable', 'Highly Engaged'): 'flow',
            ('Capable', 'Engaged'): 'flow',
            ('Capable', 'Passive'): 'flow',        # 修复死锁：强且专注=心流，不是挑战
            ('Capable', 'Withdrawal Risk'): 'anxiety',
            # 偏难区间 (吃力 -> 观察或降)
            ('Struggling', 'Highly Engaged'): 'challenge',
            ('Struggling', 'Engaged'): 'challenge',
            ('Struggling', 'Passive'): 'anxiety',
            ('Struggling', 'Withdrawal Risk'): 'fatigue',
            # 太难区间 (过载 -> 必须降)
            ('Overloaded', 'Highly Engaged'): 'anxiety',
            ('Overloaded', 'Engaged'): 'fatigue',
            ('Overloaded', 'Passive'): 'fatigue',
            ('Overloaded', 'Withdrawal Risk'): 'fatigue'
        }
        return state_matrix.get((can_continue_state, want_continue_state), 'flow')

    # ── 决策与执行层 ──

    def _check_safety_rules(self, hr_valid, hrr_pct):
        """安全一票否决权：基于滑动窗口的瞬间崩塌检测"""
        current_time = time.time()
        if hrr_pct is None: hrr_pct = 0

        # 生理累积计算
        if not hr_valid: self.hr_abnormal_count = min(10, self.hr_abnormal_count + 1)
        else: self.hr_abnormal_count = max(0, self.hr_abnormal_count - 0.3)

        if hrr_pct > 60: self.high_hrr_duration += current_time - self.last_hr_check_time
        else: self.high_hrr_duration = max(0, self.high_hrr_duration - (current_time - self.last_hr_check_time) * 0.5)

        emotion = self._current_emotion
        if emotion in ["消极高信度", "negative_high"]: self.negative_high_conf_count += 1
        else: self.negative_high_conf_count = max(0, self.negative_high_conf_count - 0.5)

        self.last_hr_check_time = current_time

        # 认知崩塌判定 (抛弃全局准确率，看近期连错趋势)
        accuracy_collapse = False
        if len(self.question_history) >= 3:
            recent_3 = list(self.question_history)[-3:]
            hits_in_3 = sum(1 for q in recent_3 if q.get('type') == 'hit')

            # 极速崩塌：最近3题全错
            if hits_in_3 == 0:
                accuracy_collapse = True
            # 趋势崩塌：最近5题只对1题
            elif len(self.question_history) >= 5:
                recent_5 = list(self.question_history)[-5:]
                hits_in_5 = sum(1 for q in recent_5 if q.get('type') == 'hit')
                if hits_in_5 <= 1:
                    accuracy_collapse = True

        return {
            'hr_abnormal': self.hr_abnormal_count > 3,
            'sustained_high_hrr': self.high_hrr_duration > 60,
            'negative_consecutive': self.negative_high_conf_count >= 5,
            'accuracy_collapse': accuracy_collapse
        }

    def get_difficulty_adjustment(self, flow_state, safety_rules, can_continue_components=None):
        """策略引擎：安全第一，其次看心流"""
        # 安全规则一票否决
        if safety_rules['accuracy_collapse']: return -1, "安全规则: 窗口准确率崩塌"
        if safety_rules['sustained_high_hrr']: return -1, "安全规则: 持续高负荷"
        if safety_rules['negative_consecutive']: return 0, "安全规则: 消极情绪连续"

        # 正常心流策略
        policy = {
            'boredom': 1,    # 太简单，直接升
            'flow': 0,       # 刚刚好，保持
            'challenge': 0,  # 有点挑战，观察
            'anxiety': -1,   # 焦虑，降难度
            'fatigue': -1    # 疲劳，降难度
        }
        adj, reason = policy.get(flow_state, 0), f"策略: {flow_state}"
        return adj, reason

    def _should_adjust_by_history(self, flow_state):
        """非对称防抖机制：降难度无需防抖，升难度需连续确认"""
        valid_states = {'boredom', 'flow', 'challenge', 'anxiety', 'fatigue'}
        if flow_state not in valid_states: return False

        self.flow_state_history.append(flow_state)
        if len(self.flow_state_history) > 5:
            self.flow_state_history.popleft()

        if self.last_state is not None and flow_state == self.last_state:
            self.consecutive_same_state += 1
        else:
            self.consecutive_same_state = 1
            self.last_state = flow_state

        # 降难度（焦虑/疲劳）：无需防抖，立即执行，老人挫败感必须快速响应
        if flow_state in ['anxiety', 'fatigue']: return True
        # 升难度（无聊）：需要连续2次确认，避免偶发高光时刻导致误升
        if flow_state == 'boredom' and self.consecutive_same_state >= 2: return True

        # 兜底：历史窗口内多数状态决定
        state_counter = Counter(self.flow_state_history)
        if len(self.flow_state_history) >= 4:
            dominant_state, count = state_counter.most_common(1)[0]
            if count >= 3 and dominant_state == flow_state: return True
        return False

    def _apply_difficulty_adjustment(self, adjustment, reason, safety_rules, is_game_running, flow_state=None):
        current_time = time.time()
        time_since_last_adjust = current_time - self.last_adjust_time

        is_increase = adjustment > 0
        is_safety_collapse = safety_rules.get('accuracy_collapse', False)
        # 非对称冷却：升难度8秒，降难度3秒
        effective_cooldown = self.increase_cooldown if is_increase else self.decrease_cooldown
        within_cooldown = time_since_last_adjust < effective_cooldown

        should_adjust = False
        if is_game_running:
            # 安全崩塌无视冷却直接降
            if is_safety_collapse:
                should_adjust = not within_cooldown
            elif flow_state:
                should_adjust = self._should_adjust_by_history(flow_state) and not within_cooldown

        if not is_game_running:
            adjustment, reason = 0, "游戏未进行中"
        elif within_cooldown and not is_safety_collapse:
            adjustment, reason = 0, f"冷却中: 还需{int(effective_cooldown - time_since_last_adjust)}秒"

        adjustment_made = False
        if should_adjust and adjustment != 0:
            new_difficulty = max(self.min_difficulty, min(self.max_difficulty, self.current_difficulty + adjustment))
            if new_difficulty != self.current_difficulty:
                self.current_difficulty = new_difficulty
                self.last_adjust_time = current_time
                adjustment_made = True

        return adjustment, reason, adjustment_made, should_adjust

    # ── 统一更新入口 ──

    def update_from_unified(self, unified):
        hr_valid = unified.get('hr_valid', False)
        hrr_pct = unified.get('hrr_pct', 0) or 0
        hr_slope = unified.get('hr_slope', 0) or 0
        emotion = unified.get('emotion', 'neutral')
        emotion_confidence = unified.get('confidence', 0) or 0

        self._current_emotion = emotion
        difficulty = unified.get('difficulty', 1)
        game_status = unified.get('game_status', 'idle')
        results = unified.get('results', [])

        new_questions_added = 0
        if results:
            for result in results:
                seq = result.get('seq', None)
                time_val = result.get('time', 0)
                if not isinstance(time_val, int): time_val = 0
                q_data = {'seq': seq, 'type': result.get('type', 'miss'), 'time': time_val, 'difficulty': result.get('difficulty', difficulty), 'score': result.get('score', 0)}
                if seq is not None and seq in self.processed_seqs: continue
                if q_data['type'] in ['hit', 'miss', 'error', 'bomb']:
                    if seq is not None: self.processed_seqs.add(seq)
                    self.question_history.append(q_data)
                    new_questions_added += 1
                    if q_data['type'] == 'hit': self.total_hits += 1
                    elif q_data['type'] == 'miss': self.total_misses += 1
                    elif q_data['type'] == 'error': self.total_errors += 1
                    elif q_data['type'] == 'bomb': self.total_bombs += 1

        self.question_count_since_last_adjustment += new_questions_added

        if self.question_count_since_last_adjustment < 5:
            return {
                'current_difficulty': self.current_difficulty,
                'adjustment': 0,
                'adjustment_made': False,
                'reason': f"积累中: {self.question_count_since_last_adjustment}/5",
                'can_continue': {'score': self._last_can_score, 'state': self._last_can_state, 'components': {}},
                'want_continue': {'score': self._last_want_score, 'state': self._last_want_state},
                'flow_state': self._last_flow_state,
                'safety_rules': self._last_safety_rules,
                'consecutive_state_count': self.consecutive_same_state,
                'window_size': len(self.question_history),
                'stats': {
                    'total_hits': self.total_hits, 'total_misses': self.total_misses,
                    'total_errors': self.total_errors, 'total_bombs': self.total_bombs,
                    'overall_accuracy': (self.total_hits / (self.total_hits + self.total_misses + self.total_errors + self.total_bombs)) if (self.total_hits + self.total_misses + self.total_errors + self.total_bombs) > 0 else 0
                }
            }

        self.question_count_since_last_adjustment = 0

        can_continue = self.estimate_can_continue(hr_valid, hrr_pct, hr_slope)
        want_continue = self.estimate_want_continue(hr_valid, hrr_pct, emotion_confidence)
        flow_state = self.estimate_flow_state(can_continue['state'], want_continue['state'])
        safety_rules = self._check_safety_rules(hr_valid, hrr_pct)

        adjustment, reason = self.get_difficulty_adjustment(flow_state, safety_rules, can_continue['components'])
        if safety_rules['hr_abnormal']: adjustment, reason = 0, "安全: HR异常"
        if safety_rules['negative_consecutive'] and adjustment > 0: adjustment, reason = 0, "安全: 消极情绪连续"
        if safety_rules['sustained_high_hrr'] and adjustment > -1: adjustment, reason = -1, "安全: 高负荷持续"

        is_game_running = game_status == 'playing'
        adjustment, reason, adjustment_made, should_adjust = self._apply_difficulty_adjustment(adjustment, reason, safety_rules, is_game_running, flow_state)

        self._last_flow_state = flow_state
        self._last_can_state = can_continue['state']
        self._last_can_score = can_continue['score']
        self._last_want_state = want_continue['state']
        self._last_want_score = want_continue['score']
        self._last_safety_rules = safety_rules
        self.last_adjustment = adjustment if should_adjust else 0

        return {
            'current_difficulty': self.current_difficulty,
            'adjustment': self.last_adjustment,
            'adjustment_made': adjustment_made,
            'reason': reason,
            'can_continue': can_continue,
            'want_continue': want_continue,
            'flow_state': flow_state,
            'safety_rules': safety_rules,
            'consecutive_state_count': self.consecutive_same_state,
            'window_size': len(self.question_history),
            'stats': {
                'total_hits': self.total_hits, 'total_misses': self.total_misses,
                'total_errors': self.total_errors, 'total_bombs': self.total_bombs,
                'overall_accuracy': (self.total_hits / (self.total_hits + self.total_misses + self.total_errors + self.total_bombs)) if (self.total_hits + self.total_misses + self.total_errors + self.total_bombs) > 0 else 0
            }
        }
