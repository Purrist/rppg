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
      <div v-if="ui.akon" class="akon-modal" @click="closeAkon">
        <div class="akon-panel" @click.stop>
          <h2>阿康助手</h2>
          <p>张爷爷，有什么需要帮忙的吗？</p>
          <button class="akon-btn" @click="closeAkon">知道啦</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { io } from 'socket.io-client'

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
const gameActive = ref(false)
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
  if (gameActive.value && socket && socket.connected) {
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
  router.push('/settings')
}

// ==================== Socket ====================
onMounted(() => {
  ball.x = window.innerWidth - 45
  ball.y = window.innerHeight / 2 - 45
  
  window.addEventListener('mousemove', handleDragging)
  window.addEventListener('mouseup', handleDragEnd)
  window.addEventListener('touchmove', handleDragging, { passive: false })
  window.addEventListener('touchend', handleDragEnd)
  
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000
  })
  
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
    if (data.state && data.state.game) {
      gameActive.value = data.state.game.active
      
      // ⭐ 如果收到 READY 状态，重置重新开始标记
      if (data.state.game.status === 'READY') {
        isRestarting.value = false
      }
      
      // 如果游戏状态是IDLE且不活跃，检查当前页面
      // ⭐ 但如果正在重新开始，忽略这个状态
      if (data.state.game.status === 'IDLE' && data.state.game.active === false && !isRestarting.value) {
        // 如果当前在训练页面，返回游戏列表
        if (route.path === '/training') {
          console.log('[App] 游戏已停止，返回游戏列表')
          router.push('/learning')
        }
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
.akon-panel { width: 100%; background: #FFF; border-radius: 40px 40px 0 0; padding: 60px; }
.akon-btn { width: 100%; padding: 25px; background: #FF7222; color: #fff; border: none; border-radius: 20px; font-size: 24px; font-weight: bold; }
</style>
