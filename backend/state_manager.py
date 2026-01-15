import time
from datetime import datetime
import json
import os

class StateManager:
    def __init__(self):
        self.is_training = False
        self.current_mode = None
        self.difficulty = "medium"
        
        self.training_start_time = None
        self.training_duration = 0
        
        self.score = 0
        self.correct_count = 0
        self.total_count = 0
        self.correct_rate = 0.0
        
        self.physiological_state = {}
        self.interaction_state = {}
        self.fused_state = {}
        
        self.training_history = []
        # 使用绝对路径保存历史数据
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_history.json")
        
        self.load_history()
    
    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.training_history = json.load(f)
                print(f"[状态管理] 加载训练历史: {len(self.training_history)} 条记录")
            except Exception as e:
                print(f"[状态管理] 加载历史失败: {e}")
                self.training_history = []
    
    def save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.training_history, f, ensure_ascii=False, indent=2)
            print(f"[状态管理] 保存训练历史: {len(self.training_history)} 条记录")
        except Exception as e:
            print(f"[状态管理] 保存历史失败: {e}")
    
    def start_training(self, mode="memory_game", difficulty="medium"):
        self.is_training = True
        self.current_mode = mode
        self.difficulty = difficulty
        self.training_start_time = time.time()
        
        self.score = 0
        self.correct_count = 0
        self.total_count = 0
        self.correct_rate = 0.0
        
        print(f"[状态管理] 开始训练: 模式={mode}, 难度={difficulty}")
        
        return {
            "status": "success",
            "mode": self.current_mode,
            "difficulty": self.difficulty
        }
    
    def stop_training(self):
        if not self.is_training:
            return {"status": "not_training"}
        
        self.training_duration = int(time.time() - self.training_start_time)
        
        session_data = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": self.current_mode,
            "difficulty": self.difficulty,
            "duration": self.training_duration,
            "score": self.score,
            "correct_count": self.correct_count,
            "total_count": self.total_count,
            "correct_rate": self.correct_rate,
            "avg_bpm": self.physiological_state.get("bpm", "--"),
            "avg_emotion": self.physiological_state.get("emotion", "neutral")
        }
        
        self.training_history.append(session_data)
        self.save_history()
        
        self.is_training = False
        
        print(f"[状态管理] 训练结束: 时长={self.training_duration}秒, 得分={self.score}, 正确率={self.correct_rate:.2%}")
        
        return session_data
    
    def update_score(self, correct):
        if not self.is_training:
            return
        
        self.total_count += 1
        if correct:
            self.correct_count += 1
            self.score += 10
        else:
            self.score = max(0, self.score - 5)
        
        self.correct_rate = self.correct_count / self.total_count if self.total_count > 0 else 0.0
        
        print(f"[状态管理] 更新得分: 总数={self.total_count}, 正确={self.correct_count}, 得分={self.score}")
    
    def update_physiological_state(self, state):
        self.physiological_state = state.copy()
        print(f"[状态管理] 生理状态: BPM={state.get('bpm', '--')}, 情绪={state.get('emotion', '--')}")
        
        if self.is_training:
            self.adjust_difficulty()
    
    def update_interaction_state(self, state):
        self.interaction_state = state.copy()
        print(f"[状态管理] 交互状态: 手势={state.get('gesture', '--')}, 目标={state.get('interaction_target', '--')}")
    
    def adjust_difficulty(self):
        bpm = self.physiological_state.get("bpm", "--")
        emotion = self.physiological_state.get("emotion", "neutral")
        fatigue = self.physiological_state.get("fatigue_level", "unknown")
        activity = self.interaction_state.get("activity_level", "none")
        
        old_difficulty = self.difficulty
        new_difficulty = self.difficulty
        
        if bpm != "--":
            if bpm > 90:
                new_difficulty = "low"
            elif bpm < 60:
                new_difficulty = "high"
            else:
                new_difficulty = "medium"
        
        if emotion in ["sad", "tired"]:
            new_difficulty = "low"
        elif emotion in ["happy", "excited"]:
            new_difficulty = "high"
        
        if fatigue == "high":
            new_difficulty = "low"
        
        if activity == "high":
            new_difficulty = "high"
        elif activity == "low":
            new_difficulty = "low"
        
        if new_difficulty != old_difficulty:
            print(f"[状态管理] 难度调整: {old_difficulty} → {new_difficulty}")
            self.difficulty = new_difficulty
    
    def get_training_status(self):
        if self.is_training:
            self.training_duration = int(time.time() - self.training_start_time)
        
        return {
            "is_training": self.is_training,
            "current_mode": self.current_mode,
            "difficulty": self.difficulty,
            "score": self.score,
            "correct_rate": round(self.correct_rate, 2),
            "duration": self.training_duration
        }
    
    def get_physiological_state(self):
        return self.physiological_state.copy()
    
    def get_interaction_state(self):
        return self.interaction_state.copy()
    
    def get_fused_state(self):
        health_score = self.calculate_health_score()
        engagement_score = self.calculate_engagement_score()
        
        self.fused_state = {
            "health_score": health_score,
            "health_status": "good" if health_score > 0.7 else "moderate" if health_score > 0.4 else "poor",
            "engagement_score": engagement_score,
            "engagement_status": "high" if engagement_score > 0.7 else "medium" if engagement_score > 0.4 else "low",
            "recommended_action": self.generate_recommendation()
        }
        
        return self.fused_state.copy()
    
    def calculate_health_score(self):
        bpm = self.physiological_state.get("bpm", "--")
        fatigue = self.physiological_state.get("fatigue_level", "unknown")
        emotion = self.physiological_state.get("emotion", "neutral")
        
        if bpm == "--":
            bpm_score = 0.5
        else:
            baseline_bpm = 70
            bpm_deviation = abs(bpm - baseline_bpm) / baseline_bpm
            bpm_score = max(0, 1 - bpm_deviation * 2)
        
        fatigue_scores = {
            "low": 1.0,
            "medium": 0.7,
            "high": 0.3,
            "unknown": 0.5
        }
        fatigue_score = fatigue_scores.get(fatigue, 0.5)
        
        emotion_scores = {
            "happy": 1.0,
            "neutral": 0.8,
            "surprise": 0.7,
            "sad": 0.4,
            "angry": 0.3,
            "fear": 0.3,
            "disgust": 0.3
        }
        emotion_score = emotion_scores.get(emotion, 0.5)
        
        health_score = (
            0.3 * bpm_score +
            0.3 * fatigue_score +
            0.4 * emotion_score
        )
        
        return round(health_score, 2)
    
    def calculate_engagement_score(self):
        attention = self.physiological_state.get("attention_score", 0.5)
        activity = self.interaction_state.get("activity_level", "none")
        gesture = self.interaction_state.get("gesture", "none")
        interaction_target = self.interaction_state.get("interaction_target", None)
        
        activity_scores = {
            "high": 1.0,
            "medium": 0.8,
            "low": 0.5,
            "none": 0.2
        }
        activity_score = activity_scores.get(activity, 0.5)
        
        gesture_scores = {
            "pointing": 1.0,
            "open_hand": 0.9,
            "victory": 0.8,
            "fist": 0.6,
            "unknown": 0.4,
            "none": 0.2
        }
        gesture_score = gesture_scores.get(gesture, 0.5)
        
        interaction_score = 0.8 if interaction_target else 0.3
        
        engagement_score = (
            0.3 * attention +
            0.3 * activity_score +
            0.2 * gesture_score +
            0.2 * interaction_score
        )
        
        return round(engagement_score, 2)
    
    def generate_recommendation(self):
        health_score = self.calculate_health_score()
        engagement_score = self.calculate_engagement_score()
        
        if health_score < 0.4:
            return {
                "action": "reduce_intensity",
                "reason": "健康状态不佳，建议降低训练强度",
                "priority": "high"
            }
        
        if engagement_score < 0.4:
            return {
                "action": "increase_engagement",
                "reason": "参与度较低，建议增加互动元素",
                "priority": "high"
            }
        
        if health_score > 0.7 and engagement_score > 0.7:
            return {
                "action": "increase_difficulty",
                "reason": "状态良好，可以适当增加难度",
                "priority": "medium"
            }
        
        return {
            "action": "maintain_current",
            "reason": "状态正常，继续当前活动",
            "priority": "low"
        }
    
    def get_training_history(self, limit=10):
        return self.training_history[-limit:] if len(self.training_history) > limit else self.training_history
    
    def reset(self):
        self.is_training = False
        self.current_mode = None
        self.difficulty = "medium"
        self.score = 0
        self.correct_count = 0
        self.total_count = 0
        self.correct_rate = 0.0
        print("[状态管理] 系统已重置")
