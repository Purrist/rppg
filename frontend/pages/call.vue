<template>
  <div class="call-page">
    <!-- 联系列表状态（白底） -->
    <div v-if="currentState === 'contacts'" class="contacts-container">
      <!-- 紧急电话区域 - 三卡片并排 -->
      <div class="emergency-section">
        <div class="section-title">🆘 紧急电话</div>
        <div class="emergency-cards">
          <div class="emergency-card" @click="callEmergency('护理站')">
            <div class="card-icon">👩‍⚕️</div>
            <div class="card-name">护理站</div>
            <div class="card-desc">紧急情况请联系</div>
            <div class="card-call">📞呼叫</div>
          </div>
          <div class="emergency-card" @click="callEmergency('110')">
            <div class="card-icon">👮</div>
            <div class="card-name">110</div>
            <div class="card-desc">报警电话</div>
            <div class="card-call">📞呼叫</div>
          </div>
          <div class="emergency-card" @click="callEmergency('120')">
            <div class="card-icon">🚑</div>
            <div class="card-name">120</div>
            <div class="card-desc">急救电话</div>
            <div class="card-call">📞呼叫</div>
          </div>
        </div>
      </div>

      <!-- 分隔线 -->
      <div class="divider">
        <span class="divider-text">常用联系人</span>
      </div>

      <!-- 联系人列表 -->
      <div class="contact-list">
        <div 
          v-for="contact in contacts" 
          :key="contact.id" 
          class="contact-item"
        >
          <div class="contact-avatar">{{ contact.avatar }}</div>
          <div class="contact-info">
            <div class="contact-name">{{ contact.name }}</div>
            <div class="contact-relation">{{ contact.relation }}</div>
            <div class="contact-phone">{{ contact.phone }}</div>
            <div class="contact-last-call">{{ contact.lastCallTime }}</div>
          </div>
          <div class="contact-call" @click="startCall(contact)">📞 呼叫</div>
        </div>
      </div>
    </div>

    <!-- 通话中状态（持续呼叫） -->
    <div v-if="currentState === 'calling'" class="calling-container">
      <!-- 视频流背景（点击视频时显示） -->
      <div v-if="isVideoOn" class="video-background">
        <img src="http://192.168.137.25:8080/video" alt="IP Camera Feed" class="video-feed" />
        <div class="video-overlay"></div>
      </div>

      <!-- 通话界面背景 -->
      <div class="calling-bg" :class="{ 'emergency-call': isEmergency, 'normal-call': !isEmergency }">
        <!-- 音波动画 -->
        <div class="wave-container">
          <div class="wave wave1"></div>
          <div class="wave wave2"></div>
          <div class="wave wave3"></div>
          <div class="wave wave4"></div>
          <div class="wave wave5"></div>
        </div>

        <!-- 通话信息 -->
        <div class="calling-info">
          <div class="calling-avatar">{{ currentContact?.avatar || (isEmergency ? '🚨' : '👤') }}</div>
          <div class="calling-name">{{ currentContact?.name || (isEmergency ? '紧急呼救' : '通话中') }}</div>
          <div class="calling-number">{{ currentContact?.phone || (isEmergency ? '120' : '') }}</div>
          <div class="calling-status">
            <span class="ringing-icon">🔔</span>
            {{ callingStatus }}
          </div>
          <div class="calling-timer">{{ callDuration }}</div>
        </div>

        <!-- 通话控制按钮 -->
        <div class="calling-controls">
          <button class="control-btn mute-btn" @click="toggleMute">
            <span>{{ isMuted ? '🔇' : '🎤' }}</span>
            <span class="control-label">{{ isMuted ? '静音' : '麦克风' }}</span>
          </button>
          <button class="control-btn speaker-btn" @click="toggleSpeaker">
            <span>{{ isSpeakerOn ? '🔊' : '🔈' }}</span>
            <span class="control-label">{{ isSpeakerOn ? '扬声器' : '听筒' }}</span>
          </button>
          <button class="control-btn video-btn" @click="toggleVideo">
            <span>{{ isVideoOn ? '📹' : '🚫' }}</span>
            <span class="control-label">{{ isVideoOn ? '视频' : '关闭' }}</span>
          </button>
          <button class="control-btn hangup-btn" @click="endCall">
            <span>📞</span>
            <span class="control-label">挂断</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

// 状态
const currentState = ref('contacts') // 'contacts' | 'calling'
const isEmergency = ref(false)
const currentContact = ref(null)
const callingStatus = ref('正在呼叫...')
const callDuration = ref('00:00')
const isMuted = ref(false)
const isSpeakerOn = ref(true)
const isVideoOn = ref(true)

