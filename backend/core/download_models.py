#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音模型下载脚本
自动下载所需的语音模型文件
"""

import os
import sys
import zipfile
import requests
from pathlib import Path

# 模型下载链接
MODEL_LINKS = {
    'paraformer-zh': 'https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-2024-03-09/resolve/main/model.int8.onnx?download=true',
    'paraformer-tokens': 'https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-2024-03-09/resolve/main/tokens.txt?download=true',
    'kws': 'https://huggingface.co/csukuangfj/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/resolve/main/encoder-epoch-12-avg-2-chunk-16-left-64.onnx?download=true',
    'kws-decoder': 'https://huggingface.co/csukuangfj/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/resolve/main/decoder-epoch-12-avg-2-chunk-16-left-64.onnx?download=true',
    'kws-joiner': 'https://huggingface.co/csukuangfj/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/resolve/main/joiner-epoch-12-avg-2-chunk-16-left-64.onnx?download=true',
    'kws-tokens': 'https://huggingface.co/csukuangfj/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/resolve/main/tokens.txt?download=true',
    'kws-keywords': 'https://huggingface.co/csukuangfj/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/resolve/main/keywords.txt?download=true',
}

# 关键词文件内容
KEYWORDS_CONTENT = """阿康 /1.0/
阿康阿康 /1.0/
akon /1.0/
你好阿康 /1.0/
阿康你好 /1.0/
小康 /1.0/
小康小康 /1.0/"""

def download_file(url, save_path):
    """下载文件"""
    print(f"下载: {url}")
    print(f"保存到: {save_path}")
    
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"✓ 下载完成: {save_path}")
        return True
    except Exception as e:
        print(f"✗ 下载失败: {e}")
        return False

def main():
    """主函数"""
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)
    
    # 创建子目录
    paraformer_dir = models_dir / "paraformer-zh"
    kws_dir = models_dir / "kws"
    
    paraformer_dir.mkdir(exist_ok=True)
    kws_dir.mkdir(exist_ok=True)
    
    print("开始下载语音模型...")
    print(f"模型保存目录: {models_dir}")
    print("=" * 60)
    
    # 下载Paraformer模型
    print("\n1. 下载Paraformer语音识别模型:")
    download_file(MODEL_LINKS['paraformer-zh'], paraformer_dir / "model.int8.onnx")
    download_file(MODEL_LINKS['paraformer-tokens'], paraformer_dir / "tokens.txt")
    
    # 下载KWS模型
    print("\n2. 下载KWS唤醒词检测模型:")
    download_file(MODEL_LINKS['kws'], kws_dir / "encoder-epoch-12-avg-2-chunk-16-left-64.onnx")
    download_file(MODEL_LINKS['kws-decoder'], kws_dir / "decoder-epoch-12-avg-2-chunk-16-left-64.onnx")
    download_file(MODEL_LINKS['kws-joiner'], kws_dir / "joiner-epoch-12-avg-2-chunk-16-left-64.onnx")
    download_file(MODEL_LINKS['kws-tokens'], kws_dir / "tokens.txt")
    
    # 创建关键词文件
    keywords_file = kws_dir / "keywords.txt"
    with open(keywords_file, 'w', encoding='utf-8') as f:
        f.write(KEYWORDS_CONTENT)
    print(f"✓ 创建关键词文件: {keywords_file}")
    
    print("\n" + "=" * 60)
    print("语音模型下载完成！")
    print("请运行: python app.py 启动系统")

if __name__ == "__main__":
    main()
