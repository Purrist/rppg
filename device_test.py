#!/usr/bin/env python3
"""
设备测试程序 - 整合摄像头、麦克风、唤醒词检测、语音识别和TTS
使用Realtek麦克风，系统扬声器，5000端口
"""
import cv2
import threading
import queue
import time
import os
import sys
from pathlib import Path
from datetime import datetime
from flask import Flask, Response, render_template_string, request

import numpy as np
import sherpa_onnx
import sounddevice as sd

# ================= 配置 =================
PORT = 5000
CAMERA_ID = 1  # 外接摄像头
IP_CAMERA_URL = "http://192.168.3.94:8080/video"

# 模型路径
BASE_DIR = Path(__file__).parent
MODEL_DIR = BASE_DIR / "backend" / "core" / "models"

# KWS 模型
KWS_MODEL_DIR = MODEL_DIR / "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
KEYWORDS_FILE = KWS_MODEL_DIR / "keywords.txt"

# ASR 模型
ASR_MODEL_DIR = MODEL_DIR / "sherpa-onnx-paraformer-zh-2024-03-09"

# TTS 模型
TTS_MODEL_DIR = MODEL_DIR / "vits-zh-hf-fanchen-C"

# 音频参数
SAMPLE_RATE = 16000
CHANNELS = 1
NUM_THREADS = 4

# VAD 参数
VAD_ENERGY_THRESHOLD = 0.015
VAD_SILENCE_TIMEOUT = 1.5
VAD_MIN_SPEECH_DURATION = 0.5
VAD_MAX_RECORD_DURATION = 10

app = Flask(__name__)

# ================= 全局状态 =================
class DeviceState:
    def __init__(self):
        self.mic_device_id = None
        self.mic_name = ""
        self.is_running = False
        self.is_recording = False
        self.last_text = ""
        self.tts_sid = 0
        self.tts_speed = 1.0
        self.tts_volume = 1.0
        self.status = "等待唤醒"
        self.audio_queue = queue.Queue()
        self.recorded_audio = []
        self.vad_is_speaking = False
        self.vad_silence_start_time = None
        
state = DeviceState()

# ================= 初始化 =================
def init_devices():
    """初始化所有设备"""
    # 检测Realtek麦克风
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if 'Realtek' in dev['name'] and dev['max_input_channels'] > 0:
            state.mic_device_id = i
            state.mic_name = dev['name']
            print(f"✅ 找到Realtek麦克风: {dev['name']} (设备ID: {i})")
            break
    
    if state.mic_device_id is None:
        # 使用默认麦克风
        state.mic_device_id = sd.default.device[0]
        state.mic_name = devices[state.mic_device_id]['name']
        print(f"⚠️ 未找到Realtek麦克风，使用默认: {state.mic_name}")

def init_kws():
    """初始化唤醒词检测"""
    if not KWS_MODEL_DIR.exists():
        raise FileNotFoundError(f"KWS模型不存在: {KWS_MODEL_DIR}")
    
    kws = sherpa_onnx.KeywordSpotter(
        tokens=str(KWS_MODEL_DIR / "tokens.txt"),
        encoder=str(KWS_MODEL_DIR / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        decoder=str(KWS_MODEL_DIR / "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        joiner=str(KWS_MODEL_DIR / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        num_threads=NUM_THREADS,
        keywords_file=str(KEYWORDS_FILE),
        keywords_score=1.0,
        keywords_threshold=0.25,
        provider="cpu",
    )
    print("✅ 唤醒词检测模型加载完成")
    return kws

def init_asr():
    """初始化语音识别"""
    if not ASR_MODEL_DIR.exists():
        raise FileNotFoundError(f"ASR模型不存在: {ASR_MODEL_DIR}")
    
    asr = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(ASR_MODEL_DIR / "model.int8.onnx"),
        tokens=str(ASR_MODEL_DIR / "tokens.txt"),
        num_threads=NUM_THREADS,
        sample_rate=SAMPLE_RATE,
        feature_dim=80,
        decoding_method="greedy_search",
    )
    print("✅ 语音识别模型加载完成")
    return asr

def init_tts():
    """初始化TTS"""
    if not TTS_MODEL_DIR.exists():
        raise FileNotFoundError(f"TTS模型不存在: {TTS_MODEL_DIR}")
    
    tts_config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(TTS_MODEL_DIR / "vits-zh-hf-fanchen-C.onnx"),
                tokens=str(TTS_MODEL_DIR / "tokens.txt"),
                lexicon=str(TTS_MODEL_DIR / "lexicon.txt"),
            ),
            num_threads=NUM_THREADS,
            provider="cpu",
        ),
        rule_fsts=f"{TTS_MODEL_DIR}/phone.fst,{TTS_MODEL_DIR}/date.fst,{TTS_MODEL_DIR}/number.fst"
    )
    tts = sherpa_onnx.OfflineTts(tts_config)
    print("✅ TTS模型加载完成")
    return tts

