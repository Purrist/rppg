import cv2
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
        self.calibration_mode = False
        self.calibration_points = []  # 四个角点 [左上, 右上, 右下, 左下]
        self.calibrated = False
        self.perspective_matrix = None
        self.warped_width = 800
        self.warped_height = 500
        
        # --- 背景减法 ---
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=40, detectShadows=False)
        self.background_ready = False
        self.bg_frame_count = 0
        
        # --- 地鼠洞区域（归一化坐标，在 warp 后的空间中）---
        self.holes = [
            {"id": 0, "norm_rect": (0.08, 0.28, 0.45, 0.85)},
            {"id": 1, "norm_rect": (0.36, 0.64, 0.45, 0.85)},
            {"id": 2, "norm_rect": (0.72, 0.92, 0.45, 0.85)}
        ]
        
        threading.Thread(target=self._run, daemon=True).start()
    
    def flip_frame(self, frame):
        """水平翻转帧，解决左右镜像问题"""
        return cv2.flip(frame, 1)
    
    def manual_calibration_click(self, event, x, y, flags, param):
        """用于手动校准的鼠标回调（如果自动检测失败）"""
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
    
    def detect_foot_by_motion(self, warped_frame):
        """使用背景减法检测脚部位置"""
        if not self.background_ready:
            return None
        
        # 应用背景减法
        fg_mask = self.bg_subtractor.apply(warped_frame)
        
        # 形态学操作，去除噪点
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        
        # 找轮廓
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        foot_pos = None
        max_area = 0
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 500 and area > max_area:  # 面积阈值
                max_area = area
                # 计算质心
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    foot_pos = (cx, cy)
        
        return foot_pos, fg_mask
    
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
            
            # 1. 水平翻转
            frame = self.flip_frame(frame)
            display_frame = frame.copy()
            
            # 2. 如果未校准，提示用户点击四个角
            if not self.calibrated:
                cv2.putText(display_frame, "请点击投影的四个角（左上 -> 右上 -> 右下 -> 左下）", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                # 显示已选点
                for i, pt in enumerate(self.calibration_points):
                    cv2.circle(display_frame, tuple(pt), 8, (0, 255, 0), -1)
                    cv2.putText(display_frame, str(i+1), (pt[0]+10, pt[1]), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # 窗口用于校准（暂时启用窗口）
                cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
                cv2.setMouseCallback("Calibration", self.manual_calibration_click)
                cv2.imshow("Calibration", display_frame)
                if cv2.waitKey(1) & 0xFF == 27:  # ESC 退出
                    cv2.destroyWindow("Calibration")
                
            # 3. 透视变换
            warped = None
            if self.calibrated:
                warped = self.warp_perspective(frame)
                
                # 4. 学习背景
                if not self.background_ready:
                    self.bg_frame_count += 1
                    self.bg_subtractor.apply(warped)
                    if self.bg_frame_count > 30:
                        self.background_ready = True
                        print("背景学习完成！")
            
            # 5. 检测脚部并计算进度
            active_index = -1
            foot_pos = None
            fg_mask = None
            
            if warped is not None and self.background_ready:
                foot_pos, fg_mask = self.detect_foot_by_motion(warped)
                active_index = self.check_hole_interaction(foot_pos)
                
                # 在 warp 图上绘制检测结果
                if foot_pos:
                    cv2.circle(warped, foot_pos, 25, (0, 255, 0), -1)
                    cv2.putText(warped, "FOOT", (foot_pos[0]-30, foot_pos[1]-30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # 绘制地鼠洞区域
                for i, hole in enumerate(self.holes):
                    r = hole["norm_rect"]
                    x1 = int(r[0] * self.warped_width)
                    x2 = int(r[1] * self.warped_width)
                    y1 = int(r[2] * self.warped_height)
                    y2 = int(r[3] * self.warped_height)
                    
                    # 根据进度改变颜色
                    if self.progress[i] > 0:
                        color = (0, 255, 0) if self.progress[i] < 100 else (0, 255, 255)
                    else:
                        color = (0, 165, 255)
                    
                    cv2.rectangle(warped, (x1, y1), (x2, y2), color, 4)
                    cv2.putText(warped, f"Hole {i+1}", (x1+10, y1+30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
            
            # 6. 进度计算
            now = time.time()
            hit_index = -1
            
            for i in range(3):
                if i == active_index:
                    if self.hover_start[i] == 0:
                        self.hover_start[i] = now
                    # 1.5秒进度（稍微快一点）
                    self.progress[i] = min(100, int((now - self.hover_start[i]) / 1.5 * 100))
                    if self.progress[i] >= 100:
                        hit_index = i
                        self.hover_start[i] = 0  # 触发后重置
                else:
                    self.hover_start[i] = 0
                    self.progress[i] = 0
            
            # 7. 编码图像
            final_display = display_frame
            if warped is not None:
                # 将 warp 图画在角落
                warped_small = cv2.resize(warped, (400, 250))
                final_display[10:260, 10:410] = warped_small
                
                if fg_mask is not None:
                    fg_mask_small = cv2.resize(fg_mask, (200, 125))
                    fg_mask_color = cv2.cvtColor(fg_mask_small, cv2.COLOR_GRAY2BGR)
                    final_display[270:395, 10:210] = fg_mask_color
            
            _, buffer = cv2.imencode('.jpg', final_display)
            self.processed_data = {
                "image": base64.b64encode(buffer).decode('utf-8'),
                "interact": {"progress": self.progress.copy(), "hit_index": hit_index}
            }

    def get_latest(self):
        return self.processed_data
