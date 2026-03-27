<template>
  <div class="app-viewport" :class="{ 'is-dev-page': isDevPage }">
    <!-- 纯页面（无侧边栏） -->
    <template v-if="isPurePage">
      <NuxtPage />
    </template>

    <!-- 常规页面（有侧边栏） -->
    <div v-else class="tablet-frame">
      <aside class="side-nav">
        <div class="nav-links">
          <div class="nav-item" :class="{ 'active-custom': currentPath === '/' }" @click="handleNavigate('/')">🏠<br>首页</div>
          <div class="nav-item" :class="{ 'active-custom': currentPath === '/health' }" @click="handleNavigate('/health')">❤️<br>健康</div>
          <div class="nav-item" :class="{ 'active-custom': currentPath === '/entertainment' }" @click="handleNavigate('/entertainment')">🎵<br>娱乐</div>
          <div class="nav-item" :class="{ 'active-custom': currentPath === '/learning' }" @click="handleNavigate('/learning')">🧩<br>益智</div> 
        </div>
        <!-- ⭐ 点击张爷爷直接跳转设置页 -->
        <div class="user-zone" @click="goToSettings">
          <div class="avatar">👴</div>
          <div class="name">张爷爷</div>
        </div>
      </aside>

      <main class="main-content">
        <NuxtPage />
      </main>

      <!-- 阿康悬浮球 -->
      <div 
        v-if="!ui.akon && currentPath !== '/'"
        class="akon-ball"
        :class="{ 'is-docked': ball.status === 'half' }"
        :style="{ left: ball.x + 'px', top: ball.y + 'px', opacity: ball.isDragging ? 1 : (ball.status === 'half' ? 0.5 : 1) }"
        @mousedown="handleDragStart"
        @touchstart.passive="handleDragStart"
      >
        <span class="akon-icon">🤖</span>
      </div>

            <!-- 阿康对话 -->
      <div v-if="ui.akon" class="akon-modal" @click.self="closeAkon">
        <div class="akon-panel" @click.stop>
          <!-- 头部 -->
          <div class="akon-header">
            <span class="akon-avatar">🤖</span>
            <span class="akon-title">阿康助手</span>
            <button class="akon-close-btn" @click="closeAkon">✕</button>
          </div>
          <!-- 消息区域 -->
          <div class="akon-messages" ref="messagesRef">
            <div v-for="(msg, idx) in akonMessages" :key="idx" class="akon-msg" :class="msg.role">
              <div class="msg-avatar">{{ msg.role === 'user' ? '👴' : '🤖' }}</div>
              <div class="msg-text">{{ msg.content }}</div>
            </div>
            <div v-if="akonLoading" class="akon-msg assistant">
              <div class="msg-avatar">🤖</div>
              <div class="msg-text loading">思考中...</div>
            </div>
          </div>
          <!-- 快捷按钮 -->
          <div class="akon-shortcuts">
            <button class="shortcut-btn" @click="sendQuick('今天天气')">🌤️ 天气</button>
            <button class="shortcut-btn" @click="sendQuick('现在几点')">🕐 时间</button>
            <button class="shortcut-btn" @click="sendQuick('回首页')">🏠 首页</button>
          </div>
          <!-- 输入区域 -->
          <div class="akon-input-row">
            <button 
              class="akon-voice-btn" 
              :class="{ 'is-recording': isListening }"
              @click="toggleVoiceInput"
              :disabled="akonLoading"
              title="语音输入"
            >
              {{ isListening ? '🔴' : '🎤' }}
            </button>
            <input v-model="akonInput" class="akon-input" placeholder="请输入或点击麦克风语音输入..." @keyup.enter="sendAkonMessage" ref="akonInputRef" />
            <button class="akon-send-btn" @click="sendAkonMessage" :disabled="!akonInput.trim() || akonLoading">发送</button>
          </div>
        </div>
        </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { initStore, setCurrentPage, isGameActive } from './core/systemStore.js'

