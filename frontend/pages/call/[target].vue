<template>
  <div class="call-page">
    <div v-if="currentState === 'calling'" class="calling-container">
      <div v-if="isVideoOn" class="video-background">
        <img src="http://192.168.137.25:8080/video" alt="IP Camera Feed" class="video-feed" />
        <div class="video-overlay"></div>
      </div>

      <div class="calling-bg" :class="{ 'emergency-call': isEmergency, 'normal-call': !isEmergency }">
        <div class="wave-container">
          <div class="wave wave1"></div>
          <div class="wave wave2"></div>
          <div class="wave wave3"></div>
          <div class="wave wave4"></div>
          <div class="wave wave5"></div>
        </div>

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

const currentState = ref('calling')
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

let audioContext = null
let ringtoneAudio = ref(null)

const emergencyContacts = [
  { id: 'nurse', name: '护理站', phone: '010-12345678', avatar: '🏥' },
  { id: 'police', name: '110', phone: '110', avatar: '👮' },
  { id: 'ambulance', name: '120', phone: '120', avatar: '🚑' },
]

const playRingTone = () => {
  try {
    if (ringtoneAudio.value) {
      ringtoneAudio.value.pause()
      ringtoneAudio.value = null
    }
    
    ringtoneAudio.value = new Audio()
    ringtoneAudio.value.src = isEmergency.value 
      ? '/sounds/call/电话呼叫声.wav' 
      : '/sounds/call/通话呼叫.mp3'
    ringtoneAudio.value.loop = true
    ringtoneAudio.value.volume = isEmergency.value ? 0.6 : 0.25
    ringtoneAudio.value.play().catch(e => {
      playFallbackRingtone()
    })
  } catch (e) {
    playFallbackRingtone()
  }
}

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

const stopRingTone = () => {
  if (ringtoneAudio.value) {
    ringtoneAudio.value.pause()
    ringtoneAudio.value = null
  }
  
  if (ringTimer) {
    clearInterval(ringTimer)
    ringTimer = null
  }
  if (audioContext) {
    audioContext.close()
    audioContext = null
  }
}

const startCallProcess = () => {
  callDuration.value = '00:00'
  playRingTone()
  
  autoExitTimer = setTimeout(() => {
    hangUp()
  }, 15000)
  
  let seconds = 0
  callTimer = setInterval(() => {
    seconds++
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0')
    const secs = (seconds % 60).toString().padStart(2, '0')
    callDuration.value = `${mins}:${secs}`
  }, 1000)
}

const toggleMute = () => {
  isMuted.value = !isMuted.value
}

const toggleSpeaker = () => {
  isSpeakerOn.value = !isSpeakerOn.value
}

const toggleVideo = () => {
  isVideoOn.value = !isVideoOn.value
}

const endCall = () => {
  stopRingTone()
  
  if (callTimer) {
    clearInterval(callTimer)
    callTimer = null
  }
  
  if (autoExitTimer) {
    clearTimeout(autoExitTimer)
    autoExitTimer = null
  }
  
  isVideoOn.value = false
  router.push('/call')
}

const callEmergency = (type) => {
  isEmergency.value = true
  isVideoOn.value = true
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

onMounted(() => {
  const target = route.params.target
  if (target === 'nurse') {
    callEmergency('护理站')
  }
})

onUnmounted(() => {
  stopRingTone()
  if (callTimer) {
    clearInterval(callTimer)
    callTimer = null
  }
  if (autoExitTimer) {
    clearTimeout(autoExitTimer)
    autoExitTimer = null
  }
})
</script>

<style scoped>
.call-page {
  min-height: 100vh;
  background: #f5f5f5;
}

.calling-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}

.video-background {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
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
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.3);
}

.calling-bg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 2;
}

.calling-bg.emergency-call {
  background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
}

.calling-bg.normal-call {
  background: linear-gradient(135deg, #33b555 0%, #2d8a4e 100%);
}

.wave-container {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 30px;
}

.wave {
  width: 6px;
  height: 40px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 3px;
  animation: wave 1.2s ease-in-out infinite;
}

.wave1 { animation-delay: 0s; }
.wave2 { animation-delay: 0.1s; }
.wave3 { animation-delay: 0.2s; }
.wave4 { animation-delay: 0.3s; }
.wave5 { animation-delay: 0.4s; }

@keyframes wave {
  0%, 100% { transform: scaleY(0.5); }
  50% { transform: scaleY(1); }
}

.calling-info {
  text-align: center;
  color: white;
}

.calling-avatar {
  font-size: 80px;
  margin-bottom: 20px;
}

.calling-name {
  font-size: 36px;
  font-weight: bold;
  margin-bottom: 10px;
}

.calling-number {
  font-size: 20px;
  opacity: 0.9;
  margin-bottom: 15px;
}

.calling-status {
  font-size: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 20px;
}

.ringing-icon {
  animation: ring 1s ease-in-out infinite;
}

@keyframes ring {
  0%, 100% { transform: rotate(-15deg); }
  50% { transform: rotate(15deg); }
}

.calling-timer {
  font-size: 48px;
  font-weight: bold;
  margin-top: 10px;
}

.calling-controls {
  display: flex;
  gap: 30px;
  margin-top: 40px;
}

.control-btn {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  cursor: pointer;
  transition: all 0.3s;
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

.control-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: scale(1.1);
}

.control-label {
  font-size: 12px;
}

.hangup-btn {
  background: #dc3545 !important;
}

.hangup-btn:hover {
  background: #c82333 !important;
}
</style>
