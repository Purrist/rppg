import os, sys, time, threading, traceback

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug.log')
open(LOG, 'w').close()  # 清空
def L(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with open(LOG, 'a') as f: f.write(line + '\n')
    print(line); sys.stdout.flush()

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

L("=== 开始 ===")

L("1. import cv2"); import cv2
L("2. import torch"); import torch
L("3. import mediapipe"); import mediapipe as mp
L("4. import flask"); from flask import Flask
L("5. imports 完成")

L("6. 打开摄像头")
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
L(f"   opened={cap.isOpened()}")

ret, frame = cap.read()
L(f"7. 读帧 ret={ret} shape={frame.shape if ret else 'None'}")

L("8. FaceMesh(5人脸)")
fm = mp.solutions.face_mesh.FaceMesh(
    static_image_mode=False, max_num_faces=5, refine_landmarks=True,
    min_detection_confidence=0.5, min_tracking_confidence=0.5)
L("   FaceMesh OK")

rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
r = fm.process(rgb)
n = len(r.multi_face_landmarks) if r.multi_face_landmarks else 0
L(f"9. 人脸检测: {n} 张脸")

L("10. SixDRepNet")
from sixdrepnet import SixDRepNet
pose_model = SixDRepNet()
L("    OK")

L("11. AU模型")
dev = torch.device('cpu')
from au_net.MEFL import MEFARG
au_net = MEFARG(num_main_classes=27, num_sub_classes=14, backbone='resnet50')
ckpt = torch.load('checkpoints/OpenGprahAU-ResNet50_second_stage.pth', map_location=dev)
au_net.load_state_dict({k.replace("module.",""):v for k,v in ckpt["state_dict"].items()})
au_net.to(dev).eval()
L("    OK")

# === 关键测试：daemon thread ===
L("12. 启动 daemon 线程推理 30 帧")
thread_ok = [True]
thread_err = [""]

def worker():
    try:
        L("    [T] 开始")
        for i in range(30):
            ret, frame = cap.read()
            if not ret: continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            r = fm.process(rgb)
            faces = r.multi_face_landmarks if r.multi_face_landmarks else []
            if faces:
                h, w = frame.shape[:2]
                lm = np.array([[p.x*w,p.y*h,p.z*w] for p in faces[0].landmark])
                # AU推理
                src = np.array([lm[j][:2] for j in [33,263,1,61,291]], dtype=np.float32)
                M = cv2.estimateAffinePartial2D(src, np.array(
                    [[38.3,51.7],[73.5,51.5],[56.0,71.7],[41.5,92.4],[70.7,92.2]],dtype=np.float32)*2.333)[0]
                if M is not None:
                    aligned = cv2.warpAffine(frame, M, (224,224), flags=cv2.INTER_LANCZOS4)
                    img = (cv2.cvtColor(aligned,cv2.COLOR_BGR2RGB).astype(np.float32)/255.0 - np.array([0.485,0.456,0.406])) / np.array([0.229,0.224,0.225])
                    img = np.transpose(img,(2,0,1))[None]
                    with torch.no_grad():
                        au_net(torch.from_numpy(img).float().to(dev))
                # 姿态推理
                xs,ys = lm[:,0],lm[:,1]
                x0,x1=int(xs.min()),int(xs.max()); y0,y1=int(ys.min()),int(ys.max())
                crop = frame[max(0,int(y0-(y1-y0)*.3)):min(h,int(y1+(y1-y0)*.3)),
                             max(0,int(x0-(x1-x0)*.3)):min(w,int(x1+(x1-x0)*.3))]
                if crop.size>0 and crop.shape[0]>=20:
                    pose_model.predict(cv2.resize(crop,(480,480)))
            if i % 10 == 0:
                L(f"    [T] 帧 {i}/30")
        L("    [T] 完成")
    except Exception as e:
        thread_ok[0] = False
        thread_err[0] = traceback.format_exc()
        L(f"    [T] 崩溃: {e}")

import numpy as np
t = threading.Thread(target=worker, daemon=True)
t.start()
t.join(timeout=20)
if t.is_alive():
    L("    [T] 20秒超时，线程卡死!")
else:
    L(f"    [T] 结果: {'成功' if thread_ok[0] else '崩溃'}")
    if not thread_ok[0]:
        L(thread_err[0])

cap.release()
fm.close()
L("=== 结束 ===")
