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
from collections import deque, Counter


class DDASystem:
    def __init__(self):
        self.window_size = 5
        self.question_history = deque(maxlen=self.window_size)
        
        self.current_difficulty = 4
        self.min_difficulty = 1
        self.max_difficulty = 8
        
        self.flow_state_history = deque(maxlen=5)
        self.consecutive_same_state = 0
        self.last_state = None
        
        self.hr_slope_ema = 0
        self.ema_alpha = 0.2
        
        self.last_decision_time = time.time()
        self.decision_interval = 10
        self.last_adjust_time = time.time()
        self.min_adjust_interval = 10
        
        self.hr_abnormal_count = 0
        self.negative_high_conf_count = 0
        self.high_hrr_duration = 0
        self.last_hr_check_time = time.time()
        
        self._current_emotion = 'neutral'
        self._last_flow_state = 'flow'
        
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.total_bombs = 0
        
        self.hr_max_age = 10.0
        self.hr_decay_half_life = 5.0
        
        self.ema_difficulty = 4.0
        self.difficulty_ema_alpha = 0.15
        self.max_single_adjustment = 1
        
        self._last_emotion_score = 0
        self._last_emotion_reliability = 1.0
        
        self.processed_seqs = set()
        self._last_game_seq = 0
    
    def reset_for_new_game(self):
        """开始新游戏时重置跨游戏状态"""
        self.question_history.clear()
        self.flow_state_history.clear()
        self.consecutive_same_state = 0
        self.last_state = None
        self.processed_seqs.clear()
        self._last_game_seq = 0
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.total_bombs = 0
        self.hr_abnormal_count = 0
        self.high_hrr_duration = 0
        self.negative_high_conf_count = 0
    
    def _calculate_hr_reliability(self, hr_valid, hr_age):
        if not hr_valid:
            return 0.0
        
        if hr_age is None or hr_age <= 0:
            return 1.0
        
        reliability = max(0.0, min(1.0, 
            math.exp(-math.log(2) * hr_age / self.hr_decay_half_life)))
        
        if hr_age > self.hr_max_age:
            reliability = 0.0
        
        return reliability
    
    def _calculate_emotion_reliability(self, confidence, face_detected=True, face_count=1):
        if not face_detected:
            return 0.2
        
        if face_count != 1:
            return 0.5
        
        return min(1.0, confidence)
    
    def _calculate_accuracy_from_history(self):
        if not self.question_history:
            return 0.5
        
        total = len(self.question_history)
        hits = sum(1 for q in self.question_history if q.get('type') == 'hit')
        return hits / total if total > 0 else 0.5
    
    def _calculate_rt_stats(self):
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
        recent = list(self.question_history)[-3:] if len(self.question_history) >= 3 else self.question_history
        
        if not recent:
            return 0.5
        
        hits = sum(1 for q in recent if q.get('type') == 'hit')
        return hits / len(recent)
    
    def _calculate_error_rate(self):
        recent = list(self.question_history)[-3:] if len(self.question_history) >= 3 else self.question_history
        
        if not recent:
            return 0
        
        errors = sum(1 for q in recent if q.get('type') in ['error', 'bomb'])
        return errors / len(recent)
    
    def _calculate_difficulty_tolerance(self):
        if len(self.question_history) < 3:
            return 10
        
        recent = list(self.question_history)[-5:]
        recent_types = [q.get('type') for q in recent]
        recent_difficulties = [q.get('difficulty', 1) for q in recent]
        
        hits = sum(1 for t in recent_types if t == 'hit')
        recent_accuracy = hits / len(recent) if len(recent) > 0 else 0.5
        
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
        
        tolerance_score = 10
        
        if recent_accuracy >= 0.8:
            tolerance_score += 10
        elif recent_accuracy >= 0.6:
            tolerance_score += 5
        
        if trend > 0.2:
            tolerance_score += 5
        elif trend < -0.2:
            tolerance_score -= 5
        
        if len(recent_difficulties) >= 2:
            last_diff = recent_difficulties[-1]
            prev_diff = recent_difficulties[-2]
            if last_diff > prev_diff:
                recent_hits_after = sum(1 for t in recent_types[-2:] if t == 'hit')
                if recent_hits_after >= 2:
                    tolerance_score += 10
                elif recent_hits_after == 0:
                    tolerance_score -= 5
        
        return max(0, min(20, tolerance_score))

    def _calculate_hrr_score(self, hrr, for_can_continue=True):
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

    def _calculate_hr_slope_score(self, hr_slope_raw, hrr_pct=0):
        if hr_slope_raw is None:
            hr_slope_raw = 0
        if hrr_pct is None:
            hrr_pct = 0
        self.hr_slope_ema = self.ema_alpha * hr_slope_raw + (1 - self.ema_alpha) * self.hr_slope_ema
        
        slope = self.hr_slope_ema
        
        if -0.5 <= slope <= 0.5:
            return 10
        elif slope < -2:
            if hrr_pct > 50:
                return -5
            return 5
        elif slope > 2:
            if hrr_pct > 50:
                return 5
            return -5
        else:
            return 8

    def estimate_can_continue(self, hr_valid, hrr_pct, hr_slope, hr_age=0):
        if hrr_pct is None:
            hrr_pct = 0
        if hr_slope is None:
            hr_slope = 0
        if hr_age is None:
            hr_age = float('inf')
        
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
        
        error_penalty = 0
        
        hrr_score = self._calculate_hrr_score(hrr) * hr_reliability
        hr_slope_score = self._calculate_hr_slope_score(hr_slope, hrr_pct) * hr_reliability
        
        cognitive_score = acc_score + rt_score + tolerance_score
        hr_score = hrr_score + hr_slope_score
        
        if hr_reliability > 0.5:
            total = cognitive_score * 0.7 + hr_score * 0.3
        else:
            total = cognitive_score * 0.9
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
        emotion_map = {
            '积极高信度': 35, 'positive_high': 35,
            '积极低信度': 15, 'positive_low': 15,
            '中性高信度': 20, 'neutral_high': 20,
            '中性': 15, 'neutral': 15,
            '消极低信度': -15, 'negative_low': -15,
            '消极高信度': -40, 'negative_high': -40
        }
        return emotion_map.get(emotion, 0)

    def _calculate_rt_engagement(self):
        rt_stats = self._calculate_rt_stats()
        ratio = rt_stats['ratio']
        
        if ratio < 0.75:
            return 15
        elif ratio <= 0.9:
            return 10
        elif ratio <= 1.15:
            return 10
        elif ratio <= 1.35:
            return -5
        else:
            return -15

    def _calculate_accuracy_confidence(self):
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
        if hrr_pct is None:
            hrr_pct = 0
        if emotion_confidence is None:
            emotion_confidence = 0
        
        use_hr = hr_valid
        
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
        emotion_reliability = self._calculate_emotion_reliability(emotion_confidence, face_detected, face_count)
        
        if emotion_reliability < 0.5:
            if self._last_emotion_reliability >= 0.5:
                emotion_score = self._last_emotion_score * emotion_reliability
            else:
                emotion_score = self._last_emotion_score * 0.5
        else:
            self._last_emotion_score = emotion_score
            emotion_score = emotion_score * emotion_reliability
        self._last_emotion_reliability = emotion_reliability
        
        rt_engagement_score = self._calculate_rt_engagement()
        acc_conf_score = self._calculate_accuracy_confidence()
        
        hit_ratio = self._calculate_hit_ratio()
        hit_boost = (hit_ratio - 0.5) * 20
        
        total = emotion_score * 1.2 + hrr_score * 0.8 + rt_engagement_score * 0.8 + acc_conf_score * 0.6 + hit_boost * 0.4
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
        state_matrix = {
            ('Strong', 'Highly Engaged'): 'boredom',
            ('Strong', 'Engaged'): 'boredom',
            ('Strong', 'Passive'): 'boredom',
            ('Strong', 'Withdrawal Risk'): 'boredom',
            ('Capable', 'Highly Engaged'): 'flow',
            ('Capable', 'Engaged'): 'flow',
            ('Capable', 'Passive'): 'boredom',
            ('Capable', 'Withdrawal Risk'): 'anxiety',
            ('Struggling', 'Highly Engaged'): 'challenge',
            ('Struggling', 'Engaged'): 'challenge',
            ('Struggling', 'Passive'): 'anxiety',
            ('Struggling', 'Withdrawal Risk'): 'fatigue',
            ('Overloaded', 'Highly Engaged'): 'anxiety',
            ('Overloaded', 'Engaged'): 'fatigue',
            ('Overloaded', 'Passive'): 'fatigue',
            ('Overloaded', 'Withdrawal Risk'): 'fatigue'
        }
        
        return state_matrix.get((can_continue_state, want_continue_state), 'flow')

    def _check_safety_rules(self, hr_valid, hrr_pct):
        current_time = time.time()
        
        if hrr_pct is None:
            hrr_pct = 0
        
        if not hr_valid:
            self.hr_abnormal_count = min(10, self.hr_abnormal_count + 1)
        else:
            self.hr_abnormal_count = max(0, self.hr_abnormal_count - 0.3)
        
        if hrr_pct > 50:
            self.high_hrr_duration += current_time - self.last_hr_check_time
        else:
            self.high_hrr_duration = max(0, self.high_hrr_duration - (current_time - self.last_hr_check_time) * 0.5)
        
        emotion = self._current_emotion
        if emotion in ["消极高信度", "negative_high"]:
            self.negative_high_conf_count += 1
        else:
            self.negative_high_conf_count = max(0, self.negative_high_conf_count - 0.5)
        
        accuracy_collapse = False
        if len(self.question_history) >= 3:
            recent_accuracy = self._calculate_accuracy_from_history()
            accuracy_collapse = recent_accuracy <= 0.4
        
        self.last_hr_check_time = current_time
        
        return {
            'hr_abnormal': self.hr_abnormal_count > 3,
            'sustained_high_hrr': self.high_hrr_duration > 60,
            'negative_consecutive': self.negative_high_conf_count >= 5,
            'accuracy_collapse': accuracy_collapse
        }

    def get_difficulty_adjustment(self, flow_state, safety_rules, can_continue_components=None):
        if safety_rules['accuracy_collapse']:
            return -1, "安全规则: 准确率崩塌"
        if safety_rules['sustained_high_hrr']:
            return -1, "安全规则: 持续高负荷"
        if safety_rules['negative_consecutive']:
            return 0, "安全规则: 消极情绪连续，禁止升难度"
        
        if can_continue_components:
            accuracy = can_continue_components.get('accuracy_value', 0)
            state = can_continue_components.get('state', 'Struggling')
            recent = list(self.question_history)[-3:] if len(self.question_history) >= 3 else self.question_history
            has_enough_data = len(recent) >= 3
            recent_accuracy = sum(1 for q in recent if q.get('type') == 'hit') / len(recent) if recent else 0
            
            if has_enough_data and recent_accuracy >= 0.8 and state != 'Overloaded':
                return 1, "表现优异: 准确率过高"
        
        policy = {
            'boredom': 1,
            'flow': 0,
            'challenge': 0,
            'anxiety': -1,
            'fatigue': -1
        }
        
        return policy.get(flow_state, 0), f"策略: {flow_state}"

    def _should_adjust_by_history(self, flow_state):
        valid_states = {'boredom', 'flow', 'challenge', 'anxiety', 'fatigue'}
        
        if flow_state not in valid_states:
            return False
        
        self.flow_state_history.append(flow_state)
        if len(self.flow_state_history) > 5:
            self.flow_state_history.popleft()
        
        if self.last_state is not None and flow_state == self.last_state:
            self.consecutive_same_state += 1
        else:
            self.consecutive_same_state = 1
        
        self.last_state = flow_state
        
        if self.consecutive_same_state >= 3:
            return True
        
        state_counter = Counter(self.flow_state_history)
        dominant_state, count = state_counter.most_common(1)[0]
        if len(self.flow_state_history) >= 4 and count >= 3 and dominant_state == flow_state:
            return True
        
        return False

    def _apply_difficulty_adjustment(self, adjustment, reason, safety_rules, is_game_running, flow_state=None):
        current_time = time.time()
        time_since_last_adjust = current_time - self.last_adjust_time
        
        is_increase = adjustment > 0
        is_excellent_performance = "表现优异" in reason
        is_safety_collapse = safety_rules['accuracy_collapse']
        
        effective_cooldown = 8 if is_increase else 15
        within_cooldown = time_since_last_adjust < effective_cooldown
        
        should_adjust = False
        if is_game_running:
            if is_excellent_performance or is_safety_collapse:
                should_adjust = not within_cooldown
            elif flow_state:
                should_adjust = self._should_adjust_by_history(flow_state) and not within_cooldown
        
        if not is_game_running:
            adjustment = 0
            reason = "游戏未进行中"
        elif within_cooldown and not is_excellent_performance and not is_safety_collapse:
            adjustment = 0
            reason = f"冷却中: 还需{int(effective_cooldown - time_since_last_adjust)}秒"
        
        adjustment_made = False
        if should_adjust:
            target_difficulty = self.current_difficulty + adjustment
            target_difficulty = max(self.min_difficulty, min(self.max_difficulty, target_difficulty))
            
            diff = target_difficulty - self.current_difficulty
            if abs(diff) > self.max_single_adjustment:
                target_difficulty = self.current_difficulty + (self.max_single_adjustment if diff > 0 else -self.max_single_adjustment)
            
            if target_difficulty != self.current_difficulty:
                self.current_difficulty = target_difficulty
                self.ema_difficulty = float(self.current_difficulty)
                self.last_adjust_time = current_time
                adjustment_made = True
        
        return adjustment, reason, adjustment_made, should_adjust

    def update(self, physiology_data, emotion_data, game_data):
        hr_valid = physiology_data.get('hr_valid', False)
        hrr_pct = physiology_data.get('hrr_pct', 0) or 0
        hr_slope = physiology_data.get('hr_slope', 0) or 0
        hr_age = physiology_data.get('hr_age', 0) or float('inf')
        
        emotion = emotion_data.get('emotion', 'neutral')
        emotion_confidence = emotion_data.get('confidence', 0) or 0
        face_detected = emotion_data.get('face_detected', True)
        face_count = emotion_data.get('face_count', 1)
        self._current_emotion = emotion
        
        game_status = game_data.get('status', 'idle')
        results = game_data.get('results', [])
        
        if results:
            for result in results:
                seq = result.get('seq', None)
                time_val = result.get('time', 0)
                if not isinstance(time_val, int):
                    time_val = 0
                q_data = {
                    'seq': seq,
                    'type': result.get('type', 'miss'),
                    'time': time_val,
                    'difficulty': result.get('difficulty', 1),
                    'score': result.get('score', 0)
                }
                
                if seq is not None and seq in self.processed_seqs:
                    continue
                
                if q_data['type'] in ['hit', 'miss', 'error', 'bomb']:
                    if seq is not None:
                        self.processed_seqs.add(seq)
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
        want_continue = self.estimate_want_continue(hr_valid, hrr_pct, emotion_confidence, face_detected, face_count)
        flow_state = self.estimate_flow_state(can_continue['state'], want_continue['state'])
        
        safety_rules = self._check_safety_rules(hr_valid, hrr_pct)
        
        adjustment, reason = self.get_difficulty_adjustment(flow_state, safety_rules, can_continue['components'])
        
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
        hr_valid = unified.get('hr_valid', False)
        hrr_pct = unified.get('hrr_pct', 0) or 0
        hr_slope = unified.get('hr_slope', 0) or 0
        hr_age = unified.get('hr_age', 0) or float('inf')
        
        emotion = unified.get('emotion', 'neutral')
        emotion_confidence = unified.get('confidence', 0) or 0
        face_detected = unified.get('face_detected', True)
        face_count = unified.get('face_count', 1)
        self._current_emotion = emotion
        
        difficulty = unified.get('difficulty', 1)
        game_status = unified.get('game_status', 'idle')
        
        results = unified.get('results', [])
        if results:
            for result in results:
                seq = result.get('seq', None)
                time_val = result.get('time', 0)
                if not isinstance(time_val, int):
                    time_val = 0
                q_data = {
                    'seq': seq,
                    'type': result.get('type', 'miss'),
                    'time': time_val,
                    'difficulty': result.get('difficulty', difficulty),
                    'score': result.get('score', 0)
                }
                
                if seq is not None and seq in self.processed_seqs:
                    continue
                
                if q_data['type'] in ['hit', 'miss', 'error', 'bomb']:
                    if seq is not None:
                        self.processed_seqs.add(seq)
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
        want_continue = self.estimate_want_continue(hr_valid, hrr_pct, emotion_confidence, face_detected, face_count)
        flow_state = self.estimate_flow_state(can_continue['state'], want_continue['state'])
        
        safety_rules = self._check_safety_rules(hr_valid, hrr_pct)
        
        adjustment, reason = self.get_difficulty_adjustment(flow_state, safety_rules, can_continue['components'])
        
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
        adjustment, reason, adjustment_made, should_adjust = self._apply_difficulty_adjustment(adjustment, reason, safety_rules, is_game_running, flow_state)
        
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