# ================= TTS播报 =================
def speak(text):
    """语音播报"""
    if not text or tts is None:
        return
    
    try:
        print(f"🔊 播报: {text}")
        state.status = "正在播报"
        audio = tts.generate(text, sid=state.tts_sid, speed=state.tts_speed)
        samples = np.array(audio.samples, dtype=np.float32) * state.tts_volume
        sd.play(samples, samplerate=audio.sample_rate)
        sd.wait()
        state.status = "等待唤醒"
    except Exception as e:
        print(f"❌ 播报失败: {e}")
        state.status = "等待唤醒"

# ================= 音频处理 =================
def audio_callback(indata, frames, time_info, status):
    """音频回调"""
    if status:
        print(f"[警告] 音频状态: {status}")
    
    if state.is_recording:
        state.recorded_audio.append(indata.copy())
        process_vad(indata)
    
    state.audio_queue.put(indata.copy())

def process_vad(audio_chunk):
    """VAD处理"""
    rms = np.sqrt(np.mean(audio_chunk ** 2))
    current_time = datetime.now()
    
    if rms > VAD_ENERGY_THRESHOLD:
        if not state.vad_is_speaking:
            state.vad_is_speaking = True
            print("🎤 检测到语音输入...")
        state.vad_silence_start_time = None
    else:
        if state.vad_is_speaking:
            if state.vad_silence_start_time is None:
                state.vad_silence_start_time = current_time
            else:
                silence_duration = (current_time - state.vad_silence_start_time).total_seconds()
                if silence_duration >= VAD_SILENCE_TIMEOUT:
                    print(f"🛑 语音结束（静音 {silence_duration:.1f} 秒）")
                    state.is_recording = False

def process_audio(kws, asr):
    """音频处理线程"""
    stream = kws.create_stream()
    
    print("\n" + "=" * 50)
    print("🎤 正在监听唤醒词'阿康'...")
    print("=" * 50 + "\n")
    
    while state.is_running:
        try:
            audio_chunk = state.audio_queue.get(timeout=0.1)
            samples = audio_chunk.flatten().astype(np.float32)
            stream.accept_waveform(SAMPLE_RATE, samples)
            
            while kws.is_ready(stream):
                kws.decode_stream(stream)
            
            result = kws.get_result(stream)
            if isinstance(result, str):
                if result.strip():
                    on_keyword_detected(result, asr)
                    stream = kws.create_stream()
            elif hasattr(result, 'keyword'):
                if result.keyword:
                    on_keyword_detected(result.keyword, asr)
                    stream = kws.create_stream()
        
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[错误] 处理音频: {e}")

def on_keyword_detected(keyword, asr):
    """检测到唤醒词"""
    normalized = keyword.strip()
    if "ā k āng" in normalized or "kāng" in normalized or "阿康" in normalized:
        print(f"\n🎉 检测到唤醒词: {keyword}")
        speak("在听呢")
        start_listening(asr)

