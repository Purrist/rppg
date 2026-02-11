# akon_tools.py - Akon 的工具箱
from datetime import datetime
import json
import os

# ============ 1. 获取时间 ============
def get_current_time():
    """获取当前时间，返回友好的中文描述"""
    now = datetime.now()
    time_str = now.strftime("%Y年%m月%d日 %H:%M")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    return f"{time_str} {weekday}"

def get_current_hour():
    """获取当前小时（用于判断早晚）"""
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
        return "夜深了，早点休息哦"

# ============ 2. 记忆管理 ============
MEMORY_DIR = "backend/memory"
MEMORY_FILE = os.path.join(MEMORY_DIR, "user_memory.json")
CONVERSATION_FILE = os.path.join(MEMORY_DIR, "conversation_history.json")

def ensure_memory_dir():
    """确保记忆目录存在"""
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
        # 初始化空文件
        if not os.path.exists(MEMORY_FILE):
            save_memory({"preferences": {}, "info": {}, "history_count": 0})
        if not os.path.exists(CONVERSATION_FILE):
            save_conversation([])

def load_memory():
    """加载用户记忆"""
    ensure_memory_dir()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"preferences": {}, "info": {}, "history_count": 0}

def save_memory(memory):
    """保存用户记忆"""
    ensure_memory_dir()
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def load_conversation():
    """加载对话历史（最近50条）"""
    ensure_memory_dir()
    try:
        with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
            return history[-50:]  # 只保留最近50条
    except:
        return []

def save_conversation(history):
    """保存对话历史"""
    ensure_memory_dir()
    # 只保留最近100条
    history = history[-100:]
    with open(CONVERSATION_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def update_preference(key, value):
    """更新用户偏好（如：喜欢的音乐、食物等）"""
    memory = load_memory()
    memory["preferences"][key] = value
    memory["history_count"] += 1
    save_memory(memory)

def get_preference(key):
    """获取用户偏好"""
    memory = load_memory()
    return memory["preferences"].get(key)

# ============ 3. 动作定义 ============
ACTIONS = {
    "play_music": {
        "description": "播放音乐",
        "params": ["音乐名称/类型"]
    },
    "play_video": {
        "description": "播放视频",
        "params": ["视频名称"]
    },
    "navigate_to": {
        "description": "跳转到页面",
        "params": ["页面名称（首页/健康/娱乐/益智/设置）"]
    },
    "show_weather": {
        "description": "显示天气",
        "params": []
    },
    "pause_playback": {
        "description": "暂停/继续播放",
        "params": []
    }
}

def execute_action(action_name, params=None):
    """执行动作（这里只是示例，实际需要集成到你的项目）"""
    if action_name not in ACTIONS:
        return f"抱歉，我不知道怎么执行 '{action_name}'"
    
    action_info = ACTIONS[action_name]
    desc = action_info["description"]
    
    # 这里返回一个模拟的响应
    # 实际项目中，你会通过 Socket.IO 发送消息给前端
    return f"正在{desc}：{', '.join(params) if params else '无参数'}"

# ============ 4. 天气API（先用模拟数据） ============
def get_weather(city="北京"):
    """获取天气信息（先用模拟数据，后面可以接真实API）"""
    # TODO: 接入真实的天气API（如和风天气、心知天气）
    weather_data = {
        "北京": {"temperature": "18°C", "condition": "晴", "humidity": "45%"},
        "上海": {"temperature": "21°C", "condition": "多云", "humidity": "60%"},
        "广州": {"temperature": "26°C", "condition": "小雨", "humidity": "80%"},
    }
    return weather_data.get(city, {"temperature": "未知", "condition": "未知", "humidity": "未知"})

def format_weather_response(city="北京"):
    """格式化天气回复"""
    weather = get_weather(city)
    time = get_current_time()
    greeting = get_time_greeting()
    
    return f"{greeting}，张爷爷！现在是{time}。{city}今天{weather['condition']}，温度{weather['temperature']}，湿度{weather['humidity']}。"

# ============ 测试代码 ============
if __name__ == "__main__":
    # 测试时间功能
    print(get_current_time())
    print(get_time_greeting())
    
    # 测试天气功能
    print(format_weather_response("北京"))
    print(format_weather_response("上海"))
    
    # 测试记忆功能
    update_preference("favorite_music", "京剧")
    update_preference("favorite_food", "红烧肉")
    print(load_memory())
    
    # 测试动作执行
    print(execute_action("play_music", ["牡丹亭"]))
    print(execute_action("navigate_to", ["健康"]))

