# core/core_agent.py
# Agent核心 - LLM推理

import os
import json
import time
import requests
from typing import Dict, Tuple


class AkonAgentState:
    """Agent状态"""
    def __init__(self):
        self.last_think_time = 0
        self.min_think_interval = 3.0
        self.thinking = False

agent_state = AkonAgentState()


def should_think(world_state: dict) -> bool:
    """判断是否需要思考"""
    if time.time() - agent_state.last_think_time < agent_state.min_think_interval:
        return False
    if agent_state.thinking:
        return False
    
    elder = world_state.get("elder", {})
    triggers = [
        elder.get("speaking", False),
        elder.get("activity_changed", False),
        elder.get("idle_minutes", 0) > 15,
        world_state.get("user_request"),
    ]
    return any(triggers)


def think(world_state: dict, state_manager=None) -> dict:
    """LLM推理"""
    agent_state.thinking = True
    agent_state.last_think_time = time.time()
    
    try:
        prompt = _build_think_prompt(world_state, state_manager)
        model = _select_model(world_state)
        
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            return _parse_decision(result)
        
        return {"need_action": False, "speak": "让我想想..."}
    
    except Exception as e:
        print(f"[Agent] 思考错误: {e}")
        return {"need_action": False}
    
    finally:
        agent_state.thinking = False


def ask_akon(user_input: str, system_state: dict) -> Tuple[str, dict]:
    """对话接口"""
    prompt = f"""你是阿康，一个温暖的陪伴助手。用户说：{user_input}

当前状态：页面{system_state.get('current_page', '/')}
{'正在玩' + system_state.get('game_name') if system_state.get('game_active') else ''}

请用简短温暖的话回复（不超过50字），如果需要执行动作，用JSON格式：
{{"response": "回复内容", "action": {{"type": "navigate/play/game", ...}}}}

动作类型：navigate(跳转页面), play(播放), game(开始游戏)"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:3b", "prompt": prompt, "stream": False},
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            return _parse_response(result)
        
        return "我听到了，让我想想...", None
    
    except Exception as e:
        return "网络有点问题，请稍等", None


def get_agent_state() -> dict:
    return {
        "thinking": agent_state.thinking,
        "last_think_time": agent_state.last_think_time
    }


def _build_think_prompt(world_state: dict, state_manager) -> str:
    summary = state_manager.get_world_summary() if state_manager else ""
    prefs = state_manager.get_user_preferences_text() if state_manager else ""
    
    return f"""你是阿康，一个主动关怀的陪伴助手。

当前状态：
{summary}

用户偏好：{prefs}

请判断是否需要主动关怀。如果需要，返回JSON：
{{"need_action": true, "action": "navigate/recommend/remind", "params": {{...}}, "speak": "要说的话"}}

关怀场景：
- 空闲超过15分钟 → 推荐活动
- 疲劳度高 → 提醒休息
- 情绪低落 → 推荐娱乐

如果不需要行动，返回：{{"need_action": false}}"""


def _select_model(world_state: dict) -> str:
    if world_state.get("elder", {}).get("speaking"):
        return "qwen2.5:3b"
    if world_state.get("elder", {}).get("idle_minutes", 0) > 30:
        return "qwen3.5:4b"
    return "qwen2.5:3b"


def _parse_decision(response: str) -> dict:
    import re
    json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    return {"need_action": False, "speak": response[:100]}


def _parse_response(response: str) -> Tuple[str, dict]:
    import re
    json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return data.get("response", response), data.get("action")
        except:
            pass
    return response, None
