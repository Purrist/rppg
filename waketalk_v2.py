#!/usr/bin/env python3
"""
实时唤醒词检测和语音复述 - 使用麦克风3
使用 FunASR 模型（VAD + ASR + PUNC）
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

# 语音识别模型路径 (Sherpa-ONNX)
ASR_MODEL_DIR = Path(r"C:\Users\purriste\Desktop\PYProject\rppg\backend\core\models\sherpa-onnx-paraformer-zh-2024-03-09")

# 语音合成配置
USE_PYTTSX3 = True  # 使用pyttsx3进行语音合成

# 音频参数
SAMPLE_RATE = 16000
CHANNELS = 1  # ✅ 改为单声道
MIC_DEVICE_ID = None  # 自动检测 Realtek 麦克风

# 检测参数
NUM_THREADS = 4
KEYWORDS_SCORE = 1.5      # 检测阈值，提高灵敏度，越高越敏感
KEYWORDS_THRESHOLD = 0.15   # 降低触发阈值，提高唤醒成功率

# 语音端点检测（VAD）参数
VAD_ENERGY_THRESHOLD = 0.02  # 降低能量阈值，提高语音检测灵敏度
VAD_SILENCE_TIMEOUT = 1.5     # 减少静音超时时间，更快结束录音
VAD_MIN_SPEECH_DURATION = 0.5  # 降低最短语音时长，捕获更短的语音
VAD_MAX_RECORD_DURATION = 15   # 缩短最长录制时长，避免长时间卡住


# 防抖和打断相关配置
DEBOUNCE_TIME = 1  # 防抖窗口时长（秒）

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
        print("[初始化] 正在加载关键词检测模型...")
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
        print("[初始化] 关键词检测模型加载完成")

        # 初始化本地语音识别器 (Paraformer 模型)
        print("[初始化] 正在加载语音识别模型...")
        try:
            self.asr = sherpa_onnx.OfflineRecognizer.from_paraformer(
                paraformer=str(ASR_MODEL_DIR / "model.int8.onnx"),
                tokens=str(ASR_MODEL_DIR / "tokens.txt"),
                num_threads=NUM_THREADS,
                sample_rate=SAMPLE_RATE,
                feature_dim=80,
                decoding_method="greedy_search",
            )
            print("[初始化] 语音识别模型加载完成")
        except Exception as e:
            print(f"[错误] 语音识别模型加载失败: {e}")
            raise
        
        # ✅ 正确检测和保存麦克风设备ID
        self.mic_device_id = self._detect_microphone()
        
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.is_recording = False
        self.is_playing = False  # 添加播放状态标志
        self.recorded_audio = []
        
        # VAD 状态
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        self.silence_intervals = []
        
        # 状态机相关
        self.state = "IDLE"  # IDLE / LISTENING / PROCESSING
        self.last_wake_time = 0  # 上次唤醒时间戳
        
        # 唤醒回复列表
        self.wake_responses = [
            "来啦",
            "在呢",
            "请说",
            "我在",
            "来了",
        ]
        
        # 语音合成器将在每次播放时动态创建
        print("[初始化] 语音合成引擎配置完成")
        
        print(f"[初始化] 系统就绪，使用麦克风设备: {self.mic_device_id}")

    def _detect_microphone(self):
        """自动检测 Realtek 麦克风"""
        print("[初始化] 正在检测麦克风设备...")
        
        # 1. 首先尝试找 Realtek 麦克风
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if 'Realtek' in dev['name'] and dev['max_input_channels'] > 0:
                print(f"[初始化] 找到 Realtek 麦克风: {dev['name']} (设备ID: {i})")
                return i
        
        # 2. 如果没找到，使用默认输入设备
        try:
            default_input = sd.default.device[0]
            if default_input >= 0:
                default_device = sd.query_devices(default_input)
                print(f"[初始化] 使用默认麦克风: {default_device['name']} (设备ID: {default_input})")
                return default_input
        except Exception as e:
            print(f"[警告] 获取默认设备失败: {e}")
        
        # 3. 如果还是没有，找第一个可用的输入设备
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                print(f"[初始化] 使用第一个可用麦克风: {dev['name']} (设备ID: {i})")
                return i
        
        raise RuntimeError("未找到任何可用的麦克风设备！")

    def audio_callback(self, indata, frames, time_info, status):
        """麦克风录音回调"""
        if status:
            print(f"[警告] 音频状态: {status}")
        
        # 如果正在播放语音，不保存录音数据
        if not self.is_playing:
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
                        # ✅ 正确重置流
                        self.kws.reset_stream(stream)
                        stream = self.kws.create_stream()
                elif hasattr(result, 'keyword'):
                    if result.keyword:
                        self.on_keyword_detected(result.keyword)
                        self.kws.reset_stream(stream)
                        stream = self.kws.create_stream()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[错误] 处理音频时出错: {e}")
                import traceback
                traceback.print_exc()

    def on_keyword_detected(self, keyword):
        """检测到关键词时的回调"""
        print("\n" + "🎉" * 20)
        print(f"✅ 检测到唤醒词: {keyword}")
        print("🎉" * 20 + "\n")
        
        current_time = time.time()
        time_since_last_wake = current_time - self.last_wake_time
        
        if self.state == "IDLE":
            # 空闲状态，直接触发唤醒
            self.trigger_action(keyword)
            self.last_wake_time = current_time
            return
        
        # 在防抖窗口内，忽略快速连续唤醒
        if time_since_last_wake < DEBOUNCE_TIME:
            print(f"[防抖] 忽略快速连续唤醒（距上次 {time_since_last_wake:.1f} 秒）")
            return
        
        # 超过防抖窗口，允许打断
        print(f"[打断] 检测到新的唤醒请求（距上次 {time_since_last_wake:.1f} 秒）")
        
        if self.state == "LISTENING":
            self.reset_listening()
        elif self.state == "PROCESSING":
            self.stop_processing_and_restart()
        
        self.trigger_action(keyword)
        self.last_wake_time = current_time

    def trigger_action(self, keyword):
        """触发后续动作"""
        normalized_keyword = keyword.strip()
        # 更宽松的匹配条件，确保能捕获"āng"等变体
        if "āng" in normalized_keyword or "kāng" in normalized_keyword or "阿康" in normalized_keyword:
            print("[触发] 匹配到唤醒词，开始录音...")
            # ✅ 在独立线程中启动录音，避免阻塞关键词检测
            import threading
            threading.Thread(target=self.start_listening).start()
        else:
            print(f"→ 收到唤醒词: {keyword}")

    def start_listening(self):
        """开始监听用户说话"""
        self.state = "LISTENING"
        
        # 播放随机唤醒回复
        response = self.get_random_wake_response()
        print(f"→ {response}")
        
        # 合成并播放回复
        try:
            self.play_audio(response)
        except Exception as e:
            print(f"[错误] 合成唤醒回复失败: {e}")
        
        print("→ 您说，我来复述")
        print(f"🔊 正在听...（说完后停顿 {VAD_SILENCE_TIMEOUT} 秒自动结束）")
        
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        self.silence_intervals = []
        
        self.is_recording = True
        self.recorded_audio = []
        
        start_time = time.time()
        
        # 确保录音线程不会阻塞主线程
        print(f"[线程] 录音线程启动，状态: LISTENING")
        
        while self.is_recording and self.is_running:
            elapsed = time.time() - start_time
            if elapsed >= VAD_MAX_RECORD_DURATION:
                print(f"⏱️ 达到最大录制时长（{VAD_MAX_RECORD_DURATION} 秒）")
                self.is_recording = False
                break
            time.sleep(0.05)
        
        self.is_recording = False
        self.state = "IDLE"
        print(f"[线程] 录音线程结束，状态: IDLE")
        
        if len(self.recorded_audio) > 0:
            total_samples = sum(len(chunk) for chunk in self.recorded_audio)
            duration = total_samples / SAMPLE_RATE
            print(f"[录音] 录制时长: {duration:.1f} 秒，采样数: {total_samples}")
            if duration >= VAD_MIN_SPEECH_DURATION:
                self.process_recorded_audio()
            else:
                print(f"→ 语音太短（{duration:.1f} 秒），请再说一次")
        else:
            print("→ 未检测到语音输入")

    def reset_listening(self):
        """打断录音，重新开始"""
        print("→ 检测到打断，重新开始 listening...")
        self.recorded_audio = []
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        self.silence_intervals = []

    def stop_processing_and_restart(self):
        """打断处理，重新开始"""
        print("→ 检测到打断，停止处理...")
        # 这里可以添加停止TTS等处理逻辑

    def play_audio(self, text):
        """播放文本语音（非阻塞）"""
        try:
            # 创建一个新线程来播放语音，避免阻塞
            import threading
            import pyttsx3
            
            def play_thread():
                try:
                    # 设置播放状态，避免系统自己的回复被当成用户输入
                    self.is_playing = True
                    
                    # 每次创建新的tts实例，避免run loop冲突
                    tts = pyttsx3.init()
                    # 设置语音属性
                    voices = tts.getProperty('voices')
                    # 选择中文语音
                    for voice in voices:
                        if 'zh' in voice.id or 'Chinese' in voice.name:
                            tts.setProperty('voice', voice.id)
                            break
                    tts.setProperty('rate', 150)  # 语速
                    tts.setProperty('volume', 1.0)  # 音量
                    
                    tts.say(text)
                    tts.runAndWait()
                    tts.stop()
                    
                    # 恢复播放状态
                    self.is_playing = False
                except Exception as e:
                    print(f"[错误] 播放音频失败: {e}")
                    # 确保恢复播放状态
                    self.is_playing = False
            
            t = threading.Thread(target=play_thread)
            t.daemon = True
            t.start()
        except Exception as e:
            print(f"[错误] 播放音频失败: {e}")

    def get_random_wake_response(self):
        """随机获取一个唤醒回复"""
        import random
        return random.choice(self.wake_responses)


    def add_punctuation(self, text):
        """使用规则-based 添加标点符号（优化版）"""
        if not text:
            return text
        
        import re
        
        # ============ 第一步：语义分隔词处理 ============
        # 只处理明确的语气词或连接词，避免破坏句子结构
        # 注意：不在 "今天"、"我" 等词后强制加逗号，保持句子连贯性
        separators = {
            "你好": "你好，",
            "您好": "您好，",
            "然后": "，然后",
            "但是": "，但是",
            "所以": "，所以",
            "因为": "，因为",
            "而且": "，而且",
            "另外": "，另外",
            "首先": "首先，",
            "最后": "，最后",
            "其实": "其实，",
        }
        
        for old, new in separators.items():
            # 简单替换，如果原词在文本中，就替换（防止重复替换可用计数限制）
            if old in text:
                text = text.replace(old, new, 1)
        
        # ============ 第二步：处理 "了" 字的动宾结构保护 ============
        # 错误做法：盲目在 "了" 后加逗号
        # 正确做法：先识别 "了 + 数词 + 量词" 这种结构，标记为不可分割，最后再处理 "了" 的断句
        
        # 1. 临时保护 "吃了一个"、"去了三次" 这种结构
        # 使用正则找到 "了 + 可选数词 + 量词"，临时替换占位符
        # 常见中文数词：一二两三四五六七八九十
        # 常见量词：个只条张件块次顿本
        pattern_verb_obj = r'了([零一二两三四五六七八九十百千万亿]*\s*[个只条张件块次顿本台辆头匹])'
        
        # 将 "了一个" 替换为 "了__PLACEHOLDER__个" 这种临时标记
        # 这样后续加逗号时就不会误伤这里
        def protect_match(match):
            return f"了__P__{match.group(1)}"
            
        text = re.sub(pattern_verb_obj, protect_match, text)
        
        # 2. 现在对剩余的 "了" 字进行处理
        # 如果 "了" 后面紧跟内容（非标点），通常表示动作完成，可以视情况加逗号
        # 但为了稳妥，我们只对句尾的 "了" 或明显语气停顿做处理
        # 这里选择：不在句中 "了" 后强制加逗号，以免破坏语流
        # 原代码的逻辑太激进，这里我们弱化它，只处理明显的独立分句
        
        # 恢复被保护的内容
        text = text.replace("了__P__", "了") # 恢复 "了一个"
        
        # ============ 第三步：处理句尾标点 ============
        if text[-1] not in ["，", "。", "！", "？", "；", "：", ".", "!", "?", ";", ":"]:
            # 疑问句判断
            if "吗" in text or "呢" in text or "什么" in text or "怎么" in text or "为什么" in text:
                text += "？"
            # 感叹句判断
            elif any(word in text[-2:] for word in ["啊", "呀", "哇", "哦"]):
                text += "！"
            # 陈述句
            else:
                text += "。"
        
        # ============ 第四步：清理和优化 ============
        # 清理重复标点
        text = re.sub(r'，+', '，', text)
        text = re.sub(r'。+', '。', text)
        
        # 清理可能出现的 "你好，，" 这种情况
        text = text.replace("，，", "，")
        
        return text

    def process_recorded_audio(self):
        """处理录制的音频并进行语音识别"""
        self.state = "PROCESSING"
        try:
            print("📝 正在识别...")
            
            audio_data = np.concatenate(self.recorded_audio, axis=0).flatten().astype(np.float32)
            
            stream = self.asr.create_stream()
            stream.accept_waveform(SAMPLE_RATE, audio_data)
            
            self.asr.decode_stream(stream)
            
            result = stream.result
            text = result.text.strip() if hasattr(result, 'text') else str(result).strip()
            
            if text:
                text_with_punctuation = self.add_punctuation(text)
                print(f"→ 您说: {text_with_punctuation}")
                
                # 合成并播放用户的语音内容
                try:
                    print("🔊 正在复述...")
                    self.play_audio(text_with_punctuation)
                except Exception as e:
                    print(f"[错误] 合成语音失败: {e}")
            else:
                print("→ 无法识别语音")
                
        except Exception as e:
            print(f"→ 识别出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.state = "IDLE"

    def run(self):
        """主运行循环"""
        self.is_running = True

        processor_thread = threading.Thread(target=self.process_audio, daemon=True)
        processor_thread.start()

        try:
            # ✅ 使用实例变量 self.mic_device_id
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.float32,
                device=self.mic_device_id,
                callback=self.audio_callback,
                blocksize=480,
            ):
                print("[状态] 麦克风已启动，开始检测...")
                processor_thread.join()

        except KeyboardInterrupt:
            print("\n[停止] 正在关闭...")
            self.is_running = False
        except Exception as e:
            print(f"[错误] {e}")
            import traceback
            traceback.print_exc()
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
            print(f"[{i:2d}] {dev['name']}")
    print("-" * 50)


if __name__ == "__main__":
    try:
        import sherpa_onnx
        import sounddevice
    except ImportError as e:
        print("缺少依赖，请安装:")
        print("pip install sherpa-onnx sounddevice numpy")
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--list-devices":
        list_audio_devices()
        sys.exit(0)

    try:
        detector = WakeTalkDetector()
        detector.run()
    except Exception as e:
        print(f"[严重错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
