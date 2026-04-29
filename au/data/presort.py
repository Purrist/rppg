import os
import sys
import cv2
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mediapipe as mp
from sixdrepnet import SixDRepNet
from au_net.MEFL import MEFARG

# Constants
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_s = 224.0 / 96.0
ALIGN_DST = np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]], dtype=np.float32) * _s
MP5 = [33, 263, 1, 61, 291]
AU_MAIN = ['AU1','AU2','AU4','AU5','AU6','AU7','AU9','AU10','AU11','AU12','AU13','AU14','AU15','AU16','AU17','AU18','AU19','AU20','AU22','AU23','AU24','AU25','AU26','AU27','AU32','AU38','AU39']

POSES = ['front', 'up', 'down', 'side']
EMOS = ['happ', 'neutral', 'sad']

FER_LABELS_8 = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]

class Preprocessor:
    def __init__(self):
        print("初始化 MediaPipe...")
        self.mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5)
        print("初始化 SixDRepNet...")
        self.repnet = SixDRepNet()
        print("初始化 AU 检测器...")
        self.dev = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.au_net = MEFARG(num_main_classes=27, num_sub_classes=14, backbone='resnet50')
        
        au_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rppg_dir = os.path.dirname(au_dir)
        ckpt = os.path.join(au_dir, 'checkpoints', 'OpenGprahAU-ResNet50_second_stage.pth')
        
        if os.path.exists(ckpt):
            d = torch.load(ckpt, map_location=self.dev, weights_only=False)
            sd = {k.replace("module.",""): v for k,v in d["state_dict"].items()}
            self.au_net.load_state_dict(sd)
            print(f"[AU] 权重已加载: {ckpt}")
        else:
            print(f"[AU] 权重缺失: {ckpt}")
        
        self.au_net.to(self.dev).eval()
        
        FER_MODEL_PATH = os.path.join(rppg_dir, "backend", "core", "models", "emotion-ferplus-8.onnx")
        print(f"FER+ 模型路径: {FER_MODEL_PATH}")
        
        if os.path.exists(FER_MODEL_PATH):
            self.fer_net = cv2.dnn.readNetFromONNX(FER_MODEL_PATH)
            self.fer_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.fer_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            print("[FER+] 权重已加载")
        else:
            self.fer_net = None
            print("[FER+] 模型不存在，将使用AU估计情绪")
        
        print("初始化完成\n")

    @staticmethod
    def read_image(filepath):
        with open(filepath, 'rb') as f:
            data = np.frombuffer(f.read(), np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)

    def align_face(self, img, lm):
        src = np.array([lm[i][:2] for i in MP5], dtype=np.float32)
        M = cv2.estimateAffinePartial2D(src, ALIGN_DST)[0]
        if M is None:
            return None
        return cv2.warpAffine(img, M, (224, 224), flags=cv2.INTER_LANCZOS4)

    def extract_au(self, aligned):
        img = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = (img - _MEAN) / _STD
        img = np.transpose(img, (2, 0, 1))[None]
        t = torch.from_numpy(img).float().to(self.dev)
        with torch.no_grad():
            out = self.au_net(t)
        if isinstance(out, (tuple, list)):
            mp_ = torch.sigmoid(out[0]).cpu().numpy()[0] * 100
        else:
            mp_ = torch.sigmoid(out).cpu().numpy()[0] * 100
        au_dict = {}
        for i, n in enumerate(AU_MAIN):
            au_dict[n] = float(mp_[i])
        return au_dict

    @staticmethod
    def softmax(x):
        e = np.exp(x - np.max(x))
        return e / (e.sum() + 1e-10)

    def estimate_emotion_from_fer(self, aligned, debug=False):
        if self.fer_net is None:
            return self.estimate_emotion_from_au(None), "FER+未加载"
        try:
            gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
            blob = gray.astype(np.float32).reshape(1, 1, 64, 64)
            self.fer_net.setInput(blob)
            scores = self.fer_net.forward()[0]
            probs = self.softmax(scores)
            
            if debug:
                debug_str = ", ".join([f"{FER_LABELS_8[i]}={probs[i]:.2f}" for i in range(len(probs))])
                debug_str += f" -> {FER_LABELS_8[np.argmax(probs)]}"
            
            label_idx = np.argmax(probs)
            label = FER_LABELS_8[label_idx]
            em_map = {
                'happiness': 'happ', 'surprise': 'happ',
                'sadness': 'sad', 'anger': 'sad', 'disgust': 'sad', 'fear': 'sad',
                'neutral': 'neutral', 'contempt': 'neutral'
            }
            result = em_map.get(label, 'neutral')
            
            if debug:
                return result, debug_str
            return result, ""
        except Exception as e:
            return self.estimate_emotion_from_au(None), f"错误: {e}"

    @staticmethod
    def estimate_emotion_from_au(au):
        if au is None:
            return 'neutral'
        au12 = au.get('AU12', 0)
        au6 = au.get('AU6', 0)
        au25 = au.get('AU25', 0)
        au15 = au.get('AU15', 0)
        au4 = au.get('AU4', 0)
        au17 = au.get('AU17', 0)
        positive_score = au12 * 0.4 + au6 * 0.3 + au25 * 0.2
        negative_score = au15 * 0.4 + au4 * 0.3 + au17 * 0.2
        if positive_score > negative_score + 10:
            return 'happ'
        elif negative_score > positive_score + 10:
            return 'sad'
        else:
            return 'neutral'

    @staticmethod
    def get_pose_from_angles(pitch, yaw):
        yaw = abs(yaw)
        if yaw > 35:
            return 'side'
        if pitch > 15:
            return 'up'
        if pitch < -20:
            return 'down'
        return 'front'

    def process(self, filepath):
        try:
            img = self.read_image(filepath)
            if img is None:
                return None, None, None, None, None

            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            r = self.mesh.process(rgb)
            if not r.multi_face_landmarks:
                return None, None, None, None, None

            h, w = img.shape[:2]
            lm = r.multi_face_landmarks[0].landmark
            landmarks = np.array([[p.x * w, p.y * h, p.z * w] for p in lm])

            x0 = min(int(p.x * w) for p in lm)
            y0 = min(int(p.y * h) for p in lm)
            x1 = max(int(p.x * w) for p in lm)
            y1 = max(int(p.y * h) for p in lm)

            m = 0.3
            bw = max(x1 - x0, 1)
            bh = max(y1 - y0, 1)
            x0 = max(0, int(x0 - bw * m))
            x1 = min(w, int(x1 + bw * m))
            y0 = max(0, int(y0 - bh * m))
            y1 = min(h, int(y1 + bh * m))

            crop = img[y0:y1, x0:x1]
            if crop.size == 0 or crop.shape[0] < 20:
                return None, None, None, None, None

            crop_resized = cv2.resize(crop, (480, 480), interpolation=cv2.INTER_LANCZOS4)
            pitch, yaw, roll = self.repnet.predict(crop_resized)
            pose = self.get_pose_from_angles(pitch, yaw)

            aligned = self.align_face(img, landmarks)
            au = None
            emotion = 'neutral'
            fer_debug = ''
            
            if aligned is not None:
                au = self.extract_au(aligned)
                emotion, fer_debug = self.estimate_emotion_from_fer(aligned, debug=True)
            
            return pose, pitch, yaw, emotion, au

        except Exception as e:
            print(f"    出错: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None, None, None

    def release(self):
        self.mesh.close()

def get_image_files(data_dir):
    extensions = ('.jpg', '.jpeg', '.png')
    all_files = os.listdir(data_dir)
    image_files = []
    for f in all_files:
        if f.lower().endswith(extensions):
            image_files.append(f)
    return image_files

def rename_only(data_dir, image_files):
    print("\n--- 模式1: 只重命名 (img-001.jpg) ---\n")
    
    counter = 1
    processed = 0
    
    for filename in sorted(image_files):
        try:
            old_path = os.path.join(data_dir, filename)
            ext = os.path.splitext(filename)[1].lower()
            
            new_ext = '.jpg' if ext in ['.png', '.jpeg'] else ext
            
            if ext == '.png':
                img = cv2.imread(old_path)
                if img is None:
                    img = Preprocessor.read_image(old_path)
                if img is not None:
                    new_name = f"img-{counter:03d}.jpg"
                    new_path = os.path.join(data_dir, new_name)
                    cv2.imwrite(new_path, img)
                    os.remove(old_path)
                    print(f"转换: {filename} -> {new_name}")
                else:
                    print(f"无法读取: {filename}")
                    continue
            else:
                new_name = f"img-{counter:03d}{new_ext}"
                new_path = os.path.join(data_dir, new_name)
                
                c = 1
                while os.path.exists(new_path):
                    new_name = f"img-{counter:03d}_{c}{new_ext}"
                    new_path = os.path.join(data_dir, new_name)
                    c += 1
                
                os.rename(old_path, new_path)
                print(f"重命名: {filename} -> {new_name}")
            
            counter += 1
            processed += 1
        
        except Exception as e:
            print(f"  处理 '{filename}' 时出错: {e}")
    
    print(f"\n完成! 共处理 {processed} 个文件")

def sort_by_pose_only(data_dir, image_files):
    print("\n--- 模式2: 按姿态分类 (front-01.jpg) ---\n")
    
    processor = Preprocessor()
    counters = {'front': 1, 'up': 1, 'down': 1, 'side': 1}
    processed = 0
    skipped = 0

    for filename in sorted(image_files):
        filepath = os.path.join(data_dir, filename)
        print(f"处理: {filename}")

        pitch, yaw, roll = None, None, None
        
        try:
            img = Preprocessor.read_image(filepath)
            if img is None:
                print(f"  无法读取，跳过")
                skipped += 1
                continue

            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            r = processor.mesh.process(rgb)
            
            if not r.multi_face_landmarks:
                print(f"  未检测到人脸，跳过")
                skipped += 1
                continue
            
            h, w = img.shape[:2]
            lm = r.multi_face_landmarks[0].landmark
            
            x0 = min(int(p.x * w) for p in lm)
            y0 = min(int(p.y * h) for p in lm)
            x1 = max(int(p.x * w) for p in lm)
            y1 = max(int(p.y * h) for p in lm)

            m = 0.3
            bw = max(x1 - x0, 1)
            bh = max(y1 - y0, 1)
            x0 = max(0, int(x0 - bw * m))
            x1 = min(w, int(x1 + bw * m))
            y0 = max(0, int(y0 - bh * m))
            y1 = min(h, int(y1 + bh * m))

            crop = img[y0:y1, x0:x1]
            if crop.size == 0 or crop.shape[0] < 20:
                print(f"  人脸太小，跳过")
                skipped += 1
                continue

            crop_resized = cv2.resize(crop, (480, 480), interpolation=cv2.INTER_LANCZOS4)
            pitch, yaw, roll = processor.repnet.predict(crop_resized)
        except Exception as e:
            print(f"  检测姿态时出错: {e}")
            skipped += 1
            continue

        if pitch is None:
            print(f"  未检测到人脸或出错，跳过")
            skipped += 1
            continue

        pose = Preprocessor.get_pose_from_angles(pitch, yaw)
        print(f"  角度: pitch={pitch:.1f}, yaw={yaw:.1f}, roll={roll:.1f}")
        print(f"  姿态: {pose}")

        ext = '.jpg'
        new_name = f"{pose}-{counters[pose]:02d}{ext}"
        new_path = os.path.join(data_dir, new_name)
        
        c = 1
        while os.path.exists(new_path):
            new_name = f"{pose}-{counters[pose]:02d}_{c}{ext}"
            new_path = os.path.join(data_dir, new_name)
            c += 1

        os.rename(filepath, new_path)
        counters[pose] += 1
        processed += 1
        print(f"  -> {new_name}")

    processor.release()
    print(f"\n完成! 成功处理: {processed}, 跳过: {skipped}")
    print(f"front={counters['front']-1}, up={counters['up']-1}, down={counters['down']-1}, side={counters['side']-1}")

def full_process(data_dir, image_files):
    print("\n--- 模式3: 完整流程 (姿态+情绪，front-happ-01.jpg) ---\n")
    
    processor = Preprocessor()
    counters = {}
    for pose in POSES:
        for emo in EMOS:
            counters[f"{pose}-{emo}"] = 1
    
    processed = 0
    skipped = 0

    for filename in sorted(image_files):
        filepath = os.path.join(data_dir, filename)
        print(f"处理: {filename}")

        pose, pitch, yaw, emotion, au = processor.process(filepath)

        if pose is None or emotion is None:
            print(f"  跳过")
            skipped += 1
            continue

        print(f"  姿态: {pose}, 情绪: {emotion}")
        
        if au is not None:
            print(f"  AU12={au.get('AU12',0):.1f} AU6={au.get('AU6',0):.1f} AU25={au.get('AU25',0):.1f} AU15={au.get('AU15',0):.1f} AU4={au.get('AU4',0):.1f}")

        key = f"{pose}-{emotion}"
        new_name = f"{key}-{counters[key]:02d}.jpg"
        new_path = os.path.join(data_dir, new_name)
        
        c = 1
        while os.path.exists(new_path):
            new_name = f"{key}-{counters[key]:02d}_{c}.jpg"
            new_path = os.path.join(data_dir, new_name)
            c += 1

        os.rename(filepath, new_path)
        counters[key] += 1
        processed += 1
        print(f"  -> {new_name}")

    processor.release()
    print(f"\n完成! 成功处理: {processed}, 跳过: {skipped}")

def main():
    data_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("\n")
    print("═══════════════════════════════════════════════════════════════")
    print("             图片预处理工具 - Presort")
    print("═══════════════════════════════════════════════════════════════")
    print(f"\n工作目录: {data_dir}")
    
    image_files = get_image_files(data_dir)
    if not image_files:
        print("\n未找到任何图片文件 (jpg/jpeg/png)")
        input("\n按回车键退出...")
        return
    
    print(f"找到 {len(image_files)} 张图片\n")
    
    while True:
        print("\n选择处理模式:")
        print("  1) 只重命名 → img-001.jpg")
        print("  2) 按姿态分类 → front-01.jpg")
        print("  3) 完整流程 → front-happ-01.jpg")
        print("  0) 退出")
        
        choice = input("\n请输入模式 (0-3): ").strip()
        
        if choice == '0':
            print("\n退出...")
            return
        elif choice == '1':
            rename_only(data_dir, image_files)
            break
        elif choice == '2':
            sort_by_pose_only(data_dir, image_files)
            break
        elif choice == '3':
            full_process(data_dir, image_files)
            break
        else:
            print("\n无效输入，请重新选择")

    input("\n按回车键退出...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n脚本出错: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")