let callTimer = null
let ringTimer = null
let autoExitTimer = null

// 音频上下文
let audioContext = null
let ringOscillator = null

// 紧急电话列表
const emergencyContacts = [
  { id: 'nurse', name: '护理站', phone: '010-12345678', avatar: '🏥' },
  { id: 'police', name: '110', phone: '110', avatar: '👮' },
  { id: 'ambulance', name: '120', phone: '120', avatar: '🚑' },
]

// 常用联系人列表
const contacts = ref([
  { id: 1, name: '张帅', relation: '儿子', phone: '13800138001', avatar: '👨', status: 'online', lastCallTime: '今天 14:30' },
  { id: 2, name: '张敏', relation: '女儿', phone: '13900139002', avatar: '👩', status: 'online', lastCallTime: '昨天 18:45' },
  { id: 3, name: '赵兰', relation: '老伴', phone: '13700137003', avatar: '👵', status: 'offline', lastCallTime: '3天前' },
  { id: 4, name: '李医生', relation: '医生', phone: '13600136004', avatar: '👨‍⚕️', status: 'online', lastCallTime: '上周' },
])

// 返回首页
const goBack = () => {
  router.push('/')
}

// 播放铃声（使用真实音频文件）
const ringtoneAudio = ref(null)

const playRingTone = () => {
  try {
    // 停止之前的铃声
    if (ringtoneAudio.value) {
      ringtoneAudio.value.pause()
      ringtoneAudio.value = null
    }
    
    // 使用真实音频文件
    ringtoneAudio.value = new Audio()
    ringtoneAudio.value.src = isEmergency.value 
      ? '/sounds/call/电话呼叫声.wav' 
      : '/sounds/call/通话呼叫.mp3'
    ringtoneAudio.value.loop = true
    // 紧急铃声音量大，日常铃声音量小
    ringtoneAudio.value.volume = isEmergency.value ? 0.6 : 0.25
    ringtoneAudio.value.play().catch(e => {
      console.log('音频播放失败，尝试使用Web Audio API:', e)
      // 降级到合成铃声
      playFallbackRingtone()
    })
  } catch (e) {
    console.log('音频播放失败:', e)
    playFallbackRingtone()
  }
}

// 降级合成铃声
const playFallbackRingtone = () => {
  try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
    
    const frequencies = isEmergency.value ? [800, 1000] : [400, 600]
    let freqIndex = 0
    
    ringTimer = setInterval(() => {
      if (!audioContext) return
      
      const ringOscillator = audioContext.createOscillator()
      const gainNode = audioContext.createGain()
      
      ringOscillator.connect(gainNode)
      gainNode.connect(audioContext.destination)
      
      ringOscillator.frequency.value = frequencies[freqIndex % 2]
      ringOscillator.type = 'sine'
      
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime)
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1)
      
      ringOscillator.start(audioContext.currentTime)
      ringOscillator.stop(audioContext.currentTime + 0.1)
      
      freqIndex++
    }, isEmergency.value ? 150 : 400)
  } catch (e) {
    console.log('[CallPage] 铃声播放失败:', e)
  }
}

// 停止铃声
const stopRingTone = () => {
  // 停止真实音频
  if (ringtoneAudio.value) {
    ringtoneAudio.value.pause()
    ringtoneAudio.value = null
  }
  
  // 停止合成铃声
  if (ringTimer) {
    clearInterval(ringTimer)
    ringTimer = null
  }
  if (ringOscillator) {
    try {
      ringOscillator.stop()
    } catch (e) {}
    ringOscillator = null
  }
  if (audioContext) {
    audioContext.close()
    audioContext = null
  }
}

// 开始紧急呼叫
const callEmergency = (type) => {
  isEmergency.value = true
  isVideoOn.value = true  // 默认开启视频
  currentState.value = 'calling'
  
  let contact = null
  if (type === '护理站') {
    contact = emergencyContacts[0]
  } else if (type === '110') {
    contact = emergencyContacts[1]
  } else if (type === '120') {
    contact = emergencyContacts[2]
  }
  currentContact.value = contact
  
  callingStatus.value = '紧急呼叫中...'
  startCallProcess()
}

// 开始普通通话
const startCall = (contact) => {
  isEmergency.value = false
  isVideoOn.value = true  // 默认开启视频
  currentState.value = 'calling'
  currentContact.value = contact
  callingStatus.value = '正在呼叫...'
  startCallProcess()
}

