<template>
  <div class="page-body">
    <h2>🧩 益智训练中心</h2>
    <div class="learning-grid">
      <div class="l-card" @click="startGame('whack_a_mole')">
        <div class="l-icon">🐹</div>
        <div class="l-text">
          <h3>趣味打地鼠</h3>
          <p>锻炼手眼协调与反应速度</p>
        </div>
      </div>
      <div class="l-card" @click="handleTodo">
        <div class="l-icon">🎨</div>
        <div class="l-text">
          <h3>色词挑战</h3>
          <p>提升认知抑制与注意力</p>
        </div>
      </div>
      <div class="l-card" @click="handleTodo">
        <div class="l-icon">🎵</div>
        <div class="l-text">
          <h3>听音猜歌</h3>
          <p>锻炼听觉记忆能力</p>
        </div>
      </div>
      <div class="l-card" @click="handleTodo">
        <div class="l-icon">🧠</div>
        <div class="l-text">
          <h3>记忆配对</h3>
          <p>提升图像记忆能力</p>
        </div>
      </div>
    </div>
  </div>
</template>


<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'

const router = useRouter()
let socket = null

// 自动检测后端地址
const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  socket.on('connect', () => {
    console.log('[益智] 后端已连接')
    // ⭐ 不需要发送 get_state，app.vue 已经处理了首次连接
  })
  
  socket.on('navigate_to', (data) => {
    router.push(data.page)
  })
  
  // ⭐ 监听游戏状态变化
  socket.on('game_update', (data) => {
    // 如果状态变为READY，跳转到training
    if (data.status === 'READY') {
      router.push('/training')
    }
  })
  
  // ⭐ system_state 只用于检测游戏是否完全停止
  socket.on('system_state', (data) => {
    // ⭐ 只有当 active=false 且 status=IDLE 时才返回游戏列表
    // restart 时 active=true（因为 READY 算激活），不会触发返回
    if (data.state && data.state.game) {
      if (data.state.game.active === false && data.state.game.status === 'IDLE') {
        // 已经在 learning 页面，不需要跳转
      }
    }
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

const startGame = (gameName) => {
  console.log('[益智] 开始游戏:', gameName)
  
  if (socket && socket.connected) {
    // ⭐ 发送 ready，等待后端返回 READY 状态后自动跳转
    socket.emit('game_control', { action: 'ready', game: gameName })
  } else {
    alert('后端未连接，请稍后重试')
  }
}

const handleTodo = () => {
  alert('该功能正在开发中，敬请期待！')
}
</script>

<style scoped>
.page-body { padding: 40px; }
.learning-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 40px; }
.l-card { 
  background: #FFF; border: 2px solid #EEE; border-radius: 30px; 
  padding: 30px; display: flex; align-items: center; gap: 20px; cursor: pointer;
  transition: transform 0.2s;
}
.l-card:active { transform: scale(0.98); }
.l-icon { font-size: 60px; }
.l-text h3 { font-size: 28px; margin-bottom: 5px; color: #333; }
.l-text p { color: #888; font-size: 18px; }
</style>
