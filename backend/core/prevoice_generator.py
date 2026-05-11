import os
import numpy as np
import soundfile as sf
import json
from pathlib import Path

def pregenerate_voice_files(tts_engine, responses, output_dir):
    """预生成回应语音频文件"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[Prevoice] 开始预生成回应语音频到 {output_dir}")
    
    for idx, response in enumerate(responses):
        try:
            audio = tts_engine.generate(response, sid=0, speed=1.2)
            samples = np.array(audio.samples, dtype=np.float32)
            output_path = output_dir / f"response_{idx}.wav"
            sf.write(str(output_path), samples, audio.sample_rate)
            print(f"[Prevoice] 已生成: {response} -> {output_path.name}")
        except Exception as e:
            print(f"[Prevoice] 生成失败 {response}: {e}")
    
    # 创建索引文件
    index_data = {
        "responses": responses,
        "count": len(responses)
    }
    with open(output_dir / "index.json", 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"[Prevoice] 预生成完成，共 {len(responses)} 个音频文件")

if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # 初始化 TTS 引擎
    try:
        import sherpa_onnx
        from voice_manager_sherpa import VoiceManager
        
        models_dir = Path(__file__).parent / "models"
        possible_dirs = [
            models_dir / "vits-zh-hf-fanchen-C",
            models_dir / "vits-zh"
        ]
        
        tts_model_dir = None
        for d in possible_dirs:
            if d.exists():
                tts_model_dir = d
                break
        
        if not tts_model_dir:
            print("[Prevoice] 未找到 VITS 模型目录")
            sys.exit(1)
        
        model_files = list(tts_model_dir.glob("*.onnx"))
        token_files = list(tts_model_dir.glob("tokens.txt"))
        lexicon_files = list(tts_model_dir.glob("lexicon.txt"))
        
        if not model_files or not token_files:
            print("[Prevoice] VITS 模型文件不完整")
            sys.exit(1)
        
        model_path = str(model_files[0])
        tokens_path = str(token_files[0])
        lexicon_path = str(lexicon_files[0]) if lexicon_files else None
        
        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=model_path,
                    tokens=tokens_path,
                    lexicon=lexicon_path,
                ),
                num_threads=2,
                provider="cpu",
            ),
            rule_fsts=f"{tts_model_dir}/phone.fst,{tts_model_dir}/date.fst,{tts_model_dir}/number.fst" if tts_model_dir.exists() else None
        )
        
        tts_engine = sherpa_onnx.OfflineTts(tts_config)
        print("[Prevoice] VITS 引擎初始化完成")
        
        # 回应语列表
        responses = [
            '来啦', '我在', '在呢', '听着呢',
            '在的', '您说', '来了', '我在呢',
        ]
        
        output_dir = Path(__file__).parent / "prevoice"
        pregenerate_voice_files(tts_engine, responses, output_dir)
        
    except Exception as e:
        print(f"[Prevoice] 初始化失败: {e}")
        import traceback
        traceback.print_exc()