# core/core_tools.py
# 行动执行器

from typing import Dict, Any


class ActionExecutor:
    """行动执行器"""
    
    def __init__(self, socketio, state_manager=None):
        self.socketio = socketio
        self.state_manager = state_manager
        
        self.actions = {
            "navigate": self._navigate,
            "recommend": self._recommend,
            "play_music": self._play_music,
            "play_video": self._play_video,
            "start_game": self._start_game,
            "speak": self._speak,
            "navigate_and_recommend": self._navigate_and_recommend,
        }
    
    def execute(self, decision: dict):
        if not decision.get("need_action"):
            return
        
        action = decision.get("action")
        params = decision.get("params", {})
        speak = decision.get("speak", "")
        
        # 执行行动
        if action in self.actions:
            self.actions[action](params)
        
        # 说话
        if speak and self.socketio:
            self.socketio.emit('akon_speak', {"text": speak})
        
        # 记录
        if self.state_manager:
            self.state_manager.record_action(action, params)
    
    def _navigate(self, params):
        page = params.get("page", "/")
        if self.socketio:
            self.socketio.emit('navigate_to', {"page": page})
    
    def _recommend(self, params):
        if self.socketio:
            self.socketio.emit('akon_recommend', {
                "type": params.get("type"),
                "items": params.get("items", [])
            })
    
    def _play_music(self, params):
        if self.socketio:
            self.socketio.emit('akon_play', {
                "type": "music",
                "music_type": params.get("music_type")
            })
    
    def _play_video(self, params):
        if self.socketio:
            self.socketio.emit('akon_play', {
                "type": "video",
                "name": params.get("video_name")
            })
    
    def _start_game(self, params):
        if self.socketio:
            self.socketio.emit('game_control', {
                "action": "ready",
                "game": params.get("game_name", "whack_a_mole")
            })
    
    def _speak(self, params):
        if self.socketio:
            self.socketio.emit('akon_speak', {"text": params.get("text", "")})
    
    def _navigate_and_recommend(self, params):
        """导航并推荐"""
        page = params.get("page", "/")
        content = params.get("content", {})
        
        if self.socketio:
            self.socketio.emit('navigate_to', {"page": page})
            if content:
                self.socketio.emit('akon_recommend', {
                    "type": content.get("type"),
                    "items": content.get("items", [])
                })


def execute_tool(tool_name: str, params: dict, socketio=None):
    """执行单个工具"""
    executor = ActionExecutor(socketio)
    if tool_name in executor.actions:
        executor.actions[tool_name](params)
        return True
    return False
