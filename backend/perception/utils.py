# perception/utils.py
# 感知模块工具函数

import cv2
import numpy as np


def draw_detection_info(frame, user_state: dict):
    """在帧上绘制检测信息 - 兼容新版数据结构"""
    if frame is None:
        return frame
    
    y = 30
    
    # 是否有人
    person = user_state.get('person_detected', False)
    cv2.putText(frame, f"Person: {'Yes' if person else 'No'}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 人数
    face_count = user_state.get('face_count', 0)
    cv2.putText(frame, f"Faces: {face_count}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 心率
    hr = user_state.get('heart_rate')
    hr_text = f"HR: {hr} BPM" if hr else "HR: -- BPM"
    cv2.putText(frame, hr_text, (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 眼睛状态
    eye_state = user_state.get('eye_state', 'unknown')
    cv2.putText(frame, f"Eyes: {eye_state}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 头部朝向
    head_dir = user_state.get('head_direction', 'unknown')
    cv2.putText(frame, f"Head: {head_dir}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 微笑
    smiling = user_state.get('is_smiling', False)
    cv2.putText(frame, f"Smile: {'Yes' if smiling else 'No'}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 亮度
    light = user_state.get('light_level', 'unknown')
    cv2.putText(frame, f"Light: {light}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 姿态
    posture = user_state.get('posture', 'unknown')
    cv2.putText(frame, f"Posture: {posture}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 活动水平
    activity = user_state.get('activity_level', 0)
    cv2.putText(frame, f"Activity: {activity:.0%}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 25
    
    # 注意力
    attention = user_state.get('attention_score', 0)
    cv2.putText(frame, f"Attention: {attention:.0%}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    return frame


def draw_zone_info(frame, zones: list, active_zones: list):
    """绘制区域信息"""
    if frame is None:
        return frame
    
    for zone in zones:
        zone_id = zone.get('id', 0)
        x, y = zone.get('x', 0), zone.get('y', 0)
        radius = zone.get('radius', 50)
        
        # 颜色
        color = (0, 255, 0) if zone_id in active_zones else (128, 128, 128)
        
        # 绘制圆
        cv2.circle(frame, (x, y), radius, color, 2)
        cv2.putText(frame, str(zone_id), (x - 10, y + 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    
    return frame


def calculate_distance(point1, point2):
    """计算两点距离"""
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)


def is_point_in_zone(point, zone):
    """判断点是否在区域内"""
    x, y = point
    zx, zy = zone.get('x', 0), zone.get('y', 0)
    radius = zone.get('radius', 50)
    
    return calculate_distance((x, y), (zx, zy)) <= radius
