<template>
  <div class="app-viewport">
    <template v-if="isPurePage">
      <NuxtPage />
    </template>

    <div v-else class="tablet-frame">
      <aside class="side-nav">
        <div class="nav-links">
          <div class="nav-item" :class="{ 'active-custom': route.path === '/' }" @click="handleNavRequest('/')">🏠<br>首页</div>
          <div class="nav-item" :class="{ 'active-custom': route.path === '/health' }" @click="handleNavRequest('/health')">❤️<br>健康</div>
          <div class="nav-item" :class="{ 'active-custom': route.path === '/entertainment' }" @click="handleNavRequest('/entertainment')">🎵<br>娱乐</div>
          <div class="nav-item" :class="{ 'active-custom': route.path === '/learning' }" @click="handleNavRequest('/learning')">🧩<br>益智</div> 
        </div>
        <div class="user-zone" @click.stop="ui.menu = !ui.menu">
          <div class="avatar">👴</div>
          <div class="name">张爷爷</div>
          <div v-if="ui.menu" class="pop-menu">
            <div @click="handleAdminNav('/developer')">🛠 开发者后台</div>
            <div @click="handleAdminNav('/projection')">📽 投影页面</div>
            <div @click="handleAdminNav('/settings')">⚙️ 系统设置</div>
          </div>
        </div>
      </aside>

      <main class="main-content">
        <NuxtPage />
      </main>

      <div 
        v-if="!ui.akon"
        class="akon-ball"
        :class="{ 'is-docked': ball.status === 'half', 'is-active': ball.status === 'full' }"
        :style="{ 
          left: ball.x + 'px', 
          top: ball.y + 'px',
          opacity: ball.isDragging ? 1 : (ball.status === 'half' ? 0.5 : 1)
        }"
        @mousedown="handleDragStart"
        @touchstart.passive="handleDragStart"
      >
        <span class="akon-icon">🤖</span>
      </div>

      <div v-if="ui.akon" class="akon-modal" @click="closeAkon">
        <div class="akon-panel" @click.stop>
          <h2>阿康助手</h2>
          <p>受众群体，该喝水了，或者我们要开始一组认知干预训练吗？</p>
          <button class="akon-btn" @click="closeAkon">知道啦</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { io } from 'socket.io-client'

const route = useRoute()
const router = useRouter()
const isPurePage = computed(() => ['projection', 'developer'].includes(route.name))
const isGameActive = computed(() => route.path === '/training')
const ui = reactive({ menu: false, akon: false })

let socket = null

const ball = reactive({
  x: 0, y: 0, status: 'half', isDragging: false,
  startX: 0, startY: 0, moveDist: 0
})

// --- 核心修改：中心化路由同步逻辑 ---

const handleNavRequest = (path) => {
  if (isGameActive.value) {
    alert("请先点击“退出游戏”")
    return
  }
  // 不再本地直接跳转，而是向后端发送请求
  if (socket) {
    socket.emit('request_nav', { page: path })
  } else {
    // 降级处理：socket未连接时本地跳转
    router.push(path)
  }
}

const handleAdminNav = (path) => {
  if (isGameActive.value) { alert("请先点击“退出游戏”"); return; }
  ui.menu = false; 
  router.push(path); // 后台页不参与全局同步，本地直接跳
}

onMounted(() => {
  // 初始化 Socket 连接
  socket = io(`http://${window.location.hostname}:8080`)

  // 监听后端强制跳转信号（多网页联动的关键）
  socket.on('navigate_to', (data) => {
    // 排除掉不参与同步的独立终端页面
    if (!isPurePage.value && route.path !== data.page) {
      router.push(data.page)
    }
  })

  // 原有 UI 逻辑
  ball.x = window.innerWidth - 45
  ball.y = window.innerHeight / 2 - 45
  window.addEventListener('mousemove', handleDragging); 
  window.addEventListener('mouseup', handleDragEnd)
  window.addEventListener('touchmove', handleDragging, { passive: false }); 
  window.addEventListener('touchend', handleDragEnd)
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

// --- 原有球体拖拽与吸附逻辑（保持现状） ---
const updateDockPos = () => {
  const winW = window.innerWidth
  if (ball.x < winW / 2) {
    ball.x = ball.status === 'half' ? -45 : 20
  } else {
    ball.x = ball.status === 'half' ? winW - 45 : winW - 110
  }
}

const handleDragStart = (e) => {
  ball.isDragging = true; ball.moveDist = 0
  const event = e.touches ? e.touches[0] : e
  ball.startX = event.clientX - ball.x; ball.startY = event.clientY - ball.y
}

const handleDragging = (e) => {
  if (!ball.isDragging) return
  const event = e.touches ? e.touches[0] : e
  ball.x = event.clientX - ball.startX
  ball.y = event.clientY - ball.startY
  ball.moveDist++
}

const handleDragEnd = () => {
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

const closeAkon = () => { ui.akon = false; ball.status = 'half'; updateDockPos(); }
</script>

<style>
/* 核心样式：严格遵循死命令，禁止修改视觉风格 */
* {
  -webkit-tap-highlight-color: transparent; 
  touch-action: manipulation;
  margin: 0; padding: 0; box-sizing: border-box;
}

html, body { 
  width: 100vw; height: 100vh; overflow: hidden; 
  background: #000; font-family: 'PingFang SC', sans-serif;
}

.app-viewport { 
  width: 100vw; height: 100vh; 
  display: flex; justify-content: center; align-items: center; 
  overflow: hidden; 
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

/* 模拟原来的 NuxtLink 样式 */
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
.pop-menu {
  position: absolute; left: 150px; bottom: 0; width: 220px; 
  background: white; border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.15); z-index: 200;
}
.pop-menu div { padding: 20px; font-size: 20px; border-bottom: 1px solid #F5F5F5; text-align: left; }
.akon-modal { position: absolute; inset: 0; background: rgba(0,0,0,0.4); z-index: 600; display: flex; align-items: flex-end; }
.akon-panel { width: 100%; background: #FFF; border-radius: 40px 40px 0 0; padding: 60px; }
.akon-btn { width: 100%; padding: 25px; background: #FF7222; color: #fff; border: none; border-radius: 20px; font-size: 24px; font-weight: bold; }
</style>