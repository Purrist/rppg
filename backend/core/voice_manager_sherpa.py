# -*- coding: utf-8 -*-
"""
语音管理器 - 使用 sherpa-onnx 实现本地语音识别和唤醒词检测
基于 waketalk_v2.py 成功经验重构
"""

import os
import sys
import time
import threading
import queue
import random
import json
from typing import Optional, Callable
from pathlib import Path
from datetime import datetime

# sherpa-onnx
import sherpa_onnx
import numpy as np
import sounddevice as sd


class VoiceManager:
    """语音管理器 - 基于 sherpa-onnx 的本地语音识别"""
    
    # 音频参数
    SAMPLE_RATE = 16000
    CHANNELS = 1
    
    # VAD参数 - 适配老年人说话特点
    VAD_ENERGY_THRESHOLD = 0.01
    VAD_SILENCE_TIMEOUT = 2.5     # 从1.5s延长到2.5s，老年人说话停顿更长
    VAD_MIN_SPEECH_DURATION = 0.5 # 从0.3s延长到0.5s，避免误检
    VAD_MAX_RECORD_DURATION = 15  # 从10s延长到15s，允许更长语音
    
    # 防抖窗口
    DEBOUNCE_TIME = 2.0  # 从1.5s延长到2.0s，更强的防抖
    
    # 全局冷却时间（无论什么状态，2秒内不接受新唤醒）
    COOLDOWN_TIME = 2.0
    
    # 唤醒词列表
    WAKE_WORDS = ['阿康', '你好阿康', '阿康你好']

    # 回应语列表 - 亲和、简短、多样化
    RESPONSES = [
        '来啦', '我在', '在呢', '听着呢',
        '在的', '您说', '来了', '我在呢', 
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
        # 语音合成器 (TTS) - 使用sherpa-onnx VITS 或 pytts
        self.tts_engine = None  # VITS引擎
        self.pytts_engine = None  # pytts引擎
        self.tts_engine_type = 'vits'  # 当前使用的引擎类型: 'vits' 或 'pytts'

        # TTS参数
        self.tts_sid = 0  # 音色ID
        self.tts_speed = 1.0  # 语速
        self.tts_volume = 1.0  # 音量
        
        # 音色配置
        self.voice_tones = []

        # 状态机
        self.state = "STANDBY"  # STANDBY / RESPONDING / LISTENING / PROCESSING
        self.last_wake_time = 0
        
        # 运行状态
        self.is_running = False
        self.is_recording = False
        self.is_playing = False
        
        # ⭐ 会话管理 - 用于强制打断
        self._session_id = 0  # 当前会话ID，每次唤醒增加
        self._current_session_id = 0  # 正在运行的会话ID
        self._session_lock = threading.Lock()
        
        # ⭐ 语音播报管理
        self._speaking_lock = threading.Lock()  # 确保同一时间只有一个播报任务
        self._current_speak_session = 0  # 当前播报会话ID
        
        # ⭐ KWS暂停控制
        self._kws_paused = False
        self._kws_lock = threading.Lock()
        
        # ⭐ 预合成音频缓存
        self._prevoice_cache = {}
        self._prevoice_loaded = False
        self._prevoice_dir = Path(__file__).parent / "prevoice"
        
        # 音频队列和录音数据
        self.audio_queue = queue.Queue()
        self.recorded_audio = []
        
        # VAD状态
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        
        # 回调函数
        self.on_wake_word: Optional[Callable] = None
        self.on_speech_recognized: Optional[Callable] = None
        
        # 麦克风设备
        self.mic_device_id = None

        # 初始化
        self._load_voice_tones()
        self._init_models()
        self._init_tts()
        
    def _init_models(self):
        """初始化语音识别和唤醒词模型"""
        # 确保模型目录存在
        if not self.models_dir.exists():
            print(f"[VoiceManager] 模型目录不存在: {self.models_dir}")
            return

        # 初始化语音识别 (Paraformer)
        self._init_asr()

        # 初始化唤醒词检测 (KWS)
        self._init_kws()
        
        # 检测麦克风
        self._detect_microphone()
        
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
                # 尝试直接在models目录下查找
                model_files = list(self.models_dir.glob("**/model.int8.onnx"))
                if model_files:
                    model_dir = model_files[0].parent
                else:
                    return

            # 查找模型文件（优先使用int8版本，兼容性更好）
            model_files = list(model_dir.glob("model.int8.onnx"))
            if not model_files:
                model_files = list(model_dir.glob("model.onnx"))

            token_files = list(model_dir.glob("tokens.txt"))

            if not model_files or not token_files:
                return

            model_path = str(model_files[0])
            tokens_path = str(token_files[0])

            # 创建识别器
            self.asr_recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                paraformer=str(model_path),
                tokens=str(tokens_path),
                num_threads=2,
                sample_rate=self.SAMPLE_RATE,
                feature_dim=80,
                decoding_method="greedy_search",
                debug=False,
            )
            print("[VoiceManager] 语音识别模型加载完成")

        except Exception as e:
            print(f"[VoiceManager] 语音识别模型加载失败: {e}")
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
                # 尝试直接在models目录下查找
                encoder_files = list(self.models_dir.glob("**/encoder-epoch-12-avg-2-chunk-16-left-64.onnx"))
                if encoder_files:
                    model_dir = encoder_files[0].parent
                else:
                    return

            # KWS模型需要encoder、decoder、joiner三个文件
            encoder_files = [f for f in model_dir.glob("encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx")]
            decoder_files = [f for f in model_dir.glob("decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx")]
            joiner_files = [f for f in model_dir.glob("joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx")]
            token_files = list(model_dir.glob("tokens.txt"))

            if not encoder_files or not decoder_files or not joiner_files or not token_files:
                return

            encoder_path = str(encoder_files[0])
            decoder_path = str(decoder_files[0])
            joiner_path = str(joiner_files[0])
            tokens_path = str(token_files[0])

            # 使用关键词文件
            keywords_file = str(model_dir / "keywords.txt")
            if not os.path.exists(keywords_file):
                # 如果关键词文件不存在，创建一个
                # 注意：移除了单独的"kāng"，避免"阿康阿康"被检测两次
                with open(keywords_file, 'w', encoding='utf-8') as f:
                    f.write("ā k āng\nā k āng ā k āng\nn ǐ h ǎo ā k āng\nā k āng n ǐ hǎo")

            # 创建唤醒词识别器
            self.kws_recognizer = sherpa_onnx.KeywordSpotter(
                tokens=tokens_path,
                encoder=encoder_path,
                decoder=decoder_path,
                joiner=joiner_path,
                keywords_file=keywords_file,
                num_threads=2,
                keywords_score=0.7,
                keywords_threshold=0.2,
                provider='cpu',
            )
            print("[VoiceManager] 唤醒词模型加载完成")

        except Exception as e:
            print(f"[VoiceManager] 唤醒词模型加载失败: {e}")
            self.kws_recognizer = None

    def _load_voice_tones(self):
        """加载音色配置文件"""
        try:
            tones_file = Path(__file__).parent / "voice_tones.json"
            if tones_file.exists():
                with open(tones_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.voice_tones = data.get('tones', [])
                print(f"[VoiceManager] 加载音色配置: {len(self.voice_tones)} 种音色")
            else:
                print(f"[VoiceManager] 音色配置文件不存在: {tones_file}")
        except Exception as e:
            print(f"[VoiceManager] 加载音色配置失败: {e}")
            self.voice_tones = []

    def _init_tts(self):
        """初始化语音合成引擎 (sherpa-onnx VITS 和 pytts)"""
        # 1. 初始化 VITS 引擎
        try:
            # 尝试多个可能的模型目录名
            possible_dirs = [
                self.models_dir / "vits-zh-hf-fanchen-C",
                self.models_dir / "vits-zh"
            ]

            tts_model_dir = None
            for d in possible_dirs:
                if d.exists():
                    tts_model_dir = d
                    break

            if not tts_model_dir:
                # 尝试直接在models目录下查找
                model_files = list(self.models_dir.glob("**/vits-zh-hf-fanchen-C.onnx"))
                if model_files:
                    tts_model_dir = model_files[0].parent
                else:
                    print("[VoiceManager] VITS模型文件不存在")
                    return

            # 查找TTS模型文件
            model_files = list(tts_model_dir.glob("*.onnx"))
            token_files = list(tts_model_dir.glob("tokens.txt"))
            lexicon_files = list(tts_model_dir.glob("lexicon.txt"))

            if not model_files or not token_files:
                print("[VoiceManager] VITS模型文件不完整")
                return

            model_path = str(model_files[0])
            tokens_path = str(token_files[0])
            lexicon_path = str(lexicon_files[0]) if lexicon_files else None

            # 创建TTS配置
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
            
            # 初始化TTS引擎
            self.tts_engine = sherpa_onnx.OfflineTts(tts_config)
            print("[VoiceManager] VITS语音合成引擎加载完成")
        except Exception as e:
            print(f"[VoiceManager] VITS语音合成引擎加载失败: {e}")
            import traceback
            traceback.print_exc()
            self.tts_engine = None
        
        # 2. 初始化 pytts 引擎作为备选
        try:
            import pyttsx3
            self.pytts_engine = pyttsx3.init()
            # 设置默认语速
            self.pytts_engine.setProperty('rate', 150)
            # 设置默认音量
            self.pytts_engine.setProperty('volume', 1.0)
            print("[VoiceManager] pytts语音合成引擎加载完成")
        except Exception as e:
            print(f"[VoiceManager] pytts语音合成引擎加载失败: {e}")
            self.pytts_engine = None

        # ⭐ 加载预合成音频缓存
        self._load_prevoice_cache()

    def _load_prevoice_cache(self):
        """加载预合成的回应语音频缓存"""
        if not self._prevoice_dir.exists():
            print("[VoiceManager] 预合成音频目录不存在")
            return
        
        index_file = self._prevoice_dir / "index.json"
        if not index_file.exists():
            print("[VoiceManager] 预合成音频索引文件不存在")
            return
        
        try:
            import json
            import soundfile as sf
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            responses = index_data.get('responses', [])
            print(f"[VoiceManager] 开始加载 {len(responses)} 个预合成音频")
            
            for idx, response in enumerate(responses):
                audio_file = self._prevoice_dir / f"response_{idx}.wav"
                if audio_file.exists():
                    data, sr = sf.read(str(audio_file), dtype='float32')
                    self._prevoice_cache[response] = {
                        'data': data,
                        'sample_rate': sr
                    }
                    print(f"[VoiceManager] 已缓存: {response}")
            
            self._prevoice_loaded = True
            print(f"[VoiceManager] 预合成音频缓存加载完成，共 {len(self._prevoice_cache)} 个")
        except Exception as e:
            print(f"[VoiceManager] 加载预合成音频失败: {e}")

    def _play_prevoice(self, response):
        """播放预合成的回应语音频（同步阻塞）"""
        if response not in self._prevoice_cache:
            return False
        
        try:
            import sounddevice as sd
            audio_data = self._prevoice_cache[response]
            sd.play(audio_data['data'], samplerate=audio_data['sample_rate'])
            sd.wait()
            return True
        except Exception as e:
            print(f"[VoiceManager] 播放预合成音频失败: {e}")
            return False

    def _detect_microphone(self):
        """自动检测 Realtek 麦克风"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            
            # 1. 首先尝试找 Realtek 麦克风
            for i, dev in enumerate(devices):
                if 'Realtek' in dev['name'] and dev['max_input_channels'] > 0:
                    self.mic_device_id = i
                    print(f"[VoiceManager] 找到 Realtek 麦克风: {dev['name']} (设备ID: {i})")
                    return
            
            # 2. 如果没找到，使用默认输入设备
            try:
                default_input = sd.default.device[0]
                if default_input >= 0:
                    self.mic_device_id = default_input
                    default_device = sd.query_devices(default_input)
                    print(f"[VoiceManager] 使用默认麦克风: {default_device['name']} (设备ID: {default_input})")
                    return
            except Exception as e:
                print(f"[VoiceManager] 获取默认设备失败: {e}")
            
            # 3. 如果还是没有，找第一个可用的输入设备
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    self.mic_device_id = i
                    print(f"[VoiceManager] 使用第一个可用麦克风: {dev['name']} (设备ID: {i})")
                    return
            
            print("[VoiceManager] 警告: 未找到任何可用的麦克风设备！")
            
        except Exception as e:
            print(f"[VoiceManager] 检测麦克风失败: {e}")

    def start_listening(self):
        """开始监听"""
        if self.is_running:
            return
        
        self.is_running = True
        self.state = "STANDBY"
        
        # 通知前端
        self.socketio.emit('voice_status', {
            'status': 'standby',
            'message': '等待唤醒...'
        })
        
        # 启动处理线程
        threading.Thread(target=self._process_audio, daemon=True).start()
        
        # 启动音频流
        threading.Thread(target=self._audio_stream, daemon=True).start()
        
        print("[VoiceManager] 开始监听，状态: STANDBY")
    
    def stop_listening(self):
        """停止监听"""
        self.is_running = False
        self.is_recording = False
        print("[VoiceManager] 停止监听")
        
        self.socketio.emit('voice_status', {
            'status': 'stopped',
            'message': '已停止'
        })
    
    def _audio_stream(self):
        """音频流采集线程"""
        import sounddevice as sd
        
        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=np.float32,
                device=self.mic_device_id,
                callback=self._audio_callback,
                blocksize=480,
            ):
                print("[VoiceManager] 麦克风已启动")
                while self.is_running:
                    time.sleep(0.1)
        except Exception as e:
            print(f"[VoiceManager] 音频流错误: {e}")
    
    def _audio_callback(self, indata, frames, time_info, status):
        """麦克风录音回调 - 修复竞态条件"""
        if status:
            print(f"[VoiceManager] 音频状态警告: {status}")
        
        # ⭐ 优先检查 _kws_paused（线程安全标记）
        # 不再依赖 is_playing（它在线程中异步设置，有竞态）
        kws_should_skip = False
        with self._kws_lock:
            kws_should_skip = self._kws_paused
        
        if not kws_should_skip:
            # 只在非暂停时放入KWS队列
            self.audio_queue.put(indata.copy())
        
        # 录音数据始终保存（录音状态由 is_recording 控制）
        if self.is_recording:
            self.recorded_audio.append(indata.copy())
            self._process_vad(indata)
    
    def _pause_kws(self):
        """暂停KWS检测（播放前调用）"""
        with self._kws_lock:
            self._kws_paused = True
        # ⭐ 清空队列中的残留音频
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        print("[VoiceManager] KWS 已暂停，队列已清空")
    
    def _resume_kws(self):
        """恢复KWS检测（播放结束后延迟调用）"""
        import traceback
        with self._kws_lock:
            self._kws_paused = False
        # ⭐ 添加调用堆栈追踪
        stack = traceback.extract_stack()
        caller = stack[-2] if len(stack) > 1 else "unknown"
        print(f"[VoiceManager] KWS 已恢复 (调用者: {caller.filename}:{caller.lineno} {caller.name})")
    
    def _process_vad(self, audio_chunk):
        """语音端点检测处理"""
        rms = np.sqrt(np.mean(audio_chunk ** 2))
        current_time = datetime.now()
        
        if rms > self.VAD_ENERGY_THRESHOLD:
            if not self.vad_is_speaking:
                self.vad_is_speaking = True
                self.vad_speech_start_time = current_time
                print("[VoiceManager] 检测到语音输入...")
            self.vad_silence_start_time = None
        else:
            if self.vad_is_speaking:
                if self.vad_silence_start_time is None:
                    self.vad_silence_start_time = current_time
                else:
                    silence_duration = (current_time - self.vad_silence_start_time).total_seconds()
                    if silence_duration >= self.VAD_SILENCE_TIMEOUT:
                        print(f"[VoiceManager] 检测到语音结束（静音 {silence_duration:.1f} 秒）")
                        self.is_recording = False
    
    def _process_audio(self):
        """音频处理线程 - 唤醒词检测"""
        if not self.kws_recognizer:
            print("[VoiceManager] 唤醒词识别器未初始化")
            return
        
        stream = self.kws_recognizer.create_stream()
        
        while self.is_running:
            try:
                audio_chunk = self.audio_queue.get(timeout=0.1)
                samples = audio_chunk.flatten().astype(np.float32)
                stream.accept_waveform(self.SAMPLE_RATE, samples)

                while self.kws_recognizer.is_ready(stream):
                    self.kws_recognizer.decode_stream(stream)

                result = self.kws_recognizer.get_result(stream)
                if isinstance(result, str):
                    if result.strip():
                        self._on_keyword_detected(result)
                        self.kws_recognizer.reset_stream(stream)
                        stream = self.kws_recognizer.create_stream()
                elif hasattr(result, 'keyword'):
                    if result.keyword:
                        self._on_keyword_detected(result.keyword)
                        self.kws_recognizer.reset_stream(stream)
                        stream = self.kws_recognizer.create_stream()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[VoiceManager] 处理音频时出错: {e}")
    
    def _on_keyword_detected(self, keyword):
        """检测到关键词时的回调 - 修复重复唤醒"""
        print(f"[VoiceManager] 检测到唤醒词: {keyword}")
        current_time = time.time()
        time_since_last_wake = current_time - self.last_wake_time
        
        # ⭐ 全局冷却：无论什么状态，2秒内不重复触发
        if time_since_last_wake < self.COOLDOWN_TIME:
            print(f"[VoiceManager] 冷却中: 忽略 ({time_since_last_wake:.2f}s < {self.COOLDOWN_TIME}s)")
            return
        
        # ⭐ 如果当前不在待机状态，不允许唤醒（除非超过5秒强制打断）
        if self.state != "STANDBY":
            if time_since_last_wake < 5.0:
                print(f"[VoiceManager] 非待机状态，忽略唤醒 (当前: {self.state})")
                return
            # 超过5秒的卡死会话，强制打断
            print(f"[VoiceManager] ⭐ 强制打断卡死会话: 当前状态 {self.state}")
            with self._session_lock:
                self._session_id += 1
                new_session_id = self._session_id
            self.is_recording = False
            self.is_playing = False
            self.recorded_audio = []
            self.vad_is_speaking = False
            self.vad_silence_start_time = None
            self.vad_speech_start_time = None
            self._pause_kws()
            time.sleep(0.1)
            self._trigger_wake_up(new_session_id)
            self.last_wake_time = current_time
            return
        
        # 正常唤醒
        self._trigger_wake_up()
        self.last_wake_time = current_time
    
    def _trigger_wake_up(self, session_id=None, skip_response=False):
        """触发唤醒
        
        Args:
            session_id: 会话ID
            skip_response: 是否跳过回应语播放（用于点击语音按钮时）
        """
        # 如果没有提供session_id，生成一个新的
        if session_id is None:
            with self._session_lock:
                self._session_id += 1
                session_id = self._session_id
        
        # 随机选择回应语（如果需要）
        response = '' if skip_response else random.choice(self.RESPONSES)
        
        # 启动录音线程
        threading.Thread(
            target=self._start_recording_session, 
            args=(response, session_id), 
            daemon=True
        ).start()
    
    def start_voice_input(self):
        """开始语音输入（点击按钮触发，不播放回应语，直接进入listening）"""
        with self._session_lock:
            self._session_id += 1
            session_id = self._session_id
        
        # 停止当前播放和录音
        self.is_playing = False
        self.is_recording = False
        
        # 直接进入录音会话，跳过responding状态
        threading.Thread(
            target=self._start_direct_recording, 
            args=(session_id,), 
            daemon=True
        ).start()
    
    def _start_direct_recording(self, session_id):
        """直接开始录音（点击语音按钮触发）"""
        # 记录当前会话ID
        with self._session_lock:
            self._current_session_id = session_id
        
        # ⭐ 检查会话是否仍然有效（可能被新的唤醒打断）
        def is_session_valid():
            with self._session_lock:
                return self._current_session_id == session_id
        
        print(f"[VoiceManager] [会话{session_id}] 状态: 直接进入 LISTENING")
        
        # 进入聆听状态
        self._set_state("LISTENING")
        self.is_recording = True
        self.recorded_audio = []
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        
        # 通知前端
        self.socketio.emit('voice_status', {
            'status': 'listening',
            'message': '正在听...',
            'state': 'LISTENING',
            'session_id': session_id
        })
        
        # 录音循环
        start_time = time.time()
        while self.is_recording and self.is_running:
            # ⭐ 检查是否被打断
            if not is_session_valid():
                print(f"[VoiceManager] [会话{session_id}] 录音被打断，退出")
                self.is_recording = False
                return
            
            elapsed = time.time() - start_time
            if elapsed >= self.VAD_MAX_RECORD_DURATION:
                print(f"[VoiceManager] [会话{session_id}] 达到最大录制时长")
                self.is_recording = False
                break
            time.sleep(0.05)
        
        # 录音结束
        self.is_recording = False
        
        # ⭐ 检查是否被打断
        if not is_session_valid():
            print(f"[VoiceManager] [会话{session_id}] 录音结束后被打断，退出")
            return
        
        if len(self.recorded_audio) > 0:
            total_samples = sum(len(chunk) for chunk in self.recorded_audio)
            duration = total_samples / self.SAMPLE_RATE
            print(f"[VoiceManager] [会话{session_id}] 录制时长: {duration:.1f} 秒")
            
            if duration >= self.VAD_MIN_SPEECH_DURATION:
                self._process_recorded_audio(session_id)
            else:
                print(f"[VoiceManager] [会话{session_id}] 语音太短（{duration:.1f} 秒）")
                self._back_to_standby()
        else:
            print(f"[VoiceManager] [会话{session_id}] 未检测到语音输入")
            self._back_to_standby()
    
    def _start_recording_session(self, response, session_id):
        """开始录音会话"""
        # 记录当前会话ID
        with self._session_lock:
            self._current_session_id = session_id
        
        # ⭐ 检查会话是否仍然有效（可能被新的唤醒打断）
        def is_session_valid():
            with self._session_lock:
                return self._current_session_id == session_id
        
        if response:
            # ⭐ 1. 先暂停KWS，再播放（防止回声触发唤醒）
            self._pause_kws()
            
            self._set_state("RESPONDING")
            print(f"[VoiceManager] [会话{session_id}] 状态: RESPONDING -> {response}")
            
            # 通知前端
            self.socketio.emit('voice_wake_up', {
                'response': response,
                'user_text': '',
                'state': 'RESPONDING',
                'session_id': session_id
            })
            
            # ⭐ 2. 同步播放回应语（阻塞直到完成）
            self._speak_sync(response)
            
            # ⭐ 3. 检查打断
            if not is_session_valid():
                return
            
            # ⭐ 4. 只保留必要延迟（等音频设备释放）
            time.sleep(0.3)
            
            if not is_session_valid():
                return
        else:
            self._pause_kws()
        
        # ⭐ 5. 清空KWS队列（可能积累了播放期间的残留）
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        
        # ⭐ 6. 延迟恢复KWS（等待回声完全消失）
        threading.Timer(0.5, self._resume_kws).start()
        
        # 进入聆听状态
        self._set_state("LISTENING")
        self.is_recording = True
        self.recorded_audio = []
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        
        print(f"[VoiceManager] [会话{session_id}] 状态: LISTENING -> 开始录音")
        
        # 通知前端
        self.socketio.emit('voice_status', {
            'status': 'listening',
            'message': '正在听...',
            'state': 'LISTENING',
            'session_id': session_id
        })
        
        # 录音循环
        start_time = time.time()
        while self.is_recording and self.is_running:
            # ⭐ 检查是否被打断
            if not is_session_valid():
                print(f"[VoiceManager] [会话{session_id}] 录音被打断，退出")
                self.is_recording = False
                return
            
            elapsed = time.time() - start_time
            if elapsed >= self.VAD_MAX_RECORD_DURATION:
                print(f"[VoiceManager] [会话{session_id}] 达到最大录制时长")
                self.is_recording = False
                break
            time.sleep(0.05)
        
        # 录音结束
        self.is_recording = False
        
        # ⭐ 检查是否被打断
        if not is_session_valid():
            print(f"[VoiceManager] [会话{session_id}] 录音结束后被打断，退出")
            return
        
        if len(self.recorded_audio) > 0:
            total_samples = sum(len(chunk) for chunk in self.recorded_audio)
            duration = total_samples / self.SAMPLE_RATE
            print(f"[VoiceManager] [会话{session_id}] 录制时长: {duration:.1f} 秒")
            
            if duration >= self.VAD_MIN_SPEECH_DURATION:
                self._process_recorded_audio(session_id)
            else:
                print(f"[VoiceManager] [会话{session_id}] 语音太短（{duration:.1f} 秒）")
                self._back_to_standby()
        else:
            print(f"[VoiceManager] [会话{session_id}] 未检测到语音输入")
            self._back_to_standby()
    
    def _process_recorded_audio(self, session_id=None):
        """处理录制的音频并进行语音识别"""
        # 检查会话是否有效
        def is_session_valid():
            with self._session_lock:
                return self._current_session_id == session_id
        
        if not self.asr_recognizer:
            print(f"[VoiceManager] [会话{session_id}] 语音识别器未初始化")
            self._back_to_standby()
            return
        
        # ⭐ 检查是否被打断
        if session_id and not is_session_valid():
            print(f"[VoiceManager] [会话{session_id}] 进入PROCESSING前被打断，退出")
            return
        
        self._set_state("PROCESSING")
        print(f"[VoiceManager] [会话{session_id}] 状态: PROCESSING -> 识别中...")
        
        # 通知前端
        self.socketio.emit('voice_status', {
            'status': 'processing',
            'message': '正在识别...',
            'state': 'PROCESSING',
            'session_id': session_id
        })
        
        try:
            audio_data = np.concatenate(self.recorded_audio, axis=0).flatten().astype(np.float32)
            
            stream = self.asr_recognizer.create_stream()
            stream.accept_waveform(self.SAMPLE_RATE, audio_data)
            
            self.asr_recognizer.decode_stream(stream)
            
            result = stream.result
            text = result.text.strip() if hasattr(result, 'text') else str(result).strip()
            
            # ⭐ 检查是否被打断
            if session_id and not is_session_valid():
                print(f"[VoiceManager] [会话{session_id}] 识别完成后被打断，退出")
                return
            
            if text:
                print(f"[VoiceManager] [会话{session_id}] 用户说: {text}")
                
                # ⭐ 发送用户语音事件（只发送一次）
                self.socketio.emit('voice_user_speak', {
                    'text': text,
                    'state': 'PROCESSING',
                    'session_id': session_id
                })
                
                # ⭐ 直接处理语音命令（不再通过回调，避免重复）
                if self.system_core:
                    self._call_llm_and_respond(text, session_id)
                elif self.on_speech_recognized:
                    # 回退到旧的回调方式
                    self.on_speech_recognized(text)
                else:
                    self._back_to_standby()
            else:
                print(f"[VoiceManager] [会话{session_id}] 无法识别语音")
                self._back_to_standby()
                
        except Exception as e:
            print(f"[VoiceManager] [会话{session_id}] 识别出错: {e}")
            import traceback
            traceback.print_exc()
            self._back_to_standby()
    
    def _call_llm_and_respond(self, user_text, session_id=None):
        """调用LLM并回应 - 添加意图识别"""
        # 检查会话是否有效
        def is_session_valid():
            with self._session_lock:
                return self._current_session_id == session_id
        
        try:
            # ⭐ 检查是否被打断
            if session_id and not is_session_valid():
                print(f"[VoiceManager] [会话{session_id}] 调用LLM前被打断，退出")
                return
            
            # ⭐ 意图识别 - 优先处理天气和时间（直接播报，不经过AI）
            intent_result = self._recognize_intent(user_text)
            
            if intent_result['intent'] == 'emergency':
                # ⚡ 紧急呼救 - 直接跳转呼叫页面并播报
                print(f"[VoiceManager] [会话{session_id}] ⚡ 紧急呼救: {user_text}")
                # 跳转到呼叫页面（紧急模式）
                self.socketio.emit('navigate_to', {'page': '/call?emergency=true'})
                self.socketio.emit('voice_llm_response', {
                    'text': intent_result['response'],
                    'state': 'PROCESSING',
                    'session_id': session_id
                })
                self._speak(intent_result['response'])
                return  # ⚡ 直接返回，不调用LLM
                
            elif intent_result['intent'] == 'weather':
                # ⚡ 直接播报天气 - 不交给AI思考
                weather_text = intent_result['response']
                print(f"[VoiceManager] [会话{session_id}] ⚡ 天气查询（跳过AI）: {weather_text}")
                self.socketio.emit('voice_llm_response', {
                    'text': weather_text,
                    'state': 'PROCESSING',
                    'session_id': session_id
                })
                self._speak(weather_text)
                return  # ⚡ 直接返回，不调用LLM
                
            elif intent_result['intent'] == 'time':
                # ⚡ 直接播报时间 - 不交给AI思考
                time_text = intent_result['response']
                print(f"[VoiceManager] [会话{session_id}] ⚡ 时间查询（跳过AI）: {time_text}")
                self.socketio.emit('voice_llm_response', {
                    'text': time_text,
                    'state': 'PROCESSING',
                    'session_id': session_id
                })
                self._speak(time_text)
                return  # ⚡ 直接返回，不调用LLM
                
            elif intent_result['intent'] == 'navigate':
                # ⚡ 页面跳转 - 不交给AI思考
                page = intent_result['page']
                print(f"[VoiceManager] [会话{session_id}] ⚡ 页面跳转（跳过AI）: {page}")
                self.socketio.emit('navigate_to', {'page': page})
                self.socketio.emit('voice_llm_response', {
                    'text': intent_result['response'],
                    'state': 'PROCESSING',
                    'session_id': session_id
                })
                self._speak(intent_result['response'])
                return  # ⚡ 直接返回，不调用LLM
                
            elif intent_result['intent'] == 'call_contact':
                # ⚡ 打电话给特定联系人 - 直接跳转通话页面
                contact = intent_result['contact']
                print(f"[VoiceManager] [会话{session_id}] ⚡ 打电话给: {contact}")
                # 跳转到呼叫页面（指定联系人）
                self.socketio.emit('navigate_to', {'page': f'/call?contact={contact}'})
                self.socketio.emit('voice_llm_response', {
                    'text': intent_result['response'],
                    'state': 'PROCESSING',
                    'session_id': session_id
                })
                self._speak(intent_result['response'])
                return  # ⚡ 直接返回，不调用LLM
            
            # ⭐ 只有其他情况才交给LLM处理
            # 使用 ask_akon 函数调用LLM
            try:
                print(f"[VoiceManager] [会话{session_id}] ⭐ 调用LLM处理: {user_text}")
                from core.core_agent import ask_akon
                
                # 获取当前系统状态作为上下文
                system_state = self.system_core.get_state() if self.system_core else {}
                print(f"[VoiceManager] [会话{session_id}] 系统状态: {system_state}")
                
                # 调用LLM
                response, action = ask_akon(user_text, system_state)
                print(f"[VoiceManager] [会话{session_id}] LLM返回: response={response}, action={action}")
                
                if response:
                    # ⭐ 限制回答长度在20字以内，去除emoji和颜文字
                    response = self._clean_response(response)
                    print(f"[VoiceManager] [会话{session_id}] LLM回复: {response}")
                    
                    # ⭐ 检查是否被打断
                    if session_id and not is_session_valid():
                        print(f"[VoiceManager] [会话{session_id}] 获取LLM回复后被打断，退出")
                        return
                    
                    # 通知前端显示LLM回复（⭐ 不再让前端播放语音，由后端统一播放）
                    self.socketio.emit('voice_llm_response', {
                        'text': response,
                        'state': 'PROCESSING',
                        'session_id': session_id
                    })
                    
                    # ⭐ 后端统一播报（_speak内部已处理KWS暂停）
                    self._speak(response)
                else:
                    self._speak("抱歉，我没听明白")
            except Exception as llm_error:
                print(f"[VoiceManager] [会话{session_id}] LLM调用出错: {llm_error}")
                self._speak("抱歉，网络有点问题，请稍等")
                # 继续执行finally回到待机
                raise
        finally:
            # ⭐ 只有当前会话有效时才回到待机
            if not session_id or is_session_valid():
                # ⭐ 延迟回到待机，等播报完成
                time.sleep(1.0)
                self._back_to_standby()
            else:
                print(f"[VoiceManager] [会话{session_id}] 已被新会话取代，不回到待机")

    def _clean_response(self, text):
        """清理LLM回复 - 限制长度在20字以内，去除emoji和颜文字"""
        if not text:
            return ""
        
        # 去除emoji和特殊字符
        import re
        # 匹配emoji的正则表达式
        emoji_pattern = re.compile(
            "["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
            u"\U00002500-\U00002BEF"  # chinese char
            u"\U00002702-\U000027B0"
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            u"\U0001f926-\U0001f937"
            u"\U00010000-\U0010ffff"
            u"\u2640-\u2642"
            u"\u2600-\u2B55"
            u"\u200d"
            u"\u23cf"
            u"\u23e9"
            u"\u231a"
            u"\ufe0f"  # variation selectors-16
            u"\u3030"
            "]+",
            flags=re.UNICODE
        )
        
        # 去除颜文字（简单匹配）
        text = emoji_pattern.sub(r'', text)
        text = re.sub(r'[^\w\s，。！？、；：（）【】—…·]+', '', text)
        
        # 限制长度在20字以内
        text = text.strip()[:20]
        
        # 确保以完整句子结尾
        if len(text) > 0 and text[-1] not in ['，', '。', '！', '？']:
            text += '。'
        
        return text

    def _recognize_intent(self, text):
        """意图识别 - 支持紧急呼救、天气、时间查询和页面跳转"""
        text = text.lower().strip()
        
        # ⭐ 紧急呼救关键词（最高优先级）
        emergency_keywords = ['救命', '救救我', '救命啊', '不舒服', '好痛', '难受', '疼', '晕倒', '心脏病', '呼吸困难']
        if any(keyword in text for keyword in emergency_keywords):
            return {
                'intent': 'emergency',
                'response': '正在为您紧急呼救'
            }
        
        # ⭐ 天气查询关键词
        weather_keywords = ['天气', '气温', '温度', '晴', '雨', '雪', '云']
        if any(keyword in text for keyword in weather_keywords):
            return {
                'intent': 'weather',
                'response': self._fetch_weather()
            }
        
        # ⭐ 时间查询关键词（排除"不舒服"等情况）
        time_keywords = ['现在几点', '几点了', '几点钟', '现在时间', '当前时间', '几点了', '几点钟']
        if any(keyword in text for keyword in time_keywords):
            return {
                'intent': 'time',
                'response': self._get_current_time()
            }
        
        # ⭐ 页面跳转关键词（严格限制在三个页面）
        # 健康页面
        health_keywords = ['健康', '身体', '心率', '监测', '生理', '运动', '血压']
        if any(keyword in text for keyword in health_keywords):
            return {
                'intent': 'navigate',
                'page': '/health',
                'response': '好的，我带您查看健康数据'
            }
        
        # 娱乐页面
        entertainment_keywords = ['娱乐', '音乐', '视频', '电影', '放松']
        if any(keyword in text for keyword in entertainment_keywords):
            return {
                'intent': 'navigate',
                'page': '/entertainment',
                'response': '好的，我带您进入娱乐页面'
            }
        
        # 益智/学习页面
        learning_keywords = ['益智', '学习', '游戏', '训练', '任务', '挑战']
        if any(keyword in text for keyword in learning_keywords):
            return {
                'intent': 'navigate',
                'page': '/learning',
                'response': '好的，我带您进行益智训练'
            }
        
        # ⭐ 打电话给特定联系人
        # 支持：打电话给儿子、给女儿打电话、呼叫老伴等
        contact_names = ['儿子', '女儿', '老伴', '医生', '张三', '李四', '王五', '赵六']
        for name in contact_names:
            if f'打电话给{name}' in text or f'给{name}打电话' in text or f'呼叫{name}' in text:
                return {
                    'intent': 'call_contact',
                    'contact': name,
                    'response': f'好的，正在拨打{name}的电话'
                }
        
        # 呼叫/紧急页面
        call_keywords = ['呼叫', '打电话', '视频', '通话', '紧急', '求救', '呼救']
        if any(keyword in text for keyword in call_keywords):
            return {
                'intent': 'navigate',
                'page': '/call',
                'response': '好的，我带您进入呼叫页面'
            }
        
        # 默认：交给LLM处理
        return {
            'intent': 'llm',
            'response': None
        }

    def _fetch_weather(self):
        """获取天气信息 - 优先从system_core获取，失败则调用API"""
        # ⭐ 优先从system_core获取（与首页保持一致）
        if self.system_core:
            try:
                state = self.system_core.get_state()
                perception = state.get('perception', {})
                # 尝试从不同的位置获取天气数据
                weather_data = perception.get('weather') or state.get('weather')
                
                if weather_data:
                    city = weather_data.get('city', '')
                    temp = weather_data.get('temperature', '')
                    weather = weather_data.get('weather', '')
                    
                    if city and temp:
                        if weather:
                            return f"{city}今天{temp}度，{weather}"
                        else:
                            return f"{city}今天{temp}度"
            except Exception as e:
                print(f"[VoiceManager] 从system_core获取天气失败: {e}")
        
        # ⭐ 回退到直接调用API（与首页使用相同的API）
        try:
            import requests
            res = requests.get('https://uapis.cn/api/v1/misc/weather?lang=zh', timeout=5)
            data = res.json()
            
            if data.get('code') == 0 and data.get('data'):
                city = data['data']['city']
                temp = data['data']['temperature']
                weather = data['data']['weather']
                return f"{city}今天{temp}度，{weather}"
            elif data.get('city'):
                return f"{data['city']}今天{data['temperature']}度，{data['weather']}"
            else:
                return "暂时无法获取天气信息"
        except Exception as e:
            print(f"[VoiceManager] 获取天气失败: {e}")
            return "暂时无法获取天气信息"

    def _get_current_time(self):
        """获取当前时间"""
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        
        # 中文时间播报格式
        hour_text = str(hour)
        minute_text = str(minute) if minute > 0 else '整'
        
        if minute == 0:
            return f"现在是{hour_text}点整"
        elif minute < 10:
            return f"现在是{hour_text}点零{minute_text}分"
        else:
            return f"现在是{hour_text}点{minute_text}分"
    
    def _set_state(self, new_state):
        """设置状态并上报"""
        old_state = self.state
        self.state = new_state
        print(f"[VoiceManager] 状态变更: {old_state} -> {new_state}")
        
        # 上报到system_core
        if self.system_core:
            try:
                self.system_core.update_voice_state({
                    'state': new_state,
                    'isRecording': self.is_recording,
                    'isPlaying': self.is_playing,
                    'timestamp': time.time()
                })
            except Exception as e:
                print(f"[VoiceManager] 上报system_core失败: {e}")
        
        # 通知前端
        self.socketio.emit('voice_state_change', {
            'state': new_state,
            'isRecording': self.is_recording,
            'isPlaying': self.is_playing,
            'timestamp': time.time()
        })
    
    def _back_to_standby(self):
        """回到待机状态"""
        # ⭐ 确保KWS恢复
        self._resume_kws()
        self._set_state("STANDBY")
        print("[VoiceManager] 状态: STANDBY -> 等待唤醒...")
        
        # 通知前端
        self.socketio.emit('voice_status', {
            'status': 'standby',
            'message': '等待唤醒...',
            'state': 'STANDBY'
        })
    
    def _reset_listening(self):
        """打断录音，重新开始"""
        print("[VoiceManager] 打断: 重置录音")
        self.is_recording = False
        self.recorded_audio = []
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
    
    def _stop_processing(self):
        """打断处理，停止语音播报"""
        print("[VoiceManager] 打断: 停止处理")
        self.is_playing = False
        
        # 强制增加播报会话ID，中断当前播报
        with self._speaking_lock:
            self._current_speak_session += 1
        
        # 尝试停止音频流
        try:
            import sounddevice as sd
            if sd.get_stream().active:
                sd.stop()
        except:
            pass
    
    def _speak_sync(self, text):
        """同步语音合成并播放（阻塞直到完成）"""
        if not text:
            return
        
        # ⭐ 优先使用预合成音频（更快响应）
        if self._prevoice_loaded and text in self._prevoice_cache:
            self._pause_kws()
            self.is_playing = True
            try:
                self._play_prevoice(text)
                print(f"[VoiceManager] 使用预合成音频播放: {text}")
            except Exception as e:
                print(f"[VoiceManager] 播放预合成音频失败: {e}")
            finally:
                self.is_playing = False
                threading.Timer(0.5, self._resume_kws).start()
            return
        
        # ⭐ 回退到实时合成（改进版）
        self._pause_kws()
        self.is_playing = True
        
        try:
            if self.tts_engine_type == 'vits' and self.tts_engine:
                audio = self.tts_engine.generate(
                    text, sid=self.tts_sid, speed=max(1.2, self.tts_speed)
                )
                samples = np.array(audio.samples, dtype=np.float32) * self.tts_volume
                
                # ⭐ 计算预期播放时间
                expected_duration = len(samples) / audio.sample_rate
                timeout_duration = expected_duration + 3.0
                
                # ⭐ 带超时的播放
                try:
                    sd.play(samples, samplerate=audio.sample_rate)
                    start_time = time.time()
                    while sd.get_stream().active and time.time() - start_time < timeout_duration:
                        time.sleep(0.03)
                    if sd.get_stream().active:
                        sd.stop()
                        print(f"[VoiceManager] 同步播放超时")
                except Exception as play_e:
                    print(f"[VoiceManager] VITS同步播放错误: {play_e}")
                    # 重试
                    try:
                        if sd.get_stream().active:
                            sd.stop()
                        sd.play(samples, samplerate=audio.sample_rate)
                        sd.wait()
                    except:
                        pass
                        
            elif self.tts_engine_type == 'pytts' and self.pytts_engine:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', int(150 * self.tts_speed))
                engine.setProperty('volume', min(1.0, self.tts_volume))
                engine.say(text)
                engine.runAndWait()
                engine.stop()
            else:
                if self.tts_engine:
                    audio = self.tts_engine.generate(text, sid=self.tts_sid, speed=max(1.2, self.tts_speed))
                    samples = np.array(audio.samples, dtype=np.float32) * self.tts_volume
                    
                    # ⭐ 带超时的播放
                    expected_duration = len(samples) / audio.sample_rate
                    timeout_duration = expected_duration + 3.0
                    
                    try:
                        sd.play(samples, samplerate=audio.sample_rate)
                        start_time = time.time()
                        while sd.get_stream().active and time.time() - start_time < timeout_duration:
                            time.sleep(0.03)
                        if sd.get_stream().active:
                            sd.stop()
                    except Exception as play_e:
                        print(f"[VoiceManager] 回退播放错误: {play_e}")
                        try:
                            if sd.get_stream().active:
                                sd.stop()
                            sd.play(samples, samplerate=audio.sample_rate)
                            sd.wait()
                        except:
                            pass
        except Exception as e:
            print(f"[VoiceManager] 同步播报错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_playing = False
            # ⭐ 播报结束后延迟恢复KWS
            threading.Timer(0.5, self._resume_kws).start()
    
    def _speak(self, text):
        """语音合成并播放（非阻塞）- 支持VITS和pytts，播报期间暂停KWS"""
        if not text:
            return
        
        # 生成新的播报会话ID，自动打断之前的播报
        with self._speaking_lock:
            self._current_speak_session += 1
            current_session = self._current_speak_session
        
        print(f"[VoiceManager] 语音播报 ({self.tts_engine_type}): {text} [会话{current_session}]")
        
        # 在后台线程中播放，避免阻塞主线程
        def play_thread():
            # ⭐ 播报前暂停KWS
            self._pause_kws()
            self.is_playing = True
            
            try:
                # 检查是否被新的播报任务打断
                def is_speaking_session_valid():
                    with self._speaking_lock:
                        return self._current_speak_session == current_session
                
                if self.tts_engine_type == 'vits' and self.tts_engine:
                    # 使用VITS生成语音
                    audio = self.tts_engine.generate(
                        text, 
                        sid=self.tts_sid, 
                        speed=max(1.2, self.tts_speed)
                    )
                    
                    # 检查是否被打断
                    if not is_speaking_session_valid():
                        print(f"[VoiceManager] 播报被打断 [会话{current_session}]")
                        return
                    
                    # 转换为numpy数组并应用音量
                    samples = np.array(audio.samples, dtype=np.float32) * self.tts_volume
                    
                    # 检查是否被打断
                    if not is_speaking_session_valid():
                        print(f"[VoiceManager] 播报被打断 [会话{current_session}]")
                        return
                    
                    # ⭐ 播放音频（改进版）
                    try:
                        # 计算预期播放时间，设置合理超时
                        expected_duration = len(samples) / audio.sample_rate
                        timeout_duration = expected_duration + 5.0  # 额外5秒缓冲
                        
                        # 检查音频设备状态
                        try:
                            if not sd.query_devices(self.mic_device_id or sd.default.device[1]):
                                print(f"[VoiceManager] 音频输出设备不可用")
                                raise RuntimeError("音频输出设备不可用")
                        except:
                            pass
                        
                        # 使用sd.play播放，设置blocking=False以便检查中断
                        sd.play(samples, samplerate=audio.sample_rate, blocking=False)
                        
                        # ⭐ 改进的播放等待循环
                        start_time = time.time()
                        while True:
                            # 检查是否被打断
                            if not is_speaking_session_valid():
                                print(f"[VoiceManager] 播报被打断 [会话{current_session}]")
                                try:
                                    sd.stop()
                                except:
                                    pass
                                return
                            
                            # 检查是否播放完成
                            if not sd.get_stream().active:
                                break
                            
                            # 检查超时
                            elapsed = time.time() - start_time
                            if elapsed > timeout_duration:
                                print(f"[VoiceManager] 播放超时 ({elapsed:.1f}s > {timeout_duration:.1f}s)")
                                try:
                                    sd.stop()
                                except:
                                    pass
                                break
                            
                            time.sleep(0.03)  # 更频繁的检查
                            
                    except Exception as e:
                        print(f"[VoiceManager] VITS播放错误: {e}")
                        # ⭐ 尝试重新初始化音频设备
                        try:
                            import sounddevice as sd_new
                            # 尝试重启音频流
                            if sd_new.get_stream().active:
                                sd_new.stop()
                            # 重新播放
                            sd_new.play(samples, samplerate=audio.sample_rate)
                            sd_new.wait()
                        except Exception as retry_e:
                            print(f"[VoiceManager] 重试播放也失败: {retry_e}")
                
                elif self.tts_engine_type == 'pytts' and self.pytts_engine:
                    # 使用pytts生成语音
                    try:
                        # 每次重新初始化引擎，避免run loop already started错误
                        import pyttsx3
                        engine = pyttsx3.init()
                        
                        # 设置语速 (pytts默认是200，我们根据tts_speed调整)
                        rate = int(150 * self.tts_speed)
                        engine.setProperty('rate', rate)
                        
                        # 设置音量
                        engine.setProperty('volume', min(1.0, self.tts_volume))
                        
                        # 播放语音
                        engine.say(text)
                        
                        # 检查是否被打断
                        if not is_speaking_session_valid():
                            print(f"[VoiceManager] 播报被打断 [会话{current_session}]")
                            engine.stop()
                            return
                        
                        engine.runAndWait()
                        
                        # 释放引擎
                        engine.stop()
                        
                    except Exception as e:
                        print(f"[VoiceManager] pytts播放错误: {e}")
                        # 如果pytts失败，尝试使用VITS，但避免递归调用
                        if self.tts_engine and self.tts_engine_type != 'vits' and is_speaking_session_valid():
                            print("[VoiceManager] 尝试切换到VITS引擎")
                            # 直接使用VITS引擎，不通过_speak方法
                            actual_speed = max(1.2, self.tts_speed)
                            audio = self.tts_engine.generate(text, sid=self.tts_sid, speed=actual_speed)
                            samples = np.array(audio.samples, dtype=np.float32) * self.tts_volume
                            sd.play(samples, samplerate=audio.sample_rate)
                            sd.wait()
                
                else:
                    # 如果当前引擎不可用，尝试另一个
                    if self.tts_engine and is_speaking_session_valid():
                        print(f"[VoiceManager] 当前引擎 {self.tts_engine_type} 不可用，切换到VITS")
                        # 直接使用VITS引擎
                        actual_speed = max(1.2, self.tts_speed)
                        audio = self.tts_engine.generate(text, sid=self.tts_sid, speed=actual_speed)
                        samples = np.array(audio.samples, dtype=np.float32) * self.tts_volume
                        sd.play(samples, samplerate=audio.sample_rate)
                        sd.wait()
                    elif self.pytts_engine and is_speaking_session_valid():
                        print(f"[VoiceManager] 当前引擎 {self.tts_engine_type} 不可用，切换到pytts")
                        # 直接使用pytts引擎
                        import pyttsx3
                        engine = pyttsx3.init()
                        rate = int(150 * self.tts_speed)
                        engine.setProperty('rate', rate)
                        engine.setProperty('volume', min(1.0, self.tts_volume))
                        engine.say(text)
                        engine.runAndWait()
                        engine.stop()
                    else:
                        print("[VoiceManager] 没有可用的TTS引擎")
                        
            except Exception as e:
                print(f"[VoiceManager] 语音播放错误: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # 确保播放状态被重置
                self.is_playing = False
                # ⭐ 播报结束后延迟恢复KWS
                threading.Timer(0.5, self._resume_kws).start()
                print(f"[VoiceManager] 播报完成 [会话{current_session}]")
        
        # 启动播放线程
        threading.Thread(target=play_thread, daemon=True).start()
    
    def _speak_vits(self, text):
        """使用VITS引擎播报"""
        # 优化：使用更快的语速
        actual_speed = max(1.2, self.tts_speed)  # 确保最小语速为1.2
        
        # 使用VITS生成语音
        audio = self.tts_engine.generate(
            text, 
            sid=self.tts_sid, 
            speed=actual_speed
        )
        
        # 转换为numpy数组并应用音量
        samples = np.array(audio.samples, dtype=np.float32) * self.tts_volume
        
        # 播放音频
        try:
            sd.play(samples, samplerate=audio.sample_rate)
            # 设置超时，避免音频设备问题导致无限等待
            start_time = time.time()
            while sd.get_stream().active and time.time() - start_time < 10:
                time.sleep(0.05)
            # 确保流被停止
            if sd.get_stream().active:
                sd.stop()
        except Exception as e:
            print(f"[VoiceManager] VITS播放错误: {e}")
            # 确保流被停止
            try:
                if sd.get_stream().active:
                    sd.stop()
            except:
                pass
    
    def _speak_pytts(self, text):
        """使用pytts引擎播报 - 在主线程中执行避免run loop错误"""
        try:
            # 每次重新初始化引擎，避免run loop already started错误
            import pyttsx3
            engine = pyttsx3.init()
            
            # 设置语速 (pytts默认是200，我们根据tts_speed调整)
            rate = int(150 * self.tts_speed)
            engine.setProperty('rate', rate)
            
            # 设置音量
            engine.setProperty('volume', min(1.0, self.tts_volume))
            
            # 播放语音
            engine.say(text)
            engine.runAndWait()
            
            # 释放引擎
            engine.stop()
            
        except Exception as e:
            print(f"[VoiceManager] pytts播放错误: {e}")
            # 如果pytts失败，尝试使用VITS，但避免递归调用
            if self.tts_engine and self.tts_engine_type != 'vits':
                print("[VoiceManager] 尝试切换到VITS引擎")
                # 直接使用VITS引擎，不通过_speak方法
                actual_speed = max(1.2, self.tts_speed)
                audio = self.tts_engine.generate(text, sid=self.tts_sid, speed=actual_speed)
                samples = np.array(audio.samples, dtype=np.float32) * self.tts_volume
                sd.play(samples, samplerate=audio.sample_rate)
                sd.wait()
    
    def set_wake_word_callback(self, callback: Callable):
        """设置唤醒词回调"""
        self.on_wake_word = callback
    
    def set_speech_recognized_callback(self, callback: Callable):
        """设置语音识别回调"""
        self.on_speech_recognized = callback

    def set_tts_sid(self, sid):
        """设置TTS音色ID"""
        try:
            self.tts_sid = int(sid)
            print(f"[VoiceManager] 设置TTS音色ID: {self.tts_sid}")
            # 同步到system_core
            if self.system_core:
                try:
                    self.system_core.update_tts_config({
                        'sid': self.tts_sid,
                        'speed': self.tts_speed,
                        'volume': self.tts_volume
                    })
                except Exception as e:
                    print(f"[VoiceManager] 同步TTS配置到system_core失败: {e}")
            return True
        except Exception as e:
            print(f"[VoiceManager] 设置TTS音色失败: {e}")
            return False

    def set_tts_speed(self, speed):
        """设置TTS语速"""
        try:
            self.tts_speed = float(speed)
            print(f"[VoiceManager] 设置TTS语速: {self.tts_speed}")
            # 同步到system_core
            if self.system_core:
                try:
                    self.system_core.update_tts_config({
                        'sid': self.tts_sid,
                        'speed': self.tts_speed,
                        'volume': self.tts_volume
                    })
                except Exception as e:
                    print(f"[VoiceManager] 同步TTS配置到system_core失败: {e}")
            return True
        except Exception as e:
            print(f"[VoiceManager] 设置TTS语速失败: {e}")
            return False

    def set_tts_volume(self, volume):
        """设置TTS音量"""
        try:
            self.tts_volume = float(volume)
            print(f"[VoiceManager] 设置TTS音量: {self.tts_volume}")
            # 同步到system_core
            if self.system_core:
                try:
                    self.system_core.update_tts_config({
                        'sid': self.tts_sid,
                        'speed': self.tts_speed,
                        'volume': self.tts_volume
                    })
                except Exception as e:
                    print(f"[VoiceManager] 同步TTS配置到system_core失败: {e}")
            return True
        except Exception as e:
            print(f"[VoiceManager] 设置TTS音量失败: {e}")
            return False

    def get_tts_config(self):
        """获取当前TTS配置"""
        return {
            'engine': self.tts_engine_type,
            'sid': self.tts_sid,
            'speed': self.tts_speed,
            'volume': self.tts_volume,
            'voice_tones': self.voice_tones
        }
    
    def set_tts_engine(self, engine):
        """设置TTS引擎: 'vits' 或 'pytts'"""
        try:
            if engine not in ['vits', 'pytts']:
                print(f"[VoiceManager] 无效的TTS引擎: {engine}")
                return False
            
            # 检查引擎是否可用
            if engine == 'vits' and not self.tts_engine:
                print(f"[VoiceManager] VITS引擎不可用")
                return False
            if engine == 'pytts' and not self.pytts_engine:
                print(f"[VoiceManager] pytts引擎不可用")
                return False
            
            old_engine = self.tts_engine_type
            self.tts_engine_type = engine
            print(f"[VoiceManager] TTS引擎切换: {old_engine} -> {engine}")
            
            # 同步到system_core
            if self.system_core:
                try:
                    self.system_core.update_tts_config({
                        'engine': self.tts_engine_type,
                        'sid': self.tts_sid,
                        'speed': self.tts_speed,
                        'volume': self.tts_volume
                    })
                except Exception as e:
                    print(f"[VoiceManager] 同步TTS配置到system_core失败: {e}")
            return True
        except Exception as e:
            print(f"[VoiceManager] 设置TTS引擎失败: {e}")
            return False


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
