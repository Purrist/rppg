# -*- coding: utf-8 -*-
"""
SystemCore - 系统核心 (v3.1 优化版)

整个系统的唯一状态中心，管理：
- AI模式（基础/智伴）
- 页面状态和流转
- 游戏状态（待机/预备/游戏中/暂停/结算）
- 游戏运行时数据（得分、时间、准确率）
- 用户感知数据（人物、情绪、注意力、疲劳度、心率）
- 环境数据
- 用户偏好和历史

优化内容：
- 添加线程锁保护
- 完善配置文件加载失败处理
- 感知数据关键变化立即广播
- 完善异常处理

设计原则：
- SystemCore是唯一的真相来源
- 所有状态变更必须通过SystemCore
- 状态变更自动广播到所有前端
"""

import json
import os
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from enum import Enum


class AIMode(Enum):
    BASIC = "basic"
    COMPANION = "companion"


class GameStatus(Enum):
    IDLE = "IDLE"
    READY = "READY"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    SETTLING = "SETTLING"


class SystemCore:
    """系统核心 - 单例模式（线程安全）"""
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, socketio=None):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, socketio=None):
        if self._initialized:
            return
        
        self.socketio = socketio
        # ⭐ 配置文件放在core目录下
        self.data_dir = os.path.dirname(__file__)
        self.config_file = os.path.join(self.data_dir, 'system_config.json')
        self.history_file = os.path.join(self.data_dir, 'training_history.json')
        
        # ⭐ 线程锁保护
        self._lock = threading.RLock()
        self._listeners_lock = threading.Lock()
        
        # 状态监听器
        self._listeners: set[Callable] = set()
        
        # ==================== 核心状态 ====================
        self._state = {
            # AI模式
            'aiMode': 'basic',
            
            # 页面状态
            'currentPage': '/',
            
            # 游戏状态
            'game': {
                'status': 'IDLE',
                'currentGame': None,
                'difficulty': 3,
                'module': None,
                'dwellTime': 2000,
            },
            
            # 游戏运行时数据
            'gameRuntime': {
                'score': 0,
                'timer': 60,
                'accuracy': 0,
                'trialCount': 0,
                'correctCount': 0,
            },
            
            # 用户感知数据
            'perception': {
                'personDetected': False,
                'personCount': 0,
                'faceCount': 0,
                'bodyDetected': False,
                'footPosition': {'x': 0, 'y': 0, 'detected': False},
                'emotion': 'neutral',
                'attention': 0,
                'fatigue': 0,
                'heartRate': None,
                'activity': 'unknown',
                'speaking': False,
                'idleMinutes': 0,
            },
            
            # 环境数据
            'environment': {
                'lightLevel': 'normal',
            },
            
            # 系统设置
            'settings': {
                'dwellTime': 2000,
                'soundEnabled': True,
                'projectionEnabled': True,
            },
            
            # 时间信息
            'timeInfo': {
                'time': datetime.now().strftime('%H:%M'),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'weekday': ['一','二','三','四','五','六','日'][datetime.now().weekday()],
            },
            
            'timestamp': 0
        }
        
        # 用户偏好
        self._preferences = {
            'favoriteMusic': ['京剧', '民歌'],
            'favoriteMovies': ['地道战', '地雷战'],
            'favoriteGames': ['打地鼠'],
        }
        
        # 训练历史
        self._training_history: List[Dict] = []
        
        # 最近操作记录
        self._recent_actions: List[Dict] = []
        
        # 内部计时
        self._last_activity_time = time.time()
        self._last_perception_time = 0
        
        # ⭐ 加载数据（带错误恢复）
        self._load_config()
        self._load_history()
        
        self._initialized = True
        print(f'[SystemCore] 初始化完成 | AI模式: {self._state["aiMode"]} | 页面: {self._state["currentPage"]}')
    
    # ==================== 数据持久化（带错误恢复）====================
    
    def _load_config(self):
        """加载配置（失败时创建默认配置）"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self._state['aiMode'] = saved.get('aiMode', 'basic')
                    self._state['settings'].update(saved.get('settings', {}))
                    self._state['game']['dwellTime'] = self._state['settings'].get('dwellTime', 2000)
                    print(f'[SystemCore] 配置已加载: aiMode={self._state["aiMode"]}')
            else:
                # ⭐ 配置文件不存在，创建默认配置
                print('[SystemCore] 配置文件不存在，创建默认配置')
                self._save_config()
        except Exception as e:
            print(f'[SystemCore] 加载配置失败: {e}，使用默认配置')
            self._save_config()  # 创建默认配置
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with self._lock:
                config = {
                    'aiMode': self._state['aiMode'],
                    'settings': self._state['settings']
                }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[SystemCore] 保存配置失败: {e}')
    
    def _load_history(self):
        """加载训练历史"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self._training_history = json.load(f)
        except Exception as e:
            print(f'[SystemCore] 加载历史失败: {e}')
            self._training_history = []
    
    def _save_history(self):
        """保存训练历史"""
        try:
            with self._lock:
                history = self._training_history.copy()
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[SystemCore] 保存历史失败: {e}')
    
    # ==================== 状态广播（线程安全）====================
    
    def _broadcast(self):
        """广播状态到所有前端（线程安全）"""
        with self._lock:
            self._state['timestamp'] = int(time.time() * 1000)
            self._state['timeInfo'] = {
                'time': datetime.now().strftime('%H:%M'),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'weekday': ['一','二','三','四','五','六','日'][datetime.now().weekday()],
            }
            state_copy = self._state.copy()
        
        # ⭐ 复制监听器列表避免并发修改
        with self._listeners_lock:
            listeners = list(self._listeners)
        
        # 通知监听器
        for listener in listeners:
            try:
                listener(state_copy)
            except Exception as e:
                print(f'[SystemCore] 监听器错误: {e}')
        
        # Socket广播
        if self.socketio:
            try:
                self.socketio.emit('system_state', state_copy)
            except Exception as e:
                print(f'[SystemCore] Socket广播错误: {e}')
    
    def subscribe(self, callback: Callable):
        """订阅状态变化（线程安全）"""
        with self._listeners_lock:
            self._listeners.add(callback)
        # 立即发送当前状态
        with self._lock:
            callback(self._state.copy())
        return lambda: self._unsubscribe(callback)
    
    def _unsubscribe(self, callback: Callable):
        """取消订阅（线程安全）"""
        with self._listeners_lock:
            self._listeners.discard(callback)
    
    # ==================== AI模式 ====================
    
    def set_ai_mode(self, mode: str) -> bool:
        """设置AI模式: basic | companion"""
        if mode not in ['basic', 'companion']:
            print(f'[SystemCore] 无效的AI模式: {mode}')
            return False
        
        with self._lock:
            old_mode = self._state['aiMode']
            if old_mode == mode:
                return True  # 无变化
            self._state['aiMode'] = mode
        
        self._save_config()
        self._broadcast()
        
        mode_text = '智伴模式' if mode == 'companion' else '基础模式'
        print(f'[SystemCore] AI模式: {old_mode} -> {mode} ({mode_text})')
        return True
    
    def get_ai_mode(self) -> str:
        with self._lock:
            return self._state['aiMode']
    
    def is_companion_mode(self) -> bool:
        with self._lock:
            return self._state['aiMode'] == 'companion'
    
    def is_basic_mode(self) -> bool:
        with self._lock:
            return self._state['aiMode'] == 'basic'
    
    # ==================== 页面状态 ====================
    
    def set_page(self, page: str):
        """设置当前页面"""
        with self._lock:
            old_page = self._state['currentPage']
            if old_page == page:
                return
            self._state['currentPage'] = page
        
        self._record_action('navigate', {'from': old_page, 'to': page})
        self._broadcast()
        print(f'[SystemCore] 页面: {old_page} -> {page}')
    
    def get_page(self) -> str:
        with self._lock:
            return self._state['currentPage']
    
    # ==================== 游戏状态 ====================
    
    def set_game_status(self, status: str) -> bool:
        """设置游戏状态: IDLE/READY/PLAYING/PAUSED/SETTLING"""
        valid = ['IDLE', 'READY', 'PLAYING', 'PAUSED', 'SETTLING']
        if status not in valid:
            print(f'[SystemCore] 无效的游戏状态: {status}')
            return False
        
        with self._lock:
            self._state['game']['status'] = status
        
        self._broadcast()
        print(f'[SystemCore] 游戏状态: {status}')
        return True
    
    def get_game_status(self) -> str:
        with self._lock:
            return self._state['game']['status']
    
    def set_current_game(self, game_id: Optional[str]):
        """设置当前游戏"""
        with self._lock:
            self._state['game']['currentGame'] = game_id
        self._broadcast()
        print(f'[SystemCore] 当前游戏: {game_id}')
    
    def get_current_game(self) -> Optional[str]:
        with self._lock:
            return self._state['game']['currentGame']
    
    def set_game_difficulty(self, difficulty: int):
        """设置游戏难度 1-8"""
        with self._lock:
            self._state['game']['difficulty'] = max(1, min(8, difficulty))
        self._broadcast()
    
    def get_game_difficulty(self) -> int:
        with self._lock:
            return self._state['game']['difficulty']
    
    def set_dwell_time(self, ms: int):
        """设置确认时间（毫秒）"""
        with self._lock:
            self._state['settings']['dwellTime'] = ms
            self._state['game']['dwellTime'] = ms
        self._save_config()
        self._broadcast()
        print(f'[SystemCore] 确认时间: {ms}ms')
    
    def get_dwell_time(self) -> int:
        with self._lock:
            return self._state['game']['dwellTime']
    
    def is_game_active(self) -> bool:
        """游戏是否激活"""
        with self._lock:
            return self._state['game']['status'] in ['READY', 'PLAYING', 'PAUSED', 'SETTLING']
    
    # ==================== 游戏运行时数据 ====================
    
    def update_game_runtime(self, updates: Dict[str, Any]):
        """更新游戏运行时数据"""
        with self._lock:
            self._state['gameRuntime'].update(updates)
        self._broadcast()
    
    def reset_game_runtime(self):
        """重置游戏运行时数据"""
        with self._lock:
            self._state['gameRuntime'] = {
                'score': 0, 'timer': 60, 'accuracy': 0,
                'trialCount': 0, 'correctCount': 0
            }
        self._broadcast()
    
    def record_training(self, data: Dict):
        """记录训练数据"""
        record = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'game': self._state['game']['currentGame'],
            'difficulty': self._state['game']['difficulty'],
            **data
        }
        with self._lock:
            self._training_history.append(record)
            if len(self._training_history) > 100:
                self._training_history = self._training_history[-100:]
        self._save_history()
    
    def get_training_history(self) -> List[Dict]:
        """获取训练历史"""
        with self._lock:
            return self._training_history.copy()
    
    # ==================== 感知数据（优化广播）====================
    
    def update_perception(self, data: Dict[str, Any]):
        """更新感知数据（关键变化立即广播）"""
        now = time.time()
        
        with self._lock:
            # 保存旧值用于比较
            old_person_detected = self._state['perception'].get('personDetected')
            old_activity = self._state['perception'].get('activity')
            
            # 更新用户活动状态
            if data.get('personDetected') or data.get('activity') != 'unknown':
                self._last_activity_time = now
            
            # 计算空闲时间
            idle_minutes = (now - self._last_activity_time) / 60
            
            # 合并数据
            perception_update = {
                'personDetected': data.get('personDetected', False),
                'personCount': data.get('personCount', 0),
                'faceCount': data.get('faceCount', 0),
                'bodyDetected': data.get('bodyDetected', False),
                'emotion': data.get('emotion', 'neutral'),
                'attention': data.get('attention', 0),
                'fatigue': data.get('fatigue', 0),
                'heartRate': data.get('heartRate'),
                'activity': data.get('activity', 'unknown'),
                'speaking': data.get('speaking', False),
                'idleMinutes': round(idle_minutes, 1),
            }
            
            # 脚部位置单独处理
            if 'footPosition' in data:
                perception_update['footPosition'] = data['footPosition']
            
            self._state['perception'].update(perception_update)
            
            # ⭐ 检查关键状态变化
            critical_change = (
                data.get('personDetected') != old_person_detected or
                data.get('activity') != old_activity
            )
        
        # ⭐ 关键变化立即广播，其他按频率限制
        if critical_change or (now - self._last_perception_time >= 0.5):
            self._last_perception_time = now
            if self.socketio:
                try:
                    with self._lock:
                        perception_copy = self._state['perception'].copy()
                    self.socketio.emit('perception_update', perception_copy)
                except Exception as e:
                    print(f'[SystemCore] 感知广播错误: {e}')
    
    def set_foot_position(self, x: float, y: float, detected: bool):
        """设置脚部位置"""
        with self._lock:
            self._state['perception']['footPosition'] = {
                'x': x, 'y': y, 'detected': detected
            }
    
    def set_user_speaking(self, speaking: bool):
        """设置用户说话状态"""
        with self._lock:
            self._state['perception']['speaking'] = speaking
        if speaking:
            self._last_activity_time = time.time()
    
    # ==================== 环境数据 ====================
    
    def update_environment(self, data: Dict[str, Any]):
        """更新环境数据"""
        with self._lock:
            self._state['environment'].update(data)
    
    # ==================== 用户偏好 ====================
    
    def get_preferences(self) -> Dict:
        """获取用户偏好"""
        with self._lock:
            return self._preferences.copy()
    
    def update_preferences(self, preferences: Dict):
        """更新用户偏好"""
        with self._lock:
            self._preferences.update(preferences)
    
    # ==================== 操作记录 ====================
    
    def _record_action(self, action_type: str, params: Dict):
        """记录操作"""
        with self._lock:
            self._recent_actions.append({
                'type': action_type,
                'params': params,
                'time': datetime.now().strftime('%H:%M')
            })
            if len(self._recent_actions) > 20:
                self._recent_actions.pop(0)
    
    def get_recent_actions(self) -> List[Dict]:
        """获取最近操作"""
        with self._lock:
            return self._recent_actions.copy()
    
    # ==================== 获取状态 ====================
    
    def get_state(self) -> Dict[str, Any]:
        """获取完整状态（线程安全）"""
        with self._lock:
            return self._state.copy()
    
    def get_world_summary(self) -> str:
        """生成世界状态摘要（用于AI）"""
        with self._lock:
            p = self._state['perception']
            g = self._state['game']
            return f"""时间: {self._state['timeInfo']['time']}
页面: {self._state['currentPage']}
游戏: {g['currentGame'] or '无'} ({g['status']})
用户: {p['activity']}, 情绪{p['emotion']}, 注意力{p['attention']:.0%}, 空闲{p['idleMinutes']:.1f}分钟
环境: {'有人' if p['personDetected'] else '无人'}"""
    
    def get_state_json(self) -> str:
        """获取JSON格式的状态"""
        with self._lock:
            return json.dumps(self._state, ensure_ascii=False, indent=2)


# ==================== 全局实例（线程安全）====================

_system_core: Optional[SystemCore] = None
_system_core_lock = threading.Lock()


def init_system_core(socketio=None) -> SystemCore:
    """初始化系统核心（线程安全）"""
    global _system_core
    if _system_core is None:
        with _system_core_lock:
            if _system_core is None:
                _system_core = SystemCore(socketio)
    return _system_core


def get_system_core() -> SystemCore:
    """获取系统核心实例（线程安全）"""
    global _system_core
    if _system_core is None:
        with _system_core_lock:
            if _system_core is None:
                _system_core = SystemCore()
    return _system_core
