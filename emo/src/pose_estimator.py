import cv2
import numpy as np

class PoseEstimator:
    """
    6DRepNet + MediaPipe 人脸框裁剪放大。
    解决远距离小目标检测失效问题。
    """

    def __init__(self, image_size):
        self.image_size = image_size
        from sixdrepnet import SixDRepNet
        self.model = SixDRepNet()

    def estimate(self, frame, landmarks):
        """
        基于 MediaPipe 人脸框裁剪后放大，再送 6DRepNet 推理。
        frame:      原始 BGR 帧
        landmarks:  MediaPipe 468 点 (N,3)
        返回: (pitch, yaw, roll)
        """
        if landmarks is None or len(landmarks) == 0:
            return 0.0, 0.0, 0.0

        h, w = frame.shape[:2]

        # 1. 用 468 点计算紧密人脸边界框
        xs = landmarks[:, 0]
        ys = landmarks[:, 1]
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())

        # 扩大 30% margin
        margin = 0.3
        bw = max(x_max - x_min, 1)
        bh = max(y_max - y_min, 1)
        x_min = max(0, int(x_min - bw * margin))
        x_max = min(w, int(x_max + bw * margin))
        y_min = max(0, int(y_min - bh * margin))
        y_max = min(h, int(y_max + bh * margin))

        face_crop = frame[y_min:y_max, x_min:x_max]
        if face_crop.size == 0 or face_crop.shape[0] < 20 or face_crop.shape[1] < 20:
            return 0.0, 0.0, 0.0

        # 2. 放大到 480x480
        face_resized = cv2.resize(face_crop, (480, 480), interpolation=cv2.INTER_LANCZOS4)

        # 3. 6DRepNet 推理
        pitch, yaw, roll = self.model.predict(face_resized)

        # numpy scalar → Python float
        pitch = float(np.asarray(pitch).item() if hasattr(pitch, 'item') else pitch)
        yaw = float(np.asarray(yaw).item() if hasattr(yaw, 'item') else yaw)
        roll = float(np.asarray(roll).item() if hasattr(roll, 'item') else roll)

        return pitch, yaw, roll