const route = useRoute()
const router = useRouter()

// ==================== 自动检测后端地址 ====================
const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  const host = window.location.hostname
  return host || 'localhost'
}

const FLASK_PORT = 5000
const backendHost = getBackendHost()
const backendUrl = `http://${backendHost}:${FLASK_PORT}`

console.log('[App] 后端地址:', backendUrl)

// 纯页面
const isPurePage = computed(() => ['projection', 'developer'].includes(route.name))
const isDevPage = computed(() => route.name === 'developer')
const currentPath = computed(() => route.path)

// 后端连接状态
const backendConnected = ref(false)
// 标记是否已经初始化过（用于重启后回到首页）
const hasInitialized = ref(false)
// ⭐ 标记是否正在重新开始
const isRestarting = ref(false)

// UI状态
const ui = reactive({ menu: false, akon: false })
const ball = reactive({
  x: 0, y: 0, status: 'half', isDragging: false,
  startX: 0, startY: 0, moveDist: 0
})

// 阿康对话状态
import { getState, addChatMessage } from './core/systemStore'
const systemState = getState()
const akonMessages = computed(() => systemState.value.chatMessages)  // ⭐ 使用全局聊天记录
const akonInput = ref('')
const akonLoading = ref(false)
const messagesRef = ref(null)
const akonInputRef = ref(null)

// ==================== 语音功能（后端处理） ====================
const isListening = ref(false)  // 后端监听状态
const isSpeaking = ref(false)   // 语音播报状态
let synth = null

// 初始化语音合成（仅用于播报）
function initVoice() {
  // 初始化语音合成（浏览器内置）
  if ('speechSynthesis' in window) {
    synth = window.speechSynthesis
    console.log('[语音] 语音合成已初始化')
  }
}

// ⭐ 接收后端语音指令
function setupVoiceSocketHandlers() {
  // 语音状态更新
  socket.on('voice_status', (data) => {
    console.log('[语音] 状态:', data.status, data.message)
    if (data.status === 'listening') {
      isListening.value = true
    } else {
      isListening.value = false
    }
  })
  
  // ⭐ 唤醒成功
  socket.on('voice_wake_up', (data) => {
    console.log('[语音] 唤醒成功:', data.response)
    // 打开对话框
    ui.akon = true
    ball.status = 'full'
    // 显示系统回应
    akonMessages.value.push({ role: 'assistant', content: data.response })
    // 显示用户说的话
    if (data.user_text) {
      akonMessages.value.push({ role: 'user', content: data.user_text })
    }
  })
  
  // ⭐ 用户说话识别结果 - 由systemStore.js处理，避免重复显示
  // socket.on('voice_user_speak', (data) => {
  //   console.log('[语音] 用户说:', data.text)
  //   // 只添加到消息列表，不自动发送，避免重复处理
  //   akonMessages.value.push({ role: 'user', content: data.text })
  //   // 不填充到输入框，避免重复显示
  // })
  
  // ⭐ 语音播报指令（后端让前端播报）
  socket.on('voice_speaking', (data) => {
    if (data.status === 'start' && data.text) {
      // 过滤掉[ACTION:]标记和表情符号，不播报action内容
      let cleanText = data.text
      // 移除[ACTION:]标记
      cleanText = cleanText.replace(/\[ACTION:\]/g, '').trim()
      // 移除表情符号（匹配常见的表情符号）
      cleanText = cleanText.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '').trim()
      if (cleanText) {
        console.log('[语音] 开始播报:', cleanText)
        isSpeaking.value = true
        // 启用前端播报，由前端统一负责所有语音播报
        speak(cleanText)
      }
    } else if (data.status === 'end') {
      console.log('[语音] 播报结束')
      isSpeaking.value = false
    }
  })
  
  // ⭐ 语音AI回复事件 - 由systemStore.js处理，避免重复显示
  // socket.on('voice_ai_response', (data) => {
  //   console.log('[语音] AI回复:', data.ai_response)
  //   // 添加AI回复到消息列表
  //   akonMessages.value.push({ role: 'assistant', content: data.ai_response })
  //   // 语音播报回复
  //   speak(data.ai_response)
  // })
  
  // 唤醒超时
  socket.on('voice_sleep', (data) => {
    console.log('[语音] 唤醒超时:', data.message)
  })
}

