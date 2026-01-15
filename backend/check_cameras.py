import cv2
import time

def check_cameras(max_cameras=10):
    print("="*50)
    print("正在检测系统中的摄像头设备...")
    print("="*50)
    
    available_cameras = []
    
    for i in range(max_cameras):
        print(f"\n正在测试摄像头 {i}...", end=" ")
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                h, w = frame.shape[:2]
                print(f"✓ 可用 - 分辨率: {w}x{h}")
                available_cameras.append({
                    'index': i,
                    'width': w,
                    'height': h
                })
            else:
                print("✗ 无法读取帧")
            cap.release()
        else:
            print("✗ 无法打开")
    
    print("\n" + "="*50)
    print(f"检测完成！共找到 {len(available_cameras)} 个可用摄像头")
    print("="*50)
    
    if available_cameras:
        print("\n可用摄像头列表:")
        for cam in available_cameras:
            print(f"  摄像头 {cam['index']}: {cam['width']}x{cam['height']}")
        
        print("\n提示: 在 app.py 中修改 cv2.VideoCapture(0, cv2.CAP_DSHOW)")
        print(f"     将 0 改为 {available_cameras[-1]['index']} 以使用外接摄像头")
    
    return available_cameras

if __name__ == "__main__":
    cams = check_cameras()
    
    if cams:
        print("\n是否要预览最后一个摄像头? (按任意键关闭)")
        cap = cv2.VideoCapture(cams[-1]['index'], cv2.CAP_DSHOW)
        
        while True:
            ret, frame = cap.read()
            if ret:
                cv2.putText(frame, f"Camera {cams[-1]['index']}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.imshow(f'Camera {cams[-1]["index"]}', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
