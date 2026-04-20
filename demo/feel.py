""" feel.py - 多模态感知系统 V2（接入 ONNX 情绪识别模型）

相比 V1 的改动：
- 新增 EmotionRecognizer 类：加载 ONNX FER 模型推理 7 类情绪概率
- 情绪识别策略：模型推理(7类) → 映射6类 + 规则补充drowsy
- 优雅降级：onnxruntime 未安装或模型文件不存在时自动回退规则方法
- 保留 V1 全部功能：人存在检测 / 专注度 / 运动量

模型来源：yikshing/emotion_test (ONNX, Apache 2.0)
  https://huggingface.co/yikshing/emotion_test
  输入: [1, 3, H, W] float32 (ImageNet 归一化)
  输出: [1, 7] float32 (angry/disgust/fear/happy/sad/surprise/neutral)
"""

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_file
import mediapipe as mp
import threading
import time
import os
from collections import deque

app = Flask(__name__)

# ============================================================
# 配置参数
# ============================================================
LOCAL_CAMERA_ID = 1                                        # 全身摄像头
DEFAULT_IP_CAMERA_URL = "http://10.215.158.45:8080/video"  # 人脸摄像头

# [V2] ONNX 情绪模型路径（与 feel.py 同目录）
EMOTION_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'emotion_model.onnx'
)

MOTION_WINDOW = 60
FOCUS_SMOOTH = 0.70
EMOTION_SMOOTH = 0.80          # [V2] 略降平滑，让模型响应更快
PERSON_TIMEOUT = 3.0
BLINK_EAR_CLOSE = 0.18
BLINK_EAR_OPEN = 0.22
BLINK_WINDOW = 30

# Face Mesh 关键轮廓
FACE_CONTOURS = [
    [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
     397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
     172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10],
    [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33],
    [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466, 263],
    [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409,
     270, 269, 267, 0, 37, 39, 40, 185, 61],
    [70, 63, 105, 66, 107],
    [300, 293, 334, 296, 336],
]

EMOTION_META = {
    'happy':     ('开心', (0, 200, 100)),
    'surprised': ('惊讶', (0, 200, 255)),
    'angry':     ('愤怒', (0, 0, 255)),
    'sad':       ('悲伤', (255, 150, 0)),
    'neutral':   ('平静', (150, 150, 150)),
    'drowsy':    ('困倦', (200, 100, 255)),
}

# [V2] ONNX 运行时检查
try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    HAS_ORT = False
    print("[WARN] onnxruntime 未安装，情绪识别将降级为规则方法")
    print("       安装命令: pip install onnxruntime")


