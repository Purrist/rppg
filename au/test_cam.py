import cv2

print("[TEST] Checking camera...")
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("[OK] Camera opened successfully")
    ret, frame = cap.read()
    if ret:
        print(f"[OK] Frame captured: {frame.shape}")
    else:
        print("[ERR] Failed to read frame")
    cap.release()
else:
    print("[ERR] Failed to open camera")
