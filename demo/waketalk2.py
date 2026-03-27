#!/usr/bin/env python3
"""
实时唤醒词检测和语音复述 - 使用麦克风3
使用本地 Sherpa-ONNX 模型，无需联网
支持语音端点检测（VAD）自动结束录制
"""
import queue
import sys
import threading
import time
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

# 音频参数
SAMPLE_RATE = 16000
CHANNELS = 1
MIC_DEVICE_ID = 3  # 麦克风设备索引

# 检测参数
NUM_THREADS = 4
KEYWORDS_SCORE = 1.0       # 检测阈值，越小越宽松
KEYWORDS_THRESHOLD = 0.25  # 触发阈值

# 语音端点检测（VAD）参数
VAD_ENERGY_THRESHOLD = 0.015  # 能量阈值，超过此值视为有语音
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

    def audio_callback(self, indata, frames, time_info, status):
        """麦克风录音回调"""
        if status:
            print(f"[警告] 音频状态: {status}")
        
        # 如果正在录制语音，保存音频数据并进行 VAD 检测
        if self.is_recording:
            self.recorded_audio.append(indata.copy())
            self.process_vad(indata)
        
        self.audio_queue.put(indata.copy())

    def process_vad(self, audio_chunk):
        """语音端点检测处理（能量检测）"""
        rms = np.sqrt(np.mean(audio_chunk ** 2))
        current_time = datetime.now()
        
        if rms > VAD_ENERGY_THRESHOLD:
            if not self.vad_is_speaking:
                self.vad_is_speaking = True
                self.vad_speech_start_time = current_time
                print("🎤 检测到语音输入...")
            if self.vad_silence_start_time:
                silence_duration = (current_time - self.vad_silence_start_time).total_seconds()
                if silence_duration >= 0.8:
                    self.silence_intervals.append((self.vad_silence_start_time, current_time, silence_duration))
                    print(f"⏸️  检测到停顿（{silence_duration:.1f} 秒）")
            self.vad_silence_start_time = None
        else:
            if self.vad_is_speaking:
                if self.vad_silence_start_time is None:
                    self.vad_silence_start_time = current_time
                else:
                    silence_duration = (current_time - self.vad_silence_start_time).total_seconds()
                    if silence_duration >= VAD_SILENCE_TIMEOUT:
                        if silence_duration >= 0.8:
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
                if isinstance(result, str):
                    if result.strip():
                        self.on_keyword_detected(result)
                        stream = self.kws.create_stream()
                elif hasattr(result, 'keyword'):
                    if result.keyword:
                        self.on_keyword_detected(result.keyword)
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
        
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        self.silence_intervals = []
        
        # 开始录制
        self.is_recording = True
        self.recorded_audio = []
        
        start_time = time.time()
        
        while self.is_recording and self.is_running:
            elapsed = time.time() - start_time
            if elapsed >= VAD_MAX_RECORD_DURATION:
                print(f"⏱️ 达到最大录制时长（{VAD_MAX_RECORD_DURATION} 秒）")
                self.is_recording = False
                break
            time.sleep(0.05)
        
        # 停止录制
        self.is_recording = False
        
        # 处理录制的音频
        if len(self.recorded_audio) > 0:
            total_samples = sum(len(chunk) for chunk in self.recorded_audio)
            duration = total_samples / SAMPLE_RATE
            if duration >= VAD_MIN_SPEECH_DURATION:
                self.process_recorded_audio()
            else:
                print(f"→ 语音太短（{duration:.1f} 秒），请再说一次")
        else:
            print("→ 未检测到语音输入")

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
            
            # 获取识别结果
            result = stream.result
            text = result.text.strip() if hasattr(result, 'text') else str(result).strip()
            
            if text:
                print(f"→ 您说: {text}")
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
