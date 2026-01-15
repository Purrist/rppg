import cv2
import numpy as np
import threading
import time
from queue import Queue

import mediapipe as mp
mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands

class ProjectorProcessor:
    def __init__(self, camera_source=0):
        self.camera_source = camera_source
        self.cap = None
        self.running = False
        self.thread = None
        
        self.pose = mp_pose.Pose(
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.hands = mp_hands.Hands(
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.person_detected = False
        self.body_position = {"x": 0.0, "y": 0.0}
        self.gesture = "none"
        self.gesture_confidence = 0.0
        self.interaction_target = None
        self.activity_level = "none"
        self.foot_detected = False
        self.foot_position = {"x": 0.0, "y": 0.0}
        
        self.frame_queue = Queue(maxsize=1)
        
        self.gesture_history = []
        self.max_history = 10
        
        self.interaction_zones = {
            "zone_1": {"x": 0.2, "y": 0.2, "radius": 0.15},
            "zone_2": {"x": 0.5, "y": 0.2, "radius": 0.15},
            "zone_3": {"x": 0.8, "y": 0.2, "radius": 0.15},
            "zone_4": {"x": 0.2, "y": 0.5, "radius": 0.15},
            "zone_5": {"x": 0.5, "y": 0.5, "radius": 0.15},
            "zone_6": {"x": 0.8, "y": 0.5, "radius": 0.15},
        }
        
        self.foot_zones = {
            "zone_1": {"x": 0.2, "y": 0.8, "radius": 0.2},
            "zone_2": {"x": 0.5, "y": 0.8, "radius": 0.2},
            "zone_3": {"x": 0.8, "y": 0.8, "radius": 0.2},
            "zone_4": {"x": 0.2, "y": 0.5, "radius": 0.2},
            "zone_5": {"x": 0.5, "y": 0.5, "radius": 0.2},
            "zone_6": {"x": 0.8, "y": 0.5, "radius": 0.2},
        }
        
        self.foot_history = []
        self.max_foot_history = 10
    
    def connect_camera(self):
        if self.cap is not None:
            self.cap.release()
        
        if isinstance(self.camera_source, str):
            print(f"[投影摄像头] 正在连接网络摄像头: {self.camera_source}")
            self.cap = cv2.VideoCapture(self.camera_source)
        else:
            print(f"[投影摄像头] 正在连接本地摄像头: {self.camera_source}")
            self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
        
        if not self.cap.isOpened():
            raise Exception(f"无法打开投影摄像头: {self.camera_source}")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        print("[投影摄像头] 连接成功！")
    
    def detect_gesture(self, hand_landmarks):
        thumb_tip = hand_landmarks.landmark[4]
        index_tip = hand_landmarks.landmark[8]
        middle_tip = hand_landmarks.landmark[12]
        ring_tip = hand_landmarks.landmark[16]
        pinky_tip = hand_landmarks.landmark[20]
        
        thumb_ip = hand_landmarks.landmark[3]
        index_pip = hand_landmarks.landmark[6]
        middle_pip = hand_landmarks.landmark[10]
        ring_pip = hand_landmarks.landmark[14]
        pinky_pip = hand_landmarks.landmark[18]
        
        fingers_up = []
        
        fingers_up.append(thumb_tip.x < thumb_ip.x)
        fingers_up.append(index_tip.y < index_pip.y)
        fingers_up.append(middle_tip.y < middle_pip.y)
        fingers_up.append(ring_tip.y < ring_pip.y)
        fingers_up.append(pinky_tip.y < pinky_pip.y)
        
        if fingers_up == [True, True, False, False, False]:
            gesture = "pointing"
            confidence = 0.9
        elif fingers_up == [True, True, True, False, False]:
            gesture = "victory"
            confidence = 0.85
        elif fingers_up == [False, False, False, False, False]:
            gesture = "fist"
            confidence = 0.8
        elif fingers_up == [True, True, True, True, True]:
            gesture = "open_hand"
            confidence = 0.85
        else:
            gesture = "unknown"
            confidence = 0.5
        
        return gesture, confidence
    
    def detect_interaction_target(self, hand_position, frame_shape):
        h, w = frame_shape[:2]
        
        for zone_name, zone in self.interaction_zones.items():
            zone_x = int(zone["x"] * w)
            zone_y = int(zone["y"] * h)
            zone_radius = int(zone["radius"] * w)
            
            hand_x = int(hand_position[0] * w)
            hand_y = int(hand_position[1] * h)
            
            distance = np.sqrt((hand_x - zone_x)**2 + (hand_y - zone_y)**2)
            
            if distance < zone_radius:
                return zone_name
        
        return None
    
    def detect_foot_interaction(self, pose_landmarks, frame_shape):
        h, w = frame_shape[:2]
        
        if not pose_landmarks:
            return None
        
        left_ankle = pose_landmarks.landmark[27]
        right_ankle = pose_landmarks.landmark[28]
        left_foot_index = pose_landmarks.landmark[29]
        right_foot_index = pose_landmarks.landmark[30]
        
        left_foot_x = int(left_foot_index.x * w)
        left_foot_y = int(left_foot_index.y * h)
        right_foot_x = int(right_foot_index.x * w)
        right_foot_y = int(right_foot_index.y * h)
        
        for zone_name, zone in self.foot_zones.items():
            zone_x = int(zone["x"] * w)
            zone_y = int(zone["y"] * h)
            zone_radius = int(zone["radius"] * w)
            
            left_distance = np.sqrt((left_foot_x - zone_x)**2 + (left_foot_y - zone_y)**2)
            right_distance = np.sqrt((right_foot_x - zone_x)**2 + (right_foot_y - zone_y)**2)
            
            if left_distance < zone_radius or right_distance < zone_radius:
                self.foot_detected = True
                self.foot_position = {"x": (left_foot_x + right_foot_x) / (2 * w), "y": (left_foot_y + right_foot_y) / (2 * h)}
                return zone_name
        
        self.foot_detected = False
        self.foot_position = {"x": 0.0, "y": 0.0}
        return None
    
    def calculate_activity_level(self, pose_landmarks, frame_shape):
        h, w = frame_shape[:2]
        
        nose = pose_landmarks.landmark[0]
        left_shoulder = pose_landmarks.landmark[11]
        right_shoulder = pose_landmarks.landmark[12]
        left_hip = pose_landmarks.landmark[23]
        right_hip = pose_landmarks.landmark[24]
        
        shoulder_width = abs(right_shoulder.x - left_shoulder.x)
        nose_y = nose.y
        
        movement_score = 0.0
        
        if shoulder_width > 0.3:
            movement_score += 0.3
        
        if nose_y < 0.4:
            movement_score += 0.3
        
        if movement_score > 0.5:
            activity = "high"
        elif movement_score > 0.2:
            activity = "medium"
        else:
            activity = "low"
        
        return activity
    
    def process_frame(self, frame):
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        res_pose = self.pose.process(rgb)
        res_hands = self.hands.process(rgb)
        
        self.person_detected = False
        self.gesture = "none"
        self.gesture_confidence = 0.0
        self.interaction_target = None
        
        if res_pose.pose_landmarks:
            self.person_detected = True
            
            pose_landmarks = res_pose.pose_landmarks
            nose = pose_landmarks.landmark[0]
            self.body_position = {"x": nose.x, "y": nose.y}
            
            self.activity_level = self.calculate_activity_level(pose_landmarks, frame.shape)
            
            foot_target = self.detect_foot_interaction(pose_landmarks, frame.shape)
            if foot_target:
                self.foot_detected = True
                self.foot_position = {"x": (pose_landmarks.landmark[27].x + pose_landmarks.landmark[28].x) / 2, "y": (pose_landmarks.landmark[27].y + pose_landmarks.landmark[28].y) / 2}
                self.interaction_target = foot_target
            else:
                self.foot_detected = False
                self.foot_position = {"x": 0.0, "y": 0.0}
            
            cv2.circle(frame, (int(nose.x * w), int(nose.y * h)), 10, (0, 255, 0), -1)
        
        if res_hands.multi_hand_landmarks:
            for hand_landmarks in res_hands.multi_hand_landmarks:
                gesture, confidence = self.detect_gesture(hand_landmarks)
                self.gesture = gesture
                self.gesture_confidence = confidence
                
                index_tip = hand_landmarks.landmark[8]
                hand_position = (index_tip.x, index_tip.y)
                
                self.interaction_target = self.detect_interaction_target(hand_position, frame.shape)
                
                self.gesture_history.append(gesture)
                if len(self.gesture_history) > self.max_history:
                    self.gesture_history.pop(0)
                
                for landmark in hand_landmarks.landmark:
                    x, y = int(landmark.x * w), int(landmark.y * h)
                    cv2.circle(frame, (x, y), 3, (255, 0, 0), -1)
        
        for zone_name, zone in self.interaction_zones.items():
            zone_x = int(zone["x"] * w)
            zone_y = int(zone["y"] * h)
            zone_radius = int(zone["radius"] * w)
            
            color = (0, 255, 0) if self.interaction_target == zone_name else (0, 0, 255)
            cv2.circle(frame, (zone_x, zone_y), zone_radius, color, 2)
            cv2.putText(frame, zone_name, (zone_x - 20, zone_y - zone_radius - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        status_text = f"Gesture: {self.gesture} | Target: {self.interaction_target or 'None'} | Activity: {self.activity_level}"
        cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return frame
    
    def get_state(self):
        return {
            "person_detected": self.person_detected,
            "body_position": self.body_position,
            "gesture": self.gesture,
            "gesture_confidence": self.gesture_confidence,
            "interaction_target": self.interaction_target,
            "activity_level": self.activity_level,
            "foot_detected": self.foot_detected,
            "foot_position": self.foot_position
        }
    
    def capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            processed_frame = self.process_frame(frame)
            
            if not self.frame_queue.full():
                self.frame_queue.put(processed_frame)
    
    def start(self):
        self.connect_camera()
        self.running = True
        self.thread = threading.Thread(target=self.capture_loop)
        self.thread.daemon = True
        self.thread.start()
        print("[投影摄像头] 处理线程已启动")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        print("[投影摄像头] 已停止")
    
    def get_frame(self):
        if not self.frame_queue.empty():
            return self.frame_queue.get()
        return None
