# akon_agent.py - Akon 智能助手（Qwen2.5:3B 版本，GPU加速）
# 支持：工具调用、对话记忆

import ollama
import json
import re
from typing import Optional, List, Dict, Any, Tuple
from akon_tools import (
    get_current_time, get_time_greeting, format_weather_response,
    load_memory, save_memory, update_preference, get_preference,
    load_conversation, save_conversation,
    get_page_route, TOOLS, execute_tool
)

# ============ 模型配置 ============
# 使用 qwen3.5:3b（更快）
MODEL = "qwen2.5:3b"

# GPU加速参数
GPU_OPTIONS = {
    "num_gpu": 80,          # 全部层放GPU
    "num_thread": 16,        # CPU线程数
    "num_ctx": 2048,        # 上下文窗口
    "temperature": 0.3,     # 降低随机性
    "top_p": 0.7,           # 减少候选词
    "num_predict": 256,     # 限制输出长度
}

# ============ 简单模式（快速响应，不调用LLM）============
def ask_akon_simple(user_input: str, system_state: Optional[dict] = None) -> Tuple[str, Optional[dict]]:
    """简单模式：直接关键词匹配"""
    user_lower = user_input.lower()
    
    # 时间
    if any(kw in user_lower for kw in ["时间", "几点", "日期"]):
        return f"现在是{get_current_time()}", None
    
    # 天气
    if any(kw in user_lower for kw in ["天气", "气温", "温度"]):
        return format_weather_response("北京"), None
    
    # 导航
    page_routes = {
        "首页": "/", "主页": "/", "回家": "/",
        "健康": "/health", "身体": "/health", "运动": "/health",
        "娱乐": "/entertainment", "玩": "/entertainment", "音乐": "/entertainment", 
        "视频": "/entertainment", "电影": "/entertainment", "看": "/entertainment",
        "益智": "/learning", "学习": "/learning", "游戏": "/learning", "认知": "/learning",
        "打地鼠": "/training", "地鼠": "/training",
        "设置": "/settings", "系统": "/settings"
    }
    
    for page_name, route in page_routes.items():
        if page_name in user_lower:
            return f"好的，正在为您跳转到{page_name}...", {"action": "navigate", "page": route}
    
    # 游戏
    if any(kw in user_lower for kw in ["打地鼠", "玩游戏"]):
        return "好的，正在为您打开打地鼠游戏...", {"action": "start_game", "game_name": "打地鼠"}
    
    # 音乐
    if any(kw in user_lower for kw in ["音乐", "听歌", "京剧", "民歌", "唱歌"]):
        music_type = "京剧" if "京剧" in user_lower else "民歌"
        return f"好的，正在为您播放{music_type}...", {"action": "play_music", "music_type": music_type}
    
    # 问候语（快速响应）
    greetings = ["你好", "您好", "早上好", "下午好", "晚上好", "嗨", "hi", "hello"]
    if any(g in user_lower for g in greetings):
        hour = get_current_hour()
        if 5 <= hour < 12:
            greet = "早上好"
        elif 12 <= hour < 18:
            greet = "下午好"
        else:
            greet = "晚上好"
        return f"{greet}，张爷爷！有什么需要帮忙的吗？", None
    
    return None, None


def get_current_hour():
    """获取当前小时"""
    from datetime import datetime
    return datetime.now().hour


# ============ 系统提示词 ============
def build_system_prompt(memory: dict, system_state: Optional[dict] = None) -> str:
    """构建系统提示词"""
    user_name = memory.get("info", {}).get("name", "张爷爷")
    
    prompt = f"""你是阿康，张爷爷的智能陪伴助手。语气要像家人一样亲切温暖。

当前时间：{get_current_time()}

规则：
1. 回答简短自然，不要太长
2. 语气温暖亲切
3. 如果用户想看电影、听音乐，告诉他去娱乐页面
"""
    return prompt


# ============ 核心对话函数 ============
def ask_akon(
    user_input: str,
    system_state: Optional[dict] = None
) -> Tuple[str, Optional[dict]]:
    """主函数：处理用户输入，返回回复和动作"""
    
    # 先尝试简单模式
    simple_response, simple_action = ask_akon_simple(user_input, system_state)
    if simple_response:
        return simple_response, simple_action
    
    # 调用LLM
    memory = load_memory()
    system_prompt = build_system_prompt(memory, system_state)
    conversation_history = load_conversation()
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-6:]:  # 减少历史
        messages.append(msg)
    messages.append({"role": "user", "content": user_input})
    
    llm_response = ""
    
    try:
        # 调用ollama（使用GPU加速参数）
        resp = ollama.chat(
            model=MODEL,
            messages=messages,
            options=GPU_OPTIONS
        )
        
        # 正确解析响应
        if hasattr(resp, 'message'):
            # 对象格式
            llm_response = resp.message.content if hasattr(resp.message, 'content') else ""
        elif isinstance(resp, dict):
            # 字典格式
            message = resp.get("message", {})
            if isinstance(message, dict):
                llm_response = message.get("content", "")
            elif hasattr(message, 'content'):
                llm_response = message.content
            else:
                llm_response = str(message) if message else ""
        else:
            llm_response = str(resp)
        
        # 清理响应
        llm_response = llm_response.strip()
        
        # 如果响应为空或包含错误信息
        if not llm_response or "model=" in llm_response or "created_at=" in llm_response:
            llm_response = "张爷爷，我没太听懂，您可以再说一遍吗？"
        
    except Exception as e:
        print(f"[Akon] 错误: {e}")
        llm_response = "张爷爷，我正在思考，请稍等..."
    
    # 保存对话历史
    conversation_history.append({"role": "user", "content": user_input})
    conversation_history.append({"role": "assistant", "content": llm_response})
    save_conversation(conversation_history)
    
    return llm_response, None
