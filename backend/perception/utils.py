# perception/utils.py
# 感知模块工具函数

import numpy as np
import cv2
from typing import Tuple, List


def smooth_signal(signal: np.ndarray, window_size: int = 5) -> np.ndarray:
    """平滑信号"""
    if len(signal) < window_size:
        return signal
    
    kernel = np.ones(window_size) / window_size
    return np.convolve(signal, kernel, mode='same')


def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """计算两点距离"""
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)


def normalize_value(value: float, min_val: float, max_val: float) -> float:
    """归一化值到0-1"""
    if max_val == min_val:
        return 0.5
    return (value - min_val) / (max_val - min_val)


def get_time_of_day() -> str:
    """获取时间段"""
    from datetime import datetime
    hour = datetime.now().hour
    
    if 5 <= hour < 8:
        return "early_morning"
    elif 8 <= hour < 12:
        return "morning"
    elif 12 <= hour < 14:
        return "noon"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 22:
        return "evening"
    else:
        return "night"


def draw_detection_info(frame: np.ndarray, user_state: dict) -> np.ndarray:
    """在帧上绘制检测信息"""
    h, w = frame.shape[:2]
    
    # 创建半透明背景
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (300, 200), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
    
    # 绘制文字
    y = 35
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    color = (255, 255, 255)
    
    # 情绪
    emotion = user_state.get("emotion", {})
    cv2.putText(frame, f"Emotion: {emotion.get('primary', 'N/A')}", 
                (20, y), font, font_scale, color, 1)
    y += 25
    
    # 心率
    hr = user_state.get("heart_rate", {})
    bpm = hr.get("bpm")
    bpm_text = f"Heart Rate: {bpm:.0f} BPM" if bpm else "Heart Rate: N/A"
    cv2.putText(frame, bpm_text, (20, y), font, font_scale, color, 1)
    y += 25
    
    # 姿态
    body = user_state.get("body_state", {})
    cv2.putText(frame, f"Posture: {body.get('posture', 'N/A')}", 
                (20, y), font, font_scale, color, 1)
    y += 25
    
    # 注意力
    eye = user_state.get("eye_state", {})
    attention = eye.get("attention_score", 0)
    cv2.putText(frame, f"Attention: {attention:.1%}", 
                (20, y), font, font_scale, color, 1)
    y += 25
    
    # 疲劳度
    overall = user_state.get("overall", {})
    fatigue = overall.get("fatigue_level", 0)
    cv2.putText(frame, f"Fatigue: {fatigue:.1%}", 
                (20, y), font, font_scale, color, 1)
    y += 25
    
    # 状态总结
    cv2.putText(frame, f"State: {overall.get('state_summary', 'N/A')}", 
                (20, y), font, font_scale, color, 1)
    
    return frame
