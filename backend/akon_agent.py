# akon_agent.py - 真正的具身智能体
# 核心：理解意图 → 自主决策 → 执行行动
# 不是"问一句答一句"，而是能真正做事

import ollama
import json
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

# ============ 模型配置 ============
MODEL = "qwen2.5:3b"
GPU_OPTIONS = {
    "num_gpu": 85,
    "num_thread": 8,
    "num_ctx": 2048,
    "temperature": 0.3,
    "num_predict": 512,
}

# ============ 用户认知模型 ============
USER_MODEL = {
    "name": "张爷爷",
    "age": 75,
    "preferences": {
        "movie_genres": ["战争片", "历史片", "京剧电影"],
        "music_types": ["京剧", "民歌"],
        "favorite_movies": ["地道战", "地雷战", "英雄儿女", "南征北战"],
        "favorite_activities": ["看戏", "听京剧", "打地鼠游戏"]
    },
    "behavior_patterns": {},
    "recent_activities": [],
    "emotional_state": None,
}

# ============ 对话历史 ============
CONVERSATION_HISTORY = []

# ============ 核心函数 ============
def ask_akon(user_input: str, system_state: Optional[dict] = None) -> Tuple[str, Optional[dict]]:
    """
    核心函数：理解用户意图，决定要执行的动作
    
    返回：
    - response: 对用户说的话
    - action: 要执行的动作（导航、推荐、播放等）
    """
    
    # 记录对话
    CONVERSATION_HISTORY.append({"role": "user", "content": user_input})
    
    # 构建系统提示词 - 让LLM理解意图并决定动作
    system_prompt = f"""你是阿康，一个真正懂张爷爷的具身智能体。

## 关于张爷爷
- 年龄：{USER_MODEL['age']}岁
- 喜欢的电影类型：{USER_MODEL['preferences']['movie_genres']}
- 喜欢的电影：{USER_MODEL['preferences']['favorite_movies']}
- 喜欢的音乐：{USER_MODEL['preferences']['music_types']}

## 你的能力
你不是一个问答机器，你能真正**做事**：
1. **导航**：跳转到指定页面
2. **推荐内容**：在页面上展示推荐内容
3. **播放媒体**：播放音乐、视频
4. **开始游戏**：打开游戏

## 重要规则
1. 当用户表达需求时，**直接行动**，不要只是问问题
2. 例如用户说"我想看电影"，你应该：
   - 跳转到娱乐页面
   - 推荐他喜欢的电影
   - 告诉他"我帮您打开了娱乐页面，推荐几部您喜欢的电影"
3. 不要说"您想看什么"，而是直接推荐他喜欢的
4. 回答要简短温暖

## 输出格式
你必须返回JSON格式：
{{
    "response": "对用户说的话",
    "action": {{
        "type": "navigate|recommend|play|game|none",
        "page": "目标页面（如果需要导航）",
        "content": {{
            "type": "movie|music|game",
            "items": ["推荐项目列表"]
        }}
    }}
}}

## 示例
用户："我想看电影"
返回：{{
    "response": "张爷爷，我帮您打开娱乐页面，推荐几部您喜欢的战争片～",
    "action": {{
        "type": "navigate_and_recommend",
        "page": "/entertainment",
        "content": {{
            "type": "movie",
            "items": ["地道战", "地雷战", "英雄儿女"]
        }}
    }}
}}

用户："我想听京剧"
返回：{{
    "response": "好的，我帮您播放京剧～",
    "action": {{
        "type": "play",
        "content": {{
            "type": "music",
            "items": ["贵妃醉酒", "霸王别姬"]
        }}
    }}
}}

用户："你好"
返回：{{
    "response": "张爷爷，下午好！今天想看点什么？",
    "action": {{
        "type": "none"
    }}
}}
"""

    # 构建消息
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加对话历史
    for msg in CONVERSATION_HISTORY[-6:]:
        messages.append(msg)
    
    try:
        # 调用LLM
        response = ollama.chat(model=MODEL, messages=messages, options=GPU_OPTIONS)
        
        # 解析响应
        if isinstance(response, dict):
            content = response.get("message", {}).get("content", "")
        else:
            content = getattr(response.message, 'content', '') if hasattr(response, 'message') else ""
        
        content = content.strip()
        
        # 解析JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            result = json.loads(json_match.group())
            response_text = result.get("response", "")
            action = result.get("action", {"type": "none"})
            
            # 记录响应
            CONVERSATION_HISTORY.append({"role": "assistant", "content": response_text})
            
            return response_text, action
        else:
            # 没有JSON，直接返回文本
            CONVERSATION_HISTORY.append({"role": "assistant", "content": content})
            return content, None
            
    except Exception as e:
        print(f"[Akon] 错误: {e}")
        return "张爷爷，我正在想...", None


# ============ 感知更新函数 ============
def update_perception(perception_data: Dict[str, Any]):
    """
    更新感知状态（供外部调用）
    这是智能体的"眼睛"
    """
    # 更新用户模型
    if "activity" in perception_data:
        USER_MODEL["recent_activities"].append({
            "activity": perception_data["activity"],
            "time": datetime.now().isoformat()
        })
        # 只保留最近20条
        USER_MODEL["recent_activities"] = USER_MODEL["recent_activities"][-20:]
    
    if "emotion" in perception_data:
        USER_MODEL["emotional_state"] = perception_data["emotion"]


def get_user_model() -> Dict:
    """获取用户模型"""
    return USER_MODEL
