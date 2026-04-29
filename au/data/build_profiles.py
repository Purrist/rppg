import os
import cv2
import numpy as np
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import mediapipe as mp
from au_net.MEFL import MEFARG

# ── Constants ──────────────────────────────────────────────
POSES = ['front', 'up', 'down', 'side']
EMOTIONS = ['neutral', 'positive', 'negative']

# 各姿态推荐使用的AU子集
POSE_AU_SUBSET = {
    'front': ['AU1', 'AU2', 'AU4', 'AU5', 'AU6', 'AU7', 'AU9', 'AU10', 'AU12', 'AU15', 'AU17', 'AU25'],
    'up': ['AU1', 'AU2', 'AU4', 'AU5', 'AU7', 'AU15', 'AU17'],
    'down': ['AU1', 'AU2', 'AU4', 'AU5', 'AU7', 'AU15'],
    'side': ['AUL1', 'AUR1', 'AUL2', 'AUR2', 'AUL6', 'AUR6', 'AU5', 'AU7', 'AU25']
}

AU_MAIN = ['AU1','AU2','AU4','AU5','AU6','AU7','AU9','AU10','AU11','AU12','AU13','AU14','AU15','AU16','AU17','AU18','AU19','AU20','AU22','AU23','AU24','AU25','AU26','AU27','AU32','AU38','AU39']
AU_SUB = ['AUL1','AUR1','AUL2','AUR2','AUL4','AUR4','AUL6','AUR6','AUL10','AUR10','AUL12','AUR12','AUL14','AUR14']

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_s = 224.0 / 96.0
ALIGN_DST = np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]], dtype=np.float32) * _s
MP5 = [33, 263, 1, 61, 291]

class FaceDetector:
    def __init__(self):
        self.fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5)
    
    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        r = self.fm.process(rgb)
        if not r.multi_face_landmarks:
            return []
        h, w = frame.shape[:2]
        return [np.array([[p.x*w, p.y*h, p.z*w] for p in fl.landmark]) for fl in r.multi_face_landmarks]
    
    def release(self):
        self.fm.close()

class AUExtractor:
    def __init__(self):
        self.sz = 224
        self.dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.net = MEFARG(num_main_classes=27, num_sub_classes=14, backbone='resnet50')
        self._clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
        ckpt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'checkpoints', 'OpenGprahAU-ResNet50_second_stage.pth')
        if os.path.exists(ckpt):
            d = torch.load(ckpt, map_location=self.dev)
            sd = {k.replace("module.",""): v for k,v in d["state_dict"].items()}
            self.net.load_state_dict(sd)
            print(f"[AU] 权重已加载: {ckpt}")
        else:
            print(f"[AU] 权重缺失: {ckpt}")
        self.net.to(self.dev).eval()
    
    def _enhance_elderly(self, img):
        lab = cv2.cvtColor((img*255).astype(np.uint8), cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        cl = self._clahe.apply(l)
        enhanced = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2RGB)
        return enhanced.astype(np.float32)/255.0
    
    def _align(self, frame, lm):
        src = np.array([lm[i][:2] for i in MP5], dtype=np.float32)
        M = cv2.estimateAffinePartial2D(src, ALIGN_DST)[0]
        if M is None:
            return None
        return cv2.warpAffine(frame, M, (self.sz, self.sz), flags=cv2.INTER_LANCZOS4)
    
    def predict(self, frame, lm):
        if lm is None:
            return None
        aligned = self._align(frame, lm)
        if aligned is None:
            return None
        img = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = self._enhance_elderly(img)
        img = (img - _MEAN) / _STD
        img = np.transpose(img, (2, 0, 1))[None]
        t = torch.from_numpy(img).float().to(self.dev)
        with torch.no_grad():
            out = self.net(t)
        if isinstance(out, (tuple, list)):
            mp_ = torch.sigmoid(out[0]).cpu().numpy()[0] * 100
            sp_ = torch.sigmoid(out[1]).cpu().numpy()[0] * 100 if len(out) > 1 else np.zeros(14)
        else:
            mp_ = torch.sigmoid(out).cpu().numpy()[0] * 100
            sp_ = np.zeros(14)
        r = {}
        for i, n in enumerate(AU_MAIN):
            r[n] = float(mp_[i])
        for i, n in enumerate(AU_SUB):
            r[n] = float(sp_[i])
        return r