// 开始通话流程（持续呼叫，不接通）
const startCallProcess = () => {
  callDuration.value = '00:00'
  
  // 开始播放铃声
  playRingTone()
  
  // 15秒后自动退出通话
  autoExitTimer = setTimeout(() => {
    console.log('[CallPage] 通话超时，自动退出')
    hangUp()
  }, 15000)
  
  // 开始计时器
  let seconds = 0
  callTimer = setInterval(() => {
    seconds++
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0')
    const secs = (seconds % 60).toString().padStart(2, '0')
    callDuration.value = `${mins}:${secs}`
  }, 1000)
}

// 切换静音
const toggleMute = () => {
  isMuted.value = !isMuted.value
}

// 切换扬声器
const toggleSpeaker = () => {
  isSpeakerOn.value = !isSpeakerOn.value
}

// 切换视频（显示/隐藏视频流）
const toggleVideo = () => {
  isVideoOn.value = !isVideoOn.value
}

// 结束通话
const endCall = () => {
  stopRingTone()
  
  if (callTimer) {
    clearInterval(callTimer)
    callTimer = null
  }
  
  // 清除自动退出定时器
  if (autoExitTimer) {
    clearTimeout(autoExitTimer)
    autoExitTimer = null
  }
  
  isVideoOn.value = false
  currentState.value = 'contacts'
  currentContact.value = null
  callingStatus.value = '已结束'
}

// 监听路由参数
watch(() => route.query, (newQuery) => {
  if (newQuery.emergency === 'true') {
    isEmergency.value = true
    currentState.value = 'calling'
    callingStatus.value = '紧急呼叫中...'
    startCallProcess()
  } else if (newQuery.contact) {
    const contact = contacts.value.find(c => c.name === newQuery.contact)
    if (contact) {
      startCall(contact)
    }
  }
}, { immediate: true })

onMounted(() => {
  console.log('[CallPage] 呼叫页面已加载')
})

onUnmounted(() => {
  stopRingTone()
  if (callTimer) {
    clearInterval(callTimer)
    callTimer = null
  }
})
</script>

<style scoped>
.call-page {
  min-height: 100vh;
  background: #f5f5f5;
}

/* 联系列表状态（白底） */
.contacts-container {
  min-height: 100vh;
  background: white;
}

.emergency-section {
  margin: 20px;
  background: #fff5f5;
  border-radius: 20px;
  padding: 20px;
  border: 1px solid #ffebee;
}

.section-title {
  font-size: 16px;
  font-weight: bold;
  color: #dc3545;
  margin-bottom: 15px;
}

/* 三卡片并排布局 */
.emergency-cards {
  display: flex;
  justify-content: space-between;
  gap: 15px;
  padding: 0 15px;
}

.emergency-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 15px;
  background: linear-gradient(145deg, #ffffff, #f8f9fa);
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid #e0e0e0;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.emergency-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  border-color: #667eea;
}

.card-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.card-name {
  font-size: 20px;
  font-weight: bold;
  color: #333;
  margin-bottom: 6px;
}

.card-desc {
  font-size: 14px;
  color: #666;
  margin-bottom: 12px;
}

.card-call {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: bold;
  color: #667eea;
  padding: 8px 16px;
  background: rgba(102, 126, 234, 0.1);
  border-radius: 20px;
  transition: all 0.2s;
}

.emergency-card:hover .card-call {
  background: #667eea;
  color: white;
}

.divider {
  display: flex;
  align-items: center;
  padding: 0 20px;
  margin: 10px 0;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #eee;
}

.divider-text {
  padding: 0 15px;
  color: #999;
  font-size: 14px;
}

.contact-list {
  margin: 0 20px 20px;
}

.contact-item {
  display: flex;
  align-items: center;
  padding: 20px;
  background: #fafafa;
  border-radius: 16px;
  cursor: pointer;
  transition: background 0.2s, box-shadow 0.2s;
  margin-bottom: 15px;
  border: 1px solid #f0f0f0;
}

.contact-item:last-child {
  margin-bottom: 0;
}

.contact-item:hover {
  background: #f0f0f0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.contact-avatar {
  font-size: 48px;
  margin-right: 20px;
}

.contact-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 30px;
}

.contact-name {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  min-width: 80px;
}

.contact-relation {
  font-size: 20px;
  color: #666;
  min-width: 80px;
}

.contact-phone {
  font-size: 20px;
  color: #333;
  min-width: 120px;
}

.contact-last-call {
  font-size: 18px;
  color: #999;
  margin-left: 20px;
}

.contact-call {
  display: flex;
  align-items: center;
  gap: 15px;
  font-size: 20px;
  font-weight: bold;
  color: white;
  padding: 12px 28px;
  background: linear-gradient(135deg, #22c55e, #16a34a);
  border-radius: 30px;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 15px rgba(34, 197, 94, 0.3);
}

.contact-call:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(34, 197, 94, 0.4);
}

