# -*- coding: utf-8 -*-
"""
训练分析系统 - 实时追踪训练数据，智能调整难度
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class TrialRecord:
    """单次答题记录"""
    trial_id: int
    timestamp: str
    module: str
    difficulty: int
    question_type: str  # 'go' 或 'no_go'
    is_correct: bool
    reaction_time_ms: float  # 反应时间（毫秒）
    target_zone: int
    selected_zone: int


@dataclass
class SessionRecord:
    """单次训练会话记录"""
    session_id: str
    start_time: str
    end_time: Optional[str]
    game_type: str
    module: str
    difficulty_history: List[Dict]  # 难度变化历史
    trials: List[TrialRecord]
    final_score: int
    final_accuracy: float
    total_trials: int
    correct_trials: int
    avg_reaction_time_ms: float
    min_difficulty: int  # 最低难度
    max_difficulty: int  # 最高难度


@dataclass
class RoundRecord:
    """单轮游戏记录（每次结算记录一次）"""
    round_id: str
    session_id: str
    timestamp: str
    game_type: str
    module: str
    score: int
    total_trials: int
    correct_trials: int
    accuracy: float
    min_difficulty: int
    max_difficulty: int
    avg_reaction_time_ms: float


class TrainingAnalytics:
    """训练分析器 - 记录详细训练数据，智能调整难度"""

    # 目标准确率区间（60%-85%）
    TARGET_ACCURACY_MIN = 0.60
    TARGET_ACCURACY_MAX = 0.85

    # 难度调整阈值
    ADJUST_THRESHOLD = 5  # 每5题评估一次

    # 时间尺度定义
    SHORT_TERM_DAYS = 7  # 短期趋势（7天）
    LONG_TERM_DAYS = 30  # 长期趋势（30天）

    def __init__(self, data_dir: str = "./core"):
        self.data_dir = data_dir
        self.data_storage_dir = os.path.join(data_dir, "data")
        self.summary_file = os.path.join(self.data_storage_dir, "training_summary.json")
        self.history_file = os.path.join(data_dir, "training_history.json")  # 兼容旧格式

        # 确保数据存储目录存在
        if not os.path.exists(self.data_storage_dir):
            try:
                os.makedirs(self.data_storage_dir)
                print(f"[TrainingAnalytics] 创建数据存储目录: {self.data_storage_dir}")
            except Exception as e:
                print(f"[TrainingAnalytics] 创建数据存储目录失败: {e}")

        # 当前会话数据
        self.current_session: Optional[SessionRecord] = None
        self.current_session_file: Optional[str] = None
        self.recent_accuracy_window = deque(maxlen=10)  # 最近10题的准确率

        # 难度表现记录（每个难度等级的准确率）
        self.difficulty_performance = {}
        for level in range(1, 9):
            self.difficulty_performance[level] = {
                'total': 0,
                'correct': 0,
                'accuracy': 0
            }

        # 最佳难度记录
        self.best_difficulty = 3
        self.best_accuracy = 0

        # 加载历史数据
        self.sessions: List[SessionRecord] = self._load_sessions()
        self.summary_data: List[Dict] = self._load_summary()
        
        # 初始化难度表现数据
        self._initialize_difficulty_performance()
        
    def _load_sessions(self) -> List[SessionRecord]:
        """加载所有会话数据"""
        sessions = []
        if not os.path.exists(self.data_storage_dir):
            return sessions
        
        # 遍历数据目录中的所有会话文件
        for filename in os.listdir(self.data_storage_dir):
            if filename.endswith('.json') and not filename == 'training_summary.json':
                file_path = os.path.join(self.data_storage_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict) and 'session_id' in data:
                            sessions.append(self._dict_to_session(data))
                except Exception as e:
                    print(f"[TrainingAnalytics] 加载会话文件 {filename} 失败: {e}")
        
        return sessions
    
    def _load_summary(self) -> List[Dict]:
        """加载汇总数据"""
        if os.path.exists(self.summary_file):
            try:
                with open(self.summary_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        return []
                    data = json.loads(content)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"[TrainingAnalytics] 加载汇总文件失败: {e}")
        return []
    
    def _dict_to_session(self, data: Dict) -> SessionRecord:
        """字典转 SessionRecord"""
        trials = [TrialRecord(**t) for t in data.get('trials', [])]
        # 从难度历史中提取最低和最高难度（兼容旧数据）
        difficulty_history = data.get('difficulty_history', [])
        if difficulty_history:
            difficulties = [d['difficulty'] for d in difficulty_history]
            min_difficulty = min(difficulties)
            max_difficulty = max(difficulties)
        else:
            min_difficulty = 3
            max_difficulty = 3
        return SessionRecord(
            session_id=data['session_id'],
            start_time=data['start_time'],
            end_time=data.get('end_time'),
            game_type=data['game_type'],
            module=data['module'],
            difficulty_history=difficulty_history,
            trials=trials,
            final_score=data.get('final_score', 0),
            final_accuracy=data.get('final_accuracy', 0),
            total_trials=data.get('total_trials', 0),
            correct_trials=data.get('correct_trials', 0),
            avg_reaction_time_ms=data.get('avg_reaction_time_ms', 0),
            min_difficulty=data.get('min_difficulty', min_difficulty),
            max_difficulty=data.get('max_difficulty', max_difficulty)
        )
    
    def start_session(self, game_type: str, module: str, initial_difficulty: int):
        """开始新的训练会话"""
        # 使用最佳难度作为初始难度，如果没有最佳难度则使用提供的初始难度
        actual_initial_difficulty = self.best_difficulty if self.best_difficulty > 0 else initial_difficulty
        
        # 创建会话记录
        session_id = f"{game_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_session = SessionRecord(
            session_id=session_id,
            start_time=datetime.now().isoformat(),
            end_time=None,
            game_type=game_type,
            module=module,
            difficulty_history=[{
                'timestamp': datetime.now().isoformat(),
                'difficulty': actual_initial_difficulty,
                'reason': '基于历史表现的最佳初始难度' if self.best_difficulty > 0 else '初始难度'
            }],
            trials=[],
            final_score=0,
            final_accuracy=0.0,
            total_trials=0,
            correct_trials=0,
            avg_reaction_time_ms=0.0,
            min_difficulty=actual_initial_difficulty,
            max_difficulty=actual_initial_difficulty
        )
        
        # 创建会话文件
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.current_session_file = os.path.join(self.data_storage_dir, f"session_{timestamp}.json")
        
        # 保存初始会话数据
        self._save_current_session()
        
        # 重置trial计数器
        self._trial_counter = 0
        self.recent_accuracy_window.clear()
        print(f"[TrainingAnalytics] 开始训练会话: {self.current_session.session_id}")
        print(f"[TrainingAnalytics] 会话文件: {self.current_session_file}")
    
    def record_trial(self, trial_data: Dict) -> Tuple[bool, int]:
        """
        记录单次答题
        返回: (是否需要调整难度, 建议的新难度)
        """
        if not self.current_session:
            return False, self.best_difficulty  # 使用最佳难度作为默认值
        
        # 创建答题记录 - 使用自增计数器确保trial_id唯一
        if not hasattr(self, '_trial_counter'):
            self._trial_counter = 0
        self._trial_counter += 1
        
        trial = TrialRecord(
            trial_id=self._trial_counter,
            timestamp=datetime.now().isoformat(),
            module=trial_data.get('module', 'unknown'),
            difficulty=trial_data.get('difficulty', 3),
            question_type=trial_data.get('question_type', 'go'),
            is_correct=trial_data.get('is_correct', False),
            reaction_time_ms=trial_data.get('reaction_time_ms', 0),
            target_zone=trial_data.get('target_zone', 0),
            selected_zone=trial_data.get('selected_zone', 0)
        )
        
        self.current_session.trials.append(trial)
        self.recent_accuracy_window.append(1 if trial.is_correct else 0)
        
        # 更新难度表现数据
        self._update_difficulty_performance(trial.difficulty, trial.is_correct)
        self._calculate_best_difficulty()
        
        # 更新会话统计
        self._update_session_stats()
        
        # 检查是否需要调整难度
        should_adjust, new_difficulty = self._evaluate_difficulty_adjustment()
        
        if should_adjust:
            self.current_session.difficulty_history.append({
                'timestamp': datetime.now().isoformat(),
                'difficulty': new_difficulty,
                'reason': f'准确率 {self._get_recent_accuracy():.1%}，自动调整'
            })
            print(f"[TrainingAnalytics] 难度调整: {trial.difficulty} -> {new_difficulty}")
        
        # 保存会话数据（每答1题就更新一次）
        self._save_current_session()
        
        return should_adjust, new_difficulty
    
    def _update_session_stats(self):
        """更新会话统计"""
        if not self.current_session:
            return

        trials = self.current_session.trials
        if not trials:
            return

        self.current_session.total_trials = len(trials)
        self.current_session.correct_trials = sum(1 for t in trials if t.is_correct)
        self.current_session.final_accuracy = (
            self.current_session.correct_trials / self.current_session.total_trials
        )
        self.current_session.avg_reaction_time_ms = sum(
            t.reaction_time_ms for t in trials
        ) / len(trials)

        # 更新最低和最高难度
        difficulties = [t.difficulty for t in trials]
        if difficulties:
            self.current_session.min_difficulty = min(difficulties)
            self.current_session.max_difficulty = max(difficulties)
    
    def _get_recent_accuracy(self) -> float:
        """获取最近答题的准确率"""
        if not self.recent_accuracy_window:
            return 0.5
        return sum(self.recent_accuracy_window) / len(self.recent_accuracy_window)
    
    def _evaluate_difficulty_adjustment(self) -> Tuple[bool, int]:
        """评估是否需要调整难度 - 多尺度调整策略"""
        if not self.current_session:
            return False, self.best_difficulty
        
        # 只有答了足够多题才调整
        if len(self.current_session.trials) < self.ADJUST_THRESHOLD:
            return False, self.current_session.trials[-1].difficulty if self.current_session.trials else self.best_difficulty
        
        recent_accuracy = self._get_recent_accuracy()
        current_difficulty = self.current_session.trials[-1].difficulty if self.current_session.trials else 3
        
        # 获取短期和长期表现
        short_term_perf = self._get_short_term_performance()
        long_term_perf = self._get_long_term_performance()
        
        # 当前难度的短期和长期准确率
        current_short_term_accuracy = short_term_perf.get(current_difficulty, 0)
        current_long_term_accuracy = long_term_perf.get(current_difficulty, 0)
        
        # 多尺度调整策略
        # 1. 单题表现（最近5题）
        # 2. 单次训练表现（当前会话）
        # 3. 短期趋势（7天）
        # 4. 长期趋势（30天）
        
        adjustment = 0
        
        # 单题表现调整
        if recent_accuracy > self.TARGET_ACCURACY_MAX:
            adjustment += 1
        elif recent_accuracy < self.TARGET_ACCURACY_MIN:
            adjustment -= 1
        
        # 短期趋势调整（如果有足够数据）
        if current_short_term_accuracy > 0:
            if current_short_term_accuracy > self.TARGET_ACCURACY_MAX + 0.1:
                adjustment += 0.5
            elif current_short_term_accuracy < self.TARGET_ACCURACY_MIN - 0.1:
                adjustment -= 0.5
        
        # 长期趋势调整（如果有足够数据）
        if current_long_term_accuracy > 0:
            if current_long_term_accuracy > self.TARGET_ACCURACY_MAX:
                adjustment += 0.3
            elif current_long_term_accuracy < self.TARGET_ACCURACY_MIN:
                adjustment -= 0.3
        
        # 限制调整幅度为±1
        adjustment = max(-1, min(1, int(round(adjustment))))
        
        # 计算新难度
        new_difficulty = current_difficulty + adjustment
        new_difficulty = max(1, min(8, new_difficulty))
        
        # 检查是否需要调整
        should_adjust = new_difficulty != current_difficulty
        
        # 如果不需要调整，考虑是否使用最佳难度
        if not should_adjust and len(self.current_session.trials) >= 10:
            # 如果当前难度的表现不如最佳难度，考虑切换到最佳难度
            current_perf = self.difficulty_performance.get(current_difficulty, {'accuracy': 0})
            best_perf = self.difficulty_performance.get(self.best_difficulty, {'accuracy': 0})
            
            if best_perf['total'] >= 10 and best_perf['accuracy'] > current_perf['accuracy'] + 0.1:
                new_difficulty = self.best_difficulty
                should_adjust = True
        
        return should_adjust, new_difficulty

    def record_round(self, final_score: int) -> Optional[Dict]:
        """
        ⭐ 记录单轮游戏（每次结算时调用）
        返回: 轮次记录字典或 None
        """
        if not self.current_session:
            return None

        # 更新统计
        self._update_session_stats()

        # 创建轮次记录
        round_record = {
            'round_id': f"{self.current_session.session_id}_round",
            'session_id': self.current_session.session_id,
            'timestamp': datetime.now().isoformat(),
            'game_type': self.current_session.game_type,
            'module': self.current_session.module,
            'score': final_score,
            'total_trials': self.current_session.total_trials,
            'correct_trials': self.current_session.correct_trials,
            'accuracy': self.current_session.final_accuracy,
            'min_difficulty': self.current_session.min_difficulty,
            'max_difficulty': self.current_session.max_difficulty,
            'avg_reaction_time_ms': self.current_session.avg_reaction_time_ms
        }

        # 保存会话数据
        self._save_current_session()

        print(f"[TrainingAnalytics] 记录单轮游戏: {round_record['round_id']}")
        print(f"  - 得分: {round_record['score']}")
        print(f"  - 准确率: {round_record['accuracy']:.2%}")
        print(f"  - 总题数: {round_record['total_trials']}, 正确: {round_record['correct_trials']}")
        print(f"  - 难度范围: {round_record['min_difficulty']} - {round_record['max_difficulty']}")

        return round_record
    
    def delete_record(self, session_id: str) -> bool:
        """
        删除训练记录
        
        参数:
            session_id: 会话ID
            
        返回:
            是否删除成功
        """
        try:
            # 从会话列表中删除
            self.sessions = [s for s in self.sessions if s.session_id != session_id]
            
            # 从汇总数据中删除
            self.summary_data = [s for s in self.summary_data if s.get('session_id') != session_id]
            
            # 保存汇总数据
            with open(self.summary_file, 'w', encoding='utf-8') as f:
                json.dump(self.summary_data, f, ensure_ascii=False, indent=2)
            
            # 删除会话文件
            for filename in os.listdir(self.data_storage_dir):
                if filename.endswith('.json') and not filename == 'training_summary.json':
                    file_path = os.path.join(self.data_storage_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if data.get('session_id') == session_id:
                                os.remove(file_path)
                                print(f"[TrainingAnalytics] 删除会话文件: {filename}")
                                break
                    except Exception as e:
                        print(f"[TrainingAnalytics] 检查会话文件 {filename} 失败: {e}")
            
            # 重新初始化难度表现数据
            self._initialize_difficulty_performance()
            
            print(f"[TrainingAnalytics] 删除训练记录成功: {session_id}")
            return True
        except Exception as e:
            print(f"[TrainingAnalytics] 删除训练记录失败: {e}")
            return False

    def _save_current_session(self):
        """保存当前会话数据"""
        if not self.current_session or not self.current_session_file:
            return
        
        try:
            data = self._session_to_dict(self.current_session)
            with open(self.current_session_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TrainingAnalytics] 保存会话数据失败: {e}")
    
    def _update_summary(self):
        """更新汇总数据"""
        if not self.current_session:
            return
        
        # 计算详细统计数据
        total_trials = self.current_session.total_trials
        correct_trials = self.current_session.correct_trials
        incorrect_trials = total_trials - correct_trials
        
        # 计算遗漏个数（超时未答的题目）
        missed_trials = sum(1 for t in self.current_session.trials if t.selected_zone is None)
        
        # 创建汇总记录
        summary_record = {
            'session_id': self.current_session.session_id,
            'timestamp': self.current_session.start_time,
            'game_type': self.current_session.game_type,
            'module': self.current_session.module,
            'difficulty_range': f"{self.current_session.min_difficulty}-{self.current_session.max_difficulty}",
            'score': self.current_session.final_score,
            'total_trials': total_trials,
            'correct_trials': correct_trials,
            'incorrect_trials': incorrect_trials,
            'missed_trials': missed_trials,
            'accuracy': self.current_session.final_accuracy,
            'avg_reaction_time_ms': self.current_session.avg_reaction_time_ms,
            'duration': self._calc_duration(self.current_session)
        }
        
        # 添加到汇总数据
        self.summary_data.append(summary_record)
        
        # 保存汇总数据
        try:
            with open(self.summary_file, 'w', encoding='utf-8') as f:
                json.dump(self.summary_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TrainingAnalytics] 保存汇总数据失败: {e}")
    
    def end_session(self, final_score: int):
        """结束训练会话"""
        if not self.current_session:
            return

        self.current_session.end_time = datetime.now().isoformat()
        self.current_session.final_score = final_score
        self._update_session_stats()

        # 保存最终会话数据
        self._save_current_session()
        
        # 更新汇总数据
        self._update_summary()
        
        # 保存到历史
        self.sessions.append(self.current_session)
        self._save_summary_history()  # 兼容旧格式

        print(f"[TrainingAnalytics] 训练会话结束: {self.current_session.session_id}")
        print(f"  - 总题数: {self.current_session.total_trials}")
        print(f"  - 准确率: {self.current_session.final_accuracy:.2%}")
        print(f"  - 平均反应时间: {self.current_session.avg_reaction_time_ms:.0f}ms")
        print(f"  - 难度范围: {self.current_session.min_difficulty} - {self.current_session.max_difficulty}")
        print(f"  - 正确: {self.current_session.correct_trials}, 错误: {self.current_session.total_trials - self.current_session.correct_trials}")

        self.current_session = None
        self.current_session_file = None
    

    
    def _save_summary_history(self):
        """保存摘要历史（兼容旧格式）"""
        try:
            summary = []
            for s in self.sessions:
                summary.append({
                    'date': s.start_time,
                    'mode': s.game_type,
                    'module': s.module,
                    'difficulty': s.difficulty_history[-1]['difficulty'] if s.difficulty_history else 3,
                    'duration': self._calc_duration(s),
                    'score': s.final_score,
                    'correct_count': s.correct_trials,
                    'total_count': s.total_trials,
                    'correct_rate': s.final_accuracy,
                    'avg_bpm': '--',
                    'avg_emotion': 'neutral'
                })
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TrainingAnalytics] 保存摘要历史失败: {e}")
    
    def _session_to_dict(self, session: SessionRecord) -> Dict:
        """SessionRecord 转字典"""
        return {
            'session_id': session.session_id,
            'start_time': session.start_time,
            'end_time': session.end_time,
            'game_type': session.game_type,
            'module': session.module,
            'difficulty_history': session.difficulty_history,
            'trials': [asdict(t) for t in session.trials],
            'final_score': session.final_score,
            'final_accuracy': session.final_accuracy,
            'total_trials': session.total_trials,
            'correct_trials': session.correct_trials,
            'avg_reaction_time_ms': session.avg_reaction_time_ms,
            'min_difficulty': session.min_difficulty,
            'max_difficulty': session.max_difficulty
        }

    def _initialize_difficulty_performance(self):
        """基于历史数据初始化难度表现记录"""
        # 遍历所有历史会话的所有试次
        for session in self.sessions:
            for trial in session.trials:
                self._update_difficulty_performance(trial.difficulty, trial.is_correct)
        
        # 计算最佳难度
        self._calculate_best_difficulty()
        print(f"[TrainingAnalytics] 难度表现初始化完成，最佳难度: {self.best_difficulty}")
    
    def _update_difficulty_performance(self, difficulty: int, correct: bool):
        """更新难度表现记录"""
        if difficulty in self.difficulty_performance:
            perf = self.difficulty_performance[difficulty]
            perf['total'] += 1
            if correct:
                perf['correct'] += 1
            perf['accuracy'] = perf['correct'] / perf['total'] if perf['total'] > 0 else 0
    
    def _calculate_best_difficulty(self):
        """计算最佳难度"""
        best_accuracy = 0
        best_difficulty = 3
        
        for level, perf in self.difficulty_performance.items():
            # 只考虑有足够数据的难度等级（至少10题）
            if perf['total'] >= 10 and perf['accuracy'] > best_accuracy:
                # 优先选择在目标准确率区间内的难度
                if self.TARGET_ACCURACY_MIN <= perf['accuracy'] <= self.TARGET_ACCURACY_MAX:
                    best_accuracy = perf['accuracy']
                    best_difficulty = level
        
        if best_accuracy > 0:
            self.best_accuracy = best_accuracy
            self.best_difficulty = best_difficulty
    
    def _get_short_term_performance(self) -> Dict[int, float]:
        """获取短期（7天）难度表现"""
        today = datetime.now().date()
        short_term_start = today - timedelta(days=self.SHORT_TERM_DAYS)
        
        performance = {}
        for level in range(1, 9):
            performance[level] = {'total': 0, 'correct': 0}
        
        # 统计短期数据
        for session in self.sessions:
            session_date = datetime.fromisoformat(session.start_time).date()
            if short_term_start <= session_date <= today:
                for trial in session.trials:
                    if trial.difficulty in performance:
                        performance[trial.difficulty]['total'] += 1
                        if trial.is_correct:
                            performance[trial.difficulty]['correct'] += 1
        
        # 计算准确率
        short_term_accuracy = {}
        for level, data in performance.items():
            if data['total'] > 0:
                short_term_accuracy[level] = data['correct'] / data['total']
            else:
                short_term_accuracy[level] = 0
        
        return short_term_accuracy
    
    def _get_long_term_performance(self) -> Dict[int, float]:
        """获取长期（30天）难度表现"""
        today = datetime.now().date()
        long_term_start = today - timedelta(days=self.LONG_TERM_DAYS)
        
        performance = {}
        for level in range(1, 9):
            performance[level] = {'total': 0, 'correct': 0}
        
        # 统计长期数据
        for session in self.sessions:
            session_date = datetime.fromisoformat(session.start_time).date()
            if long_term_start <= session_date <= today:
                for trial in session.trials:
                    if trial.difficulty in performance:
                        performance[trial.difficulty]['total'] += 1
                        if trial.is_correct:
                            performance[trial.difficulty]['correct'] += 1
        
        # 计算准确率
        long_term_accuracy = {}
        for level, data in performance.items():
            if data['total'] > 0:
                long_term_accuracy[level] = data['correct'] / data['total']
            else:
                long_term_accuracy[level] = 0
        
        return long_term_accuracy
    
    def _load_rounds_history(self) -> List[RoundRecord]:
        """加载轮次历史"""
        if os.path.exists(self.rounds_file):
            try:
                with open(self.rounds_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        return []
                    data = json.loads(content)
                    if not isinstance(data, list):
                        return []
                    return [RoundRecord(**r) for r in data]
            except Exception as e:
                print(f"[TrainingAnalytics] 加载轮次历史失败: {e}")
                return []
        return []

    def _save_rounds_history(self):
        """保存轮次历史"""
        try:
            data = [asdict(r) for r in self.rounds]
            with open(self.rounds_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TrainingAnalytics] 保存轮次历史失败: {e}")
    
    def _calc_duration(self, session: SessionRecord) -> int:
        """计算训练时长（秒）"""
        if not session.end_time:
            return 0
        try:
            start = datetime.fromisoformat(session.start_time)
            end = datetime.fromisoformat(session.end_time)
            return int((end - start).total_seconds())
        except:
            return 0
    
    # ==================== 统计查询接口 ====================
    
    def get_daily_stats(self) -> Dict:
        """获取今日统计"""
        today = datetime.now().date()
        today_sessions = [
            s for s in self.sessions
            if datetime.fromisoformat(s.start_time).date() == today
        ]
        return self._calc_stats(today_sessions)
    
    def get_weekly_stats(self) -> Dict:
        """获取本周统计"""
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        week_sessions = [
            s for s in self.sessions
            if week_ago <= datetime.fromisoformat(s.start_time).date() <= today
        ]
        return self._calc_stats(week_sessions)
    
    def get_monthly_stats(self) -> Dict:
        """获取本月统计"""
        today = datetime.now().date()
        month_ago = today - timedelta(days=30)
        month_sessions = [
            s for s in self.sessions
            if month_ago <= datetime.fromisoformat(s.start_time).date() <= today
        ]
        return self._calc_stats(month_sessions)
    
    def _calc_stats(self, sessions: List[SessionRecord]) -> Dict:
        """计算统计数据"""
        if not sessions:
            return {
                'count': 0,
                'total_trials': 0,
                'avg_accuracy': 0,
                'avg_reaction_time': 0,
                'total_duration': 0
            }
        
        total_trials = sum(s.total_trials for s in sessions)
        total_correct = sum(s.correct_trials for s in sessions)
        
        return {
            'count': len(sessions),
            'total_trials': total_trials,
            'avg_accuracy': (total_correct / total_trials) if total_trials > 0 else 0,
            'avg_reaction_time': sum(s.avg_reaction_time_ms for s in sessions) / len(sessions),
            'total_duration': sum(self._calc_duration(s) for s in sessions)
        }
    
    def get_accuracy_trend(self, days: int = 7) -> List[Dict]:
        """获取准确率趋势（用于图表）"""
        today = datetime.now().date()
        trend = []
        
        for i in range(days - 1, -1, -1):
            date = today - timedelta(days=i)
            day_sessions = [
                s for s in self.sessions
                if datetime.fromisoformat(s.start_time).date() == date
            ]
            
            if day_sessions:
                total_trials = sum(s.total_trials for s in day_sessions)
                total_correct = sum(s.correct_trials for s in day_sessions)
                accuracy = total_correct / total_trials if total_trials > 0 else 0
            else:
                accuracy = 0
            
            trend.append({
                'date': date.strftime('%m-%d'),
                'accuracy': round(accuracy * 100, 1),
                'count': len(day_sessions)
            })
        
        return trend


# 全局实例
_analytics = None

def init_training_analytics(data_dir: str = "./core") -> TrainingAnalytics:
    """初始化训练分析器"""
    global _analytics
    _analytics = TrainingAnalytics(data_dir)
    return _analytics

def get_training_analytics() -> TrainingAnalytics:
    """获取训练分析器实例"""
    return _analytics