# ============================================================
# [V2] ONNX 情绪识别器
# ============================================================
class EmotionRecognizer:
    """加载 ONNX FER 模型，输入人脸 BGR 图像，输出 6 类情绪概率"""

    # 标准 FER 7 类标签
    FER7_LABELS = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']

    # 7 类 → 6 类映射（disgust→angry, fear→sad）
    MAP_7TO6 = {
        'angry': 'angry',
        'disgust': 'angry',
        'fear': 'sad',
        'happy': 'happy',
        'sad': 'sad',
        'surprise': 'surprised',
        'neutral': 'neutral',
    }

    def __init__(self, model_path):
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        if not HAS_ORT:
            raise RuntimeError("onnxruntime 未安装")

        # 限制线程数，避免与 MediaPipe 抢 CPU
        sess_opts = ort.SessionOptions()
        sess_opts.inter_op_num_threads = 2
        sess_opts.intra_op_num_threads = 2
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            model_path, sess_opts,
            providers=['CPUExecutionProvider']
        )

        # 自动探测输入输出信息
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.input_shape = inp.shape          # 通常 [1, 3, 224, 224]
        out = self.session.get_outputs()[0]
        self.output_name = out.name
        self.output_shape = out.shape         # 通常 [1, 7]

        # 从 shape 解析输入尺寸，兼容动态 batch
        self.in_h = int(self.input_shape[2]) if self.input_shape[2] > 0 else 224
        self.in_w = int(self.input_shape[3]) if self.input_shape[3] > 0 else 224

        # 如果输出维度不是 7，使用占位标签
        n_classes = int(self.output_shape[1]) if len(self.output_shape) > 1 else 7
        if n_classes == 7:
            self.labels = self.FER7_LABELS
        else:
            self.labels = [f'class_{i}' for i in range(n_classes)]
            print(f"[WARN] 模型输出 {n_classes} 类，非标准 7 类，映射可能不准确")

        # ImageNet 归一化参数
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

        print(f"[OK] 情绪模型已加载: {os.path.basename(model_path)}")
        print(f"     输入: {self.input_name} {list(self.input_shape)} → {self.in_w}x{self.in_h}")
        print(f"     输出: {self.output_name} {list(self.output_shape)} ({n_classes}类)")

    def predict(self, face_bgr):
        """
        输入: 人脸区域 BGR 图像 (numpy array)
        输出: dict，6 类情绪概率 {'happy': 0.8, 'neutral': 0.15, ...}
        """
        if face_bgr is None or face_bgr.size == 0:
            return None

        # BGR → RGB → resize
        face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        face = cv2.resize(face_rgb, (self.in_w, self.in_h))

        # float32 + 归一化
        face = face.astype(np.float32) / 255.0
        face = (face - self.mean) / self.std

        # HWC → CHW → NCHW
        face = np.transpose(face, (2, 0, 1))
        face = np.expand_dims(face, axis=0)

        # 推理
        raw = self.session.run([self.output_name], {self.input_name: face})[0]
        probs = raw[0].astype(np.float64)

        # softmax（如果模型输出的是 logits）
        if np.any(probs < 0) or np.abs(np.sum(probs) - 1.0) > 0.1:
            probs = np.exp(probs - np.max(probs))
            probs = probs / (np.sum(probs) + 1e-10)

        # 7 类 → 6 类映射
        result6 = {k: 0.0 for k in ['happy', 'surprised', 'angry', 'sad', 'neutral', 'drowsy']}
        for i, label in enumerate(self.labels):
            if i < len(probs):
                mapped = self.MAP_7TO6.get(label, 'neutral')
                result6[mapped] += float(probs[i])

        # 归一化（合并后重新归一）
        total = sum(result6.values())
        if total > 0:
            for k in result6:
                result6[k] /= total

        return result6


