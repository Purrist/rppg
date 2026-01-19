import os
import sys

# 彻底屏蔽冗余警告
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

try:
    print("--- 正在检测环境 ---")
    import numpy as np
    print(f"1. NumPy 版本: {np.__version__}") # [cite: 19, 33]

    import tensorflow as tf
    # 尝试调用一个具体的函数来激活模块
    v = tf.constant([1.0, 2.0]) 
    print(f"2. TensorFlow 运行正常") 
    
    import mediapipe as mp
    mesh = mp.solutions.face_mesh.FaceMesh()
    print(f"3. MediaPipe 初始化成功") # [cite: 17, 30]

    from deepface import DeepFace
    print(f"4. DeepFace 加载成功") # [cite: 41, 42]

    print("\n🚀 【恭喜】环境已彻底修复，所有库现在可以共同工作了！")

except AttributeError as e:
    print(f"\n❌ 模块加载异常: {e}")
    print("提示: 这通常是因为 D:\anaconda\envs\rppg\lib\site-packages 下有旧的 tensorflow 残留。")
except Exception as e:
    print(f"\n❌ 发生错误: {e}")