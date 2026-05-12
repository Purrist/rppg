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
          <div class="nav-item" :class="{ 'active-custom': currentPath === '/call' }" @click="handleNavigate('/call')">📞<br>通话</div>
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
        @touchstart="handleDragStart"
        @click="handleBallClick"
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
              <div class="msg-text">
                {{ msg.content }}
                <span v-if="isTyping && idx === akonMessages.length - 1" class="cursor">|</span>
              </div>
            </div>
            <div v-if="akonLoading" class="akon-msg assistant">
              <div class="msg-avatar">🤖</div>
              <div class="msg-text loading">
                思考中<span class="dot dot1">.</span><span class="dot dot2">.</span><span class="dot dot3">.</span>
              </div>
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
const isPurePage = computed(() => ['projection', 'developer', 'screen-saver'].includes(route.name))
const isDevPage = computed(() => route.name === 'developer')
const currentPath = computed(() => route.path)

// ⭐ 屏保相关
const SCREEN_SAVER_DELAY = 4 * 60 * 1000 
let screenSaverTimer = null

function resetScreenSaverTimer() {
  if (screenSaverTimer) clearTimeout(screenSaverTimer)
  screenSaverTimer = setTimeout(() => {
    if (!isPurePage.value && !ui.akon && route.path !== '/screen-saver') {
      router.push('/screen-saver')
    }
  }, SCREEN_SAVER_DELAY)
}

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
import { getState, addChatMessage, setVoiceLoading } from './core/systemStore'
const systemState = getState()
const globalMessages = computed(() => systemState.value.chatMessages)  // ⭐ 使用全局聊天记录
const akonMessages = ref([])  // 本地聊天消息数组，用于实现打字机效果
const akonInput = ref('')
const akonLoading = computed(() => systemState.value.voice?.isLoading || false)  // ⭐ 使用全局loading状态
const messagesRef = ref(null)
const akonInputRef = ref(null)

// 打字机效果
const typingText = ref('')   // 正在逐字显示的文字
const isTyping = ref(false)  // 是否正在打字

// 监听全局消息变化，同步到本地（但在打字时不同步，避免覆盖打字效果）
watch(globalMessages, (newMessages) => {
  if (!isTyping.value) {
    akonMessages.value = [...newMessages]
  }
}, { deep: true })

