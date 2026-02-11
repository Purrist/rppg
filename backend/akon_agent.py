# akon_agent.py - 升级版：带时间/天气/记忆/动作的 Akon
import ollama
from akon_tools import (
    get_current_time, get_time_greeting, format_weather_response,
    load_memory, save_memory, update_preference, get_preference,
    load_conversation, save_conversation,
    execute_action, ACTIONS
)
import re

MODEL = "qwen2.5:3b"

def extract_action(user_input):
    """从用户输入中提取动作（简单的关键词匹配）"""
    user_input = user_input.lower()
    
    # 定义动作关键词映射
    action_keywords = {
        "play_music": ["播放", "放", "听歌", "音乐", "戏曲", "京剧", "民歌"],
        "play_video": ["播放", "看", "视频", "电影", "电视剧"],
        "navigate_to": ["跳转", "去", "打开", "看看"],
        "show_weather": ["天气", "气温", "温度"],
        "pause_playback": ["暂停", "停止", "继续"]
    }
    
    # 页面关键词
    page_keywords = {
        "首页": ["首页", "主页", "回家"],
        "健康": ["健康", "身体", "运动"],
        "娱乐": ["娱乐", "玩", "音乐", "视频"],
        "益智": ["益智", "学习", "游戏"],
        "设置": ["设置", "系统"]
    }
    
    # 检测动作
    detected_action = None
    action_params = []
    
    for action, keywords in action_keywords.items():
        for keyword in keywords:
            if keyword in user_input:
                detected_action = action
                # 提取动作参数（简单的词提取）
                if action == "play_music":
                    # 尝试提取音乐名称
                    music_keywords = ["京剧", "民歌", "戏曲", "红歌", "流行"]
                    for mk in music_keywords:
                        if mk in user_input:
                            action_params.append(mk)
                            break
                    if not action_params:
                        # 如果没识别到具体音乐，用记忆中的偏好
                        fav_music = get_preference("favorite_music")
                        if fav_music:
                            action_params.append(fav_music)
                
                elif action == "navigate_to":
                    # 尝试提取页面名称
                    for page, page_words in page_keywords.items():
                        for pw in page_words:
                            if pw in user_input:
                                action_params.append(page)
                                break
                
                elif action == "show_weather":
                    # 提取城市名称
                    cities = ["北京", "上海", "广州", "深圳", "杭州"]
                    for city in cities:
                        if city in user_input:
                            action_params.append(city)
                            break
                
                break
    
    if detected_action:
        return detected_action, action_params
    return None, []

def extract_preferences(user_input):
    """从用户输入中提取用户偏好"""
    preferences = {}
    
    # 音乐偏好
    music_keywords = {
        "京剧": "favorite_music",
        "民歌": "favorite_music",
        "戏曲": "favorite_music",
        "流行音乐": "favorite_music",
        "红歌": "favorite_music"
    }
    
    # 食物偏好
    food_keywords = {
        "红烧肉": "favorite_food",
        "饺子": "favorite_food",
        "面条": "favorite_food",
        "清淡": "food_preference",
        "辣": "food_preference"
    }
    
    # 检测偏好
    all_keywords = {**music_keywords, **food_keywords}
    for keyword, pref_key in all_keywords.items():
        if keyword in user_input:
            preferences[pref_key] = keyword
    
    return preferences

def build_system_prompt(memory, time_str, weather_str):
    """构建系统提示词，注入时间、天气、记忆"""
    preferences = memory.get("preferences", {})
    
    prompt = f"""你是阿康，一个温暖、耐心的老年陪伴助手。你的用户是张爷爷。

【当前信息】
- 时间：{time_str}
- 天气：{weather_str}

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

【重要规则】
- 回答要简短，不要太长
- 如果他想执行某个动作（播放音乐、跳转页面等），明确告诉他你要执行了
- 如果他说喜欢什么东西，要在末尾加 [记住：xxx] 来标注需要记住的
- 语气要像家人一样亲切、温暖
"""
    return prompt

def extract_memory_markers(response):
    """提取回复中的记忆标记"""
    markers = re.findall(r'\[记住：(.*?)\]', response)
    # 移除标记
    clean_response = re.sub(r'\[记住：.*?\]', '', response).strip()
    return clean_response, markers

def process_memory_markers(markers):
    """处理记忆标记，保存到文件"""
    for marker in markers:
        # 简单的关键词匹配
        music_keywords = ["京剧", "民歌", "戏曲", "音乐"]
        food_keywords = ["红烧肉", "饺子", "面条", "肉"]
        
        if any(mk in marker for mk in music_keywords):
            # 记录音乐偏好
            for mk in music_keywords:
                if mk in marker:
                    update_preference("favorite_music", mk)
                    break
        
        elif any(fk in marker for fk in food_keywords):
            # 记录食物偏好
            for fk in food_keywords:
                if fk in marker:
                    update_preference("favorite_food", fk)
                    break

def ask_akon(user_input):
    """主函数：处理用户输入，返回回复和动作"""
    # 1. 检查是否有动作指令
    action_name, action_params = extract_action(user_input)
    action_response = None
    
    if action_name:
        # 执行动作
        action_response = execute_action(action_name, action_params)
        # 对于某些动作，直接返回，不需要 LLM 处理
        if action_name == "show_weather":
            city = action_params[0] if action_params else "北京"
            return format_weather_response(city), action_name, action_params
    
    # 2. 获取当前信息
    time_str = get_current_time()
    weather_str = format_weather_response()[:30] + "..."  # 截取一部分
    
    # 3. 提取用户偏好
    new_preferences = extract_preferences(user_input)
    for key, value in new_preferences.items():
        update_preference(key, value)
    
    # 4. 加载记忆和对话历史
    memory = load_memory()
    conversation_history = load_conversation()
    
    # 5. 构建消息
    system_prompt = build_system_prompt(memory, time_str, weather_str)
    
    # 构建对话历史（最近10轮）
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加历史对话（限制最近10轮）
    for msg in conversation_history[-10:]:
        messages.append(msg)
    
    # 添加当前用户输入
    messages.append({"role": "user", "content": user_input})
    
    # 如果有动作响应，也加上
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
        # 如果有其他动作，加上动作响应
        final_response = f"{action_response}\n\n{clean_response}"
    
    return final_response, action_name, action_params

# ============ 命令行测试 ============
if __name__ == "__main__":
    print("===== Akon 升级版测试 =====\n")
    
    while True:
        user_input = input("你：")
        if user_input.lower() in ["退出", "再见", "bye"]:
            print("Akon：再见，张爷爷！有什么需要随时叫我。")
            break
        
        response, action_name, action_params = ask_akon(user_input)
        print(f"Akon：{response}")
        
        if action_name:
            print(f"  [动作] {action_name}({', '.join(action_params) if action_params else ''})")
        print()

