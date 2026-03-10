# perception/body_state_detector.py
# 身体状态检测模块

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple
from collections import deque
import time

# 尝试导入MediaPipe
try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class BodyStateDetector:
    """
    身体状态检测器
    
    检测：
    - posture: 姿态 (sitting, standing, walking, lying, unknown)
    - activity_level: 活动水平 (0-1)
    - activity_duration: 活动持续时间
    - head_pose: 头部姿态 (frontal, left, right, up, down)
    - movement_frequency: 动作频率
    - stillness_duration: 静止持续时间
    """
    
    def __init__(self):
        # MediaPipe Pose
        if HAS_MEDIAPIPE:
            self.mp_pose = mp.solutions.pose
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
        
        # 历史记录
        self.pose_history = deque(maxlen=60)
        self.position_history = deque(maxlen=300)
        
        # 状态
        self.current_posture = "unknown"
        self.posture_start_time = time.time()
        self.activity_level = 0.0
        self.movement_frequency = 0.0
        self.stillness_start_time = time.time()
        
        # 上次位置
        self.last_shoulder_center = None
        self.last_time = time.time()
        self.prev_gray = None
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        """检测身体状态"""
        if frame is None or frame.size == 0:
            return self._get_default_result()
        
        result = self._get_default_result()
        
        try:
            if HAS_MEDIAPIPE:
                result = self._detect_with_mediapipe(frame)
            else:
                result = self._detect_simple(frame)
            
            # 更新历史
            self.pose_history.append({
                "posture": result["posture"],
                "activity_level": result["activity_level"],
                "time": time.time()
            })
            
            # 计算活动持续时间
            if result["posture"] == self.current_posture:
                result["activity_duration"] = time.time() - self.posture_start_time
            else:
                self.current_posture = result["posture"]
                self.posture_start_time = time.time()
            
            # 计算静止时间
            if result["activity_level"] < 0.1:
                result["stillness_duration"] = time.time() - self.stillness_start_time
            else:
                self.stillness_start_time = time.time()
                result["stillness_duration"] = 0
            
            # 计算动作频率
            result["movement_frequency"] = self._calculate_movement_frequency()
            
        except Exception as e:
            print(f"[身体状态检测] 错误: {e}")
        
        return result
    
    def _get_default_result(self) -> Dict[str, Any]:
        """获取默认结果"""
        return {
            "posture": self.current_posture,
            "activity_level": self.activity_level,
            "activity_duration": time.time() - self.posture_start_time,
            "head_pose": "frontal",
            "movement_frequency": self.movement_frequency,
            "stillness_duration": time.time() - self.stillness_start_time,
        }
    
    def _detect_with_mediapipe(self, frame: np.ndarray) -> Dict[str, Any]:
        """使用MediaPipe检测"""
        result = self._get_default_result()
        
        h, w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        pose_result = self.pose.process(rgb_frame)
        
        if pose_result.pose_landmarks:
            landmarks = pose_result.pose_landmarks.landmark
            
            # 获取关键点
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
            right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
            left_knee = landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE.value]
            right_knee = landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE.value]
            nose = landmarks[self.mp_pose.PoseLandmark.NOSE.value]
            left_ear = landmarks[self.mp_pose.PoseLandmark.LEFT_EAR.value]
            right_ear = landmarks[self.mp_pose.PoseLandmark.RIGHT_EAR.value]
            
            # 计算肩膀中心
            shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
            shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2
            
            # 计算活动水平
            current_time = time.time()
            if self.last_shoulder_center is not None:
                dx = shoulder_center_x - self.last_shoulder_center[0]
                dy = shoulder_center_y - self.last_shoulder_center[1]
                dt = current_time - self.last_time
                
                if dt > 0:
                    speed = np.sqrt(dx*dx + dy*dy) / dt
                    result["activity_level"] = min(1.0, speed * 5)
            
            self.last_shoulder_center = (shoulder_center_x, shoulder_center_y)
            self.last_time = current_time
            
            # 记录位置历史
            self.position_history.append({
                "x": shoulder_center_x,
                "y": shoulder_center_y,
                "time": current_time
            })
            
            # 判断姿态
            hip_center_y = (left_hip.y + right_hip.y) / 2
            knee_center_y = (left_knee.y + right_knee.y) / 2
            shoulder_hip_dist = hip_center_y - shoulder_center_y
            hip_knee_dist = knee_center_y - hip_center_y
            
            if shoulder_hip_dist > 0 and hip_knee_dist > 0:
                if hip_knee_dist < shoulder_hip_dist * 0.5:
                    result["posture"] = "sitting"
                else:
                    result["posture"] = "standing"
            
            if abs(shoulder_center_y - hip_center_y) < 0.1:
                result["posture"] = "lying"
            
            # 判断走动
            if len(self.position_history) >= 30:
                recent = list(self.position_history)[-30:]
                positions = [(p["x"], p["y"]) for p in recent]
                total_movement = sum(
                    np.sqrt((positions[i][0]-positions[i-1][0])**2 + 
                           (positions[i][1]-positions[i-1][1])**2)
                    for i in range(1, len(positions))
                )
                if total_movement > 1.0 and result["posture"] == "standing":
                    result["posture"] = "walking"
            
            # 头部姿态
            ear_diff_x = left_ear.x - right_ear.x
            
            if abs(ear_diff_x) > 0.1:
                result["head_pose"] = "right" if ear_diff_x > 0 else "left"
            elif nose.y < shoulder_center_y - 0.3:
                result["head_pose"] = "up"
            elif nose.y > shoulder_center_y - 0.1:
                result["head_pose"] = "down"
            else:
                result["head_pose"] = "frontal"
        
        return result
    
    def _detect_simple(self, frame: np.ndarray) -> Dict[str, Any]:
        """简化版检测"""
        result = self._get_default_result()
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        
        if self.prev_gray is not None:
            frame_delta = cv2.absdiff(self.prev_gray, gray)
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            motion_pixels = np.count_nonzero(thresh)
            total_pixels = thresh.shape[0] * thresh.shape[1]
            result["activity_level"] = min(1.0, motion_pixels / total_pixels * 10)
        
        self.prev_gray = gray
        return result
    
    def _calculate_movement_frequency(self) -> float:
        """计算动作频率"""
        if len(self.pose_history) < 30:
            return 0.0
        
        recent = list(self.pose_history)[-60:]
        changes = 0
        prev_active = recent[0]["activity_level"] > 0.2
        
        for p in recent[1:]:
            curr_active = p["activity_level"] > 0.2
            if curr_active != prev_active:
                changes += 1
            prev_active = curr_active
        
        duration = recent[-1]["time"] - recent[0]["time"]
        return changes / duration * 60 if duration > 0 else 0.0
