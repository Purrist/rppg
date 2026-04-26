import cv2
import numpy as np
from sixdrepnet import SixDRepNet

def main():
    print("初始化 6DRepNet...")
    model = SixDRepNet()
    print("完成")

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        pitch, yaw, roll = model.predict(frame)
        pitch = float(np.asarray(pitch).item() if hasattr(pitch, 'item') else pitch)
        yaw = float(np.asarray(yaw).item() if hasattr(yaw, 'item') else yaw)
        roll = float(np.asarray(roll).item() if hasattr(roll, 'item') else roll)

        vis = model.draw_axis(frame, yaw, pitch, roll)
        cv2.putText(vis, f"P:{pitch:6.1f}  Y:{yaw:6.1f}  R:{roll:6.1f}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.imshow("6DRepNet Test", vis)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()