def start_listening(asr):
    """开始监听用户说话"""
    print("→ 您说，我来复述")
    
    state.status = "正在倾听"
    state.vad_is_speaking = False
    state.vad_silence_start_time = None
    state.is_recording = True
    state.recorded_audio = []
    
    start_time = time.time()
    
    while state.is_recording and state.is_running:
        elapsed = time.time() - start_time
        if elapsed >= VAD_MAX_RECORD_DURATION:
            print(f"⏱️ 达到最大录制时长")
            state.is_recording = False
            break
        time.sleep(0.05)
    
    state.is_recording = False
    
    if len(state.recorded_audio) > 0:
        total_samples = sum(len(chunk) for chunk in state.recorded_audio)
        duration = total_samples / SAMPLE_RATE
        
        if duration >= VAD_MIN_SPEECH_DURATION:
            process_recorded_audio(asr)
        else:
            print(f"→ 语音太短（{duration:.1f} 秒）")
            speak("语音太短，请再说一次")
    else:
        print("→ 未检测到语音输入")

def process_recorded_audio(asr):
    """处理录制的音频"""
    try:
        print("📝 正在识别...")
        
        audio_data = np.concatenate(state.recorded_audio, axis=0).flatten().astype(np.float32)
        
        stream = asr.create_stream()
        stream.accept_waveform(SAMPLE_RATE, audio_data)
        
        asr.decode_stream(stream)
        
        result = stream.result
        text = result.text.strip() if hasattr(result, 'text') else str(result).strip()
        
        if text:
            print(f"→ 您说: {text}")
            state.last_text = text
            speak(f"您说{text}")
        else:
            print("→ 无法识别语音")
            speak("无法识别，请再说一次")
    
    except Exception as e:
        print(f"→ 识别出错: {e}")
        speak("识别出错")
    finally:
        state.status = "等待唤醒"

# ================= 视频流 =================
def gen_frames_local():
    """本地摄像头视频流"""
    cap = cv2.VideoCapture(CAMERA_ID)
    while True:
        success, frame = cap.read()
        if not success:
            continue
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

