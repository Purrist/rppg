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
    
    # VAD参数
    VAD_ENERGY_THRESHOLD = 0.01
    VAD_SILENCE_TIMEOUT = 1.5
    VAD_MIN_SPEECH_DURATION = 0.3
    VAD_MAX_RECORD_DURATION = 10
    
    # 防抖窗口
    DEBOUNCE_TIME = 1.5
    
    # 唤醒词列表
    WAKE_WORDS = ['阿康', '阿康阿康', 'akon', '你好阿康', '阿康你好', '小康', '小康小康']

    # 回应语列表 - 亲和、简短、多样化
    RESPONSES = [
        '来啦', '诶', '我在', '在呢', '听着呢',
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
        # 语音合成器 (TTS) - 使用sherpa-onnx VITS
        self.tts_engine = None

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
        """初始化语音合成引擎 (sherpa-onnx VITS)"""
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
            print(f"[VoiceManager] 语音合成引擎加载失败: {e}")
            import traceback
            traceback.print_exc()
            self.tts_engine = None

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
        """麦克风录音回调"""
        if status:
            print(f"[VoiceManager] 音频状态警告: {status}")
        
        # 如果正在播放语音，不保存录音数据，也不进行唤醒词检测
        if not self.is_playing:
            # 如果正在录制语音，保存音频数据并进行 VAD 检测
            if self.is_recording:
                self.recorded_audio.append(indata.copy())
                self._process_vad(indata)
            # 只有不在播放时才将音频放入队列进行唤醒词检测
            self.audio_queue.put(indata.copy())
    
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
        """检测到关键词时的回调"""
        print(f"[VoiceManager] 检测到唤醒词: {keyword}")
        
        current_time = time.time()
        time_since_last_wake = current_time - self.last_wake_time
        
        # ⭐ 连续唤醒词切分检测：间隔<0.8s只触发一次
        if time_since_last_wake < 0.8:
            print(f"[VoiceManager] 连续唤醒检测: 忽略间隔 {time_since_last_wake:.2f}s 的重复唤醒")
            return
        
        if self.state == "STANDBY":
            # 待机状态，直接触发唤醒
            self._trigger_wake_up()
            self.last_wake_time = current_time
            return
        
        # 在防抖窗口内，忽略快速连续唤醒
        if time_since_last_wake < self.DEBOUNCE_TIME:
            print(f"[VoiceManager] 防抖: 忽略快速连续唤醒")
            return
        
        # ⭐ 超过防抖窗口，强制打断当前会话
        print(f"[VoiceManager] ⭐ 强制打断: 当前状态 {self.state}")
        
        # 增加会话ID，标记当前会话为过期
        with self._session_lock:
            self._session_id += 1
            new_session_id = self._session_id
        
        # 立即停止录音和播放
        self.is_recording = False
        self.is_playing = False
        
        # 清空录音数据
        self.recorded_audio = []
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        self.vad_speech_start_time = None
        
        # 通知前端打断事件
        self.socketio.emit('voice_interrupted', {
            'previous_state': self.state,
            'message': '检测到新的唤醒，打断当前流程'
        })
        
        # 短暂延迟确保旧会话退出
        time.sleep(0.1)
        
        # 触发新的唤醒流程
        self._trigger_wake_up(new_session_id)
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
        
        # 如果有回应语，进入回应状态并播放
        if response:
            # 进入回应状态
            self._set_state("RESPONDING")
            print(f"[VoiceManager] [会话{session_id}] 状态: RESPONDING -> {response}")
            
            # 通知前端弹出对话框
            self.socketio.emit('voice_wake_up', {
                'response': response,
                'user_text': '',
                'state': 'RESPONDING',
                'session_id': session_id
            })
            
            # ⭐ 通知前端播放回应并等待完成
            speak_event = threading.Event()
            
            def speak_and_wait(text):
                """后端播放语音并等待完成"""
                if not text:
                    speak_event.set()
                    return
                
                print(f"[VoiceManager] [会话{session_id}] 后端播放: {text}")
                self.is_playing = True
                
                # 通知前端播放状态
                self.socketio.emit('voice_speaking', {
                    'status': 'start',
                    'text': text
                })
                
                # 后端实际播放语音
                def play_thread():
                    try:
                        # 调用_speak方法进行后端播放
                        self._speak(text)
                        # 等待播放完成
                        # 由于_speak是异步的，我们需要估算播放时间
                        play_time = max(0.5, len(text) * 0.1)
                        time.sleep(play_time)
                    except Exception as e:
                        print(f"[VoiceManager] 播放错误: {e}")
                    finally:
                        self.is_playing = False
                        speak_event.set()
                        self.socketio.emit('voice_speaking', {'status': 'end'})
                
                threading.Thread(target=play_thread, daemon=True).start()
            
            # 通知前端播放回应
            speak_and_wait(response)
            
            # ⭐ 等待语音播放完成（最多等待3秒）
            speak_event.wait(timeout=3.0)
            
            # ⭐ 检查是否被打断
            if not is_session_valid():
                print(f"[VoiceManager] [会话{session_id}] 已被打断，退出")
                return
            
            # ⭐ 额外延迟确保音频设备释放
            time.sleep(0.3)
            
            # ⭐ 再次检查是否被打断
            if not is_session_valid():
                print(f"[VoiceManager] [会话{session_id}] 延迟后被打断，退出")
                return
        else:
            # 没有回应语（点击按钮触发），直接进入聆听状态
            print(f"[VoiceManager] [会话{session_id}] 跳过回应语，直接进入聆听状态")
        
        # ⭐ 检查是否被打断
        if not is_session_valid():
            print(f"[VoiceManager] [会话{session_id}] 已被打断，退出")
            return
        
        # ⭐ 额外延迟确保音频设备释放和回声消除
        time.sleep(0.5)
        
        # ⭐ 再次检查是否被打断
        if not is_session_valid():
            print(f"[VoiceManager] [会话{session_id}] 延迟后被打断，退出")
            return
        
        # ⭐ 确保播放状态已完全结束
        self.is_playing = False
        
        # ⭐ 再等待一小段时间确保系统稳定
        time.sleep(0.2)
        
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
                
                # ⭐ 只通过回调让app.py处理LLM调用和语音播报
                # 不再在VoiceManager内部重复调用
                if self.on_speech_recognized:
                    # 当有回调时，由app.py处理，不再发送voice_user_speak事件
                    # 避免重复处理
                    self.on_speech_recognized(text)
                else:
                    # 如果没有回调，才在内部处理
                    # 通知前端显示用户语音（模拟用户发送消息）
                    self.socketio.emit('voice_user_speak', {
                        'text': text,
                        'state': 'PROCESSING',
                        'session_id': session_id
                    })
                    if self.system_core:
                        self._call_llm_and_respond(text, session_id)
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
        """调用LLM并回应"""
        # 检查会话是否有效
        def is_session_valid():
            with self._session_lock:
                return self._current_session_id == session_id
        
        try:
            # ⭐ 检查是否被打断
            if session_id and not is_session_valid():
                print(f"[VoiceManager] [会话{session_id}] 调用LLM前被打断，退出")
                return
            
            # 调用系统核心的LLM
            if hasattr(self.system_core, 'process_message'):
                response = self.system_core.process_message(user_text)
                
                if response:
                    print(f"[VoiceManager] [会话{session_id}] LLM回复: {response}")
                    
                    # ⭐ 检查是否被打断
                    if session_id and not is_session_valid():
                        print(f"[VoiceManager] [会话{session_id}] 获取LLM回复后被打断，退出")
                        return
                    
                    # 通知前端显示LLM回复
                    self.socketio.emit('voice_llm_response', {
                        'text': response,
                        'state': 'PROCESSING',
                        'session_id': session_id
                    })
                    
                    # 启用后端播报
                    self._speak(response)
            else:
                # 如果没有process_message方法，直接复述
                self._speak(f"您说: {user_text}")
                
        except Exception as e:
            print(f"[VoiceManager] [会话{session_id}] LLM调用出错: {e}")
            self._speak("抱歉，处理您的请求时出错了")
        finally:
            # ⭐ 只有当前会话有效时才回到待机
            if not session_id or is_session_valid():
                self._back_to_standby()
            else:
                print(f"[VoiceManager] [会话{session_id}] 已被新会话取代，不回到待机")
    
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
    
    def _speak(self, text):
        """语音合成并播放（非阻塞）- 后端使用VITS播报"""
        if not text or not self.tts_engine:
            return
        
        print(f"[VoiceManager] 语音播报: {text}")
        
        # 设置播放状态
        self.is_playing = True
        
        # 在后台线程中播放，避免阻塞
        def play_thread():
            try:
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
                sd.play(samples, samplerate=audio.sample_rate)
                sd.wait()
                
            except Exception as e:
                print(f"[VoiceManager] 语音播放错误: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.is_playing = False
        
        threading.Thread(target=play_thread, daemon=True).start()
    
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
            'sid': self.tts_sid,
            'speed': self.tts_speed,
            'volume': self.tts_volume,
            'voice_tones': self.voice_tones
        }


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