// 语音合成（前端播报）
function speak(text) {
  if (!synth || !text) return
  
  // 取消之前的语音
  synth.cancel()
  
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 1.0
  utterance.pitch = 1.0
  
  utterance.onstart = () => {
    isSpeaking.value = true
  }
  
  utterance.onend = () => {
    isSpeaking.value = false
  }
  
  synth.speak(utterance)
}

// ⭐ 语音输入按钮（触发语音输入）
function toggleVoiceInput() {
  // 通知后端开始语音输入
  socket.emit('start_voice_input')
  console.log('[语音] 开始语音输入，请说话...')
  // 显示录音状态
  isListening.value = true
}

let socket = null

// 动态控制body滚动
watch(isDevPage, (dev) => {
  if (typeof document !== 'undefined') {
    if (dev) {
      document.body.style.overflow = 'auto'
      document.documentElement.style.overflow = 'auto'
    } else {
      document.body.style.overflow = 'hidden'
      document.documentElement.style.overflow = 'hidden'
    }
  }
}, { immediate: true })

// ==================== 导航 ====================
async function handleNavigate(page) {
  // 如果游戏活跃，先停止游戏
  if (isGameActive() && socket && socket.connected) {
    console.log('[App] 游戏活跃，先停止游戏')
    socket.emit('game_control', { action: 'stop' })
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  
  if (backendConnected.value && socket) {
    socket.emit('navigate', { page, source: 'user' })
  } else {
    router.push(page)
  }
}

// ⭐ 点击张爷爷直接跳转设置页
function goToSettings() {
  handleNavigate('/settings')
}

// ==================== Socket ====================
onMounted(() => {
  ball.x = window.innerWidth - 45
  ball.y = window.innerHeight / 2 - 45
  
  window.addEventListener('mousemove', handleDragging)
  window.addEventListener('mouseup', handleDragEnd)
  window.addEventListener('touchmove', handleDragging, { passive: false })
  window.addEventListener('touchend', handleDragEnd)
  
  // ⭐ 初始化语音功能（仅初始化语音合成，语音识别由后端处理）
  initVoice()
  
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000
  })
  
  // ⭐ 初始化系统Store（订阅后端状态）
  initStore(socket)
  
  socket.on('connect', () => {
    backendConnected.value = true
    console.log('[App] 后端已连接')
    
    // 只在首次连接时检查是否需要导航到首页
    if (!hasInitialized.value) {
      hasInitialized.value = true
      socket.emit('get_state', { client: 'tablet', first_connect: true })
    }
  })
  
  socket.on('disconnect', () => {
    backendConnected.value = false
    console.log('[App] 后端断开')
  })
  
  socket.on('connect_error', (err) => {
    backendConnected.value = false
    console.log('[App] 连接错误:', err.message)
  })
  
  // 收到系统状态时，检查是否需要导航
  socket.on('system_state', (data) => {
    // ⭐ 如果收到 READY 状态，重置重新开始标记
    if (data.game?.status === 'READY') {
      isRestarting.value = false
    }
    
    // 如果游戏状态是IDLE，检查当前页面
    // ⭐ 但如果正在重新开始，忽略这个状态
    if (data.game?.status === 'IDLE' && !isRestarting.value) {
      // 如果当前在训练页面，返回游戏列表
      if (route.path === '/training') {
        console.log('[App] 游戏已停止，返回游戏列表')
        router.push('/learning')
      }
    }
  })
  
  socket.on('navigate_to', (data) => {
    if (!isPurePage.value && route.path !== data.page) {
      router.push(data.page)
    }
  })
  
  socket.on('navigate_error', (data) => {
    alert(data.message || '请先退出当前游戏')
  })
  
  // ⭐ 设置语音Socket事件处理
  setupVoiceSocketHandlers()
  
  // ⭐ 监听路由变化，同步页面状态
  watch(() => route.path, (newPath) => {
    console.log('[App] 页面切换:', newPath)
    // /developer 和 /projection 不参与管理，不发送页面切换事件
    if (!isPurePage.value) {
      setCurrentPage(newPath)
    }
  }, { immediate: true })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
  window.removeEventListener('mousemove', handleDragging)
  window.removeEventListener('mouseup', handleDragEnd)
  window.removeEventListener('touchmove', handleDragging)
  window.removeEventListener('touchend', handleDragEnd)
})

