# -*- coding: utf-8 -*-
"""
System Center - 系统数据中心

这是整个系统的唯一数据中心，所有状态都在这里管理：
1. AI模式（基础/智伴）
2. 页面状态
3. 游戏状态
4. 感知数据（摄像头）
5. 用户生理状态
6. 系统设置

原则：
- 后端是唯一的真相来源
- 前端只订阅和显示
- 所有操作都发送到后端处理
"""

import json
import os
from datetime import datetime

class SystemCenter:
    """系统数据中心 - 单例模式"""
    
    _instance = None
    
    def __new__(cls, socketio=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, socketio=None):
        if self._initialized:
            return
        
        self.socketio = socketio
        self.config_file = os.path.join(os.path.dirname(__file__), 'system_config.json')
        
        # 默认状态
        self._state = {
            # AI模式
            'aiMode': 'basic',  # 'basic' | 'companion'
            
            # 当前页面
            'currentPage': '/',
            
            # 游戏状态
            'gameState': {
                'status': 'IDLE',  # IDLE, READY, PLAYING, PAUSED, SETTLING
                'currentGame': None,  # 'whack_a_mole' | 'processing_speed'
                'difficulty': 3,
                'score': 0,
                'timer': 60,
                'accuracy': 0,
                'module': None,
                'dwellTime': 2000
            },
            
            # 感知数据（来自摄像头）
            'perception': {
                'personDetected': False,
                'faceCount': 0,
                'bodyDetected': False,
                'footPosition': {'x': 0, 'y': 0, 'detected': False},
                'emotion': 'neutral',
                'attention': 0,
                'fatigue': 0,
                'lightLevel': 'normal',
                'timestamp': 0
            },
            
            # 用户生理状态
            'userState': {
                'heartRate': None,
                'hrv': None,
                'stressLevel': 0,
                'overallState': 'normal'
            },
            
            # 系统设置
            'settings': {
                'dwellTime': 2000,
                'soundEnabled': True,
                'projectionEnabled': True
            },
            
            'timestamp': 0
        }
        
        # 加载保存的配置
        self._load_config()
        
        self._initialized = True
        print('[SystemCenter] 初始化完成')
    
    def _load_config(self):
        """从文件加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self._state['aiMode'] = saved.get('aiMode', 'basic')
                    self._state['settings'] = {**self._state['settings'], **saved.get('settings', {})}
                    self._state['gameState']['dwellTime'] = self._state['settings']['dwellTime']
                    print(f'[SystemCenter] 配置已加载: aiMode={self._state["aiMode"]}, dwellTime={self._state["settings"]["dwellTime"]}ms')
        except Exception as e:
            print(f'[SystemCenter] 加载配置失败: {e}')
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            config = {
                'aiMode': self._state['aiMode'],
                'settings': self._state['settings']
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[SystemCenter] 保存配置失败: {e}')
    
    def _broadcast(self):
        """广播状态到所有前端"""
        if self.socketio:
            self._state['timestamp'] = int(datetime.now().timestamp() * 1000)
            self.socketio.emit('system_state', self._state)
    
    # ==================== AI模式 ====================
    
    def set_ai_mode(self, mode):
        """设置AI模式"""
        if mode not in ['basic', 'companion']:
            print(f'[SystemCenter] 无效的AI模式: {mode}')
            return False
        
        old_mode = self._state['aiMode']
        self._state['aiMode'] = mode
        self._save_config()
        self._broadcast()
        
        print(f'[SystemCenter] AI模式切换: {old_mode} -> {mode}')
        return True
    
    def get_ai_mode(self):
        return self._state['aiMode']
    
    def is_companion_mode(self):
        return self._state['aiMode'] == 'companion'
    
    def is_basic_mode(self):
        return self._state['aiMode'] == 'basic'
    
    # ==================== 页面状态 ====================
    
    def set_page(self, page):
        """设置当前页面"""
        self._state['currentPage'] = page
        self._broadcast()
        print(f'[SystemCenter] 页面切换: {page}')
    
    def get_page(self):
        return self._state['currentPage']
    
    # ==================== 游戏状态 ====================
    
    def set_game_status(self, status):
        """设置游戏状态"""
        valid = ['IDLE', 'READY', 'PLAYING', 'PAUSED', 'SETTLING']
        if status not in valid:
            print(f'[SystemCenter] 无效的游戏状态: {status}')
            return False
        
        self._state['gameState']['status'] = status
        self._broadcast()
        print(f'[SystemCenter] 游戏状态: {status}')
        return True
    
    def set_current_game(self, game_id):
        """设置当前游戏"""
        self._state['gameState']['currentGame'] = game_id
        self._broadcast()
        print(f'[SystemCenter] 当前游戏: {game_id}')
    
    def update_game_state(self, updates):
        """更新游戏状态"""
        self._state['gameState'].update(updates)
        self._broadcast()
    
    def get_game_state(self):
        return self._state['gameState'].copy()
    
    # ==================== 感知数据 ====================
    
    def update_perception(self, data):
        """更新感知数据（来自摄像头）"""
        self._state['perception'].update(data)
        # 感知数据更新频繁，不每次都广播，由调用者控制频率
    
    def set_foot_position(self, x, y, detected):
        """设置脚部位置"""
        self._state['perception']['footPosition'] = {
            'x': x,
            'y': y,
            'detected': detected
        }
    
    def get_foot_position(self):
        return self._state['perception']['footPosition'].copy()
    
    def broadcast_perception(self):
        """广播感知数据"""
        if self.socketio:
            self.socketio.emit('perception_update', self._state['perception'])
    
    # ==================== 用户状态 ====================
    
    def update_user_state(self, data):
        """更新用户生理状态"""
        self._state['userState'].update(data)
        self._broadcast()
    
    def set_heart_rate(self, bpm):
        """设置心率"""
        self._state['userState']['heartRate'] = bpm
        self._broadcast()
    
    # ==================== 设置 ====================
    
    def set_dwell_time(self, ms):
        """设置确认时间"""
        self._state['settings']['dwellTime'] = ms
        self._state['gameState']['dwellTime'] = ms
        self._save_config()
        self._broadcast()
        print(f'[SystemCenter] 确认时间: {ms}ms')
    
    def get_dwell_time(self):
        return self._state['settings']['dwellTime']
    
    def update_settings(self, settings):
        """更新设置"""
        self._state['settings'].update(settings)
        self._save_config()
        self._broadcast()
    
    # ==================== 获取完整状态 ====================
    
    def get_state(self):
        """获取完整状态"""
        return self._state.copy()
    
    def get_state_json(self):
        """获取JSON格式的状态"""
        return json.dumps(self._state, ensure_ascii=False, indent=2)


# 全局实例
_system_center = None

def init_system_center(socketio):
    """初始化系统中心"""
    global _system_center
    _system_center = SystemCenter(socketio)
    return _system_center

def get_system_center():
    """获取系统中心实例"""
    global _system_center
    if _system_center is None:
        _system_center = SystemCenter()
    return _system_center
