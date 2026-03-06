# akon_agent.py - 升级版：带系统状态的 Akon
import ollama
from akon_tools import (
    get_current_time, get_time_greeting, format_weather_response,
    load_memory, save_memory, update_preference, get_preference,
    load_conversation, save_conversation,
    execute_action, ACTIONS
)
import re

MODEL = "qwen2.5:3b"

def extract_action(user_input, system_state=None):
    """从用户输入中提取动作，结合系统状态"""
    user_input = user_input.lower()
    
    # 页面路径映射
    page_routes = {
        "首页": "/",
        "主页": "/",
        "回家": "/",
        "健康": "/health",
        "身体": "/health",
        "运动": "/health",
        "娱乐": "/entertainment",
        "玩": "/entertainment",
        "音乐": "/entertainment",
        "视频": "/entertainment",
        "益智": "/learning",
        "学习": "/learning",
        "游戏": "/learning",
        "打地鼠": "/training",
        "设置": "/settings",
        "系统": "/settings"
    }
    
    # 动作关键词映射
    action_keywords = {
        "play_music": ["播放音乐", "放音乐", "听歌", "听音乐", "来首"],
        "play_video": ["播放视频", "看视频", "看电影", "看电视"],
        "navigate_to": ["跳转", "去", "打开", "看看", "我要", "进入"],
        "show_weather": ["天气", "气温", "温度"],
        "pause_playback": ["暂停", "停止"],
        "exit_game": ["退出游戏", "结束游戏", "不玩了"]
    }
    
    detected_action = None
    action_params = []
    
    # 检测退出游戏
    if system_state and system_state.get("game_active"):
        for keyword in action_keywords.get("exit_game", []):
            if keyword in user_input:
                return "exit_game", []
    
    # 检测导航
    for keyword, route in page_routes.items():
        if keyword in user_input:
            # 检查是否在游戏中
            if system_state and system_state.get("game_active"):
                # 在游戏中，不能导航
                return None, []
            detected_action = "navigate_to"
            action_params = [route]
            break
    
    # 如果没有检测到导航，检测其他动作
    if not detected_action:
        for action, keywords in action_keywords.items():
            for keyword in keywords:
                if keyword in user_input:
                    detected_action = action
                    break
            if detected_action:
                break
    
    return detected_action, action_params

def extract_preferences(user_input):
    """从用户输入中提取用户偏好"""
    preferences = {}
    
    music_keywords = {
        "京剧": "favorite_music",
        "民歌": "favorite_music",
        "戏曲": "favorite_music",
        "流行音乐": "favorite_music",
        "红歌": "favorite_music"
    }
    
    food_keywords = {
        "红烧肉": "favorite_food",
        "饺子": "favorite_food",
        "面条": "favorite_food",
        "清淡": "food_preference",
        "辣": "food_preference"
    }
    
    all_keywords = {**music_keywords, **food_keywords}
    for keyword, pref_key in all_keywords.items():
        if keyword in user_input:
            preferences[pref_key] = keyword
    
    return preferences

def build_system_prompt(memory, time_str, weather_str, system_state=None):
    """构建系统提示词，注入时间、天气、记忆和系统状态"""
    preferences = memory.get("preferences", {})
    
    prompt = f"""你是阿康，一个温暖、耐心的老年陪伴助手。你的用户是张爷爷。

【当前信息】
- 时间：{time_str}
- 天气：{weather_str}
"""
    
    # 添加系统状态
    if system_state:
        prompt += f"""
【系统状态】
- 当前页面：{system_state.get('current_page', '/')}
- 游戏状态：{'游戏中(' + system_state.get('game_name', '') + ')' if system_state.get('game_active') else '空闲'}
- 参与度评分：{system_state.get('engagement_score', 0)}
"""
        
        # 添加用户偏好
        top_pages = system_state.get('top_pages', [])
        if top_pages:
            prompt += f"- 常访问页面：{', '.join([p[0] for p in top_pages[:3]])}\n"
        
        top_games = system_state.get('top_games', [])
        if top_games:
            prompt += f"- 常玩游戏：{', '.join([g[0] for g in top_games[:3]])}\n"
    
    prompt += """
【张爷爷的偏好】
"""
    if preferences:
        for key, value in preferences.items():
            key_cn = {
                "favorite_music": "喜欢的音乐",
                "favorite_food": "喜欢的食物",
                "food_preference": "饮食偏好"
            }.get(key, key)
            prompt += f"- {key_cn}：{value}\n"
    else:
        prompt += "- 暂无记录\n"
    
    prompt += """
【你的能力】
1. 情感陪伴：用温暖、亲切的语气和张爷爷聊天
2. 信息查询：告诉他时间、天气等信息
3. 执行动作：识别他的指令，如"播放音乐"、"跳转到健康页"等
4. 记住他的喜好：如果他提到喜欢什么，要记住
5. 智能推荐：根据他的使用习惯，推荐他可能喜欢的内容

【重要规则】
- 回答要简短，不要太长
- 如果他想执行某个动作（播放音乐、跳转页面等），明确告诉他你要执行了
- 如果他说喜欢什么东西，要在末尾加 [记住：xxx] 来标注需要记住的
- 如果他在游戏中想跳转页面，要提醒他先退出游戏
- 语气要像家人一样亲切、温暖
"""
    return prompt

