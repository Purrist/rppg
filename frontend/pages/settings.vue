<template>
  <div class="settings-page">
    <h1>⚙️ 系统设置</h1>
    
    <div class="settings-section">
      <h2>个人信息</h2>
      <div class="setting-item">
        <span class="label">姓名</span>
        <span class="value">张爷爷</span>
      </div>
      <div class="setting-item">
        <span class="label">年龄</span>
        <span class="value">72岁</span>
      </div>
    </div>
    
    <!-- ⭐ AI模式设置 -->
    <div class="settings-section">
      <h2>智伴系统</h2>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">智伴模式</div>
          <div class="label-sub">
            <template v-if="aiCompanionEnabled">
              AI会基于数据实现主动式交互，提供健康监测、认知训练和情感陪伴
            </template>
            <template v-else>
              基础模式：AI不参与游戏难度调整，不会主动交互，仅支持页面切换和问答功能
            </template>
          </div>
        </span>
        <div class="toggle-switch" @click="aiCompanionEnabled = !aiCompanionEnabled; toggleAIMode()">
          <div class="toggle-track" :class="{ active: aiCompanionEnabled }">
            <div class="toggle-thumb" :class="{ active: aiCompanionEnabled }"></div>
          </div>
          <span class="toggle-label">{{ aiCompanionEnabled ? '已开启' : '已关闭' }}</span>
        </div>
      </div>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">唤醒识别</div>
          <div class="label-sub">
            启用后，系统会监听唤醒词"阿康阿康"，识别后开始语音交互
          </div>
        </span>
        <div class="toggle-switch" @click="voiceWakeupEnabled = !voiceWakeupEnabled; toggleVoiceWakeup()">
          <div class="toggle-track" :class="{ active: voiceWakeupEnabled }">
            <div class="toggle-thumb" :class="{ active: voiceWakeupEnabled }"></div>
          </div>
          <span class="toggle-label">{{ voiceWakeupEnabled ? '已开启' : '已关闭' }}</span>
        </div>
      </div>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">语音朗读</div>
          <div class="label-sub">
            启用后，AI会通过语音朗读回复内容
          </div>
        </span>
        <div class="toggle-switch" @click="voiceSpeakingEnabled = !voiceSpeakingEnabled; toggleVoiceSpeaking()">
          <div class="toggle-track" :class="{ active: voiceSpeakingEnabled }">
            <div class="toggle-thumb" :class="{ active: voiceSpeakingEnabled }"></div>
          </div>
          <span class="toggle-label">{{ voiceSpeakingEnabled ? '已开启' : '已关闭' }}</span>
        </div>
      </div>
      <div class="setting-hint">
        <p>💡 <strong>基础模式</strong>：系统按预设程序运行，AI仅提供基础问答和页面切换功能</p>
        <p>💡 <strong>智伴模式</strong>：AI主动分析数据，动态调整游戏难度，提供个性化健康建议和情感陪伴</p>
        <p>💡 <strong>语音功能</strong>：唤醒识别和语音朗读可以独立开启或关闭，不影响智伴模式的其他功能</p>
      </div>
    </div>

    <div class="settings-section">
      <h2>投影交互设置</h2>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">确认时间（灵敏度）</div>
          <div class="label-sub">站在识别区域后，进度圈从0%到100%所需的时间</div>
        </span>
        <div class="value-control">
          <button class="adjust-btn" @click="decreaseDwellTime" :disabled="dwellTime <= 1500">−</button>
          <span class="value">{{ (dwellTime / 1000).toFixed(1) }}秒</span>
          <button class="adjust-btn" @click="increaseDwellTime" :disabled="dwellTime >= 4000">+</button>
        </div>
      </div>
      <div class="setting-hint">
        <p>💡 <strong>提示</strong>：确认时间越短，交互越灵敏，但可能误触；确认时间越长，交互越稳定，但需要等待更久。</p>
        <p>推荐设置：<strong>2.0秒</strong>（适合大多数用户）</p>
      </div>
    </div>
    
    <div class="settings-section">
      <h2>语音设置</h2>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">语音引擎</div>
          <div class="label-sub">
            选择语音合成引擎（VITS更自然，pytts更稳定）
          </div>
        </span>
        <div class="select-control">
          <select v-model="selectedTtsEngine" @change="updateTtsEngine">
            <option value="vits">VITS (推荐)</option>
            <option value="pytts">pytts</option>
          </select>
        </div>
      </div>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">音色选择</div>
          <div class="label-sub">
            选择语音合成的音色
          </div>
        </span>
        <div class="select-control">
          <select v-model="selectedVoiceId" @change="updateVoiceTone">
            <option v-for="tone in voiceTones" :key="tone.id" :value="tone.id">
              {{ tone.name }}
            </option>
          </select>
        </div>
      </div>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">语速调节</div>
          <div class="label-sub">
            调整语音合成的语速
          </div>
        </span>
        <div class="slider-control">
          <input 
            type="range" 
            v-model="ttsSpeed" 
            min="0.5" 
            max="1.5" 
            step="0.1"
            @input="updateTtsSpeed"
          >
          <span class="slider-value">{{ ttsSpeed }}</span>
        </div>
      </div>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">音量调节</div>
          <div class="label-sub">
            调整语音合成的音量
          </div>
        </span>
        <div class="slider-control">
          <input 
            type="range" 
            v-model="ttsVolume" 
            min="0" 
            max="2" 
            step="0.1"
            @input="updateTtsVolume"
          >
          <span class="slider-value">{{ ttsVolume }}</span>
        </div>
      </div>
    </div>

    <div class="settings-section">
      <h2>系统管理</h2>
      <div class="setting-item clickable" @click="goToDeveloper">
        <span class="label">🛠 开发者后台</span>
        <span class="arrow">→</span>
      </div>
      <div class="setting-item clickable" @click="goToProjection">
        <span class="label">📽 投影页面</span>
        <span class="arrow">→</span>
      </div>
    </div>
    
    <div class="settings-section">
      <h2>关于</h2>
      <div class="setting-item">
        <span class="label">系统版本</span>
        <span class="value">v1.0.0</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { initStore, subscribe, setAIMode, setDwellTime } from '../core/systemStore.js'

