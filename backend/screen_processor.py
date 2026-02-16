import cv2
import mediapipe as mp
import time
import base64
import threading
import numpy as np

class ScreenProcessor:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # --- 状态变量 ---
        self.processed_data = {"image": "", "interact": {"progress": [0,0,0], "hit_index": -1}}
        self.hover_start = [0, 0, 0]
        self.progress = [0, 0, 0]
        
        # --- 校准变量 ---
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
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        
        threading.Thread(target=self._run, daemon=True).start()
    
    def rotate_frame(self, frame):
        """处理摄像头90度旋转，水平翻转"""
        # 旋转90度
        rotated = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        # 水平翻转
        flipped = cv2.flip(rotated, 1)
        return flipped
    
    def manual_calibration_click(self, event, x, y, flags, param):
        """用于手动校准的鼠标回调"""
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.calibration_points) < 4:
                self.calibration_points.append([x, y])
                print(f"已选择点 {len(self.calibration_points)}: ({x}, {y})")
                if len(self.calibration_points) == 4:
                    self.calibrate_perspective(self.calibration_points)
    
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
        """使用MediaPipe Pose检测人体，然后找到脚部位置"""
        rgb = cv2.cvtColor(warped_frame, cv2.COLOR_BGR2RGB)
        results = self.mp_pose.process(rgb)
        
        foot_pos = None
        h, w, _ = warped_frame.shape
        
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            
            # 检测关键点可见性
            left_ankle = landmarks[27]    # 左踝
            left_foot_idx = landmarks[31] # 左脚尖
            right_ankle = landmarks[28]   # 右踝
            right_foot_idx = landmarks[32]# 右脚尖
            
            candidates = []
            
            # 收集可见的脚部关键点
            if left_ankle.visibility > 0.6:
                candidates.append( (left_ankle.x, left_ankle.y) )
            if left_foot_idx.visibility > 0.6:
                candidates.append( (left_foot_idx.x, left_foot_idx.y) )
            if right_ankle.visibility > 0.6:
                candidates.append( (right_ankle.x, right_ankle.y) )
            if right_foot_idx.visibility > 0.6:
                candidates.append( (right_foot_idx.x, right_foot_idx.y) )
            
            if candidates:
                # 选择y坐标最大的点（最下方的脚）
                candidates.sort(key=lambda p: p[1], reverse=True)
                fx, fy = candidates[0]
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
            
            # 1. 旋转 + 翻转
            frame = self.rotate_frame(frame)
            display_frame = frame.copy()
            
            # 2. 如果未校准，提示用户点击四个角
            if not self.calibrated:
                cv2.putText(display_frame, "请点击投影的四个角（左上 -> 右上 -> 右下 -> 左下）", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                
                for i, pt in enumerate(self.calibration_points):
                    cv2.circle(display_frame, tuple(pt), 10, (0, 255, 0), -1)
                    cv2.putText(display_frame, str(i+1), (pt[0]+15, pt[1]), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                
                cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
                cv2.setMouseCallback("Calibration", self.manual_calibration_click)
                cv2.imshow("Calibration", display_frame)
                cv2.waitKey(1)
                
            # 3. 透视变换
            warped = None
            if self.calibrated:
                warped = self.warp_perspective(frame)
            
            # 4. 检测脚部并计算进度
            active_index = -1
            foot_pos = None
            pose_results = None
            
            if warped is not None:
                foot_pos, pose_results = self.detect_foot_from_pose(warped)
                active_index = self.check_hole_interaction(foot_pos)
                
                # 绘制骨架
                if pose_results and pose_results.pose_landmarks:
                    mp.solutions.drawing_utils.draw_landmarks(
                        warped, 
                        pose_results.pose_landmarks, 
                        mp.solutions.pose.POSE_CONNECTIONS
                    )
                
                # 绘制脚部和区域
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
                        color = (100, 150, 200)  # 灰蓝色加载
                    if self.progress[i] >= 100:
                        color = (0, 255, 0)
                    
                    cv2.rectangle(warped, (x1, y1), (x2, y2), color, 5)
                    cv2.putText(warped, f"Hole {i+1}", (x1+15, y1+40),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
            
            # 5. 进度计算：2秒
            now = time.time()
            hit_index = -1
            
            for i in range(3):
                if i == active_index:
                    if self.hover_start[i] == 0:
                        self.hover_start[i] = now
                    self.progress[i] = min(100, int((now - self.hover_start[i]) / 2.0 * 100))
                    if self.progress[i] >= 100:
                        hit_index = i
                        self.hover_start[i] = now + 0.5  # 冷却0.5秒
                else:
                    if self.hover_start[i] != 0 and now - self.hover_start[i] > 0.5:
                        self.hover_start[i] = 0
                        self.progress[i] = 0
            
            # 6. 编码图像
            final_display = display_frame
            if warped is not None:
                warped_small = cv2.resize(warped, (480, 300))
                final_display[20:320, 20:500] = warped_small
            
            _, buffer = cv2.imencode('.jpg', final_display)
            self.processed_data = {
                "image": base64.b64encode(buffer).decode('utf-8'),
                "interact": {"progress": self.progress.copy(), "hit_index": hit_index}
            }

    def get_latest(self):
        return self.processed_data