def extract_memory_markers(response):
    """提取回复中的记忆标记"""
    markers = re.findall(r'\[记住：(.*?)\]', response)
    clean_response = re.sub(r'\[记住：.*?\]', '', response).strip()
    return clean_response, markers

def process_memory_markers(markers):
    """处理记忆标记，保存到文件"""
    for marker in markers:
        music_keywords = ["京剧", "民歌", "戏曲", "音乐"]
        food_keywords = ["红烧肉", "饺子", "面条", "肉"]
        
        if any(mk in marker for mk in music_keywords):
            for mk in music_keywords:
                if mk in marker:
                    update_preference("favorite_music", mk)
                    break
        
        elif any(fk in marker for fk in food_keywords):
            for fk in food_keywords:
                if fk in marker:
                    update_preference("favorite_food", fk)
                    break

def ask_akon(user_input, system_state=None):
    """
    主函数：处理用户输入，返回回复和动作
    
    Args:
        user_input: 用户输入文本
        system_state: 系统状态（可选），包含：
            - current_page: 当前页面
            - game_active: 是否在游戏中
            - game_name: 游戏名称
            - top_pages: 常访问页面
            - top_games: 常玩游戏
            - engagement_score: 参与度评分
    """
    # 1. 检查是否有动作指令
    action_name, action_params = extract_action(user_input, system_state)
    action_response = None
    
    if action_name:
        action_response = execute_action(action_name, action_params)
        if action_name == "show_weather":
            city = action_params[0] if action_params else "北京"
            return format_weather_response(city), action_name, action_params
        
        # 如果是退出游戏，直接返回
        if action_name == "exit_game":
            return "好的，正在为您退出游戏...", action_name, action_params
    
    # 2. 获取当前信息
    time_str = get_current_time()
    weather_str = format_weather_response()[:30] + "..."
    
    # 3. 提取用户偏好
    new_preferences = extract_preferences(user_input)
    for key, value in new_preferences.items():
        update_preference(key, value)
    
    # 4. 加载记忆和对话历史
    memory = load_memory()
    conversation_history = load_conversation()
    
    # 5. 构建消息
    system_prompt = build_system_prompt(memory, time_str, weather_str, system_state)
    
    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in conversation_history[-10:]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_input})
    
    if action_response:
        messages.append({"role": "assistant", "content": f"（动作执行：{action_response}）"})
    
    # 6. 调用 LLM
    try:
        resp = ollama.chat(model=MODEL, messages=messages)
        llm_response = resp["message"]["content"]
    except Exception as e:
        llm_response = f"抱歉，我出了一点小问题：{str(e)}"
    
    # 7. 处理记忆标记
    clean_response, memory_markers = extract_memory_markers(llm_response)
    process_memory_markers(memory_markers)
    
    # 8. 保存对话历史
    conversation_history.append({"role": "user", "content": user_input})
    conversation_history.append({"role": "assistant", "content": clean_response})
    save_conversation(conversation_history)
    
    # 9. 返回结果
    final_response = clean_response
    if action_response and "show_weather" not in str(action_response):
        final_response = f"{action_response}\n\n{clean_response}"
    
    return final_response, action_name, action_params

# ============ 命令行测试 ============
if __name__ == "__main__":
    print("===== Akon 升级版测试 =====\n")
    
    # 模拟系统状态
    test_state = {
        "current_page": "/",
        "game_active": False,
        "game_name": None,
        "top_pages": [("/learning", 5), ("/entertainment", 3)],
        "top_games": [("whack_a_mole", 2)],
        "engagement_score": 50
    }
    
    while True:
        user_input = input("你：")
        if user_input.lower() in ["退出", "再见", "bye"]:
            print("Akon：再见，张爷爷！有什么需要随时叫我。")
            break
        
        response, action_name, action_params = ask_akon(user_input, test_state)
        print(f"Akon：{response}")
        
        if action_name:
            print(f"  [动作] {action_name}({', '.join(str(p) for p in action_params) if action_params else ''})")
        print()