// 监听消息变化，自动滚动到底部
watch(akonMessages, async () => {
  await nextTick()
  scrollToBottom()
}, { deep: true })



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
    // 不显示系统回应，只由systemStore处理
  })
  
  // ⭐ 用户说话识别结果 - 由systemStore.js处理，避免重复显示
  // socket.on('voice_user_speak', (data) => {
  //   console.log('[语音] 用户说:', data.text)
  //   // 只添加到消息列表，不自动发送，避免重复处理
  //   akonMessages.value.push({ role: 'user', content: data.text })
  //   // 不填充到输入框，避免重复显示
  // })
  
  // ⭐ 语音播报指令（后端直接播报，前端不播放）
  socket.on('voice_speaking', (data) => {
    if (data.status === 'start' && data.text) {
      console.log('[语音] 后端开始播报:', data.text)
      isSpeaking.value = true
    } else if (data.status === 'end') {
      console.log('[语音] 后端播报结束')
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

// ⭐ 统一处理AI回复（打字机效果 + 语音）
async function handleAIResponse(event) {
  const { text, source } = event.detail
  console.log('[App] 收到AI回复:', text, '来源:', source)
  
  // 插入一条空的AI消息到本地数组
  akonMessages.value.push({
    role: 'assistant',
    content: '',
    typing: true
  })
  
  // 滚动到底部
  await nextTick()
  scrollToBottom()
  
  // 开始逐字打字
  await startTypeWriter(text, source)
}

// ==================== Socket ====================
onMounted(() => {
  ball.x = window.innerWidth - 45
  ball.y = window.innerHeight / 2 - 45
  
  window.addEventListener('mousemove', handleDragging)
  window.addEventListener('mouseup', handleDragEnd)
  window.addEventListener('touchmove', handleDragging, { passive: false })
  window.addEventListener('touchend', handleDragEnd)
  
  // 初始化本地消息数组
  akonMessages.value = [...globalMessages.value]
  
  // 监听全局事件，打开Akon面板
  window.addEventListener('openAkon', async (event) => {
    ui.akon = true
    // 滚动到底部
    await nextTick()
    scrollToBottom()
    
    // 如果需要开始录音
    if (event.detail && event.detail.startRecording) {
      // 调用toggleVoiceInput函数开始录音
      toggleVoiceInput()
    }
  })
  
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
    
    // ⭐ 检测毫米波雷达数据，有人靠近时退出屏保
    if (showScreenSaver.value) {
      const distance = data.perception?.physiology?.raw?.distance
      const distanceValid = data.perception?.physiology?.raw?.distance_valid
      const isHuman = data.perception?.physiology?.raw?.is_human
      
      if (distanceValid && distance < 150 && isHuman) {
        console.log('[屏保] 检测到有人靠近，退出屏保')
        exitScreenSaver()
      }
    }
  })
  
  socket.on('navigate_to', (data) => {
    if (!isPurePage.value && route.path !== data.page) {
      router.push(data.page)
      ui.akon = false
    }
  })
  
  socket.on('navigate_error', (data) => {
    alert(data.message || '请先退出当前游戏')
  })
  
  // ⭐ 设置语音Socket事件处理
  setupVoiceSocketHandlers()
  
  // ⭐ 监听AI回复事件（统一处理所有来源的AI回复）
  window.addEventListener('ai_response', handleAIResponse)
  
  // ⭐ 监听路由变化，同步页面状态
  watch(() => route.path, (newPath) => {
    console.log('[App] 页面切换:', newPath)
    // /developer 和 /projection 不参与管理，不发送页面切换事件
    if (!isPurePage.value) {
      setCurrentPage(newPath)
    }
  }, { immediate: true })
  
  // ⭐ 屏保相关事件监听
  function handleActivity() {
    // 只有在非屏保页面时才重置计时器
    if (route.path !== '/screen-saver') {
      resetScreenSaverTimer()
    }
  }
  
  window.addEventListener('click', handleActivity)
  window.addEventListener('touchstart', handleActivity)
  window.addEventListener('keydown', handleActivity)
  
  // ⭐ 监听退出屏保事件
  window.addEventListener('exit-screen-saver', () => {
    resetScreenSaverTimer()
  })
  
  // ⭐ 初始化屏保计时器
  resetScreenSaverTimer()
})

onUnmounted(() => {
  if (socket) socket.disconnect()
  window.removeEventListener('mousemove', handleDragging)
  window.removeEventListener('mouseup', handleDragEnd)
  window.removeEventListener('touchmove', handleDragging, { passive: false })
  window.removeEventListener('touchend', handleDragEnd)
  window.removeEventListener('ai_response', handleAIResponse)
})

// ==================== 球体拖拽 ====================
function updateDockPos() {
  const winW = window.innerWidth
  const winH = window.innerHeight
  const ballSize = 90
  
  // 确保球不会超出屏幕上下边界
  ball.y = Math.max(20, Math.min(winH - ballSize - 20, ball.y))
  
  // 吸附到屏幕左右边缘
  if (ball.x < winW / 2) {
    // 左边缘
    ball.x = ball.status === 'half' ? 0 : 20
  } else {
    // 右边缘
    ball.x = ball.status === 'half' ? winW - ballSize : winW - ballSize - 20
  }
}

function handleDragStart(e) {
  // 阻止默认行为，避免页面滚动
  if (e.cancelable) {
    e.preventDefault()
  }
  ball.isDragging = true
  ball.moveDist = 0
  const event = e.touches ? e.touches[0] : e
  ball.startX = event.clientX - ball.x
  ball.startY = event.clientY - ball.y
  
  // 拖动开始时设置为完全显示状态
  ball.status = 'full'
  
  // 添加拖动样式
  const ballElement = document.querySelector('.akon-ball')
  if (ballElement) {
    ballElement.style.transition = 'none' // 禁用过渡效果以提高拖动流畅度
  }
}

function handleDragging(e) {
  if (!ball.isDragging) return
  
  // 阻止默认行为，避免页面滚动
  if (e.cancelable) {
    e.preventDefault()
  }
  
  const event = e.touches ? e.touches[0] : e
  const winW = window.innerWidth
  const winH = window.innerHeight
  const ballSize = 90
  
  // 计算新位置，确保不会超出屏幕
  let newX = event.clientX - ball.startX
  let newY = event.clientY - ball.startY
  
  // 边界检查
  newX = Math.max(0, Math.min(winW - ballSize, newX))
  newY = Math.max(0, Math.min(winH - ballSize, newY))
  
  // 直接更新位置，不使用setTimeout，提高响应速度
  ball.x = newX
  ball.y = newY
  ball.moveDist++
}

function handleDragEnd(e) {
  if (!ball.isDragging) return
  ball.isDragging = false
  
  // 恢复过渡效果
  const ballElement = document.querySelector('.akon-ball')
  if (ballElement) {
    ballElement.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
  }
  
  if (ball.moveDist < 3) {
    // 点击操作
    if (ball.status === 'half') {
      // 从半隐藏状态点击，变为完全显示
      ball.status = 'full'
    } else {
      // 从完全显示状态点击，打开对话框
      ui.akon = true
      // 滚动到底部
      nextTick(() => {
        scrollToBottom()
      })
    }
  } else {
    // 拖动操作，吸附到边缘
    ball.status = 'half'
  }
  
  // 平滑动画吸附
  updateDockPos()
}

function closeAkon() {
  ui.akon = false
  ball.status = 'half'
  updateDockPos()
}

function handleBallClick(e) {
  // 阻止默认行为，避免与拖动事件冲突
  if (e.cancelable) {
    e.preventDefault()
  }
  
  // 只有在非拖动状态下才处理点击
  if (!ball.isDragging) {
    if (ball.status === 'half') {
      // 从半隐藏状态点击，变为完全显示
      ball.status = 'full'
    } else {
      // 从完全显示状态点击，打开对话框
      ui.akon = true
      // 滚动到底部
      nextTick(() => {
        scrollToBottom()
      })
    }
    updateDockPos()
  }
}

// ==================== 阿康对话 ====================
async function sendAkonMessage() {
  const text = akonInput.value.trim()
  if (!text || akonLoading.value) return
  
  // 添加用户消息到全局聊天记录
  addChatMessage({ role: 'user', content: text })
  akonInput.value = ''
  setVoiceLoading(true)  // ⭐ 设置思考中状态
  
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
    
    // 触发ai_response事件，统一处理打字机和语音
    window.dispatchEvent(new CustomEvent('ai_response', { 
      detail: { text: processedResponse, source: 'text' } 
    }))
    
  } catch (error) {
    // 触发ai_response事件
    window.dispatchEvent(new CustomEvent('ai_response', { 
      detail: { text: '抱歉，网络出了点问题。', source: 'text' } 
    }))
  }
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

async function startTypeWriter(fullText, source = 'text') {
  isTyping.value = true
  typingText.value = ''

  for (let i = 0; i < fullText.length; i++) {
    typingText.value += fullText[i]
    
    // 把最新文字更新到本地消息列表
    const lastMsg = akonMessages.value[akonMessages.value.length - 1]
    if (lastMsg) {
      lastMsg.content = typingText.value
    }

    // 每字延迟 80~150 ms（自己调速度）
    await new Promise(r => setTimeout(r, 100))
  }

  isTyping.value = false
  
  // 打字完成后，添加完整的消息到全局记录
  addChatMessage({ role: 'assistant', content: fullText })
  
  // ⭐ 关键修复：当来源是 voice 时，后端已经播报过了，不再重复触发
  // 只有来源是 text（用户手动输入）时，才通知后端播报
  if (socket && socket.connected && source !== 'voice') {
    socket.emit('speak_text', { text: fullText, source })
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
.nav-links { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 22px; }

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
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 8px 25px rgba(255,114,34,0.4);
  touch-action: none;
  user-select: none;
}

.akon-ball:hover {
  transform: scale(1.05);
  box-shadow: 0 10px 30px rgba(255,114,34,0.5);
}

.akon-ball.is-docked {
  transform: scale(0.95);
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

/* 思考中点闪烁 - 三个点依次出现 */
.dot1, .dot2, .dot3 {
  animation: dotFade 1.2s infinite;
  opacity: 0;
}
.dot2 { animation-delay: 0.2s; }
.dot3 { animation-delay: 0.4s; }

@keyframes dotFade {
  0%, 20% { opacity: 0; }
  50% { opacity: 1; }
  100% { opacity: 0; }
}

/* 打字光标 */
.cursor {
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
