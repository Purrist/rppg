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
    
    perception = world_state.get("perception", {})
    triggers = [
        perception.get("speaking", False),
        perception.get("activity_changed", False),
        perception.get("idleMinutes", 0) > 15,
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
    """对话接口 - 返回纯文本回复和可选的action"""
    
    # ⭐ 简化prompt，要求直接返回纯文本，只在需要跳转时附加标记
    prompt = f'''你是阿康，一个温暖的陪伴助手。用户说："{user_input}"

当前页面：{system_state.get('current_page', '/')}

请直接回复用户的话，用温暖简短的语气，使用自然的口语化表达。

只有当用户明确要求跳转页面或询问某个功能时，才添加[ACTION:页面路径]标记。
如果用户只是闲聊、问问题、寻求建议，不需要跳转，直接回答即可。

例如：
用户：我想看电影
回复：好的，为您跳转到娱乐页面。
[ACTION:/entertainment]

用户：西红柿炒鸡蛋怎么做
回复：西红柿炒鸡蛋很简单，先炒鸡蛋，再炒西红柿混在一起就好啦。

可用页面：
- /entertainment (娱乐视频)
- /learning (益智游戏)
- /health (健康监测)
- /settings (设置)
- /call (通话)
- /contact (联系人)
- / (首页)
'''

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "gemma3:4b", "prompt": prompt, "stream": False},
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            return _parse_simple_response(result)
        
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
    if world_state.get("perception", {}).get("speaking"):
        return "gemma3:4b"
    if world_state.get("perception", {}).get("idleMinutes", 0) > 30:
        return "gemma3:4b"
    return "gemma3:4b"


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
    """解析LLM响应，提取JSON中的response和action"""
    import re
    
    # 尝试匹配JSON对象（支持嵌套）
    # 查找第一个 { 和最后一个匹配的 }
    start = response.find('{')
    end = response.rfind('}')
    
    if start != -1 and end != -1 and start < end:
        try:
            json_str = response[start:end+1]
            data = json.loads(json_str)
            
            # 只返回response字段的内容，去掉多余空白
            resp_text = data.get("response", "").strip()
            action = data.get("action")
            
            # 如果response为空，返回原始响应（去掉JSON部分）
            if not resp_text:
                resp_text = response[:start].strip() + response[end+1:].strip()
                resp_text = resp_text.strip('`"\' \n\r')
            
            return resp_text, action
        except json.JSONDecodeError:
            pass
    
    # 没有JSON或解析失败，返回清理后的原始响应
    clean_response = response.strip('`"\' \n\r')
    return clean_response, None


def _parse_simple_response(response: str) -> Tuple[str, dict]:
    """⭐ 简化版响应解析 - 提取纯文本和[ACTION:路径]或JSON格式的action"""
    import re
    import json
    
    action = None
    
    # 首先尝试解析 JSON 格式的响应（如果有的话）
    json_start = response.find('{')
    json_end = response.rfind('}')
    if json_start != -1 and json_end != -1 and json_start < json_end:
        try:
            json_str = response[json_start:json_end+1]
            data = json.loads(json_str)
            if 'action' in data:
                action = data['action']
                # 如果response中有文本字段，优先使用
                if 'response' in data:
                    response = data['response']
                else:
                    # 否则使用JSON前面的文本
                    response = response[:json_start].strip()
        except json.JSONDecodeError:
            pass
    
    # 如果没有找到JSON的action，尝试查找 [ACTION:页面路径] 标记
    if not action:
        action_match = re.search(r'\[ACTION:([^\]]+)\]', response)
        if action_match:
            page = action_match.group(1).strip()
            action = {"type": "navigate", "page": page}
            # 移除 ACTION 标记，保留前面的文本
            response = response[:action_match.start()].strip()
    
    # 清理响应文本
    clean_response = response.strip('`"\' \n\r')
    
    return clean_response, action
