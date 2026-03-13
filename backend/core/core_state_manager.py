# core/core_state_manager.py
# 世界模型 - 系统状态管理器

import time
from datetime import datetime
from typing import Dict, Any


class SystemStateManager:
    """系统状态管理器 - 世界模型"""
    
    def __init__(self, socketio=None):
        self.socketio = socketio
        self.current_page = "/"
        
        # 世界状态
        self.world_state = {
            "time": datetime.now().strftime("%H:%M"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "weekday": ["一","二","三","四","五","六","日"][datetime.now().weekday()],
            
            "elder": {
                "activity": "unknown",
                "mood": "neutral",
                "attention": 0.5,
                "fatigue": 0.0,
                "last_interaction": "",
                "idle_minutes": 0,
                "speaking": False,
                "activity_changed": False,
            },
            
            "environment": {
                "light_level": "normal",
                "person_present": False,
                "person_count": 0,
            },
            
            "system": {
                "current_page": "/",
                "active_game": None,
                "recent_actions": []
            }
        }
        
        # 用户偏好
        self.user_preferences = {
            "favorite_music": ["京剧", "民歌"],
            "favorite_movies": ["地道战", "地雷战"],
            "favorite_games": ["打地鼠"],
        }
        
        self._last_activity_time = time.time()
        self._last_activity = "unknown"
    
    def update_world(self, perception_data: dict):
        """更新世界状态"""
        if not perception_data:
            return
        
        # 更新时间
        self.world_state["time"] = datetime.now().strftime("%H:%M")
        self.world_state["date"] = datetime.now().strftime("%Y-%m-%d")
        
        # 更新老人状态
        elder = self.world_state["elder"]
        
        # 活动状态
        body = perception_data.get("body_state", {})
        new_activity = body.get("posture", "unknown")
        if new_activity != elder["activity"]:
            elder["activity_changed"] = True
            elder["activity"] = new_activity
        else:
            elder["activity_changed"] = False
        
        # 情绪
        emotion = perception_data.get("emotion", {})
        elder["mood"] = emotion.get("primary", "neutral")
        
        # 注意力
        eye = perception_data.get("eye_state", {})
        elder["attention"] = eye.get("attention_score", 0.5)
        
        # 疲劳度
        overall = perception_data.get("overall", {})
        elder["fatigue"] = overall.get("fatigue_level", 0.0)
        
        # 空闲时间
        if elder["speaking"] or elder["activity_changed"]:
            self._last_activity_time = time.time()
        elder["idle_minutes"] = (time.time() - self._last_activity_time) / 60
        
        # 更新环境状态
        env = perception_data.get("environment", {})
        self.world_state["environment"]["person_present"] = env.get("person_present", False)
        self.world_state["environment"]["person_count"] = env.get("person_count", 0)
        self.world_state["environment"]["light_level"] = env.get("light_level", "normal")
    
    def get_world_state(self) -> dict:
        return self.world_state.copy()
    
    def get_world_summary(self) -> str:
        """生成世界状态文本描述"""
        elder = self.world_state["elder"]
        env = self.world_state["environment"]
        
        return f"""当前时间: {self.world_state['time']}
用户状态: {elder['activity']}, 情绪{elder['mood']}, 注意力{elder['attention']:.0%}
空闲时间: {elder['idle_minutes']:.1f}分钟
环境: {'有人' if env['person_present'] else '无人'}, 光线{env['light_level']}"""
    
    def get_user_preferences_text(self) -> str:
        return f"喜欢: 音乐-{','.join(self.user_preferences.get('favorite_music', []))}, 电影-{','.join(self.user_preferences.get('favorite_movies', []))}"
    
    def navigate_to(self, page: str):
        self.current_page = page
        self.world_state["system"]["current_page"] = page
    
    def get_current_page(self) -> str:
        return self.current_page
    
    def set_user_speaking(self, speaking: bool, text: str = ""):
        self.world_state["elder"]["speaking"] = speaking
        if speaking:
            self._last_activity_time = time.time()
    
    def record_action(self, action_type: str, params: dict):
        self.world_state["system"]["recent_actions"].append({
            "type": action_type,
            "params": params,
            "time": datetime.now().strftime("%H:%M")
        })
        if len(self.world_state["system"]["recent_actions"]) > 20:
            self.world_state["system"]["recent_actions"].pop(0)


# 单例
_state_manager = None

def init_state_manager(socketio=None):
    global _state_manager
    _state_manager = SystemStateManager(socketio)
    return _state_manager

def get_state_manager():
    return _state_manager
