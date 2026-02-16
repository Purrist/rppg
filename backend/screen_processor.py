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
        
        # --- 地鼠洞区域（归一化坐标，在 warp 后的空间中）---
        self.holes = [
            {"id": 0, "norm_rect": (0.08, 0.28, 0.45, 0.85)},
            {"id": 1, "norm_rect": (0.36, 0.64, 0.45, 0.85)},
            {"id": 2, "norm_rect": (0.72, 0.92, 0.45, 0.85)}
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
                        self.holes = config['holes']
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
    
    def update_hole(self, index, x1, x2, y1, y2):
        """更新地鼠洞区域（从前端调用）"""
        if 0 <= index < 3:
            self.holes[index]["norm_rect"] = (x1, x2, y1, y2)
            return True
        return False
    
    def reset_calibration(self):
        """重置校准"""
        self.calibration_points = []
        self.calibrated = False
        self.perspective_matrix = None
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
    
    def check_hole_interaction(self, foot_pos):
        """检查脚是否在某个地鼠洞内"""
        if foot_pos is None:
            return -1
        
        fx, fy = foot_pos
        active_index = -1
        
        for i, hole in enumerate(self.holes):
            r = hole["norm_rect"]
            x1 = int(r[0] * self.warped_width)
            x2 = int(r[1] * self.warped_width)
            y1 = int(r[2] * self.warped_height)
            y2 = int(r[3] * self.warped_height)
            
            if x1 < fx < x2 and y1 < fy < y2:
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
                    r = hole["norm_rect"]
                    x1 = int(r[0] * self.warped_width)
                    x2 = int(r[1] * self.warped_width)
                    y1 = int(r[2] * self.warped_height)
                    y2 = int(r[3] * self.warped_height)
                    
                    color = (200, 200, 200)
                    if self.progress[i] > 0:
                        color = (100, 150, 200)
                    if self.progress[i] >= 100:
                        color = (0, 255, 0)
                    
                    cv2.rectangle(warped, (x1, y1), (x2, y2), color, 5)
                    cv2.putText(warped, f"Hole {i+1}", (x1+15, y1+40),
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
