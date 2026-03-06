<template>
  <div class="home-page">
    <div class="welcome-banner">
      <h1>早安，张爷爷</h1>
      <p>今天是 2026年1月22日 星期四，天气晴朗。</p>
    </div>
    
    <div class="main-grid">
      <div class="card health-summary" @click="handleNavigate('/health')">
        <div class="card-icon">❤️</div>
        <div class="card-info">
          <h3>生理信号监测</h3>
          <p>当前解析稳定，波动率正常</p>
        </div>
      </div>
      
      <div class="card training-summary" @click="handleNavigate('/learning')">
        <div class="card-icon">🧠</div>
        <div class="card-info">
          <h3>今日训练任务</h3>
          <p>色词识别挑战（待开始）</p>
        </div>
      </div>
    </div>

    <div class="quick-actions">
      <div class="action-btn call">视频通话</div>
      <div class="action-btn sos">紧急呼救</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'

const router = useRouter()
let socket = null
const backendConnected = ref(false)

// Flask 后端端口
const FLASK_PORT = 5000

onMounted(() => {
  try {
    socket = io(`http://localhost:${FLASK_PORT}`, {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionAttempts: 3,
      timeout: 5000
    })
    
    socket.on('connect', () => {
      backendConnected.value = true
    })
    
    socket.on('disconnect', () => {
      backendConnected.value = false
    })
    
    socket.on('connect_error', () => {
      backendConnected.value = false
    })
    
    // 监听导航事件
    socket.on('navigate_to', (data) => {
      router.push(data.page)
    })
  } catch (e) {
    console.error('Socket初始化失败', e)
  }
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

// 统一导航（带降级处理）
const handleNavigate = (page) => {
  if (backendConnected.value && socket) {
    socket.emit('navigate', { page, source: 'user' })
  } else {
    // 后端未连接，降级为本地导航
    router.push(page)
  }
}
</script>

<style scoped>
.home-page { padding: 80px 40px 40px; }
.welcome-banner h1 { font-size: 48px; color: #333; }
.welcome-banner p { font-size: 22px; color: #888; margin-top: 10px; }

.main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 50px; }
.card { background: #FFF; border: 2px solid #F0F0F0; border-radius: 35px; padding: 40px; display: flex; align-items: center; gap: 25px; cursor: pointer; transition: 0.3s; }
.card:hover { border-color: #FF7222; background: #FFF9F6; }
.card-icon { font-size: 50px; }
.card-info h3 { font-size: 28px; color: #333; }
.card-info p { font-size: 18px; color: #777; margin-top: 5px; }

.quick-actions { margin-top: 40px; display: flex; gap: 30px; }
.action-btn { flex: 1; height: 120px; border-radius: 30px; display: flex; align-items: center; justify-content: center; font-size: 30px; font-weight: bold; color: #FFF; cursor: pointer; }
.call { background: #33B555; }
.sos { background: #FF4D4D; }
</style>
