# -*- coding: utf-8 -*-
"""
语音管理器 - 使用 sherpa-onnx 实现本地语音识别和唤醒词检测
"""

import os
import sys
import time
import threading
import queue
import tempfile
import random
from typing import Optional, Callable
from pathlib import Path

# sherpa-onnx
import sherpa_onnx
import numpy as np


class VoiceManager:
    """语音管理器 - 基于 sherpa-onnx 的本地语音识别"""
    
    # 唤醒词列表
    WAKE_WORDS = ['阿康', '阿康阿康', 'akon', '你好阿康', '阿康你好', '小康', '小康小康']

    # 回应语列表 - 亲和、简短、多样化
    RESPONSES = [
        '来啦', '诶', '我在', '有什么能帮您', '请说', '在呢', '听着呢',
        '您好呀', '在的', '您说', '我听着', '请讲', '在听呢',
        '来了来了', '在的您说', '我在听', '请吩咐', '到'
    ]
    
    def __init__(self, socketio, system_core):
        self.socketio = socketio
        self.system_core = system_core
        
        # 模型路径
        self.models_dir = Path(__file__).parent / "models"
        
        # 语音识别器
        self.asr_recognizer = None
        # 唤醒词识别器
        self.kws_recognizer = None
        # 语音合成器 (TTS)
        self.tts_recognizer = None

        # 备用唤醒方案 - Google Speech Recognition
        self.use_google_kws = False
        self.google_recognizer = None
        self.google_microphone = None

        # 状态
        self.is_listening = False
        self.is_speaking = False
        self.is_awakened = False
        self.awake_timer = None

        # 音频队列
        self.audio_queue = queue.Queue()

        # 回调函数
        self.on_wake_word: Optional[Callable] = None
        self.on_speech_recognized: Optional[Callable] = None

        # 初始化
        self._init_models()
        
    def _init_models(self):
        """初始化语音识别和唤醒词模型"""
        print("[VoiceManager] 正在初始化 sherpa-onnx 模型...")

        # 确保模型目录存在
        if not self.models_dir.exists():
            print(f"[VoiceManager] 模型目录不存在: {self.models_dir}")
            return

        # 初始化语音识别 (Paraformer)
        self._init_asr()

        # 初始化唤醒词检测 (KWS)
        self._init_kws()

        # 初始化语音合成 (TTS)
        self._init_tts()
        
    def _init_asr(self):
        """初始化语音识别模型"""
        try:
            # 尝试多个可能的模型目录名
            possible_dirs = [
                self.models_dir / "paraformer-zh",
                self.models_dir / "sherpa-onnx-paraformer-zh-2024-03-09"
            ]

            model_dir = None
            for d in possible_dirs:
                if d.exists():
                    model_dir = d
                    break

            if not model_dir:
                print(f"[VoiceManager] 警告：ASR 模型不存在，尝试从下载脚本创建的目录加载")
                # 尝试直接在models目录下查找
                model_files = list(self.models_dir.glob("**/model.int8.onnx"))
                if model_files:
                    model_dir = model_files[0].parent
                    print(f"[VoiceManager] 找到模型目录: {model_dir}")
                else:
                    print(f"[VoiceManager] 警告：ASR 模型不存在")
                    return

            # 查找模型文件（优先使用int8版本，兼容性更好）
            model_files = list(model_dir.glob("model.int8.onnx"))
            if not model_files:
                model_files = list(model_dir.glob("model.onnx"))

            token_files = list(model_dir.glob("tokens.txt"))

            if not model_files or not token_files:
                print(f"[VoiceManager] 警告：ASR 模型文件不完整")
                print(f"  模型文件: {model_files}")
                print(f"  词表文件: {token_files}")
                return

            model_path = str(model_files[0])
            tokens_path = str(token_files[0])

            print(f"[VoiceManager] 加载 ASR 模型: {Path(model_path).name}")
            print(f"  模型路径: {model_path}")
            print(f"  词表路径: {tokens_path}")

            # 创建识别器
            self.asr_recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                paraformer=str(model_path),
                tokens=str(tokens_path),
                num_threads=2,
                sample_rate=16000,
                feature_dim=80,
                decoding_method="greedy_search",
                debug=False,
            )

            print("[VoiceManager] ASR 模型加载完成")

        except Exception as e:
            print(f"[VoiceManager] ASR 模型加载失败: {e}")
            import traceback
            traceback.print_exc()
            self.asr_recognizer = None
    
    def _init_kws(self):
        """初始化唤醒词模型"""
        try:
            # 尝试多个可能的模型目录名
            possible_dirs = [
                self.models_dir / "kws",
                self.models_dir / "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
            ]

            model_dir = None
            for d in possible_dirs:
                if d.exists():
                    model_dir = d
                    break

            if not model_dir:
                print(f"[VoiceManager] 警告：KWS 模型不存在，尝试从下载脚本创建的目录加载")
                # 尝试直接在models目录下查找
                encoder_files = list(self.models_dir.glob("**/encoder-epoch-12-avg-2-chunk-16-left-64.onnx"))
                if encoder_files:
                    model_dir = encoder_files[0].parent
                    print(f"[VoiceManager] 找到模型目录: {model_dir}")
                else:
                    print(f"[VoiceManager] 警告：KWS 模型不存在")
                    self._init_google_kws()
                    return

            # KWS模型需要encoder、decoder、joiner三个文件
            # 使用非int8版本（兼容性更好）
            encoder_files = [f for f in model_dir.glob("encoder-epoch-12-avg-2-chunk-16-left-64.onnx")]
            decoder_files = [f for f in model_dir.glob("decoder-epoch-12-avg-2-chunk-16-left-64.onnx")]
            joiner_files = [f for f in model_dir.glob("joiner-epoch-12-avg-2-chunk-16-left-64.onnx")]
            token_files = list(model_dir.glob("tokens.txt"))

            if not encoder_files or not decoder_files or not joiner_files or not token_files:
                print(f"[VoiceManager] 警告：KWS 模型文件不完整")
                print(f"  encoder: {encoder_files}")
                print(f"  decoder: {decoder_files}")
                print(f"  joiner: {joiner_files}")
                print(f"  tokens: {token_files}")
                self._init_google_kws()
                return

            encoder_path = str(encoder_files[0])
            decoder_path = str(decoder_files[0])
            joiner_path = str(joiner_files[0])
            tokens_path = str(token_files[0])

            # 使用关键词文件
            keywords_file = str(model_dir / "keywords.txt")
            if not os.path.exists(keywords_file):
                # 如果关键词文件不存在，创建一个
                with open(keywords_file, 'w', encoding='utf-8') as f:
                    f.write("阿康 /1.0/\n阿康阿康 /1.0/\nakon /1.0/\n你好阿康 /1.0/\n阿康你好 /1.0/\n小康 /1.0/\n小康小康 /1.0/")
                print(f"[VoiceManager] 创建关键词文件: {keywords_file}")
            print(f"[VoiceManager] 使用关键词文件: {keywords_file}")

            print(f"[VoiceManager] 加载 KWS 模型")
            print(f"  encoder: {encoder_path}")
            print(f"  decoder: {decoder_path}")
            print(f"  joiner: {joiner_path}")
            print(f"  tokens: {tokens_path}")

            # 创建唤醒词识别器
            self.kws_recognizer = sherpa_onnx.KeywordSpotter(
                tokens=tokens_path,
                encoder=encoder_path,
                decoder=decoder_path,
                joiner=joiner_path,
                keywords_file=keywords_file,
                num_threads=2,
                sample_rate=16000,
                feature_dim=80,
                max_active_paths=4,
                keywords_score=1.0,
                keywords_threshold=0.25,
                num_trailing_blanks=1,
                provider='cpu',
            )

            print("[VoiceManager] KWS 模型加载完成")

        except Exception as e:
            print(f"[VoiceManager] KWS 模型加载失败: {e}")
            import traceback
            traceback.print_exc()
            print("[VoiceManager] 尝试使用Google Speech Recognition作为备用唤醒方案...")
            self._init_google_kws()

    def _init_google_kws(self):
        """初始化Google Speech Recognition作为备用唤醒方案"""
        try:
            import speech_recognition as sr
            self.google_recognizer = sr.Recognizer()
            self.google_microphone = sr.Microphone()
            self.use_google_kws = True
            print("[VoiceManager] Google Speech Recognition备用方案已启用")
        except ImportError:
            print("[VoiceManager] 警告: 未安装speech_recognition库，无法使用备用唤醒方案")
            print("[VoiceManager] 请运行: pip install SpeechRecognition")
            self.use_google_kws = False
        except Exception as e:
            print(f"[VoiceManager] Google KWS初始化失败: {e}")
            self.use_google_kws = False

    def _detect_wake_word_google(self) -> bool:
        """使用Google Speech Recognition检测唤醒词"""
        if not self.use_google_kws or not self.google_recognizer:
            return False

        try:
            with self.google_microphone as source:
                print("[VoiceManager] 等待唤醒词...")
                self.google_recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.google_recognizer.listen(source, phrase_time_limit=3)

            try:
                text = self.google_recognizer.recognize_google(audio, language="zh-CN")
                print(f"[VoiceManager] Google识别: {text}")

                # 检查是否包含唤醒词
                wake_words = ['阿康', '阿康阿康', 'akon', '你好阿康', '阿康你好', '小康', '小康小康']
                if any(word in text for word in wake_words):
                    print("[VoiceManager] ✅ 唤醒成功！")
                    return True
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"[VoiceManager] Google API错误: {e}")

        except Exception as e:
            print(f"[VoiceManager] Google KWS检测错误: {e}")

        return False

    def _init_tts(self):
        """初始化语音合成模型 (VITS)"""
        try:
            # 尝试多个可能的模型目录名
            possible_dirs = [
                self.models_dir / "vits-zh-hf-fanchen-C",
                self.models_dir / "vits-zh",
                self.models_dir / "tts"
            ]

            model_dir = None
            for d in possible_dirs:
                if d.exists():
                    model_dir = d
                    break

            if not model_dir:
                print(f"[VoiceManager] TTS: 使用 edge-tts")
                return

            # 查找模型文件
            model_files = list(model_dir.glob("*.onnx"))
            if not model_files:
                print(f"[VoiceManager] TTS: 使用 edge-tts")
                return

            model_path = str(model_files[0])

            # 创建TTS合成器
            self.tts_recognizer = {
                'model_path': model_path,
                'model_dir': model_dir
            }

            print("[VoiceManager] TTS 模型加载完成")

        except Exception as e:
            print(f"[VoiceManager] TTS: 使用 edge-tts")
            self.tts_recognizer = None

    def start_listening(self):
        """开始监听"""
        if self.is_listening:
            return
        
        self.is_listening = True
        print("[VoiceManager] 开始监听...")
        
        # 通知前端
        self.socketio.emit('voice_status', {
            'status': 'listening',
            'message': '正在监听...'
        })
        
        # 启动监听线程
        threading.Thread(target=self._listen_loop, daemon=True).start()
    
    def stop_listening(self):
        """停止监听"""
        self.is_listening = False
        print("[VoiceManager] 停止监听")
        
        self.socketio.emit('voice_status', {
            'status': 'idle',
            'message': '已停止'
        })
    
    def _listen_loop(self):
        """监听循环"""
        import sounddevice as sd
        
        sample_rate = 16000
        block_size = 1600  # 100ms 的音频
        
        print("[VoiceManager] 监听循环启动，等待唤醒词...")
        print(f"[VoiceManager] 唤醒词: {self.WAKE_WORDS}")
        
        # 音频缓冲区
        audio_buffer = []
        
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype=np.float32,
            blocksize=block_size
        ) as stream:
            print("[VoiceManager] 音频流已打开")
            
            while self.is_listening:
                try:
                    # 读取音频数据
                    audio_data, _ = stream.read(block_size)
                    audio_data = audio_data.flatten()
                    
                    # 添加到缓冲区
                    audio_buffer.extend(audio_data)
                    
                    # 每 2 秒处理一次
                    if len(audio_buffer) >= sample_rate * 2:
                        # 转换为 numpy 数组
                        audio_np = np.array(audio_buffer, dtype=np.float32)
                        audio_buffer = []
                        
                        # 检测唤醒词
                        if not self.is_awakened:
                            if self.kws_recognizer:
                                # 使用本地KWS模型
                                if self._detect_wake_word(audio_np):
                                    self._on_wake_up()
                            elif self.use_google_kws:
                                # 使用Google Speech Recognition作为备用
                                if self._detect_wake_word_google():
                                    self._on_wake_up()
                            else:
                                # KWS识别器未初始化，记录错误
                                print("[VoiceManager] 警告: 唤醒词识别器未初始化，无法检测唤醒词")
                        
                        # 识别语音（已唤醒状态）
                        elif self.is_awakened:
                            if self.asr_recognizer:
                                text = self._recognize_speech(audio_np)
                                if text:
                                    print(f"[VoiceManager] 识别到: '{text}'")
                                    self._on_user_speak(text)
                            else:
                                # ASR识别器未初始化，提示用户
                                print("[VoiceManager] 警告: 语音识别器未初始化，无法识别语音")
                                # 退出唤醒状态，避免持续无响应
                                self._on_awake_timeout()
                    
                except Exception as e:
                    print(f"[VoiceManager] 监听错误: {e}")
                    time.sleep(0.1)
    
    def _detect_wake_word(self, audio_data: np.ndarray) -> bool:
        """检测唤醒词"""
        if not self.kws_recognizer:
            return False

        try:
            # 创建流
            stream = self.kws_recognizer.create_stream()

            # 接受音频数据
            stream.accept_waveform(16000, audio_data)

            # 识别
            while self.kws_recognizer.is_ready(stream):
                self.kws_recognizer.decode_stream(stream)

            # 获取结果
            result = self.kws_recognizer.get_result(stream)

            if result:
                print(f"[VoiceManager] 唤醒词检测: {result}")
                # 检查是否包含唤醒词
                return any(word in result for word in self.WAKE_WORDS)

            return False

        except Exception as e:
            print(f"[VoiceManager] 唤醒词检测错误: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _recognize_speech(self, audio_data: np.ndarray) -> Optional[str]:
        """识别语音"""
        if not self.asr_recognizer:
            return None
        
        try:
            # 创建流
            stream = self.asr_recognizer.create_stream()
            
            # 接受音频数据
            stream.accept_waveform(16000, audio_data)
            
            # 识别
            self.asr_recognizer.decode_stream(stream)
            
            # 获取结果
            result = stream.result.text
            
            return result.strip() if result else None
            
        except Exception as e:
            print(f"[VoiceManager] 语音识别错误: {e}")
            return None
    
    def _on_wake_up(self):
        """唤醒回调"""
        self.is_awakened = True
        print("[VoiceManager] 唤醒成功！")
        
        # 随机选择回应语
        response = random.choice(self.RESPONSES)
        
        # 语音回应
        self.speak(response)
        
        # 通知前端
        self.socketio.emit('voice_wake_up', {
            'response': response,
            'user_text': ''
        })
        
        # 设置唤醒超时
        if self.awake_timer:
            self.awake_timer.cancel()
        self.awake_timer = threading.Timer(30.0, self._on_awake_timeout)
        self.awake_timer.start()
        
        # 触发回调
        if self.on_wake_word:
            self.on_wake_word('')
    
    def _on_user_speak(self, text: str):
        """用户说话回调"""
        print(f"[VoiceManager] 用户说: {text}")
        
        # 重置唤醒定时器
        if self.awake_timer:
            self.awake_timer.cancel()
        self.awake_timer = threading.Timer(30.0, self._on_awake_timeout)
        self.awake_timer.start()
        
        # 通知前端
        self.socketio.emit('voice_user_speak', {
            'text': text
        })
        
        # 触发回调
        if self.on_speech_recognized:
            self.on_speech_recognized(text)
    
    def _on_awake_timeout(self):
        """唤醒超时"""
        print("[VoiceManager] 唤醒超时，退出唤醒状态")
        self.is_awakened = False
        
        self.socketio.emit('voice_sleep', {
            'message': '已退出唤醒状态'
        })
    
    def speak(self, text: str):
        """语音合成"""
        if not text:
            return
        
        print(f"[VoiceManager] 语音播报: {text}")
        
        # 使用系统 TTS 或 edge-tts
        threading.Thread(
            target=self._do_speak,
            args=(text,),
            daemon=True
        ).start()
    
    def _do_speak(self, text: str):
        """执行语音合成 - 优先使用本地VITS模型，失败则使用edge-tts"""
        try:
            self.is_speaking = True

            self.socketio.emit('voice_speaking', {
                'status': 'start',
                'text': text
            })

            # 尝试使用本地VITS模型
            if self.tts_recognizer:
                try:
                    self._speak_with_vits(text)
                    return
                except Exception as e:
                    print(f"[VoiceManager] 本地TTS失败，回退到edge-tts: {e}")

            # 使用 edge-tts 作为备用
            self._speak_with_edge_tts(text)

        except Exception as e:
            print(f"[VoiceManager] 语音合成错误: {e}")
        finally:
            self.is_speaking = False
            self.socketio.emit('voice_speaking', {'status': 'end'})

    def _speak_with_vits(self, text: str):
        """使用本地VITS模型进行语音合成"""
        import sounddevice as sd

        model_path = self.tts_recognizer['model_path']
        model_dir = self.tts_recognizer['model_dir']

        print(f"[VoiceManager] 使用VITS合成: {text}")

        # 创建TTS实例
        tts = sherpa_onnx.OfflineTts(
            model=model_path,
            tokens=str(model_dir / "tokens.txt"),
            data_dir=str(model_dir / "espeak-ng-data"),
            num_threads=4,
        )

        # 生成音频
        audio = tts.generate(text, sid=0, speed=1.0)

        if audio.samples is None or len(audio.samples) == 0:
            raise RuntimeError("VITS生成音频失败")

        # 播放音频
        samples = np.array(audio.samples, dtype=np.float32)
        sd.play(samples, audio.sample_rate)
        sd.wait()

        print("[VoiceManager] VITS播放完成")

    def _speak_with_edge_tts(self, text: str):
        """使用edge-tts进行语音合成（备用方案）"""
        import asyncio
        import edge_tts
        import sounddevice as sd
        from pydub import AudioSegment

        print(f"[VoiceManager] 使用edge-tts合成: {text}")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tmp_path = tmp_file.name

        try:
            communicate = edge_tts.Communicate(
                text,
                "zh-CN-XiaoxiaoNeural",
                rate="+0%",
                volume="+0%"
            )
            asyncio.run(communicate.save(tmp_path))

            # 播放
            audio = AudioSegment.from_mp3(tmp_path)
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples = samples / (2**15)

            sd.play(samples, audio.frame_rate)
            sd.wait()

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    def set_wake_word_callback(self, callback: Callable):
        """设置唤醒词回调"""
        self.on_wake_word = callback
    
    def set_speech_recognized_callback(self, callback: Callable):
        """设置语音识别回调"""
        self.on_speech_recognized = callback


# 全局实例
_voice_manager = None

def init_voice_manager(socketio, system_core):
    """初始化语音管理器"""
    global _voice_manager
    _voice_manager = VoiceManager(socketio, system_core)
    return _voice_manager

def get_voice_manager():
    """获取语音管理器实例"""
    return _voice_manager
