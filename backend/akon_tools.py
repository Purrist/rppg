# akon_tools.py - Akon 工具箱（Qwen3.5-4B 版本）
# 包含：时间、天气、记忆、动作、页面导航等工具

from datetime import datetime
import json
import os

# ============ 路径配置 ============
MEMORY_DIR = "backend/memory"
MEMORY_FILE = os.path.join(MEMORY_DIR, "user_memory.json")
CONVERSATION_FILE = os.path.join(MEMORY_DIR, "conversation_history.json")

# ============ 1. 时间工具 ============
def get_current_time():
    """获取当前时间，返回友好的中文描述"""
    now = datetime.now()
    time_str = now.strftime("%Y年%m月%d日 %H:%M")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    return f"{time_str} {weekday}"

def get_current_hour():
    """获取当前小时"""
    return datetime.now().hour

def get_time_greeting():
    """根据时间返回问候语"""
    hour = get_current_hour()
    if 5 <= hour < 12:
        return "早上好"
    elif 12 <= hour < 18:
        return "下午好"
    elif 18 <= hour < 22:
        return "晚上好"
    else:
        return "夜深了"

# ============ 2. 天气工具 ============
def get_weather(city="北京"):
    """获取天气信息（模拟数据）"""
    weather_data = {
        "北京": {"temperature": "18°C", "condition": "晴", "humidity": "45%", "wind": "北风3级"},
        "上海": {"temperature": "21°C", "condition": "多云", "humidity": "60%", "wind": "东风2级"},
        "广州": {"temperature": "26°C", "condition": "小雨", "humidity": "80%", "wind": "南风2级"},
    }
    return weather_data.get(city, {"temperature": "20°C", "condition": "晴", "humidity": "50%", "wind": "微风"})

def format_weather_response(city="北京"):
    """格式化天气回复"""
    weather = get_weather(city)
    time = get_current_time()
    greeting = get_time_greeting()
    
    return f"{greeting}！现在是{time}。{city}今天{weather['condition']}，温度{weather['temperature']}，湿度{weather['humidity']}，{weather['wind']}。"

# ============ 3. 记忆管理 ============
def ensure_memory_dir():
    """确保记忆目录存在"""
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
    if not os.path.exists(MEMORY_FILE):
        save_memory({"preferences": {}, "info": {"name": "张爷爷"}, "history_count": 0})
    if not os.path.exists(CONVERSATION_FILE):
        save_conversation([])

def load_memory():
    """加载用户记忆"""
    ensure_memory_dir()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"preferences": {}, "info": {"name": "张爷爷"}, "history_count": 0}

def save_memory(memory):
    """保存用户记忆"""
    ensure_memory_dir()
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def load_conversation():
    """加载对话历史"""
    ensure_memory_dir()
    try:
        with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_conversation(history):
    """保存对话历史"""
    ensure_memory_dir()
    history = history[-100:]  # 只保留最近100条
    with open(CONVERSATION_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def update_preference(key, value):
    """更新用户偏好"""
    memory = load_memory()
    memory["preferences"][key] = value
    memory["history_count"] += 1
    save_memory(memory)
    return f"好的，我记住了您喜欢{value}"

def get_preference(key):
    """获取用户偏好"""
    memory = load_memory()
    return memory["preferences"].get(key)

# ============ 4. 页面导航映射 ============
PAGE_ROUTES = {
    "首页": "/", "主页": "/", "回家": "/",
    "健康": "/health", "身体": "/health", "运动": "/health",
    "娱乐": "/entertainment", "玩": "/entertainment", "音乐": "/entertainment", "视频": "/entertainment",
    "益智": "/learning", "学习": "/learning", "游戏": "/learning", "认知": "/learning",
    "打地鼠": "/training", "地鼠": "/training",
    "设置": "/settings", "系统": "/settings"
}

def get_page_route(page_name):
    """根据页面名称获取路由"""
    return PAGE_ROUTES.get(page_name)

# ============ 5. 工具定义（供 Qwen3.5 Function Calling 使用）============
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "导航到指定页面。当用户想去某个页面时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {
                        "type": "string",
                        "description": "目标页面路径，如 /health, /entertainment, /learning, /settings"
                    }
                },
                "required": ["page"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "show_weather",
            "description": "显示天气信息。当用户问天气时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，默认北京"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "show_time",
            "description": "显示当前时间。当用户问时间时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "播放音乐。当用户想听音乐时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "music_type": {
                        "type": "string",
                        "description": "音乐类型，如 京剧、民歌、戏曲、流行"
                    }
                },
                "required": ["music_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_video",
            "description": "播放视频。当用户想看视频时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_name": {
                        "type": "string",
                        "description": "视频名称，如 西游记、三国演义"
                    }
                },
                "required": ["video_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_game",
            "description": "开始认知训练游戏。当用户想玩游戏时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_name": {
                        "type": "string",
                        "description": "游戏名称，如 打地鼠、色词测试"
                    }
                },
                "required": ["game_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_preference",
            "description": "保存用户偏好到记忆。当用户表达喜欢某事物时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "偏好类别，如 favorite_music, favorite_food, favorite_video"
                    },
                    "value": {
                        "type": "string",
                        "description": "偏好值"
                    }
                },
                "required": ["category", "value"]
            }
        }
    }
]

# ============ 6. 工具执行器 ============
def execute_tool(tool_name, arguments):
    """
    执行工具调用
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数字典
    
    Returns:
        (success, result) 元组
    """
    if tool_name == "navigate_to":
        page = arguments.get("page", "/")
        return True, {"action": "navigate", "page": page}
    
    elif tool_name == "show_weather":
        city = arguments.get("city", "北京")
        weather_text = format_weather_response(city)
        return True, {"action": "weather", "text": weather_text}
    
    elif tool_name == "show_time":
        time_text = f"现在是{get_current_time()}"
        return True, {"action": "time", "text": time_text}
    
    elif tool_name == "play_music":
        music_type = arguments.get("music_type", "民歌")
        return True, {"action": "play_music", "music_type": music_type}
    
    elif tool_name == "play_video":
        video_name = arguments.get("video_name", "")
        return True, {"action": "play_video", "video_name": video_name}
    
    elif tool_name == "start_game":
        game_name = arguments.get("game_name", "打地鼠")
        return True, {"action": "start_game", "game_name": game_name}
    
    elif tool_name == "save_preference":
        category = arguments.get("category", "")
        value = arguments.get("value", "")
        if category and value:
            update_preference(category, value)
            return True, {"action": "save_preference", "text": f"好的，我记住了您喜欢{value}"}
        return False, {"error": "缺少参数"}
    
    else:
        return False, {"error": f"未知工具: {tool_name}"}


# ============ 测试代码 ============
if __name__ == "__main__":
    print("=== Akon 工具箱测试 ===\n")
    
    # 测试时间
    print(f"当前时间: {get_current_time()}")
    print(f"问候语: {get_time_greeting()}\n")
    
    # 测试天气
    print(f"天气: {format_weather_response('北京')}\n")
    
    # 测试页面路由
    print(f"页面路由: {get_page_route('健康')}")
    print(f"页面路由: {get_page_route('打地鼠')}\n")
    
    # 测试工具执行
    success, result = execute_tool("navigate_to", {"page": "/health"})
    print(f"导航工具: {result}")
    
    success, result = execute_tool("show_weather", {"city": "北京"})
    print(f"天气工具: {result}")