def gen_frames_ip():
    """IP摄像头视频流"""
    cap = cv2.VideoCapture(IP_CAMERA_URL)
    while True:
        success, frame = cap.read()
        if not success:
            continue
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# ================= HTML页面 =================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>设备测试</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 20px; }
        .video-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .video-box { background: #fff; border-radius: 8px; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .video-box h3 { margin-top: 0; color: #333; }
        .video-box img { width: 100%; border-radius: 4px; }
        .control-panel { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-top: 30px; }
        .control-group { margin-bottom: 15px; }
        .control-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .control-group input[type="range"] { width: 100%; }
        .control-group select { width: 100%; padding: 5px; margin: 5px 0; }
        .control-group span { display: inline-block; width: 50px; text-align: center; }
        .status { background: #e3f2fd; padding: 15px; border-radius: 4px; margin-top: 15px; }
        .status-item { margin: 5px 0; }
        .last-text { font-size: 18px; color: #1976d2; font-weight: bold; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎤 设备测试控制台</h1>
        </div>
        
        <div class="control-panel">
            <h2>⚙️ TTS参数设置</h2>
            
            <div class="control-group">
                <label>音色 (SID): <span id="sid-value">0</span></label>
                <input type="range" id="sid" min="0" max="186" value="0" 
                       oninput="updateSid(this.value)">
                <select id="sid-select" onchange="updateSidSelect(this.value)">
                    <option value="0">默认音色</option>
                    <option value="1">男声1</option>
                    <option value="2">男声2</option>
                    <option value="3">男声3</option>
                    <option value="4">女声1</option>
                    <option value="5">女声2</option>
                    <option value="6">女声3</option>
                    <option value="7">少年</option>
                    <option value="8">儿童</option>
                    <option value="9">老人</option>
                    <option value="10">机器人</option>
                    <!-- 更多音色选项 -->
                    <option value="180">甜美女声</option>
                    <option value="181">成熟男声</option>
                    <option value="182">中性</option>
                    <option value="183">温柔女声</option>
                    <option value="184">深沉男声</option>
                    <option value="185">活泼女声</option>
                    <option value="186">阳光男声</option>
                </select>
                <small>0-186共187种音色</small>
            </div>
            
            <div class="control-group">
                <label>语速: <span id="speed-value">1.0</span></label>
                <input type="range" id="speed" min="0.5" max="1.5" step="0.1" value="1.0"
                       oninput="updateSpeed(this.value)">
                <small>0.5-1.5，1.0为正常语速</small>
            </div>
            
            <div class="control-group">
                <label>音量: <span id="volume-value">1.0</span></label>
                <input type="range" id="volume" min="0" max="2" step="0.1" value="1.0"
                       oninput="updateVolume(this.value)">
                <small>0-2，1.0为正常音量</small>
            </div>
            
            <div class="status">
                <h3>📊 状态信息</h3>
                <div class="status-item">🎤 麦克风: {{ mic_name }}</div>
                <div class="status-item">🔊 扬声器: 系统默认</div>
                <div class="status-item">🎯 唤醒词: 阿康</div>
                <div class="status-item">📋 状态: <span id="status-text">{{ status }}</span></div>
                <div class="last-text">📝 最后识别: <span id="last-text">{{ last_text }}</span></div>
            </div>
        </div>
        
        <div class="video-grid">
            <div class="video-box">
                <h3>📷 本地摄像头 (ID: 1)</h3>
                <img src="/video/local" alt="本地摄像头">
            </div>
            <div class="video-box">
                <h3>🌐 IP摄像头 (192.168.3.94)</h3>
                <img src="/video/ip" alt="IP摄像头">
            </div>
        </div>
    </div>
    
    <script>
        function updateSid(value) {
            document.getElementById('sid-value').textContent = value;
            document.getElementById('sid-select').value = value;
            fetch('/api/set_sid?value=' + value);
        }
        
        function updateSidSelect(value) {
            document.getElementById('sid-value').textContent = value;
            document.getElementById('sid').value = value;
            fetch('/api/set_sid?value=' + value);
        }
        
        function updateSpeed(value) {
            document.getElementById('speed-value').textContent = value;
            fetch('/api/set_speed?value=' + value);
        }
        
        function updateVolume(value) {
            document.getElementById('volume-value').textContent = value;
            fetch('/api/set_volume?value=' + value);
        }
        
        // 定期更新状态信息
        setInterval(function() {
            fetch('/api/get_status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('last-text').textContent = data.last_text || "等待唤醒...";
                    document.getElementById('status-text').textContent = data.status || "等待唤醒";
                });
        }, 1000);
    </script>
</body>
</html>
"""

# ================= Flask路由 =================
@app.route('/')
def index():
    return render_template_string(HTML_PAGE, mic_name=state.mic_name, last_text=state.last_text, status=state.status)

@app.route('/video/local')
def video_local():
    return Response(gen_frames_local(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video/ip')
def video_ip():
    return Response(gen_frames_ip(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/set_sid')
def set_sid():
    state.tts_sid = int(request.args.get('value', 0))
    return {'status': 'ok', 'sid': state.tts_sid}

@app.route('/api/set_speed')
def set_speed():
    state.tts_speed = float(request.args.get('value', 1.0))
    return {'status': 'ok', 'speed': state.tts_speed}

@app.route('/api/set_volume')
def set_volume():
    state.tts_volume = float(request.args.get('value', 1.0))
    return {'status': 'ok', 'volume': state.tts_volume}

@app.route('/api/get_status')
def get_status():
    return {'last_text': state.last_text, 'status': state.status}

# ================= 主程序 =================
def main():
    global tts, kws, asr
    
    print("=" * 60)
    print("🚀 设备测试程序启动")
    print("=" * 60)
    
    # 初始化设备
    init_devices()
    
    # 初始化模型
    try:
        kws = init_kws()
        asr = init_asr()
        tts = init_tts()
    except Exception as e:
        print(f"❌ 模型初始化失败: {e}")
        sys.exit(1)
    
    # 启动音频处理
    state.is_running = True
    
    def audio_thread():
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.float32,
            device=state.mic_device_id,
            callback=audio_callback,
            blocksize=480,
        ):
            process_audio(kws, asr)
    
    threading.Thread(target=audio_thread, daemon=True).start()
    
    # 播报启动完成
    speak("设备测试程序已启动，请说阿康唤醒我")
    
    print("\n" + "=" * 60)
    print(f"🌐 访问地址: http://127.0.0.1:{PORT}")
    print("=" * 60 + "\n")
    
    # 启动Flask
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
