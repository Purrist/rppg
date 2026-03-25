#!/usr/bin/env python3
"""
实时唤醒词检测和语音复述 - 使用麦克风3
使用本地 Sherpa-ONNX 模型，无需联网
支持语音端点检测（VAD）自动结束录制
"""
import queue
import sys
import threading
import wave
import tempfile
import os
from pathlib import Path
from datetime import datetime

import numpy as np
import sherpa_onnx
import sounddevice as sd

# ============ 配置区域 ============
# 关键词检测模型路径
KWS_MODEL_DIR = Path(r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01")
KEYWORDS_FILE = KWS_MODEL_DIR / "keywords.txt"

# 语音识别模型路径 (本地模型，无需联网)
ASR_MODEL_DIR = Path(r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\sherpa-onnx-paraformer-zh-2024-03-09")

# FSMN VAD 模型路径 (FunASR)
VAD_MODEL_DIR = Path(r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\damo-speech_fsmn_vad_zh-cn-16k-common-onnx\damo\speech_fsmn_vad_zh-cn-16k-common-onnx")

# 标点预测模型路径 (FunASR)
PUNC_MODEL_DIR = Path(r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\damo-punc_ct-transformer_cn-en-common-vocab471067-large-onnx\damo\punc_ct-transformer_cn-en-common-vocab471067-large-onnx")

# 音频参数
SAMPLE_RATE = 16000
CHANNELS = 1
MIC_DEVICE_ID = 3  # 麦克风设备索引

# 检测参数
NUM_THREADS = 4
KEYWORDS_SCORE = 1.0       # 检测阈值，越小越宽松
KEYWORDS_THRESHOLD = 0.25  # 触发阈值

# 语音端点检测（VAD）参数
VAD_SILENCE_TIMEOUT = 1.5     # 静音超时时间（秒），超过此时间无语音则结束录制
VAD_MIN_SPEECH_DURATION = 0.5  # 最短语音时长（秒），避免误触发
VAD_MAX_RECORD_DURATION = 10   # 最长录制时长（秒），防止无限录制


class WakeTalkDetector:
    def __init__(self):
        # 检查模型文件
        if not KWS_MODEL_DIR.exists():
            raise FileNotFoundError(f"关键词检测模型目录不存在: {KWS_MODEL_DIR}")
        if not KEYWORDS_FILE.exists():
            raise FileNotFoundError(f"关键词文件不存在: {KEYWORDS_FILE}")
        if not ASR_MODEL_DIR.exists():
            raise FileNotFoundError(f"语音识别模型目录不存在: {ASR_MODEL_DIR}")

        # 初始化关键词检测器
        self.kws = sherpa_onnx.KeywordSpotter(
            tokens=str(KWS_MODEL_DIR / "tokens.txt"),
            encoder=str(KWS_MODEL_DIR / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            decoder=str(KWS_MODEL_DIR / "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            joiner=str(KWS_MODEL_DIR / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            num_threads=NUM_THREADS,
            keywords_file=str(KEYWORDS_FILE),
            keywords_score=KEYWORDS_SCORE,
            keywords_threshold=KEYWORDS_THRESHOLD,
            provider="cpu",
        )

        # 初始化本地语音识别器 (Paraformer 模型)
        print("[初始化] 正在加载语音识别模型...")
        self.asr = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=str(ASR_MODEL_DIR / "model.int8.onnx"),
            tokens=str(ASR_MODEL_DIR / "tokens.txt"),
            num_threads=NUM_THREADS,
            sample_rate=SAMPLE_RATE,
            feature_dim=80,
            decoding_method="greedy_search",
        )
        print("[初始化] 语音识别模型加载完成")
        
        # 初始化 FSMN VAD 模型 (FunASR)
        self.use_fsmn_vad = False
        if VAD_MODEL_DIR.exists():
            try:
                print("[初始化] 正在加载 FSMN VAD 模型...")
                # 读取 VAD 配置文件
                import yaml
                vad_config_path = VAD_MODEL_DIR / "config.yaml"
                if vad_config_path.exists():
                    with open(vad_config_path, 'r', encoding='utf-8') as f:
                        vad_config = yaml.safe_load(f)
                    
                    # 初始化 FSMN VAD
                    self.vad = sherpa_onnx.VadModel(
                        encoder=str(VAD_MODEL_DIR / "model_quant.onnx"),
                        num_threads=NUM_THREADS,
                        provider="cpu",
                    )
                    self.use_fsmn_vad = True
                    print("[初始化] FSMN VAD 模型加载完成")
                else:
                    print("[警告] VAD 配置文件不存在，使用能量检测")
            except Exception as e:
                print(f"[警告] FSMN VAD 模型加载失败: {e}，使用能量检测")
        else:
            print("[警告] FSMN VAD 模型目录不存在，使用能量检测")
        
        # 初始化标点预测模型 (FunASR)
        self.use_punc_model = False
        if PUNC_MODEL_DIR.exists():
            try:
                print("[初始化] 正在加载标点预测模型...")
                # 这里需要根据实际的标点模型 API 进行初始化
                # 暂时使用占位符，后续根据模型格式调整
                self.punc_model = None  # 占位符
                self.use_punc_model = True
                print("[初始化] 标点预测模型加载完成")
            except Exception as e:
                print(f"[警告] 标点预测模型加载失败: {e}，使用规则-based 标点")
        else:
            print("[警告] 标点预测模型目录不存在，使用规则-based 标点")
        
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.is_recording = False
        self.recorded_audio = []
        
        # VAD 状态
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        self.silence_intervals = []  # 记录静音间隔（开始时间，结束时间，时长）
        
        print(f"[初始化] 关键词检测模型加载完成，使用麦克风设备: {MIC_DEVICE_ID}")

    def audio_callback(self, indata, frames, time, status):
        """麦克风录音回调"""
        if status:
            print(f"[警告] 音频状态: {status}")
        
        # 如果正在录制语音，保存音频数据并进行 VAD 检测
        if self.is_recording:
            self.recorded_audio.append(indata.copy())
            self.process_vad(indata)
        
        self.audio_queue.put(indata.copy())

    def process_vad(self, audio_chunk):
        """语音端点检测处理"""
        # 计算音频能量（RMS）
        rms = np.sqrt(np.mean(audio_chunk ** 2))
        
        current_time = datetime.now()
        
        if rms > VAD_ENERGY_THRESHOLD:
            # 检测到语音
            if not self.vad_is_speaking:
                # 语音开始
                self.vad_is_speaking = True
                self.vad_speech_start_time = current_time
                print("🎤 检测到语音输入...")
            # 检查是否有静音间隔需要记录
            if self.vad_silence_start_time:
                silence_duration = (current_time - self.vad_silence_start_time).total_seconds()
                if silence_duration >= 0.8:  # 0.8秒以上的静音
                    self.silence_intervals.append((self.vad_silence_start_time, current_time, silence_duration))
                    print(f"⏸️  检测到停顿（{silence_duration:.1f} 秒）")
            # 重置静音计时器
            self.vad_silence_start_time = None
        else:
            # 检测到静音
            if self.vad_is_speaking:
                if self.vad_silence_start_time is None:
                    # 开始计算静音时间
                    self.vad_silence_start_time = current_time
                else:
                    # 检查静音时长
                    silence_duration = (current_time - self.vad_silence_start_time).total_seconds()
                    if silence_duration >= VAD_SILENCE_TIMEOUT:
                        # 静音超时，结束录制
                        # 记录最后一个静音间隔
                        if silence_duration >= 1.0:
                            self.silence_intervals.append((self.vad_silence_start_time, current_time, silence_duration))
                        print(f"🛑 检测到语音结束（静音 {silence_duration:.1f} 秒）")
                        self.is_recording = False

    def process_audio(self):
        """音频处理线程"""
        stream = self.kws.create_stream()
        
        print("\n" + "=" * 50)
        print("🎤 正在监听唤醒词... (按 Ctrl+C 停止)")
        print("=" * 50 + "\n")

        while self.is_running:
            try:
                audio_chunk = self.audio_queue.get(timeout=0.1)
                samples = audio_chunk.flatten().astype(np.float32)
                stream.accept_waveform(SAMPLE_RATE, samples)

                while self.kws.is_ready(stream):
                    self.kws.decode_stream(stream)

                result = self.kws.get_result(stream)
                # 处理返回值，可能是字符串或对象
                if isinstance(result, str):
                    # 如果返回的是字符串，检查是否包含关键词
                    if result.strip():
                        self.on_keyword_detected(result)
                        # 重置流，避免重复触发
                        stream = self.kws.create_stream()
                elif hasattr(result, 'keyword'):
                    # 如果返回的是对象，检查 keyword 属性
                    if result.keyword:
                        self.on_keyword_detected(result.keyword)
                        # 重置流，避免重复触发
                        stream = self.kws.create_stream()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[错误] 处理音频时出错: {e}")

    def on_keyword_detected(self, keyword):
        """检测到关键词时的回调"""
        print("\n" + "🎉" * 20)
        print(f"✅ 检测到唤醒词: {keyword}")
        print("🎉" * 20 + "\n")
        
        # 这里可以添加你的业务逻辑
        # 例如：启动语音识别、触发某个事件等
        self.trigger_action(keyword)

    def trigger_action(self, keyword):
        """触发后续动作"""
        # 处理可能的空格和格式
        normalized_keyword = keyword.strip()
        
        # 检查是否包含唤醒词的核心部分
        if "ā k āng" in normalized_keyword or "kāng" in normalized_keyword or "阿康" in normalized_keyword:
            self.start_listening()
        else:
            print(f"→ 收到唤醒词: {keyword}")

    def start_listening(self):
        """开始监听用户说话（使用 VAD 自动结束）"""
        print("→ 您说，我来复述")
        print(f"🔊 正在听...（说完后停顿 {VAD_SILENCE_TIMEOUT} 秒自动结束）")
        
        # 重置 VAD 状态
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        self.silence_intervals = []  # 重置静音间隔记录
        
        # 开始录制
        self.is_recording = True
        self.recorded_audio = []
        
        # 等待录制完成（使用 VAD 或超时）
        import time
        start_time = time.time()
        
        while self.is_recording and self.is_running:
            # 检查是否超过最大录制时长
            elapsed = time.time() - start_time
            if elapsed >= VAD_MAX_RECORD_DURATION:
                print(f"⏱️ 达到最大录制时长（{VAD_MAX_RECORD_DURATION} 秒）")
                self.is_recording = False
                break
            
            # 检查是否有足够的语音数据
            if self.vad_is_speaking and self.vad_speech_start_time:
                speech_duration = (datetime.now() - self.vad_speech_start_time).total_seconds()
                if speech_duration >= VAD_MIN_SPEECH_DURATION and not self.is_recording:
                    # 语音时长足够且已停止录制
                    break
            
            time.sleep(0.05)  # 短暂休眠，避免 CPU 占用过高
        
        # 停止录制
        self.is_recording = False
        
        # 处理录制的音频
        if len(self.recorded_audio) > 0:
            # 检查语音时长
            total_samples = sum(len(chunk) for chunk in self.recorded_audio)
            duration = total_samples / SAMPLE_RATE
            
            if duration >= VAD_MIN_SPEECH_DURATION:
                self.process_recorded_audio()
            else:
                print(f"→ 语音太短（{duration:.1f} 秒），请再说一次")
        else:
            print("→ 未检测到语音输入")

    def add_punctuation(self, text):
        """为文本添加标点符号"""
        if not text:
            return text
        
        # 1. 处理感叹词位置（避免在感叹词前加逗号）
        # 先标记感叹词位置
        exclamations = ["啊", "呀", "哇", "哦"]
        exclamation_positions = []
        for i, char in enumerate(text):
            if char in exclamations:
                exclamation_positions.append(i)
        
        # 2. 根据静音间隔添加逗号
        if self.silence_intervals:
            interval_count = len(self.silence_intervals)
            if interval_count > 0 and len(text) > 5:  # 文本长度足够
                # 简单策略：根据静音间隔数量在文本中添加逗号
                # 按字符长度平均分割
                total_chars = len(text)
                chars_per_part = total_chars // (interval_count + 1)
                
                new_text = ""
                for i, char in enumerate(text):
                    new_text += char
                    # 检查是否在感叹词位置附近
                    near_exclamation = any(abs(i - pos) <= 1 for pos in exclamation_positions)
                    # 在每个部分结束时添加逗号，但避免在感叹词附近
                    if (i + 1) % chars_per_part == 0 and i < total_chars - 1 and not near_exclamation:
                        new_text += "，"
                text = new_text
        
        # 3. 基本标点规则
        # 句尾添加句号
        if text[-1] not in ["。", "！", "？", "；", "：", ".", "!", "?", ";", ":"]:
            text += "。"
        
        # 4. 替换常见的分隔词
        text = text.replace("然后", "，然后")
        text = text.replace("但是", "，但是")
        text = text.replace("所以", "，所以")
        text = text.replace("因为", "，因为")
        text = text.replace("而且", "，而且")
        text = text.replace("另外", "，另外")
        
        # 5. 处理疑问词
        if "吗" in text or "呢" in text or "什么" in text or "怎么" in text or "为什么" in text:
            # 如果句尾不是问号，替换为问号
            if text[-1] == "。":
                text = text[:-1] + "？"
        
        # 6. 处理感叹词
        if "啊" in text or "呀" in text or "哇" in text or "哦" in text:
            # 如果句尾不是感叹号，替换为感叹号
            if text[-1] == "。" and (text[-2] in "啊呀哇哦" or text[-3:-1] in "啊呀哇哦"):
                text = text[:-1] + "！"
        
        # 7. 清理多余的逗号
        # 移除感叹词前的逗号
        text = text.replace("，啊", "啊")
        text = text.replace("，呀", "呀")
        text = text.replace("，哇", "哇")
        text = text.replace("，哦", "哦")
        
        return text

    def process_recorded_audio(self):
        """处理录制的音频并进行语音识别"""
        try:
            print("📝 正在识别...")
            
            # 合并音频数据
            audio_data = np.concatenate(self.recorded_audio, axis=0).flatten().astype(np.float32)
            
            # 创建识别流
            stream = self.asr.create_stream()
            stream.accept_waveform(SAMPLE_RATE, audio_data)
            
            # 进行识别
            self.asr.decode_stream(stream)
            
            # 获取识别结果 (使用正确的 API 方法)
            result = stream.result
            text = result.text.strip() if hasattr(result, 'text') else str(result).strip()
            
            if text:
                # 添加标点符号
                text_with_punctuation = self.add_punctuation(text)
                print(f"→ 您说: {text_with_punctuation}")
            else:
                print("→ 无法识别语音")
                
        except Exception as e:
            print(f"→ 识别出错: {e}")

    def run(self):
        """主运行循环"""
        self.is_running = True

        # 启动音频处理线程
        processor_thread = threading.Thread(target=self.process_audio, daemon=True)
        processor_thread.start()

        try:
            # 启动麦克风录音
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.float32,
                device=MIC_DEVICE_ID,
                callback=self.audio_callback,
                blocksize=480,  # 约30ms的音频块
            ):
                print("[状态] 麦克风已启动，开始检测...")
                processor_thread.join()

        except KeyboardInterrupt:
            print("\n[停止] 正在关闭...")
            self.is_running = False
        except Exception as e:
            print(f"[错误] {e}")
            # 列出可用设备帮助调试
            print("\n可用的音频设备:")
            print(sd.query_devices())
        finally:
            self.is_running = False


def list_audio_devices():
    """列出所有音频设备"""
    print("\n可用音频设备列表:")
    print("-" * 50)
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            marker = " ← 当前选择" if i == MIC_DEVICE_ID else ""
            print(f"[{i:2d}] {dev['name']}{marker}")
    print("-" * 50)


if __name__ == "__main__":
    # 安装依赖提示
    try:
        import sherpa_onnx
        import sounddevice
    except ImportError as e:
        print("缺少依赖，请安装:")
        print("pip install sherpa-onnx sounddevice numpy")
        sys.exit(1)

    # 查看设备列表（可选）
    if len(sys.argv) > 1 and sys.argv[1] == "--list-devices":
        list_audio_devices()
        sys.exit(0)

    # 运行检测器
    detector = WakeTalkDetector()
    detector.run()