# perception/utils.py
# 感知模块工具函数

import cv2
import numpy as np


def draw_detection_info(frame, user_state: dict):
    """在帧上绘制检测信息"""
    if frame is None:
        return frame
    
    y = 30
    
    # 是否有人
    person = user_state.get('person_detected', False)
    skeleton = user_state.get('skeleton_detected', False)
    cv2.putText(frame, f"Person: {'Yes' if person else 'No'} (Skeleton: {'Yes' if skeleton else 'No'})", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    y += 22
    
    # 人数
    face_count = user_state.get('face_count', 0)
    cv2.putText(frame, f"Faces: {face_count}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    y += 22
    
    # 心率
    hr = user_state.get('physical_load', {}).get('heart_rate')
    hr_text = f"HR: {hr} BPM" if hr else "HR: -- BPM"
    cv2.putText(frame, hr_text, (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    y += 22
    
    # 姿态
    posture = user_state.get('posture', {}).get('type', 'unknown')
    fall = user_state.get('physical_load', {}).get('fall_detected', False)
    posture_color = (0, 0, 255) if fall else (0, 255, 0)
    cv2.putText(frame, f"Posture: {posture}{' [FALL!]' if fall else ''}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, posture_color, 2)
    y += 22
    
    # 情绪
    emotion = user_state.get('emotion', {}).get('primary', 'unknown')
    cv2.putText(frame, f"Emotion: {emotion}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    y += 22
    
    # 三维指标
    physical = user_state.get('physical_load', {}).get('value', 0)
    cognitive = user_state.get('cognitive_load', {}).get('value', 0)
    engagement = user_state.get('engagement', {}).get('value', 0)
    
    cv2.putText(frame, f"Physical Load: {physical:.2f}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    y += 22
    
    cv2.putText(frame, f"Cognitive Load: {cognitive:.2f}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    y += 22
    
    cv2.putText(frame, f"Engagement: {engagement:.2f}", (10, y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    return frame


def draw_zone_info(frame, zones: list, active_zones: list):
    """绘制区域信息"""
    if frame is None:
        return frame
    
    for zone in zones:
        zone_id = zone.get('id', 0)
        x, y = zone.get('x', 0), zone.get('y', 0)
        radius = zone.get('radius', 50)
        
        color = (0, 255, 0) if zone_id in active_zones else (128, 128, 128)
        
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
