# perception/environment_detector.py
# 环境检测模块

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


class EnvironmentDetector:
    """
    环境检测器
    
    检测环境状态：
    - light_level: 光照水平 (dark, dim, normal, bright)
    - light_value: 光照数值
    - person_count: 人数
    - person_present: 是否有人
    - person_distance: 人与摄像头距离
    - face_detected: 是否检测到人脸
    - face_id: 人脸ID（用于识别）
    """
    
    # 光照阈值
    LIGHT_THRESHOLDS = {
        "dark": 50,
        "dim": 100,
        "normal": 180,
        "bright": 220
    }
    
    def __init__(self):
        # 人脸检测器
        if HAS_MEDIAPIPE:
            self.mp_face = mp.solutions.face_detection
            self.face_detector = self.mp_face.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5
            )
        else:
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
        
        # 人脸识别器（用于识别不同用户）
        self.face_recognizer = None
        self.known_faces = {}  # id -> face_encoding
        self.next_face_id = 1
        
        # 历史记录
        self.light_history = deque(maxlen=30)
        self.person_history = deque(maxlen=10)
        
        # 上次结果
        self.last_result = {
            "light_level": "normal",
            "light_value": 0,
            "person_count": 0,
            "person_present": False,
            "person_distance": None,
            "face_detected": False,
            "face_id": None,
        }
    
    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        检测环境状态
        
        Args:
            frame: BGR图像
        
        Returns:
            环境状态字典
        """
        if frame is None or frame.size == 0:
            return self.last_result
        
        result = self.last_result.copy()
        
        try:
            # 1. 光照检测
            light_level, light_value = self._detect_light(frame)
            result["light_level"] = light_level
            result["light_value"] = light_value
            self.light_history.append(light_value)
            
            # 2. 人脸/人检测
            person_info = self._detect_persons(frame)
            result.update(person_info)
            
            self.last_result = result
            
        except Exception as e:
            print(f"[环境检测] 错误: {e}")
        
        return result
    
    def _detect_light(self, frame: np.ndarray) -> Tuple[str, int]:
        """检测光照水平"""
        # 转换到灰度图
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        
        # 计算平均亮度
        light_value = int(np.mean(gray))
        
        # 分类
        if light_value < self.LIGHT_THRESHOLDS["dark"]:
            light_level = "dark"
        elif light_value < self.LIGHT_THRESHOLDS["dim"]:
            light_level = "dim"
        elif light_value < self.LIGHT_THRESHOLDS["bright"]:
            light_level = "normal"
        else:
            light_level = "bright"
        
        return light_level, light_value
    
    def _detect_persons(self, frame: np.ndarray) -> Dict[str, Any]:
        """检测人脸和人数"""
        result = {
            "person_count": 0,
            "person_present": False,
            "person_distance": None,
            "face_detected": False,
            "face_id": None,
        }
        
        h, w = frame.shape[:2]
        
        if HAS_MEDIAPIPE:
            return self._detect_mediapipe(frame, h, w, result)
        else:
            return self._detect_opencv(frame, h, w, result)
    
    def _detect_mediapipe(self, frame: np.ndarray, h: int, w: int, result: Dict) -> Dict:
        """使用MediaPipe检测"""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_detector.process(rgb_frame)
        
        if results.detections:
            result["person_count"] = len(results.detections)
            result["person_present"] = True
            result["face_detected"] = True
            
            # 取第一个检测到的人脸
            detection = results.detections[0]
            bboxC = detection.location_data.relative_bounding_box
            
            # 计算距离（基于人脸大小）
            face_width = bboxC.width * w
            face_height = bboxC.height * h
            face_area = face_width * face_height
            
            # 距离估算（简化模型）
            # 假设正常距离下人脸面积约为画面面积的5%
            normal_area = w * h * 0.05
            if face_area > 0:
                distance_ratio = normal_area / face_area
                # 转换为米（假设正常距离为1米）
                result["person_distance"] = max(0.3, min(3.0, distance_ratio))
            
            # 人脸ID（简化：基于位置）
            face_x = int(bboxC.xmin * w)
            face_y = int(bboxC.ymin * h)
            result["face_id"] = f"face_{face_x//100}_{face_y//100}"
        
        return result
    
    def _detect_opencv(self, frame: np.ndarray, h: int, w: int, result: Dict) -> Dict:
        """使用OpenCV检测"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )
        
        if len(faces) > 0:
            result["person_count"] = len(faces)
            result["person_present"] = True
            result["face_detected"] = True
            
            # 取第一个检测到的人脸
            x, y, face_w, face_h = faces[0]
            
            # 计算距离
            face_area = face_w * face_h
            normal_area = w * h * 0.05
            if face_area > 0:
                distance_ratio = normal_area / face_area
                result["person_distance"] = max(0.3, min(3.0, distance_ratio))
            
            # 人脸ID
            result["face_id"] = f"face_{x//100}_{y//100}"
        
        return result
    
    def get_average_light(self) -> int:
        """获取平均光照"""
        if not self.light_history:
            return 0
        return int(np.mean(list(self.light_history)))
    
    def is_person_stable(self) -> bool:
        """判断人是否稳定存在"""
        if len(self.person_history) < 5:
            return False
        
        recent = list(self.person_history)[-5:]
        return all(p for p in recent)
    
    def register_face(self, face_id: str, encoding: np.ndarray):
        """注册已知人脸"""
        self.known_faces[face_id] = encoding
    
    def identify_face(self, encoding: np.ndarray) -> Optional[str]:
        """识别人脸"""
        if not self.known_faces:
            return None
        
        best_match = None
        best_distance = float('inf')
        
        for face_id, known_encoding in self.known_faces.items():
            distance = np.linalg.norm(encoding - known_encoding)
            if distance < best_distance and distance < 0.6:  # 阈值
                best_distance = distance
                best_match = face_id
        
        return best_match
