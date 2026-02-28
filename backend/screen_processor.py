import cv2
import mediapipe as mp
import time
import base64
import threading
import numpy as np
import json
import os

class ScreenProcessor:
    def __init__(self, url, socketio=None):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.socketio = socketio
        
        # --- 状态变量 ---
        self.processed_data = {"image": "", "interact": {"progress": [0,0,0], "hit_index": -1}}
        self.hover_start = [0, 0, 0]
        self.progress = [0, 0, 0]
        
        # --- 校准变量 ---
        self.config_file = "calibration_config.json"
        self.calibration_points = []  # 四个角点 [左上, 右上, 右下, 左下]
        self.calibrated = False
        self.perspective_matrix = None
        self.warped_width = 800
        self.warped_height = 500
        
        # --- 地鼠洞区域（归一化坐标，4个点的多边形，在 warp 后的空间中）---
        self.holes = [
            {"id": 0, "points": [[0.08, 0.45], [0.28, 0.45], [0.28, 0.85], [0.08, 0.85]]},
            {"id": 1, "points": [[0.36, 0.45], [0.64, 0.45], [0.64, 0.85], [0.36, 0.85]]},
            {"id": 2, "points": [[0.72, 0.45], [0.92, 0.45], [0.92, 0.85], [0.72, 0.85]]}
        ]
        
        # --- 媒体管道 ---
        self.mp_pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.4,
            min_tracking_confidence=0.4
        )
        
        # 加载保存的配置
        self.load_config()
        
        threading.Thread(target=self._run, daemon=True).start()
    
    def load_config(self):
        """加载保存的校准配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if 'calibration_points' in config:
                        self.calibration_points = config['calibration_points']
                        if len(self.calibration_points) == 4:
                            self.calibrate_perspective(self.calibration_points)
                    if 'holes' in config:
                        # 转换旧格式（norm_rect）到新格式（points）
                        loaded_holes = config['holes']
                        for i, hole in enumerate(loaded_holes):
                            if 'norm_rect' in hole and 'points' not in hole:
                                x1, x2, y1, y2 = hole['norm_rect']
                                loaded_holes[i] = {
                                    "id": hole.get("id", i),
                                    "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                                }
                        self.holes = loaded_holes
                print("已加载校准配置！")
            except Exception as e:
                print(f"加载配置失败: {e}")
    
    def save_config(self):
        """保存校准配置"""
        config = {
            'calibration_points': self.calibration_points,
            'holes': self.holes
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f)
            print("配置已保存！")
            if self.socketio:
                self.socketio.emit('calibration_saved', {'status': 'success'})
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def rotate_frame(self, frame):
        """处理摄像头90度旋转，水平翻转"""
        rotated = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        flipped = cv2.flip(rotated, 1)
        return flipped
    
    def update_calibration_point(self, index, x, y):
        """更新校准点（从前端调用）"""
        if 0 <= index < 4:
            self.calibration_points = self.calibration_points[:index] + [[x, y]] + self.calibration_points[index+1:]
            if len(self.calibration_points) == 4:
                self.calibrate_perspective(self.calibration_points)
            return True
        return False
    
    def update_hole(self, index, points):
        """更新地鼠洞区域（从前端调用，4个点）"""
        if 0 <= index < 3 and len(points) == 4:
            self.holes[index]["points"] = points
            return True
        return False
    
    def reset_calibration(self):
        """重置校准"""
        self.calibration_points = []
        self.calibrated = False
        self.perspective_matrix = None
        # 重置地鼠洞为默认值
        self.holes = [
            {"id": 0, "points": [[0.08, 0.45], [0.28, 0.45], [0.28, 0.85], [0.08, 0.85]]},
            {"id": 1, "points": [[0.36, 0.45], [0.64, 0.45], [0.64, 0.85], [0.36, 0.85]]},
            {"id": 2, "points": [[0.72, 0.45], [0.92, 0.45], [0.92, 0.85], [0.72, 0.85]]}
        ]
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        print("校准已重置！")
    
    def calibrate_perspective(self, src_points):
        """计算透视变换矩阵"""
        if len(src_points) != 4:
            return False
        
        src = np.float32(src_points)
        dst = np.float32([
            [0, 0],
            [self.warped_width, 0],
            [self.warped_width, self.warped_height],
            [0, self.warped_height]
        ])
        
        self.perspective_matrix = cv2.getPerspectiveTransform(src, dst)
        self.calibrated = True
        print("校准完成！透视变换矩阵已计算。")
        self.save_config()
        return True
    
    def warp_perspective(self, frame):
        """应用透视变换"""
        if not self.calibrated or self.perspective_matrix is None:
            return None
        
        warped = cv2.warpPerspective(
            frame, 
            self.perspective_matrix, 
            (self.warped_width, self.warped_height)
        )
        return warped
    
    def detect_foot_from_pose(self, warped_frame):
        """使用MediaPipe Pose检测脚部/腿部，不要求完整人体"""
        rgb = cv2.cvtColor(warped_frame, cv2.COLOR_BGR2RGB)
        results = self.mp_pose.process(rgb)
        
        foot_pos = None
        h, w, _ = warped_frame.shape
        
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            
            candidates = []
            
            # 检测关键点：23(左髋), 24(右髋), 25(左膝), 26(右膝), 27(左踝), 28(右踝), 29(左脚跟), 30(右脚跟), 31(左脚尖), 32(右脚尖)
            foot_related_indices = [23, 24, 25, 26, 27, 28, 29, 30, 31, 32]
            
            for idx in foot_related_indices:
                if idx < len(landmarks) and landmarks[idx].visibility > 0.4:
                    candidates.append( (landmarks[idx].x, landmarks[idx].y, landmarks[idx].visibility) )
            
            if candidates:
                candidates.sort(key=lambda p: p[1], reverse=True)
                fx, fy, _ = candidates[0]
                foot_pos = (int(fx * w), int(fy * h))
        
        return foot_pos, results
    
    def point_in_polygon(self, point, polygon):
        """使用射线法判断点是否在多边形内"""
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def check_hole_interaction(self, foot_pos):
        """检查脚是否在某个地鼠洞内"""
        if foot_pos is None:
            return -1
        
        fx, fy = foot_pos
        active_index = -1
        
        for i, hole in enumerate(self.holes):
            # 将归一化坐标转换为实际像素坐标
            polygon = [
                (p[0] * self.warped_width, p[1] * self.warped_height)
                for p in hole["points"]
            ]
            
            if self.point_in_polygon((fx, fy), polygon):
                active_index = i
                break
        
        return active_index
    
    def _run(self):
        while True:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            frame = self.rotate_frame(frame)
            display_frame = frame.copy()
            
            warped = None
            if self.calibrated:
                warped = self.warp_perspective(frame)
            
            active_index = -1
            foot_pos = None
            pose_results = None
            
            if warped is not None:
                foot_pos, pose_results = self.detect_foot_from_pose(warped)
                active_index = self.check_hole_interaction(foot_pos)
                
                if pose_results and pose_results.pose_landmarks:
                    mp.solutions.drawing_utils.draw_landmarks(
                        warped, 
                        pose_results.pose_landmarks, 
                        mp.solutions.pose.POSE_CONNECTIONS
                    )
                
                if foot_pos:
                    cv2.circle(warped, foot_pos, 30, (0, 255, 0), -1)
                    cv2.putText(warped, "FOOT DETECTED", (foot_pos[0]-80, foot_pos[1]-40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                
                for i, hole in enumerate(self.holes):
                    # 将归一化坐标转换为实际像素坐标
                    polygon = np.array([
                        (int(p[0] * self.warped_width), int(p[1] * self.warped_height))
                        for p in hole["points"]
                    ], np.int32)
                    polygon = polygon.reshape((-1, 1, 2))
                    
                    color = (200, 200, 200)
                    if self.progress[i] > 0:
                        color = (100, 150, 200)
                    if self.progress[i] >= 100:
                        color = (0, 255, 0)
                    
                    cv2.polylines(warped, [polygon], True, color, 5)
                    # 计算中心点用于放置文字
                    M = cv2.moments(polygon)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        cv2.putText(warped, f"Hole {i+1}", (cx-40, cy+10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
            
            now = time.time()
            hit_index = -1
            
            for i in range(3):
                if i == active_index:
                    if self.hover_start[i] == 0:
                        self.hover_start[i] = now
                    self.progress[i] = min(100, int((now - self.hover_start[i]) / 2.0 * 100))
                    if self.progress[i] >= 100:
                        hit_index = i
                        self.hover_start[i] = now + 0.5
                else:
                    if self.hover_start[i] != 0 and now - self.hover_start[i] > 0.5:
                        self.hover_start[i] = 0
                        self.progress[i] = 0
            
            final_display = display_frame
            if warped is not None:
                # 修复数组形状错误：先检查目标区域大小
                target_h = 300
                target_w = 480
                warped_small = cv2.resize(warped, (target_w, target_h))
                
                # 确保不会越界
                disp_h, disp_w = final_display.shape[:2]
                if disp_h >= 320 and disp_w >= 500:
                    final_display[20:320, 20:500] = warped_small
            
            _, buffer = cv2.imencode('.jpg', final_display)
            self.processed_data = {
                "image": base64.b64encode(buffer).decode('utf-8'),
                "interact": {"progress": self.progress.copy(), "hit_index": hit_index},
                "calibration": {
                    "points": self.calibration_points,
                    "holes": self.holes,
                    "calibrated": self.calibrated
                }
            }

    def get_latest(self):
        return self.processed_data