const router = useRouter()

// Socket.IO 连接
let socket = null
let unsubscribe = null

// 确认时间（毫秒），范围1500-4000ms，默认2000ms
const dwellTime = ref(2000)

// AI模式开关
const aiCompanionEnabled = ref(false)

// 语音功能开关
const voiceWakeupEnabled = ref(true)
const voiceSpeakingEnabled = ref(true)

// TTS设置
const selectedTtsEngine = ref('vits')
const selectedVoiceId = ref(0)
const ttsSpeed = ref(1.0)
const ttsVolume = ref(1.0)
const voiceTones = ref([])

const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

onMounted(() => {
  // 建立 Socket.IO 连接
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  // ⭐ 初始化系统Store
  initStore(socket)
  
  socket.on('connect', () => {
    console.log('[settings] 后端已连接')
    // 请求当前状态
    socket.emit('get_system_state')
    // 请求TTS配置
    socket.emit('get_tts_config')
  })
  
  // 接收TTS配置
  socket.on('tts_config', (config) => {
    console.log('[settings] 收到TTS配置:', config)
    if (config) {
      selectedTtsEngine.value = config.engine || 'vits'
      selectedVoiceId.value = config.sid || 0
      ttsSpeed.value = config.speed || 1.0
      ttsVolume.value = config.volume || 1.0
      voiceTones.value = config.voice_tones || []
    }
  })
  
  // ⭐ 订阅后端状态更新
  unsubscribe = subscribe((state) => {
    // 更新确认时间
    if (state.settings?.dwellTime !== undefined) {
      dwellTime.value = state.settings.dwellTime
    }
    // 更新AI模式
    if (state.aiMode !== undefined) {
      aiCompanionEnabled.value = state.aiMode === 'companion'
    }
    // 更新语音设置
    if (state.settings?.voiceWakeup !== undefined) {
      voiceWakeupEnabled.value = state.settings.voiceWakeup
    }
    if (state.settings?.voiceSpeaking !== undefined) {
      voiceSpeakingEnabled.value = state.settings.voiceSpeaking
    }
  })
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
  if (socket) socket.disconnect()
})

// 减少确认时间
const decreaseDwellTime = () => {
  if (dwellTime.value > 1500) {
    dwellTime.value -= 500
    saveDwellTime()
  }
}

// 增加确认时间
const increaseDwellTime = () => {
  if (dwellTime.value < 4000) {
    dwellTime.value += 500
    saveDwellTime()
  }
}

// 保存设置 - 发送到后端
const saveDwellTime = () => {
  // ⭐ 发送到后端，后端是唯一的真相来源
  setDwellTime(dwellTime.value)
  console.log('[settings] 确认时间已发送到后端:', dwellTime.value, 'ms')
}

// 切换AI模式 - 发送到后端
const toggleAIMode = () => {
  const newMode = aiCompanionEnabled.value ? 'companion' : 'basic'
  setAIMode(newMode)
  console.log('[settings] AI模式发送到后端:', newMode)
}

// 切换唤醒识别 - 发送到后端
const toggleVoiceWakeup = () => {
  setVoiceSetting('wakeup', voiceWakeupEnabled.value)
  console.log('[settings] 唤醒识别设置发送到后端:', voiceWakeupEnabled.value)
}