// ==================== 球体拖拽 ====================
function updateDockPos() {
  const winW = window.innerWidth
  if (ball.x < winW / 2) {
    ball.x = ball.status === 'half' ? -45 : 20
  } else {
    ball.x = ball.status === 'half' ? winW - 45 : winW - 110
  }
}

function handleDragStart(e) {
  ball.isDragging = true
  ball.moveDist = 0
  const event = e.touches ? e.touches[0] : e
  ball.startX = event.clientX - ball.x
  ball.startY = event.clientY - ball.y
}

function handleDragging(e) {
  if (!ball.isDragging) return
  const event = e.touches ? e.touches[0] : e
  ball.x = event.clientX - ball.startX
  ball.y = event.clientY - ball.startY
  ball.moveDist++
}

function handleDragEnd() {
  if (!ball.isDragging) return
  ball.isDragging = false
  if (ball.moveDist < 5) {
    if (ball.status === 'half') ball.status = 'full'
    else ui.akon = true
  } else {
    ball.status = 'half'
  }
  updateDockPos()
}

function closeAkon() {
  ui.akon = false
  ball.status = 'half'
  updateDockPos()
}

// ==================== 阿康对话 ====================
async function sendAkonMessage() {
  const text = akonInput.value.trim()
  if (!text || akonLoading.value) return
  
  // 添加用户消息到全局聊天记录
  addChatMessage({ role: 'user', content: text })
  akonInput.value = ''
  akonLoading.value = true
  
  // 滚动到底部
  await nextTick()
  scrollToBottom()
  
  try {
    // 调用后端API
    const response = await fetch(`${backendUrl}/api/akon/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
    
    const data = await response.json()
    
    // 移除[ACTION:]标记
    let processedResponse = data.response.replace(/\[ACTION:\]/g, '').trim()
    // 添加回复到全局聊天记录
    addChatMessage({ role: 'assistant', content: processedResponse })
    
    // 启用前端播报，确保手动输入时也能语音播报
    speak(processedResponse)
    
  } catch (error) {
    addChatMessage({ role: 'assistant', content: '抱歉，网络出了点问题。' })
    speak('抱歉，网络出了点问题。')
  }
  
  akonLoading.value = false
  await nextTick()
  scrollToBottom()
}

function sendQuick(text) {
  akonInput.value = text
  sendAkonMessage()
}

function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}
</script>

<style>
* {
  -webkit-tap-highlight-color: transparent; 
  touch-action: manipulation;
  margin: 0; padding: 0; box-sizing: border-box;
}

html, body { 
  width: 100vw; 
  height: 100vh; 
  background: #000; 
  font-family: 'PingFang SC', sans-serif;
}

.app-viewport { 
  width: 100vw; 
  height: 100vh; 
  display: flex; 
  justify-content: center; 
  align-items: center; 
}

.app-viewport.is-dev-page {
  height: auto;
  min-height: 100vh;
  align-items: flex-start;
}

.tablet-frame {
  width: 100vw; height: 62.5vw; 
  max-height: 100vh; max-width: 160vh;
  background: #FFFFFF; display: flex; position: relative; overflow: hidden;
}

.side-nav {
  width: 140px; background: #F8F9FA; display: flex; flex-direction: column;
  padding: 40px 0; border-right: 1px solid #EEE; z-index: 100;
}
.nav-links { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 30px; }

.nav-item { 
  cursor: pointer; color: #333; font-size: 22px; font-weight: bold; 
  text-align: center; width: 100px; padding: 15px 0; border-radius: 20px;
  transition: all 0.2s;
}
.active-custom { background: #FF7222 !important; color: #FFF !important; }

.main-content { 
  flex: 1; height: 100%; overflow-y: auto; 
  padding: 40px; scrollbar-width: none; 
}
.main-content::-webkit-scrollbar { display: none; }

.akon-ball {
  position: fixed; width: 90px; height: 90px; background: #FF7222;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  z-index: 500; cursor: pointer;
  transform: translate3d(0, 0, 0); 
  will-change: left, top;
  transition: opacity 0.3s;
  box-shadow: 0 8px 25px rgba(255,114,34,0.4);
  touch-action: none;
}
.akon-icon { font-size: 45px; pointer-events: none; }

.user-zone { text-align: center; position: relative; cursor: pointer; margin-top: auto; }
.avatar { font-size: 50px; }
.name { font-size: 20px; font-weight: bold; margin-top: 5px; }

.akon-modal { position: absolute; inset: 0; background: rgba(0,0,0,0.4); z-index: 600; display: flex; align-items: flex-end; }
.akon-panel { width: 100%; background: #FFF; border-radius: 40px 40px 0 0; padding: 30px; max-height: 70%; display: flex; flex-direction: column; }

/* 头部 */
.akon-header { display: flex; align-items: center; margin-bottom: 20px; }
.akon-avatar { font-size: 40px; margin-right: 10px; }
.akon-title { flex: 1; font-size: 26px; font-weight: bold; }
.akon-close-btn { width: 44px; height: 44px; background: #F0F0F0; border: none; border-radius: 50%; font-size: 20px; cursor: pointer; }

/* 消息区域 */
.akon-messages { flex: 1; overflow-y: auto; margin-bottom: 15px; }
.akon-msg { display: flex; margin-bottom: 12px; }
.akon-msg.user { flex-direction: row-reverse; }
.msg-avatar { width: 40px; height: 40px; background: #F5F5F5; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 22px; flex-shrink: 0; }
.msg-text { max-width: 70%; padding: 12px 16px; border-radius: 16px; font-size: 20px; line-height: 1.4; margin: 0 10px; }
.akon-msg.user .msg-text { background: #FF7222; color: #FFF; }
.akon-msg.assistant .msg-text { background: #F5F5F5; }
.msg-text.loading { color: #999; }

/* 快捷按钮 */
.akon-shortcuts { display: flex; gap: 10px; margin-bottom: 15px; }
.shortcut-btn { padding: 10px 16px; background: #FFF3E0; border: 2px solid #FFD6B3; border-radius: 20px; font-size: 18px; color: #FF7222; cursor: pointer; }

/* 输入区域 */
.akon-input-row { display: flex; gap: 10px; align-items: center; }
.akon-voice-btn { width: 50px; height: 50px; background: #F5F5F5; border: 2px solid #E0E0E0; border-radius: 50%; font-size: 24px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.3s; }
.akon-voice-btn:hover { background: #FFF3E0; border-color: #FF7222; }
.akon-voice-btn.is-recording { background: #FF4444; border-color: #FF4444; animation: pulse 1s infinite; }
.akon-voice-btn:disabled { opacity: 0.5; cursor: not-allowed; }
@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}
.akon-input { flex: 1; padding: 14px 18px; border: 2px solid #E0E0E0; border-radius: 24px; font-size: 20px; outline: none; }
.akon-input:focus { border-color: #FF7222; }
.akon-send-btn { padding: 14px 28px; background: #FF7222; color: #FFF; border: none; border-radius: 24px; font-size: 20px; font-weight: bold; cursor: pointer; }
.akon-send-btn:disabled { background: #CCC; cursor: not-allowed; }
</style>
