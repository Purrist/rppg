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
import sys
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from enum import Enum

# 添加父目录到路径，导入 perception 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from perception.dda import DDASystem
except ImportError:
    DDASystem = None


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

        # ⭐ DDA 系统初始化
        self.dda_system = None
        if DDASystem is not None:
            self.dda_system = DDASystem()
            self.dda_system.current_difficulty = 4
            
        # ⭐ DDA 专用的感知数据缓存
        self._dda_perception_data = {
            'hr_valid': False,
            'hrr_pct': 0,
            'hr_slope': 0,
            'emotion': 'neutral',
            'confidence': 0,
            'face_detected': True,
            'face_count': 1
        }

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
                # ⭐ 扩展：完整的 hlkk.py 生理数据
                'physiology': {
                    'raw': {
                        'hr': None,
                        'br': None,
                        'hph': None,
                        'bph': None,
                        'is_human': 0,
                        'distance': 0,
                        'distance_valid': 0,
                        'signal_state': 'INIT',
                        'hr_valid': False,
                        'br_valid': False,
                        'phase_valid': False
                    },
                    'analysis': {
                        'hrr': None,
                        'hrr_label': None,
                        'slope': None,
                        'slope_label': None,
                        'brv': None,
                        'brv_label': None,
                        'brel': None,
                        'brel_label': None,
                        'cr': None,
                        'cr_label': None,
                        'plv': None,
                        'plv_label': None,
                        'mean_phase_diff': None
                    }
                },
                # ⭐ 扩展：完整的 emotion.py 面部/情绪数据
                'face': {
                    'au': {
                        'emotion': 'no_face',
                        'confidence': 0.0,
                        'scores': {'neutral': 0, 'positive': 0, 'negative': 0},
                        'pose': '-',
                        'pitch': 0,
                        'yaw': 0,
                        'roll': 0,
                        'au_features': {},
                        'engagement': 'None',
                        'face_detected': False,
                        'face_count': 0,
                        'speaking': False
                    },
                    'fer': {
                        'label': 'neutral',
                        'conf': 0.0,
                        'probs_3': {'neutral': 0, 'positive': 0, 'negative': 0},
                        'has_face': False
                    },
                    'fusion': {
                        'emotion': 'no_face',
                        'confidence': 0.0,
                        'scores': {'neutral': 0, 'positive': 0, 'negative': 0}
                    }
                }
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
                'voiceWakeup': True,
                'voiceSpeaking': True,
            },
            
            # TTS配置
            'tts': {
                'engine': 'vits',  # 'vits' 或 'pytts'
                'sid': 0,
                'speed': 1.0,
                'volume': 1.0,
            },
            
            # 时间信息
            'timeInfo': {
                'time': datetime.now().strftime('%H:%M'),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'weekday': ['一','二','三','四','五','六','日'][datetime.now().weekday()],
            },
            
            'timestamp': 0,
            
            # ⭐ 语音状态
            'voice': {
                'state': 'STANDBY',  # STANDBY / RESPONDING / LISTENING / PROCESSING
                'isRecording': False,
                'isPlaying': False,
                'lastWakeTime': 0,
                'message': '等待唤醒...'
            }
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
        
        # 系统监控
        self._monitoring = {
            'start_time': datetime.now().isoformat(),
            'broadcast_count': 0,
            'state_update_count': 0,
            'error_count': 0,
            'last_error': None,
            'performance': {
                'average_broadcast_time': 0,
                'total_broadcast_time': 0,
            }
        }
        
        # 内部计时
        self._last_activity_time = time.time()
        self._last_perception_time = 0
        self._last_game_runtime_time = 0
        self._last_full_broadcast_time = 0
        
        # 广播频率配置
        self._broadcast_config = {
            'perception': 0.5,  # 500ms
            'game_runtime': 0.1,  # 100ms
            'full': 1.0,  # 1000ms
        }
        
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
                    # 确保语音设置存在
                    if 'voiceWakeup' not in self._state['settings']:
                        self._state['settings']['voiceWakeup'] = True
                    if 'voiceSpeaking' not in self._state['settings']:
                        self._state['settings']['voiceSpeaking'] = True
                    # 加载TTS配置
                    if 'tts' in saved:
                        self._state['tts'].update(saved.get('tts', {}))
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
                    'settings': self._state['settings'],
                    'tts': self._state['tts']
                }
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[SystemCore] 保存配置失败: {e}')
            # 尝试使用备用路径
            try:
                backup_path = os.path.join(os.path.dirname(__file__), 'system_config_backup.json')
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                print(f'[SystemCore] 已保存到备用路径: {backup_path}')
            except Exception as backup_error:
                print(f'[SystemCore] 备用保存也失败: {backup_error}')
    
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
            # 确保目录存在
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[SystemCore] 保存历史失败: {e}')
            # 尝试使用备用路径
            try:
                backup_path = os.path.join(os.path.dirname(__file__), 'training_history_backup.json')
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                print(f'[SystemCore] 已保存到备用路径: {backup_path}')
            except Exception as backup_error:
                print(f'[SystemCore] 备用保存也失败: {backup_error}')
    
    # ==================== 状态广播（线程安全）====================
    
    def _broadcast(self, force=False, important_fields=None):
        """广播状态到所有前端（线程安全，带频率限制）
        
        Args:
            force: 是否强制广播，忽略频率限制
            important_fields: 重要字段列表，当这些字段变化时优先广播
        """
        start_time = time.time()
        now = start_time
        
        # 检查是否需要广播
        if not force and (now - self._last_full_broadcast_time < self._broadcast_config['full']):
            # 如果有重要字段变化，仍然广播
            if important_fields:
                pass  # 允许重要字段变化时广播
            else:
                return
        
        with self._lock:
            self._state['timestamp'] = int(time.time() * 1000)
            self._state['timeInfo'] = {
                'time': datetime.now().strftime('%H:%M'),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'weekday': ['一','二','三','四','五','六','日'][datetime.now().weekday()],
            }
            state_copy = self._state.copy()
            
            # 更新最后广播时间
            self._last_full_broadcast_time = now
            
            # 更新监控数据
            self._monitoring['broadcast_count'] += 1
            self._monitoring['state_update_count'] += 1
        
        # ⭐ 复制监听器列表避免并发修改
        with self._listeners_lock:
            listeners = list(self._listeners)
        
        # 通知监听器
        for listener in listeners:
            try:
                listener(state_copy)
            except Exception as e:
                print(f'[SystemCore] 监听器错误: {e}')
                with self._lock:
                    self._monitoring['error_count'] += 1
                    self._monitoring['last_error'] = f'监听器错误: {e}'
        
        # Socket广播
        if self.socketio:
            try:
                self.socketio.emit('system_state', state_copy)
            except Exception as e:
                print(f'[SystemCore] Socket广播错误: {e}')
                with self._lock:
                    self._monitoring['error_count'] += 1
                    self._monitoring['last_error'] = f'Socket广播错误: {e}'
        
        # 记录性能数据
        broadcast_time = time.time() - start_time
        with self._lock:
            self._monitoring['performance']['total_broadcast_time'] += broadcast_time
            self._monitoring['performance']['average_broadcast_time'] = (
                self._monitoring['performance']['total_broadcast_time'] / 
                self._monitoring['broadcast_count']
            )
    
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
        """设置当前页面 - 只允许跳转到健康、娱乐、益智、呼叫四个页面"""
        # ⭐ 页面白名单：只允许这四个页面跳转
        ALLOWED_PAGES = ['/health', '/entertainment', '/learning', '/call']
        
        # 如果不是允许的页面，直接忽略，不做任何操作
        if page not in ALLOWED_PAGES:
            print(f'[SystemCore] 忽略无效页面跳转: {page}')
            return
        
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
            old_difficulty = self._state['game']['difficulty']
            new_difficulty = max(1, min(8, difficulty))
            if old_difficulty != new_difficulty:
                self._state['game']['difficulty'] = new_difficulty
                # 难度变化时立即广播，不受频率限制
                self._broadcast(force=True, important_fields=['game.difficulty'])
                print(f'[SystemCore] 游戏难度: {old_difficulty} -> {new_difficulty}')

    def set_game_module(self, module: str):
        """设置游戏模块"""
        with self._lock:
            self._state['game']['module'] = module
        self._broadcast()
        print(f'[SystemCore] 游戏模块: {module}')
    
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
    
    def set_voice_setting(self, voice_type: str, enabled: bool):
        """设置语音功能"""
        with self._lock:
            if voice_type == 'wakeup':
                self._state['settings']['voiceWakeup'] = enabled
            elif voice_type == 'speaking':
                self._state['settings']['voiceSpeaking'] = enabled
        self._save_config()
        self._broadcast()
        print(f'[SystemCore] 语音设置: {voice_type} = {enabled}')
    
    def update_voice_state(self, voice_data: Dict[str, Any]):
        """更新语音状态（由VoiceManager调用）"""
        with self._lock:
            old_state = self._state['voice']['state']
            
            # 更新语音状态
            if 'state' in voice_data:
                self._state['voice']['state'] = voice_data['state']
            if 'isRecording' in voice_data:
                self._state['voice']['isRecording'] = voice_data['isRecording']
            if 'isPlaying' in voice_data:
                self._state['voice']['isPlaying'] = voice_data['isPlaying']
            if 'timestamp' in voice_data:
                self._state['voice']['lastWakeTime'] = voice_data['timestamp']
            
            # 根据状态更新消息
            state_messages = {
                'STANDBY': '等待唤醒...',
                'RESPONDING': '回应中...',
                'LISTENING': '聆听中...',
                'PROCESSING': '处理中...'
            }
            self._state['voice']['message'] = state_messages.get(
                self._state['voice']['state'], '未知状态'
            )
            
            new_state = self._state['voice']['state']
        
        # 状态变化时广播
        if old_state != new_state:
            self._broadcast(force=True, important_fields=['voice'])
            print(f'[SystemCore] 语音状态: {old_state} -> {new_state}')
        else:
            # 非状态变化但数据更新时也广播（但不必强制）
            self._broadcast(important_fields=['voice'])
    
    def get_voice_state(self) -> Dict[str, Any]:
        """获取当前语音状态"""
        with self._lock:
            return dict(self._state['voice'])
    
    def get_dwell_time(self) -> int:
        with self._lock:
            return self._state['game']['dwellTime']
    
    def update_tts_config(self, tts_config: Dict[str, Any]):
        """更新TTS配置"""
        with self._lock:
            if 'engine' in tts_config:
                self._state['tts']['engine'] = tts_config['engine']
            if 'sid' in tts_config:
                self._state['tts']['sid'] = tts_config['sid']
            if 'speed' in tts_config:
                self._state['tts']['speed'] = tts_config['speed']
            if 'volume' in tts_config:
                self._state['tts']['volume'] = tts_config['volume']
        self._save_config()
        self._broadcast()
        print(f'[SystemCore] TTS配置更新: {tts_config}')
    
    def set_tts_engine(self, engine: str) -> bool:
        """设置TTS引擎: 'vits' 或 'pytts'"""
        if engine not in ['vits', 'pytts']:
            print(f'[SystemCore] 无效的TTS引擎: {engine}')
            return False
        
        with self._lock:
            old_engine = self._state['tts']['engine']
            if old_engine == engine:
                return True
            self._state['tts']['engine'] = engine
        
        self._save_config()
        self._broadcast()
        print(f'[SystemCore] TTS引擎: {old_engine} -> {engine}')
        return True
    
    def get_tts_engine(self) -> str:
        """获取当前TTS引擎"""
        with self._lock:
            return self._state['tts']['engine']
    
    def is_game_active(self) -> bool:
        """游戏是否激活"""
        with self._lock:
            return self._state['game']['status'] in ['READY', 'PLAYING', 'PAUSED', 'SETTLING']
    
    # ==================== 游戏运行时数据 ====================
    
    def update_game_runtime(self, updates: Dict[str, Any]):
        """更新游戏运行时数据（按频率限制广播）"""
        now = time.time()
        
        with self._lock:
            self._state['gameRuntime'].update(updates)
            
            # 检查是否需要广播
            should_broadcast = (now - self._last_game_runtime_time >= self._broadcast_config['game_runtime'])
            if should_broadcast:
                self._last_game_runtime_time = now
                # 在锁内复制数据
                game_runtime_copy = self._state['gameRuntime'].copy()
                game_status_copy = self._state['game'].copy()
        
        # 按频率限制广播
        if should_broadcast and self.socketio:
            try:
                self.socketio.emit('game_runtime_update', {
                    'gameRuntime': game_runtime_copy,
                    'gameStatus': game_status_copy,
                    'gameDifficulty': game_status_copy.get('difficulty', 3)  # 确保包含游戏难度
                })
            except Exception as e:
                print(f'[SystemCore] 游戏运行时广播错误: {e}')
    
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
    
    def save_game_session(self, session_data: Dict):
        """保存完整的游戏会话数据到data文件夹"""
        try:
            # 确保data文件夹存在
            data_dir = os.path.join(self.data_dir, 'data')
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
                print(f'[SystemCore] 创建数据目录: {data_dir}')
            
            # 生成会话ID和文件名
            session_id = session_data.get('session_id', f"{session_data.get('game_type', 'game')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            session_file = os.path.join(data_dir, f"session_{session_id.split('_')[-2]}_{session_id.split('_')[-1]}.json")
            
            # 保存会话数据
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            # 更新训练摘要
            self._update_training_summary(session_data)
            
            print(f'[SystemCore] 游戏会话数据已保存: {session_file}')
            return True
        except Exception as e:
            print(f'[SystemCore] 保存游戏会话失败: {e}')
            return False
    
    def _update_training_summary(self, session_data: Dict):
        """更新训练摘要文件"""
        try:
            data_dir = os.path.join(self.data_dir, 'data')
            summary_file = os.path.join(data_dir, 'training_summary.json')
            
            # 读取现有摘要
            summaries = []
            if os.path.exists(summary_file):
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summaries = json.load(f)
            
            # 创建新摘要
            new_summary = {
                'session_id': session_data.get('session_id'),
                'timestamp': session_data.get('start_time'),
                'game_type': session_data.get('game_type'),
                'module': session_data.get('module'),
                'difficulty_range': f"{session_data.get('min_difficulty', 1)}-{session_data.get('max_difficulty', 8)}",
                'score': session_data.get('final_score', 0),
                'total_trials': session_data.get('total_trials', 0),
                'correct_trials': session_data.get('correct_trials', 0),
                'incorrect_trials': session_data.get('total_trials', 0) - session_data.get('correct_trials', 0),
                'missed_trials': session_data.get('missed_trials', 0),
                'accuracy': session_data.get('final_accuracy', 0),
                'avg_reaction_time_ms': session_data.get('avg_reaction_time_ms', 0),
                'duration': session_data.get('duration', 0)
            }
            
            # 添加到摘要列表
            summaries.append(new_summary)
            
            # 保存摘要文件
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summaries, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            print(f'[SystemCore] 更新训练摘要失败: {e}')
    
    def get_training_history(self) -> List[Dict]:
        """获取训练历史"""
        with self._lock:
            return self._training_history.copy()
    
    def delete_training_record(self, session_id: str) -> bool:
        """删除训练记录，同时删除summary和session文件"""
        try:
            data_dir = os.path.join(self.data_dir, 'data')
            summary_file = os.path.join(data_dir, 'training_summary.json')
            
            # 读取摘要文件
            summaries = []
            if os.path.exists(summary_file):
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summaries = json.load(f)
            
            # 找到要删除的记录
            record_to_delete = None
            for i, summary in enumerate(summaries):
                if summary.get('session_id') == session_id:
                    record_to_delete = summary
                    summaries.pop(i)
                    break
            
            if not record_to_delete:
                print(f'[SystemCore] 未找到训练记录: {session_id}')
                return False
            
            # 保存更新后的摘要
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summaries, f, ensure_ascii=False, indent=2)
            
            # 删除对应的session文件
            if session_id:
                # 从session_id提取日期和时间部分
                parts = session_id.split('_')
                if len(parts) >= 2:
                    date_time_part = f"{parts[-2]}_{parts[-1]}"
                    session_file = os.path.join(data_dir, f"session_{date_time_part}.json")
                    if os.path.exists(session_file):
                        os.remove(session_file)
                        print(f'[SystemCore] 已删除会话文件: {session_file}')
            
            # 从内存历史中删除
            with self._lock:
                self._training_history = [h for h in self._training_history if h.get('session_id') != session_id]
            
            print(f'[SystemCore] 训练记录已删除: {session_id}')
            return True
        except Exception as e:
            print(f'[SystemCore] 删除训练记录失败: {e}')
            return False
    
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
            
            # 合并数据 - 包含所有感知字段
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
                # 扩展字段用于developer页面显示
                'physicalLoad': data.get('fatigue', 0),  # 身体负荷 = 疲劳度
                'cognitiveLoad': 1 - data.get('attention', 0.5),  # 认知负荷 = 1 - 注意力
                'engagement': data.get('attention', 0.5),  # 参与度 = 注意力
                'lightLevel': data.get('lightLevel', 'normal'),
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
            
            # ⭐ 在锁内更新_last_perception_time，避免竞态条件
            should_broadcast = critical_change or (now - self._last_perception_time >= 0.5)
            if should_broadcast:
                self._last_perception_time = now
                # 在锁内复制数据
                perception_copy = self._state['perception'].copy()
        
        # ⭐ 关键变化立即广播，其他按频率限制
        if should_broadcast and self.socketio:
            try:
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
    
    # ==================== 完整生理数据更新（来自 hlkk.py） ====================
    
    def update_physiology_data(self, raw_data: Dict[str, Any], analysis_data: Dict[str, Any] = None):
        """
        更新完整的生理数据（来自 hlkk.py）
        
        Args:
            raw_data: 原始数据 (hr, br, hph, bph, is_human, distance, distance_valid, signal_state, hr_valid, br_valid, phase_valid)
            analysis_data: 分析数据 (hrr, hrr_label, slope, slope_label, brv, brv_label, brel, brel_label, cr, cr_label, plv, plv_label, mean_phase_diff)
        """
        with self._lock:
            if raw_data:
                self._state['perception']['physiology']['raw'].update({
                    'hr': raw_data.get('hr'),
                    'br': raw_data.get('br'),
                    'hph': raw_data.get('hph'),
                    'bph': raw_data.get('bph'),
                    'is_human': raw_data.get('is_human', 0),
                    'distance': raw_data.get('distance', 0),
                    'distance_valid': raw_data.get('distance_valid', 0),
                    'signal_state': raw_data.get('signal_state', 'INIT'),
                    'hr_valid': raw_data.get('hr_valid', False),
                    'br_valid': raw_data.get('br_valid', False),
                    'phase_valid': raw_data.get('phase_valid', False)
                })
            
            if analysis_data:
                self._state['perception']['physiology']['analysis'].update({
                    'hrr': analysis_data.get('hrr'),
                    'hrr_label': analysis_data.get('hrr_label'),
                    'slope': analysis_data.get('slope'),
                    'slope_label': analysis_data.get('slope_label'),
                    'brv': analysis_data.get('brv'),
                    'brv_label': analysis_data.get('brv_label'),
                    'brel': analysis_data.get('brel'),
                    'brel_label': analysis_data.get('brel_label'),
                    'cr': analysis_data.get('cr'),
                    'cr_label': analysis_data.get('cr_label'),
                    'plv': analysis_data.get('plv'),
                    'plv_label': analysis_data.get('plv_label'),
                    'mean_phase_diff': analysis_data.get('mean_phase_diff')
                })
    
    # ==================== 完整面部/情绪数据更新（来自 emotion.py） ====================
    
    def update_face_emotion_data(self, au_data: Dict[str, Any] = None, fer_data: Dict[str, Any] = None, fusion_data: Dict[str, Any] = None):
        """
        更新完整的面部/情绪数据（来自 emotion.py）
        
        Args:
            au_data: AU 数据 (emotion, confidence, scores, pose, pitch, yaw, roll, au_features, engagement, face_detected, face_count, speaking)
            fer_data: FER 数据 (label, conf, probs_3, has_face)
            fusion_data: Fusion 数据 (emotion, confidence, scores)
        """
        with self._lock:
            if au_data:
                self._state['perception']['face']['au'].update({
                    'emotion': au_data.get('emotion', 'no_face'),
                    'confidence': au_data.get('confidence', 0.0),
                    'scores': au_data.get('scores', {'neutral': 0, 'positive': 0, 'negative': 0}),
                    'pose': au_data.get('pose', '-'),
                    'pitch': au_data.get('pitch', 0),
                    'yaw': au_data.get('yaw', 0),
                    'roll': au_data.get('roll', 0),
                    'au_features': au_data.get('au_features', {}),
                    'engagement': au_data.get('engagement', 'None'),
                    'face_detected': au_data.get('face_detected', False),
                    'face_count': au_data.get('face_count', 0),
                    'speaking': au_data.get('speaking', False)
                })
            
            if fer_data:
                self._state['perception']['face']['fer'].update({
                    'label': fer_data.get('label', 'neutral'),
                    'conf': fer_data.get('conf', 0.0),
                    'probs_3': fer_data.get('probs_3', {'neutral': 0, 'positive': 0, 'negative': 0}),
                    'has_face': fer_data.get('has_face', False)
                })
            
            if fusion_data:
                self._state['perception']['face']['fusion'].update({
                    'emotion': fusion_data.get('emotion', 'no_face'),
                    'confidence': fusion_data.get('confidence', 0.0),
                    'scores': fusion_data.get('scores', {'neutral': 0, 'positive': 0, 'negative': 0})
                })
    
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
    
    def get_monitoring_data(self) -> Dict[str, Any]:
        """获取系统监控数据"""
        with self._lock:
            return self._monitoring.copy()
    
    def reset_monitoring(self):
        """重置系统监控数据"""
        with self._lock:
            self._monitoring = {
                'start_time': datetime.now().isoformat(),
                'broadcast_count': 0,
                'state_update_count': 0,
                'error_count': 0,
                'last_error': None,
                'performance': {
                    'average_broadcast_time': 0,
                    'total_broadcast_time': 0,
                }
            }
            print('[SystemCore] 监控数据已重置')

    # ==================== DDA 系统 ====================

    def get_dda_system(self):
        """获取 DDA 系统实例"""
        return self.dda_system

    def reset_dda_for_new_game(self):
        """为新游戏重置 DDA"""
        if self.dda_system is not None:
            self.dda_system.reset_for_new_game()
            print(f'[SystemCore] DDA 系统已为新游戏重置')

    def set_dda_perception_data(self, perception_data):
        """设置 DDA 专用的感知数据"""
        with self._lock:
            self._dda_perception_data.update(perception_data)

    def get_dda_perception_data(self):
        """获取 DDA 专用的感知数据"""
        with self._lock:
            return self._dda_perception_data.copy()


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