// 切换语音朗读 - 发送到后端
const toggleVoiceSpeaking = () => {
  setVoiceSetting('speaking', voiceSpeakingEnabled.value)
  console.log('[settings] 语音朗读设置发送到后端:', voiceSpeakingEnabled.value)
}

const goToDeveloper = () => {
  router.push('/developer')
}

const goToProjection = () => {
  router.push('/projection')
}

// 更新语音引擎
const updateTtsEngine = () => {
  socket.emit('set_tts_engine', { engine: selectedTtsEngine.value })
  console.log('[settings] 语音引擎设置发送到后端:', selectedTtsEngine.value)
}

// 更新语音音色
const updateVoiceTone = () => {
  socket.emit('set_tts_sid', selectedVoiceId.value)
  console.log('[settings] 音色设置发送到后端:', selectedVoiceId.value)
}

// 更新语速
const updateTtsSpeed = () => {
  socket.emit('set_tts_speed', parseFloat(ttsSpeed.value))
  console.log('[settings] 语速设置发送到后端:', ttsSpeed.value)
}

// 更新音量
const updateTtsVolume = () => {
  socket.emit('set_tts_volume', parseFloat(ttsVolume.value))
  console.log('[settings] 音量设置发送到后端:', ttsVolume.value)
}

// 设置语音相关配置
const setVoiceSetting = (type, value) => {
  socket.emit('set_voice_setting', { type, value })
  console.log('[settings] 语音设置发送到后端:', type, value)
}
</script>

<style scoped>
.settings-page {
  padding: 40px;
}

.settings-page h1 {
  font-size: 36px;
  font-weight: 900;
  color: #333;
  margin-bottom: 40px;
}

.settings-section {
  margin-bottom: 40px;
}

.settings-section h2 {
  font-size: 24px;
  color: #888;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #EEE;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #FFF;
  border-radius: 15px;
  margin-bottom: 15px;
}

.setting-item.clickable {
  cursor: pointer;
  transition: background 0.2s;
}

.setting-item.clickable:hover {
  background: #F5F5F5;
}

.setting-item .label {
  font-size: 22px;
  color: #333;
}

.label-main {
  font-size: 22px;
  font-weight: 600;
  color: #333;
  margin-bottom: 5px;
}

.label-sub {
  font-size: 16px;
  color: #888;
  max-width: 400px;
  line-height: 1.4;
}

.value-control {
  display: flex;
  align-items: center;
  gap: 15px;
}

.value-control .value {
  font-size: 24px;
  font-weight: 700;
  color: #FF7222;
  min-width: 80px;
  text-align: center;
}

.adjust-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid #FF7222;
  background: #FFF;
  color: #FF7222;
  font-size: 24px;
  font-weight: bold;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.adjust-btn:hover:not(:disabled) {
  background: #FF7222;
  color: #FFF;
}

.adjust-btn:disabled {
  border-color: #CCC;
  color: #CCC;
  cursor: not-allowed;
}

.setting-hint {
  background: #FFF5F0;
  padding: 20px;
  border-radius: 15px;
  margin-top: 10px;
}

.setting-hint p {
  font-size: 18px;
  color: #666;
  line-height: 1.6;
  margin-bottom: 10px;
}

.setting-hint p:last-child {
  margin-bottom: 0;
}

.setting-hint strong {
  color: #FF7222;
}

.setting-item .value {
  font-size: 22px;
  color: #888;
}

.setting-item .arrow {
  font-size: 24px;
  color: #CCC;
}

/* ⭐ 切换开关样式 */
.toggle-switch {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
}

.toggle-track {
  width: 60px;
  height: 32px;
  background: #CCC;
  border-radius: 16px;
  position: relative;
  transition: background 0.3s;
}

.toggle-track.active {
  background: #33B555;
}

.toggle-thumb {
  width: 28px;
  height: 28px;
  background: #FFF;
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.3s;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.toggle-thumb.active {
  transform: translateX(28px);
}

.toggle-label {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  min-width: 60px;
}

.select-control select {
  padding: 10px 15px;
  font-size: 18px;
  border: 2px solid #FF7222;
  border-radius: 8px;
  background: #FFF;
  color: #333;
  min-width: 200px;
}

.slider-control {
  display: flex;
  align-items: center;
  gap: 15px;
  min-width: 200px;
}

.slider-control input[type="range"] {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #CCC;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}

.slider-control input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #FF7222;
  cursor: pointer;
}

.slider-control input[type="range"]::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #FF7222;
  cursor: pointer;
  border: none;
}

.slider-value {
  font-size: 18px;
  font-weight: 600;
  color: #FF7222;
  min-width: 60px;
  text-align: right;
}
</style>
