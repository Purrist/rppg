# -*- coding: utf-8 -*-
"""
依赖项检查和自动安装脚本
"""

import subprocess
import sys
import importlib
import os

# 必需的依赖项
REQUIRED_PACKAGES = [
    # 核心依赖
    'flask',
    'flask-cors',
    'flask-socketio',
    'opencv-python',
    'numpy',
    'mediapipe',
    
    # 语音相关
    'sherpa-onnx',
    'sounddevice',
    'numpy',  # 重复，确保安装
    
    # 平板视频流处理
    'urllib3',
    
    # 可选依赖
    'SpeechRecognition',  # 备用语音识别
    'edge-tts',  # 备用TTS
    'pydub',  # 音频处理
]

def check_package(package):
    """检查包是否已安装"""
    try:
        importlib.import_module(package)
        return True
    except ImportError:
        return False

def install_package(package):
    """安装包"""
    print(f"[依赖检查] 安装 {package}...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
        return True
    except subprocess.CalledProcessError:
        print(f"[依赖检查] 安装 {package} 失败")
        return False

def check_and_install_dependencies():
    """检查并安装所有依赖项"""
    print("[依赖检查] 开始检查依赖项...")
    
    missing_packages = []
    
    for package in REQUIRED_PACKAGES:
        if not check_package(package):
            missing_packages.append(package)
        else:
            print(f"[依赖检查] {package} ✓")
    
    if missing_packages:
        print(f"[依赖检查] 缺少以下包: {', '.join(missing_packages)}")
        print("[依赖检查] 开始安装...")
        
        for package in missing_packages:
            install_package(package)
        
        print("[依赖检查] 依赖项安装完成")
    else:
        print("[依赖检查] 所有依赖项都已安装")

if __name__ == "__main__":
    check_and_install_dependencies()
