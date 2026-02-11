<template>
  <div class="app-viewport">
    <template v-if="isPurePage">
      <NuxtPage />
    </template>

    <div v-else class="tablet-frame">
      <aside class="side-nav">
        <div class="nav-links">
          <NuxtLink :to="isGameActive ? '' : '/'" class="nav-item" @click.native="handleNavLock">🏠<br>首页</NuxtLink>
          <NuxtLink :to="isGameActive ? '' : '/health'" class="nav-item" @click.native="handleNavLock">❤️<br>健康</NuxtLink>
          <NuxtLink :to="isGameActive ? '' : '/entertainment'" class="nav-item" @click.native="handleNavLock">🎵<br>娱乐</NuxtLink>
          <NuxtLink :to="isGameActive ? '' : '/learning'" class="nav-item" @click.native="handleNavLock">🧩<br>益智</NuxtLink> 
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
import { reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const isPurePage = computed(() => ['projection', 'developer'].includes(route.name))
const isGameActive = computed(() => route.path === '/training')
const ui = reactive({ menu: false, akon: false })

const ball = reactive({
  x: 0, y: 0, status: 'half', isDragging: false,
  startX: 0, startY: 0, moveDist: 0
})

const updateDockPos = () => {
  const winW = window.innerWidth
  if (ball.x < winW / 2) {
    ball.x = ball.status === 'half' ? -45 : 20
  } else {
    ball.x = ball.status === 'half' ? winW - 45 : winW - 110
  }
}

// 导航锁定函数
const handleNavLock = () => {
  if (isGameActive.value) alert("请先点击“退出游戏”")
}
const handleAdminNav = (path) => {
  if (isGameActive.value) { alert("请先点击“退出游戏”"); return; }
  ui.menu = false; router.push(path);
}

onMounted(() => {
  ball.x = window.innerWidth - 45
  ball.y = window.innerHeight / 2 - 45
  window.addEventListener('mousemove', handleDragging); window.addEventListener('mouseup', handleDragEnd)
  window.addEventListener('touchmove', handleDragging, { passive: false }); window.addEventListener('touchend', handleDragEnd)
})

const handleDragStart = (e) => {
  ball.isDragging = true; ball.moveDist = 0
  const event = e.touches ? e.touches[0] : e
  ball.startX = event.clientX - ball.x; ball.startY = event.clientY - ball.y
}

const handleDragging = (e) => {
  if (!ball.isDragging) return
  const event = e.touches ? e.touches[0] : e
  // 零延迟关键：直接赋值，利用 transform 优化渲染
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
/* 核心：严禁改动视觉风格，仅处理比例锁定和卡顿 */
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
  overflow: hidden; /* 强制拦截任何滚动 */
}

/* 16:10 平板框架：死命令锁定 */
.tablet-frame {
  width: 100vw; height: 62.5vw; /* 严格 16:10 比例公式 */
  max-height: 100vh; max-width: 160vh;
  background: #FFFFFF; display: flex; position: relative; overflow: hidden;
}

/* 侧边栏：恢复原有 140px 宽度 */
.side-nav {
  width: 140px; background: #F8F9FA; display: flex; flex-direction: column;
  padding: 40px 0; border-right: 1px solid #EEE; z-index: 100;
}
.nav-links { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 30px; }
.nav-item { 
  text-decoration: none; color: #333; font-size: 22px; font-weight: bold; 
  text-align: center; width: 100px; padding: 15px 0; border-radius: 20px;
}
.router-link-active { background: #FF7222 !important; color: #FFF !important; }

.main-content { 
  flex: 1; height: 100%; overflow-y: auto; 
  padding: 40px; scrollbar-width: none; 
}
.main-content::-webkit-scrollbar { display: none; }

/* 阿康球：注入 GPU 加速，解决卡顿 */
.akon-ball {
  position: fixed; width: 90px; height: 90px; background: #FF7222;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  z-index: 500; cursor: pointer;
  transform: translate3d(0, 0, 0); /* 开启硬件加速 */
  will-change: left, top;
  transition: opacity 0.3s;
  box-shadow: 0 8px 25px rgba(255,114,34,0.4);
  touch-action: none;
}
.akon-icon { font-size: 45px; pointer-events: none; }

/* 其他弹窗样式原封不动保留... */
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