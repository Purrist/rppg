import cv2
import mediapipe as mp
from deepface import DeepFace
import time

class EmotionProcessor:
    def __init__(self, camera_url):
        self.cap = cv2.VideoCapture(camera_url)
        # 优化：降低摄像头输入分辨率可以极大提升流速
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # 性能优化变量
        self.last_emotion = "Analyzing..."
        self.frame_count = 0
        self.process_every_n_frames = 15  # 每 15 帧才进行一次深度情绪识别
        
        print(f"✅ 引擎已优化：每 {self.process_every_n_frames} 帧分析一次情绪")

    def get_processed_frame(self):
        success, frame = self.cap.read()
        if not success: return None

        self.frame_count += 1

        # 1. 情绪识别 (抽帧执行，避免卡顿)
        if self.frame_count % self.process_every_n_frames == 0:
            try:
                # 使用较轻量级的检测器 opencv 或 fastmtcnn
                results = DeepFace.analyze(
                    frame, 
                    actions=['emotion'], 
                    enforce_detection=False, 
                    detector_backend='opencv', # 关键：opencv 最快，mtcnn 最准
                    silent=True
                )
                self.last_emotion = results[0]['dominant_emotion']
            except Exception:
                pass

        # 2. 绘制实时网格 (这一部分很快，可以每帧执行)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results_mesh = self.face_mesh.process(rgb_frame)
        
        if results_mesh.multi_face_landmarks:
            for face_landmarks in results_mesh.multi_face_landmarks:
                self.mp_drawing.draw_landmarks(
                    image=frame,
                    landmark_list=face_landmarks,
                    connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                    connection_drawing_spec=self.mp_drawing.DrawingSpec(color=(74, 144, 226), thickness=1)
                )

        # 3. 将情绪文字直接绘制在画面上（确保你看得到结果）
        cv2.putText(frame, f"STATUS: {self.last_emotion.upper()}", (30, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (74, 144, 226), 3)

        # 4. 降低编码质量以换取流畅度
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buffer.tobytes()