# -*- coding: utf-8 -*-
"""
系统状态管理器 - 统一管理所有页面状态和用户交互
"""

import time
import json
import threading
from datetime import datetime
from collections import defaultdict

class SystemStateManager:
    """
    统一系统状态管理器
    
    功能：
    1. 管理当前页面状态（所有设备同步）
    2. 收集用户交互数据
    3. 分析用户偏好
    4. 提供AI控制接口
    """
    
    def __init__(self, socketio=None):
        self.socketio = socketio
        
        # ==================== 核心状态 ====================
        self.state = {
            # 当前页面（所有设备同步）
            "current_page": "/",
            
            # 游戏状态
            "game": {
                "active": False,
                "name": None,        # 当前游戏名称
                "status": "IDLE",    # IDLE, READY, PLAYING, PAUSED
                "score": 0,
                "timer": 0
            },
            
            # 用户状态
            "user": {
                "detected": False,
                "position": {"x": 320, "y": 180},
                "in_zone": False
            },
            
            # 系统模式
            "mode": "normal"  # normal, game, training
        }
        
        # ==================== 用户行为数据 ====================
        self.user_actions = []  # 最近的行为记录
        self.max_actions = 1000  # 最多保留1000条记录
        
        # ==================== 用户偏好统计 ====================
        self.preferences = {
            "pages": defaultdict(int),      # 页面访问次数
            "games": defaultdict(int),      # 游戏游玩次数
            "music": defaultdict(int),      # 音乐播放次数
            "videos": defaultdict(int),     # 视频观看次数
            "interactions": defaultdict(int) # 交互类型统计
        }
        
        # ==================== 会话数据 ====================
        self.session = {
            "start_time": time.time(),
            "total_time": 0,
            "active_time": 0,
            "last_activity": time.time()
        }
        
        # ==================== 锁 ====================
        self._lock = threading.Lock()
    
    # ==================== 页面管理 ====================
    
    def get_current_page(self):
        """获取当前页面"""
        with self._lock:
            return self.state["current_page"]
    
    def navigate_to(self, page, source="user"):
        """
        导航到指定页面
        
        Args:
            page: 目标页面路径
            source: 来源 ("user", "ai", "system")
        """
        with self._lock:
            old_page = self.state["current_page"]
            self.state["current_page"] = page
            
            # 记录行为
            self._record_action({
                "type": "navigate",
                "from": old_page,
                "to": page,
                "source": source,
                "timestamp": datetime.now().isoformat()
            })
            
            # 更新偏好
            self.preferences["pages"][page] += 1
        
        # 广播页面变化
        self._broadcast_state()
        
        return True
    
    def can_navigate(self):
        """检查是否可以导航（是否在游戏中）"""
        with self._lock:
            return not self.state["game"]["active"]
    
    # ==================== 游戏管理 ====================
    
    def start_game(self, game_name):
        """开始游戏"""
        with self._lock:
            self.state["game"]["active"] = True
            self.state["game"]["name"] = game_name
            self.state["game"]["status"] = "READY"
            self.state["mode"] = "game"
            
            # 记录行为
            self._record_action({
                "type": "game_start",
                "game": game_name,
                "timestamp": datetime.now().isoformat()
            })
            
            # 更新偏好
            self.preferences["games"][game_name] += 1
        
        self._broadcast_state()
    
    def update_game_state(self, status, score=0, timer=0):
        """更新游戏状态"""
        with self._lock:
            self.state["game"]["status"] = status
            self.state["game"]["score"] = score
            self.state["game"]["timer"] = timer
        
        self._broadcast_state()
    
    def end_game(self):
        """结束游戏"""
        with self._lock:
            game_name = self.state["game"]["name"]
            score = self.state["game"]["score"]
            
            self.state["game"]["active"] = False
            self.state["game"]["name"] = None
            self.state["game"]["status"] = "IDLE"
            self.state["mode"] = "normal"
            
            # 记录行为
            self._record_action({
                "type": "game_end",
                "game": game_name,
                "score": score,
                "timestamp": datetime.now().isoformat()
            })
        
        self._broadcast_state()
    
    # ==================== 用户交互收集 ====================
    
    def record_interaction(self, interaction_type, data=None):
        """
        记录用户交互
        
        Args:
            interaction_type: 交互类型
                - "click": 点击
                - "view": 观看
                - "listen": 听音乐
                - "play_game": 玩游戏
                - "voice": 语音指令
            data: 附加数据
        """
        with self._lock:
            action = {
                "type": interaction_type,
                "data": data or {},
                "timestamp": datetime.now().isoformat()
            }
            self._record_action(action)
            
            # 更新交互统计
            self.preferences["interactions"][interaction_type] += 1
            
            # 更新会话
            self.session["last_activity"] = time.time()
        
        # 根据类型更新特定偏好
        if interaction_type == "listen" and data:
            self.preferences["music"][data.get("name", "unknown")] += 1
        elif interaction_type == "view" and data:
            self.preferences["videos"][data.get("name", "unknown")] += 1
    
    def _record_action(self, action):
        """内部方法：记录行为"""
        self.user_actions.append(action)
        if len(self.user_actions) > self.max_actions:
            self.user_actions.pop(0)
    
    # ==================== 用户偏好分析 ====================
    
    def get_preferences(self):
        """获取用户偏好"""
        with self._lock:
            return {
                "pages": dict(self.preferences["pages"]),
                "games": dict(self.preferences["games"]),
                "music": dict(self.preferences["music"]),
                "videos": dict(self.preferences["videos"]),
                "interactions": dict(self.preferences["interactions"])
            }
    
    def get_top_preferences(self, category, n=5):
        """获取某类别的Top N偏好"""
        with self._lock:
            data = self.preferences.get(category, {})
            sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
            return sorted_data[:n]
    
    def get_engagement_score(self):
        """计算用户参与度评分"""
        with self._lock:
            total_interactions = sum(self.preferences["interactions"].values())
            unique_pages = len(self.preferences["pages"])
            games_played = sum(self.preferences["games"].values())
            
            # 简单评分公式
            score = total_interactions * 1 + unique_pages * 5 + games_played * 10
            return score
    
    # ==================== AI控制接口 ====================
    
    def ai_navigate(self, page, reason=""):
        """
        AI控制导航
        
        Args:
            page: 目标页面
            reason: 导航原因
        """
        return self.navigate_to(page, source="ai")
    
    def get_state_for_ai(self):
        """获取给AI的状态摘要"""
        with self._lock:
            return {
                "current_page": self.state["current_page"],
                "game_active": self.state["game"]["active"],
                "game_name": self.state["game"]["name"],
                "mode": self.state["mode"],
                "top_pages": self.get_top_preferences("pages", 3),
                "top_games": self.get_top_preferences("games", 3),
                "engagement_score": self.get_engagement_score(),
                "recent_actions": self.user_actions[-10:] if self.user_actions else []
            }
    
    # ==================== 状态广播 ====================
    
    def _broadcast_state(self):
        """广播状态到所有客户端"""
        if self.socketio:
            self.socketio.emit('system_state', self.get_full_state())
    
    def get_full_state(self):
        """获取完整状态"""
        with self._lock:
            return {
                "state": dict(self.state),
                "preferences": self.get_preferences(),
                "session": {
                    "duration": time.time() - self.session["start_time"],
                    "engagement_score": self.get_engagement_score()
                }
            }
    
    # ==================== 持久化 ====================
    
    def save_to_file(self, filepath="user_data.json"):
        """保存用户数据到文件"""
        with self._lock:
            data = {
                "preferences": self.get_preferences(),
                "actions": self.user_actions[-100:],  # 最近100条
                "session": self.session
            }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存用户数据失败: {e}")
            return False
    
    def load_from_file(self, filepath="user_data.json"):
        """从文件加载用户数据"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            with self._lock:
                if "preferences" in data:
                    for category, items in data["preferences"].items():
                        if category in self.preferences:
                            for key, value in items.items():
                                self.preferences[category][key] = value
                
                if "actions" in data:
                    self.user_actions = data["actions"]
            
            return True
        except Exception as e:
            print(f"加载用户数据失败: {e}")
            return False


# 全局实例
_state_manager_instance = None

def init_state_manager(socketio=None):
    """初始化状态管理器"""
    global _state_manager_instance
    _state_manager_instance = SystemStateManager(socketio)
    return _state_manager_instance

def get_state_manager():
    """获取状态管理器实例"""
    global _state_manager_instance
    if _state_manager_instance is None:
        _state_manager_instance = SystemStateManager()
    return _state_manager_instance