/* 通话中状态 */
.calling-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  overflow: hidden;
}

/* 视频流背景 */
.video-background {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1;
}

.video-feed {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.video-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.15);
}

/* 通话界面背景 */
.calling-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transition: background 0.3s;
}

.calling-bg.emergency-call {
  background: linear-gradient(135deg, rgba(220, 53, 69, 0.75) 0%, rgba(200, 35, 51, 0.75) 50%, rgba(167, 29, 42, 0.75) 100%);
}

.calling-bg.normal-call {
  background: linear-gradient(135deg, rgba(40, 167, 69, 0.75) 0%, rgba(32, 201, 151, 0.75) 50%, rgba(23, 162, 184, 0.75) 100%);
}

/* 音波动画 - 只保留外面大圈 */
.wave-container {
  position: absolute;
  width: 450px;
  height: 450px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wave {
  position: absolute;
  border-radius: 50%;
  animation: wave 2.5s infinite cubic-bezier(0.36, 0.07, 0.19, 0.97);
}

.wave1 { 
  width: 220px; 
  height: 220px; 
  animation-delay: 0s; 
  background: radial-gradient(circle, rgba(255,255,255,0.3) 0%, rgba(255,255,255,0.1) 40%, rgba(255,255,255,0.03) 70%, transparent 100%);
  border: 2px solid rgba(255, 255, 255, 0.55);
  box-shadow: 0 0 20px rgba(255, 255, 255, 0.3);
}
.wave2 { 
  width: 280px; 
  height: 280px; 
  animation-delay: 0.25s; 
  background: radial-gradient(circle, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0.08) 40%, rgba(255,255,255,0.02) 70%, transparent 100%);
  border: 2px solid rgba(255, 255, 255, 0.45);
  box-shadow: 0 0 15px rgba(255, 255, 255, 0.25);
}
.wave3 { 
  width: 340px; 
  height: 340px; 
  animation-delay: 0.5s; 
  background: radial-gradient(circle, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.06) 40%, rgba(255,255,255,0.015) 70%, transparent 100%);
  border: 2px solid rgba(255, 255, 255, 0.35);
}
.wave4 { 
  width: 400px; 
  height: 400px; 
  animation-delay: 0.75s; 
  background: radial-gradient(circle, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.04) 40%, rgba(255,255,255,0.01) 70%, transparent 100%);
  border: 1px solid rgba(255, 255, 255, 0.25);
}
.wave5 { 
  width: 440px; 
  height: 440px; 
  animation-delay: 1s; 
  background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.02) 40%, transparent 70%);
  border: 1px solid rgba(255, 255, 255, 0.15);
}

@keyframes wave {
  0% {
    transform: scale(1);
    opacity: 0.95;
    border-width: 3px;
  }
  50% {
    opacity: 0.5;
    border-width: 2px;
  }
  100% {
    transform: scale(1.5);
    opacity: 0.05;
    border-width: 1px;
  }
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 30px rgba(255, 255, 255, 0.8), 0 0 60px rgba(255, 255, 255, 0.5);
  }
  50% {
    transform: scale(1.2);
    box-shadow: 0 0 40px rgba(255, 255, 255, 1), 0 0 80px rgba(255, 255, 255, 0.7);
  }
}

.calling-info {
  text-align: center;
  color: white;
  z-index: 10;
}

.calling-avatar {
  font-size: 120px;
  margin-bottom: 20px;
  filter: drop-shadow(0 4px 20px rgba(0, 0, 0, 0.3));
}

.calling-name {
  font-size: 36px;
  font-weight: bold;
  margin-bottom: 8px;
}

.calling-number {
  font-size: 18px;
  opacity: 0.8;
  margin-bottom: 15px;
}

.calling-status {
  font-size: 20px;
  opacity: 0.9;
  margin-bottom: 20px;
}

.ringing-icon {
  animation: ring 1s infinite;
  margin-right: 8px;
}

@keyframes ring {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-10deg); }
  75% { transform: rotate(10deg); }
}

.calling-timer {
  font-size: 56px;
  font-weight: bold;
  font-family: 'Courier New', monospace;
  text-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.calling-controls {
  display: flex;
  justify-content: center;
  gap: 30px;
  margin-top: 60px;
  z-index: 10;
}

.control-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
}

.control-btn:hover {
  transform: scale(1.1);
}

.control-btn span:first-child {
  font-size: 32px;
}

.control-label {
  font-size: 12px;
  color: white;
  margin-top: 5px;
}

.hangup-btn {
  background: rgba(255, 255, 255, 0.9);
}

.hangup-btn span:first-child {
  color: #dc3545;
}

.hangup-btn .control-label {
  color: #333;
}
</style>