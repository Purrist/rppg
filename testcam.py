import cv2
import time

# ========== 核心：调用外接摄像头 1 ==========
cap = cv2.VideoCapture(1)

# 强制配置摄像头（更稳定）
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("✅ 外接摄像头 1 已打开")
print("按 q 键退出")

while True:
    ret, frame = cap.read()
    if not ret:
        print("❌ 读取失败")
        break

    # 显示画面
    cv2.imshow("外接摄像头 1", frame)

    # 按 q 退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放
cap.release()
cv2.destroyAllWindows()