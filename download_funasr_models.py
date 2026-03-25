#!/usr/bin/env python3
"""
下载 FunASR 模型到本地目录
"""
import os
import sys
from pathlib import Path

# 模型下载目录
MODEL_DIR = Path(r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models")

# 需要下载的模型列表
MODELS = {
    "vad": "damo/speech_fsmn_vad_zh-cn-16k-common-onnx",
    "punc": "damo/punc_ct-transformer_cn-en-common-vocab471067-large-onnx",
    # ASR 模型我们已有类似的，可以暂时不下载
}

def download_model(model_id: str, local_dir: Path):
    """从 ModelScope 下载模型"""
    try:
        from modelscope import snapshot_download
        print(f"正在下载模型: {model_id}")
        print(f"下载到: {local_dir}")
        
        # 创建本地目录
        local_dir.mkdir(parents=True, exist_ok=True)
        
        # 下载模型
        snapshot_download(model_id, cache_dir=str(local_dir))
        print(f"✅ 模型下载完成: {model_id}")
        return True
        
    except ImportError:
        print("❌ 缺少 modelscope 库，请先安装:")
        print("pip install modelscope")
        return False
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        return False

def main():
    print("=" * 60)
    print("FunASR 模型下载工具")
    print("=" * 60)
    print()
    
    # 检查 modelscope 是否安装
    try:
        import modelscope
        print(f"✅ ModelScope 版本: {modelscope.__version__}")
    except ImportError:
        print("❌ 未安装 modelscope，请先安装:")
        print("pip install modelscope")
        sys.exit(1)
    
    print()
    print(f"模型将下载到: {MODEL_DIR}")
    print()
    
    # 下载每个模型
    success_count = 0
    for model_type, model_id in MODELS.items():
        local_dir = MODEL_DIR / model_id.replace("/", "-")
        if download_model(model_id, local_dir):
            success_count += 1
        print()
    
    print("=" * 60)
    print(f"下载完成: {success_count}/{len(MODELS)} 个模型")
    print("=" * 60)

if __name__ == "__main__":
    main()