def normalize_profile(au_dict, au_subset):
    """
    自身归一化：将AU向量转换为轮廓向量
    步骤1: 减去自身均值
    步骤2: 除以标准差
    """
    values = [au_dict.get(au, 0.0) for au in au_subset]
    arr = np.array(values, dtype=np.float32)
    
    mean_val = np.mean(arr)
    centered = arr - mean_val
    
    std_val = np.std(arr)
    if std_val < 1e-6:
        std_val = 1.0
    
    normalized = centered / std_val
    
    result = {}
    for i, au in enumerate(au_subset):
        result[au] = float(normalized[i])
    
    return result, float(mean_val), float(std_val)

def build_profiles(data_dir):
    print("初始化检测器...")
    detector = FaceDetector()
    au_extractor = AUExtractor()
    
    profiles = {}
    diagnostics = {}
    
    for pose in POSES:
        profiles[pose] = {}
        diagnostics[pose] = {}
        
        for emotion in EMOTIONS:
            folder_name = f"{pose}-{emotion}"
            folder_path = os.path.join(data_dir, folder_name)
            
            if not os.path.exists(folder_path):
                print(f"跳过文件夹: {folder_path} (不存在)")
                continue
            
            au_subset = POSE_AU_SUBSET[pose]
            all_profiles = []
            all_raw_aus = []
            
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                
                img_path = os.path.join(folder_path, filename)
                frame = cv2.imread(img_path)
                if frame is None:
                    print(f"无法读取: {img_path}")
                    continue
                
                lm_list = detector.process(frame)
                if not lm_list:
                    print(f"未检测到人脸: {filename}")
                    continue
                
                lm = lm_list[0]
                au = au_extractor.predict(frame, lm)
                if au is None:
                    print(f"AU提取失败: {filename}")
                    continue
                
                all_raw_aus.append(au)
                
                profile, mean_val, std_val = normalize_profile(au, au_subset)
                all_profiles.append(profile)
                
                print(f"处理: {folder_name}/{filename} -> {len(all_profiles)}张")
            
            if len(all_profiles) == 0:
                print(f"警告: {folder_name} 中没有有效图片")
                profiles[pose][emotion] = None
                diagnostics[pose][emotion] = {'count': 0, 'mean': None, 'std': None}
                continue
            
            mean_profile = {}
            for au in au_subset:
                values = [p[au] for p in all_profiles]
                mean_profile[au] = float(np.mean(values))
            
            std_profile = {}
            for au in au_subset:
                values = [p[au] for p in all_profiles]
                std_profile[au] = float(np.std(values))
            
            profiles[pose][emotion] = {
                'mean': mean_profile,
                'std': std_profile,
                'au_subset': au_subset,
                'sample_count': len(all_profiles)
            }
            
            diagnostics[pose][emotion] = {
                'count': len(all_profiles),
                'au_subset': au_subset,
                'raw_au_stats': calculate_au_stats(all_raw_aus, au_subset)
            }
            
            print(f"完成 {folder_name}: {len(all_profiles)} 张图片")
    
    detector.release()
    
    output_path = os.path.join(data_dir, 'emotion_profiles.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)
    
    diagnostic_path = os.path.join(data_dir, 'profiles_diagnostics.json')
    with open(diagnostic_path, 'w', encoding='utf-8') as f:
        json.dump(diagnostics, f, indent=2, ensure_ascii=False)
    
    print(f"\n轮廓模板已保存到: {output_path}")
    print(f"诊断报告已保存到: {diagnostic_path}")
    
    return profiles, diagnostics

def calculate_au_stats(au_list, au_subset):
    stats = {}
    for au in au_subset:
        values = [au_dict.get(au, 0.0) for au_dict in au_list]
        stats[au] = {
            'mean': float(np.mean(values)),
            'std': float(np.std(values)),
            'min': float(np.min(values)),
            'max': float(np.max(values))
        }
    return stats

if __name__ == "__main__":
    data_dir = os.path.dirname(os.path.abspath(__file__))
    build_profiles(data_dir)