# ============================================================
# 多模态感知处理器 V2
# ============================================================
class MultiModalProcessor:
    def __init__(self):
        # ---- 摄像头 ----
        self.local_cap = None
        self.ip_cap = None
        self.local_running = False
        self.ip_running = False

        # ---- 人存在检测 ----
        self.person_detected_local = False
        self.person_detected_ip = False
        self.person_detected = False
        self.person_last_seen = 0.0
        self.person_status = "offline"

        # ---- 情绪识别 ----
        self.emotion = "neutral"
        self.emotion_confidence = 0.0
        self.emotion_scores = {}
        self.emotion_history = deque(maxlen=60)
        self.emotion_method = "none"       # [V2] "model" / "rule" / "none"

        # ---- 专注度 ----
        self.focus_score = 50.0
        self.focus_history = deque(maxlen=120)
        self.blink_count = 0
        self.blink_rate = 0.0
        self.head_yaw = 0.0
        self.head_pitch = 0.0
        self.head_motion_score = 0.0
        self.eye_openness = 0.0

        # ---- 运动量 ----
        self.motion_intensity = 0.0
        self.motion_history = deque(maxlen=120)
        self.motion_accumulator = 0.0
        self.motion_window = deque(maxlen=MOTION_WINDOW)
        self.prev_pose_points = None

        # ---- FPS ----
        self.local_fps = 0.0
        self.ip_fps = 0.0
        self._local_fc = 0
        self._ip_fc = 0
        self._fps_time = time.time()

        # ---- 帧输出缓冲 ----
        self.local_frame_out = None
        self.ip_frame_out = None

        # ---- 眨眼状态机 ----
        self._blink_state = 'open'
        self._blink_timestamps = deque(maxlen=50)

        # ---- 面部微运动 ----
        self._prev_face_pts = None
        self._face_motion_win = deque(maxlen=30)

        # ---- 线程与运行控制 ----
        self.lock = threading.Lock()
        self.running = True
        self.start_time = time.time()

        # ---- MediaPipe（延迟初始化） ----
        self.face_mesh = None
        self.face_detection = None
        self.pose_detector = None

        # ---- [V2] ONNX 情绪模型 ----
        self.emotion_recognizer = None

    # ============================================================
    # 启动 / 停止
    # ============================================================
    def start(self):
        print("[INIT] 初始化 MediaPipe ...")
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5,
        )
        self.face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.3,
        )
        self.pose_detector = mp.solutions.pose.Pose(
            model_complexity=1,
            min_detection_confidence=0.5, min_tracking_confidence=0.5,
        )
        print("[OK] MediaPipe 就绪")

        # [V2] 加载情绪模型
        self._load_emotion_model()

        # 本地摄像头
        self.local_cap = cv2.VideoCapture(LOCAL_CAMERA_ID)
        if self.local_cap.isOpened():
            try: self.local_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception: pass
            self.local_running = True
            w = int(self.local_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.local_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[OK] 本地摄像头 {LOCAL_CAMERA_ID}: {w}x{h}")
        else:
            print(f"[WARN] 本地摄像头 {LOCAL_CAMERA_ID} 打开失败")

        # IP 摄像头
        self.ip_cap = cv2.VideoCapture(DEFAULT_IP_CAMERA_URL)
        if self.ip_cap.isOpened():
            try: self.ip_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception: pass
            self.ip_running = True
            w = int(self.ip_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.ip_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[OK] IP 摄像头: {w}x{h}")
        else:
            print(f"[WARN] IP 摄像头打开失败: {DEFAULT_IP_CAMERA_URL}")

        if not self.local_running and not self.ip_running:
            raise RuntimeError("所有摄像头均无法打开")

        if self.local_running:
            threading.Thread(target=self._local_worker, daemon=True).start()
        if self.ip_running:
            threading.Thread(target=self._ip_worker, daemon=True).start()

    def stop(self):
        self.running = False
        if self.local_cap: self.local_cap.release()
        if self.ip_cap: self.ip_cap.release()

    # ============================================================
    # [V2] 加载 ONNX 情绪模型
    # ============================================================
    def _load_emotion_model(self):
        if not HAS_ORT:
            print("[INFO] 情绪识别: 规则方法 (onnxruntime 未安装)")
            self.emotion_method = "rule"
            return
        if not os.path.isfile(EMOTION_MODEL_PATH):
            print(f"[INFO] 情绪识别: 规则方法 (模型文件未找到)")
            print(f"       期望路径: {EMOTION_MODEL_PATH}")
            print(f"       下载: https://huggingface.co/yikshing/emotion_test")
            self.emotion_method = "rule"
            return
        try:
            self.emotion_recognizer = EmotionRecognizer(EMOTION_MODEL_PATH)
            self.emotion_method = "model"
            print("[INFO] 情绪识别: ONNX 模型推理")
        except Exception as e:
            print(f"[WARN] 情绪模型加载失败: {e}")
            print("[INFO] 情绪识别: 降级为规则方法")
            self.emotion_method = "rule"
            self.emotion_recognizer = None

    # ============================================================
    # 本地摄像头工作线程：姿态 + 运动量
    # ============================================================
    def _local_worker(self):
        while self.running:
            try:
                ret, frame = self.local_cap.read()
                if not ret:
                    time.sleep(0.01); continue
                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self.pose_detector.process(rgb)

                with self.lock:
                    self._local_fc += 1
                    if result.pose_landmarks:
                        self.person_detected_local = True
                        self._compute_motion(result.pose_landmarks)
                        self._draw_pose(frame, result.pose_landmarks, w, h)
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, f"MOTION: {self.motion_intensity:.1f}%",
                                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 229, 160), 1)
                        cv2.putText(frame, f"ACC: {self.motion_accumulator:.1f}",
                                    (w - 180, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        bar_w = int(w * min(self.motion_intensity, 100) / 100)
                        bar_c = (0, 229, 160) if self.motion_intensity < 30 else \
                                (0, 180, 120) if self.motion_intensity < 60 else (0, 100, 255)
                        cv2.rectangle(frame, (0, h - 4), (bar_w, h), bar_c, -1)
                    else:
                        self.person_detected_local = False
                        self.prev_pose_points = None
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, "NO PERSON", (10, 24),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
                    self._update_person()
                    self._update_fps()
                    self.local_frame_out = frame
            except Exception as e:
                print(f"[LOCAL ERROR] {e}")
                time.sleep(0.01)

    # ============================================================
    # IP 摄像头工作线程：人脸 + 情绪 + 专注度
    # ============================================================
    def _ip_worker(self):
        while self.running:
            try:
                ret, frame = self.ip_cap.read()
                if not ret:
                    time.sleep(0.01); continue
                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                det = self.face_detection.process(rgb)
                has_face = det.detections is not None and len(det.detections) > 0
                mesh_result = None
                if has_face:
                    mesh_result = self.face_mesh.process(rgb)
                    has_mesh = (mesh_result.multi_face_landmarks is not None
                                and len(mesh_result.multi_face_landmarks) > 0)
                else:
                    has_mesh = False

                with self.lock:
                    self._ip_fc += 1
                    if has_mesh:
                        self.person_detected_ip = True
                        lm = mesh_result.multi_face_landmarks[0]

                        # [V2] 情绪识别：模型推理 + 规则辅助 drowsy
                        self._compute_emotion_v2(frame, det, lm)

                        # 专注度（不变）
                        self._compute_focus(lm)

                        # 绘制面部轮廓
                        self._draw_face_contours(frame, lm, w, h)

                        # HUD
                        cv2.rectangle(frame, (0, 0), (w, 54), (0, 0, 0), -1)
                        cn, color = EMOTION_META.get(self.emotion, ('?', (150, 150, 150)))
                        method_tag = "[M]" if self.emotion_method == "model" else "[R]"
                        cv2.putText(frame, f"{method_tag} {cn} ({self.emotion_confidence:.0%})",
                                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                        fc = (0, 229, 160) if self.focus_score > 60 else \
                             (0, 180, 120) if self.focus_score > 30 else (0, 80, 255)
                        cv2.putText(frame, f"Focus: {self.focus_score:.0f}%",
                                    (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.45, fc, 1)
                        cv2.putText(frame, f"Blink: {self.blink_rate:.0f}/min",
                                    (w - 170, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        cv2.putText(frame, f"Eye: {self.eye_openness:.2f}",
                                    (w - 170, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
                        bar_w = int(w * min(self.focus_score, 100) / 100)
                        cv2.rectangle(frame, (0, h - 4), (bar_w, h), fc, -1)
                    else:
                        self.person_detected_ip = False
                        self.emotion = "neutral"
                        self.emotion_confidence = max(0, self.emotion_confidence - 0.02)
                        self.focus_score = self.focus_score * 0.98
                        cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
                        cv2.putText(frame, "NO FACE", (10, 24),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
                    self._update_person()
                    self._update_fps()
                    self.ip_frame_out = frame
            except Exception as e:
                print(f"[IP ERROR] {e}")
                time.sleep(0.01)

    # ============================================================
    # 人存在融合判定
    # ============================================================
    def _update_person(self):
        self.person_detected = self.person_detected_local or self.person_detected_ip
        if self.person_detected:
            self.person_last_seen = time.time()
            self.person_status = "present"
        elif time.time() - self.person_last_seen > PERSON_TIMEOUT:
            self.person_status = "offline"
        elif self.person_status == "present":
            self.person_status = "lost"

    # ============================================================
    # FPS 统计
    # ============================================================
    def _update_fps(self):
        now = time.time()
        dt = now - self._fps_time
        if dt >= 1.0:
            self.local_fps = self._local_fc / dt if dt > 0 else 0
            self.ip_fps = self._ip_fc / dt if dt > 0 else 0
            self._local_fc = 0
            self._ip_fc = 0
            self._fps_time = now

    # ============================================================
    # 运动量计算（不变）
    # ============================================================
    def _compute_motion(self, pose_landmarks):
        pts = np.array([(lm.x, lm.y) for lm in pose_landmarks.landmark])
        if self.prev_pose_points is not None:
            diff = np.sqrt(np.sum((pts - self.prev_pose_points) ** 2, axis=1))
            frame_motion = float(np.mean(diff))
            self.motion_window.append(frame_motion)
            avg = float(np.mean(self.motion_window))
            self.motion_intensity = min(100.0, avg * 3000)
            self.motion_accumulator += frame_motion
            self.motion_history.append(round(self.motion_intensity, 1))
        self.prev_pose_points = pts.copy()

    # ============================================================
    # [V2] 情绪识别 V2：模型推理 + 规则辅助 drowsy
    # ============================================================
    def _compute_emotion_v2(self, frame, detection_result, face_landmarks):
        lm = np.array([(p.x, p.y, p.z) for p in face_landmarks.landmark])
        fh = np.linalg.norm(lm[10][:2] - lm[152][:2])

        # --- 规则辅助：提取 EAR 和嘴巴张开度（用于 drowsy 检测） ---
        is_drowsy = False
        ear = 0.3
        mouth_open = 0.0
        if fh > 1e-6:
            l_ear = abs(lm[159][1] - lm[145][1]) / (abs(lm[33][0] - lm[133][0]) + 1e-8)
            r_ear = abs(lm[386][1] - lm[374][1]) / (abs(lm[362][0] - lm[263][0]) + 1e-8)
            ear = (l_ear + r_ear) / 2
            self.eye_openness = ear
            mouth_open = abs(lm[13][1] - lm[14][1]) / fh
            # 困倦判定：眼半闭 + 嘴巴张开（打哈欠）
            if ear < 0.18 and mouth_open > 0.03:
                is_drowsy = True

        # --- 模型推理路径 ---
        if self.emotion_recognizer is not None:
            face_crop = self._crop_face(frame, detection_result)
            model_scores = self.emotion_recognizer.predict(face_crop)
            if model_scores is not None:
                # 如果检测到困倦，注入 drowsy 分数
                if is_drowsy:
                    model_scores['drowsy'] = max(model_scores.get('drowsy', 0), 0.55)
                    # 压制其他情绪
                    for k in model_scores:
                        if k != 'drowsy':
                            model_scores[k] *= 0.5
                    # 重新归一化
                    total = sum(model_scores.values())
                    if total > 0:
                        for k in model_scores:
                            model_scores[k] /= total

                self.emotion_scores = {k: round(v, 3) for k, v in model_scores.items()}
                self._apply_emotion_smooth(model_scores)
                return
            # 模型推理失败（如人脸裁剪异常），降级到规则

        # --- 规则降级路径 ---
        self.emotion_method = "rule"
        self._compute_emotion_rules(lm, fh, ear, mouth_open)

    def _crop_face(self, frame, detection_result):
        """从 Face Detection 结果中裁剪人脸区域"""
        try:
            det = detection_result.detections[0]
            bbox = det.location_data.relative_bounding_box
            h, w = frame.shape[:2]

            # 相对坐标 → 像素坐标，clamp 到画面内
            x = max(0, int(bbox.xmin * w))
            y = max(0, int(bbox.ymin * h))
            bw = min(int(bbox.width * w), w - x)
            bh = min(int(bbox.height * h), h - y)

            if bw < 20 or bh < 20:
                return None

            # 扩大 25% padding（包含更多面部上下文）
            pad_x = int(bw * 0.25)
            pad_y = int(bh * 0.25)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(w, x + bw + pad_x)
            y2 = min(h, y + bh + pad_y)

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
                return None
            return crop
        except Exception:
            return None

    def _apply_emotion_smooth(self, scores):
        """对模型输出做平滑切换（防止情绪标签闪烁）"""
        max_emo = max(scores, key=scores.get)
        total = sum(scores.values())
        raw_conf = scores[max_emo] / (total + 1e-8)

        self.emotion_method = "model"
        if self.emotion == max_emo:
            self.emotion_confidence = min(
                1.0, self.emotion_confidence * EMOTION_SMOOTH
                + raw_conf * (1 - EMOTION_SMOOTH) + 0.012)
        else:
            if raw_conf > self.emotion_confidence * 1.15 and raw_conf > 0.25:
                self.emotion = max_emo
                self.emotion_confidence = raw_conf * 0.55
            else:
                self.emotion_confidence *= 0.95

        self.emotion_history.append({
            'emotion': self.emotion,
            'confidence': round(self.emotion_confidence, 2),
            'scores': self.emotion_scores,
        })

    def _compute_emotion_rules(self, lm, fh, ear, mouth_open):
        """V1 规则方法（作为降级方案保留）"""
        if fh < 1e-6:
            return

        mouth_w = np.linalg.norm(lm[61][:2] - lm[291][:2]) / fh
        smile = ((lm[17][1] - lm[61][1]) + (lm[17][1] - lm[291][1])) / (2 * fh)
        brow_h = ((lm[159][1] - lm[107][1]) + (lm[386][1] - lm[336][1])) / (2 * fh)
        frown_r = (np.linalg.norm(lm[107][:2] - lm[336][:2])
                   / (np.linalg.norm(lm[133][:2] - lm[362][:2]) + 1e-8))

        s = {'happy': 0.0, 'surprised': 0.0, 'angry': 0.0,
             'sad': 0.0, 'neutral': 0.25, 'drowsy': 0.0}

        if smile > 0.005:
            s['happy'] += min(smile * 40, 0.8)
        if mouth_open > 0.04 and smile > 0.003:
            s['happy'] += 0.2
        if mouth_open > 0.06:
            s['surprised'] += min((mouth_open - 0.06) * 15, 0.5)
        if brow_h > 0.09:
            s['surprised'] += min((brow_h - 0.09) * 20, 0.3)
        if brow_h < 0.04:
            s['angry'] += min((0.04 - brow_h) * 25, 0.5)
        if frown_r < 0.85:
            s['angry'] += min((0.85 - frown_r) * 5, 0.3)
        if smile < -0.003:
            s['sad'] += min(abs(smile) * 50, 0.5)
        if ear < 0.18:
            s['drowsy'] += min((0.18 - ear) * 15, 0.6)
        if mouth_open > 0.04 and ear < 0.22:
            s['drowsy'] += 0.25
        if abs(smile) < 0.003 and mouth_open < 0.03 and 0.04 < brow_h < 0.08:
            s['neutral'] += 0.3

        self.emotion_scores = {k: round(v, 3) for k, v in s.items()}
        self._apply_emotion_smooth(s)

    # ============================================================
    # 专注度识别（不变）
    # ============================================================
    def _compute_focus(self, face_landmarks):
        lm = np.array([(p.x, p.y, p.z) for p in face_landmarks.landmark])
        fh = np.linalg.norm(lm[10][:2] - lm[152][:2])
        if fh < 1e-6:
            return

        nose = lm[1]
        l_ch, r_ch = lm[234], lm[454]
        chin, forehead = lm[152], lm[10]
        fw = abs(r_ch[0] - l_ch[0]) + 1e-8
        fhv = abs(chin[1] - forehead[1]) + 1e-8
        self.head_yaw = (nose[0] - (l_ch[0] + r_ch[0]) / 2) / fw
        self.head_pitch = (nose[1] - (forehead[1] + chin[1]) / 2) / fhv
        head_dev = abs(self.head_yaw) + abs(self.head_pitch)

        l_ear = abs(lm[159][1] - lm[145][1]) / (abs(lm[33][0] - lm[133][0]) + 1e-8)
        r_ear = abs(lm[386][1] - lm[374][1]) / (abs(lm[362][0] - lm[263][0]) + 1e-8)
        ear = (l_ear + r_ear) / 2
        self.eye_openness = ear

        now = time.time()
        if ear < BLINK_EAR_CLOSE and self._blink_state == 'open':
            self._blink_state = 'closed'
            self.blink_count += 1
            self._blink_timestamps.append(now)
        elif ear > BLINK_EAR_OPEN:
            self._blink_state = 'open'
        recent = [t for t in self._blink_timestamps if now - t < BLINK_WINDOW]
        self.blink_rate = len(recent) * (60.0 / BLINK_WINDOW)

        if self._prev_face_pts is not None:
            fm = float(np.mean(np.sqrt(
                np.sum((lm[:, :2] - self._prev_face_pts) ** 2, axis=1))))
        else:
            fm = 0.0
        self._prev_face_pts = lm[:, :2].copy()
        self._face_motion_win.append(fm)
        self.head_motion_score = float(np.mean(self._face_motion_win))

        score = 100.0
        score -= head_dev * 100
        score -= max(0, head_dev - 0.15) * 200
        if self.blink_rate > 25:
            score -= (self.blink_rate - 25) * 4
        elif self.blink_rate < 5 and len(recent) > 2:
            score -= (5 - self.blink_rate) * 6
        if self.head_motion_score > 0.3:
            score -= (self.head_motion_score - 0.3) * 60
        if ear < 0.2:
            score -= (0.2 - ear) * 400

        score = float(np.clip(score, 0, 100))
        self.focus_score = self.focus_score * FOCUS_SMOOTH + score * (1 - FOCUS_SMOOTH)
        self.focus_history.append(round(self.focus_score, 1))

    # ============================================================
    # HUD 绘制辅助（不变）
    # ============================================================
    def _draw_pose(self, frame, pose_landmarks, w, h):
        conns = mp.solutions.pose.POSE_CONNECTIONS
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in pose_landmarks.landmark]
        for c in conns:
            i, j = c
            if i < len(pts) and j < len(pts):
                cv2.line(frame, pts[i], pts[j], (0, 229, 160), 2)
        for idx in [0, 11, 12, 15, 16, 23, 24, 25, 26, 27, 28]:
            if idx < len(pts):
                cv2.circle(frame, pts[idx], 4, (0, 229, 160), -1)

    def _draw_face_contours(self, frame, face_landmarks, w, h):
        pts = [(int(p.x * w), int(p.y * h)) for p in face_landmarks.landmark]
        for contour in FACE_CONTOURS:
            for i in range(len(contour) - 1):
                a, b = contour[i], contour[i + 1]
                if a < len(pts) and b < len(pts):
                    cv2.line(frame, pts[a], pts[b], (0, 200, 140), 1)

    # ============================================================
    # API 数据输出
    # ============================================================
    def get_status(self):
        with self.lock:
            return {
                'person': {
                    'detected': self.person_detected,
                    'local': self.person_detected_local,
                    'ip': self.person_detected_ip,
                    'status': self.person_status,
                    'uptime': round(time.time() - self.start_time, 0),
                },
                'emotion': {
                    'current': self.emotion,
                    'cn': EMOTION_META.get(self.emotion, ('?',))[0],
                    'confidence': round(self.emotion_confidence, 2),
                    'method': self.emotion_method,
                    'scores': self.emotion_scores,
                    'history': list(self.emotion_history)[-30:],
                },
                'focus': {
                    'score': round(self.focus_score, 1),
                    'history': list(self.focus_history)[-60:],
                    'blink_rate': round(self.blink_rate, 1),
                    'head_yaw': round(self.head_yaw, 3),
                    'head_pitch': round(self.head_pitch, 3),
                    'head_motion': round(self.head_motion_score, 4),
                    'eye_openness': round(self.eye_openness, 3),
                },
                'motion': {
                    'intensity': round(self.motion_intensity, 1),
                    'history': list(self.motion_history)[-60:],
                    'accumulated': round(self.motion_accumulator, 2),
                },
                'system': {
                    'local_fps': round(self.local_fps, 1),
                    'ip_fps': round(self.ip_fps, 1),
                    'local_cam': f'Local {LOCAL_CAMERA_ID}',
                    'ip_cam': DEFAULT_IP_CAMERA_URL,
                    'emotion_model': os.path.basename(EMOTION_MODEL_PATH)
                                     if self.emotion_recognizer else 'none',
                    'emotion_method': self.emotion_method,
                },
            }


# ============================================================
# 初始化
# ============================================================
processor = MultiModalProcessor()
processor.start()


# ============================================================
# Flask 路由
# ============================================================
@app.route('/')
def index():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'camm.html')
    return send_file(p) if os.path.exists(p) else "<h1>camm.html not found</h1>"


def _stream_frames(frame_attr, label, default_w=640, default_h=360):
    while processor.running:
        with processor.lock:
            frame = getattr(processor, frame_attr, None)
        if frame is not None:
            ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                       + jpeg.tobytes() + b'\r\n')
        else:
            ph = np.zeros((default_h, default_w, 3), dtype=np.uint8)
            cv2.putText(ph, label, (default_w // 2 - 120, default_h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 1)
            ok, jpeg = cv2.imencode('.jpg', ph, [cv2.IMWRITE_JPEG_QUALITY, 50])
            if ok:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                       + jpeg.tobytes() + b'\r\n')
        time.sleep(0.033)


@app.route('/video_local')
def video_local():
    return Response(_stream_frames('local_frame_out', 'Local Camera Offline'),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_ip')
def video_ip():
    return Response(_stream_frames('ip_frame_out', 'IP Camera Offline'),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/status')
def api_status():
    return jsonify(processor.get_status())


# ============================================================
# 入口
# ============================================================
if __name__ == '__main__':
    try:
        print("=" * 64)
        print("  Multi-Modal Perception System V2")
        print("  Person Detection  : Dual Camera Fusion (OR logic)")
        print(f"  Emotion Recognition: {'ONNX Model' if processor.emotion_recognizer else 'Rule-based (fallback)'}")
        print("  Focus Estimation  : IP Cam + Head/Blink/Motion")
        print("  Motion Tracking   : Local Cam + Pose")
        print("-" * 64)
        print(f"  Local : Camera {LOCAL_CAMERA_ID}  (full body)")
        print(f"  IP    : {DEFAULT_IP_CAMERA_URL}  (face)")
        print(f"  Model : {processor.emotion_method}")
        print(f"  http://localhost:5000")
        print("=" * 64)
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down ...")
    finally:
        processor.stop()
