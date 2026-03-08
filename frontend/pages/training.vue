<template>
  <div class="training-container">
    <!-- 准备状态 -->
    <div v-if="game.status === 'READY'" class="ready-view">
      <div class="center-hint">请在投影区域开始游戏</div>
      <div class="hint-sub">站在投影区域的圆圈内即可开始</div>
      <div class="bottom-bar">
        <button @click="exitGame" class="big-exit-btn" :disabled="isExiting">
          {{ isExiting ? '退出中...' : '退出游戏' }}
        </button>
      </div>
    </div>

    <!-- 游戏中 -->
    <div v-else-if="game.status === 'PLAYING'" class="playing-view">
      <div class="header">
        <h1>🐹 打地鼠</h1>
        <div class="timer-display">
          <span class="timer-label">剩余时间</span>
          <span class="timer-value">{{ game.timer }}s</span>
        </div>
      </div>

      <div class="stats-row">
        <div class="stat-item">
          <span class="stat-label">得分</span>
          <span class="stat-value score">{{ game.score }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">准确率</span>
          <span class="stat-value">{{ game.accuracy || 0 }}%</span>
        </div>
      </div>

      <div class="game-hint">
        💡 请在投影区域踩踏地鼠所在的洞
      </div>

      <div class="game-controls">
        <button @click="pauseGame" class="ctrl-btn pause">⏸ 暂停</button>
        <button @click="restartGame" class="ctrl-btn restart">🔄 重新开始</button>
        <button @click="exitGame" class="ctrl-btn exit">✖ 结束游戏</button>
      </div>
    </div>
    
    <!-- 暂停状态 -->
    <div v-else-if="game.status === 'PAUSED'" class="paused-view">
      <h1>⏸ 游戏已暂停</h1>
      <div class="pause-buttons">
        <button @click="resumeGame" class="resume-btn">▶ 继续游戏</button>
        <button @click="restartGame" class="restart-btn">🔄 重新开始</button>
        <button @click="exitGame" class="exit-btn">✖ 结束游戏</button>
      </div>
    </div>
    
    <!-- 默认状态 -->
    <div v-else class="default-view">
      <div class="center-hint">等待游戏...</div>
      <div class="bottom-bar">
        <button @click="goBack" class="big-exit-btn" :disabled="isExiting">
          {{ isExiting ? '返回中...' : '返回' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { useRouter } from 'vue-router'

const router = useRouter()
const game = ref({ status: 'IDLE', score: 0, timer: 60, accuracy: 0, current_mole: -1 })
const isExiting = ref(false)
let socket = null

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
    console.log('[训练页] 后端已连接')
    // ⭐ 连接时获取当前状态
    socket.emit('get_state')
  })
  
  socket.on('game_update', (data) => {
    game.value = data
    console.log('[训练页] 游戏状态:', data.status)
  })
  
  socket.on('system_state', (data) => {
    if (data.state && data.state.game) {
      game.value.status = data.state.game.status || 'IDLE'
      game.value.score = data.state.game.score || 0
      game.value.timer = data.state.game.timer || 60
      
      // 如果游戏状态变为IDLE且不活跃，返回游戏列表
      if (data.state.game.status === 'IDLE' && data.state.game.active === false) {
        console.log('[训练页] 游戏已停止，返回游戏列表')
        isExiting.value = false
        router.push('/learning')
      }
    }
  })
  
  socket.on('navigate_to', (data) => {
    router.push(data.page)
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

// ==================== 游戏控制 ====================
const pauseGame = () => {
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'pause' })
  }
}

const resumeGame = () => {
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'pause' })
  }
}

const restartGame = () => {
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'stop' })
    setTimeout(() => {
      socket.emit('game_control', { action: 'ready', game: 'whack_a_mole' })
    }, 300)
  }
}

const exitGame = () => {
  if (isExiting.value) return
  
  console.log('[训练页] 结束游戏')
  isExiting.value = true
  
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'stop' })
  }
  
  // 延迟返回，等待状态同步
  setTimeout(() => {
    isExiting.value = false
    router.push('/learning')
  }, 200)
}

const goBack = () => {
  if (isExiting.value) return
  
  console.log('[训练页] 返回')
  isExiting.value = true
  
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'stop' })
  }
  
  setTimeout(() => {
    isExiting.value = false
    router.push('/learning')
  }, 200)
}
</script>

<style scoped>
.training-container { 
  height: 100%; 
  width: 100%; 
  background: #FFF; 
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.ready-view, .default-view { 
  flex: 1;
  display: flex; 
  flex-direction: column; 
  align-items: center; 
  justify-content: center; 
  padding: 40px;
}

.center-hint { 
  font-size: 48px; 
  font-weight: 900; 
  color: #333; 
  text-align: center;
}

.hint-sub {
  font-size: 24px;
  color: #888;
  margin-top: 20px;
}

.bottom-bar { 
  padding: 30px;
  display: flex; 
  justify-content: center;
}

.big-exit-btn { 
  padding: 20px 60px;
  background: #333; 
  color: #FFF; 
  border-radius: 50px; 
  font-size: 28px; 
  border: none;
  cursor: pointer;
}

.big-exit-btn:disabled {
  background: #999;
  cursor: not-allowed;
}

.playing-view { 
  flex: 1;
  padding: 30px; 
  display: flex; 
  flex-direction: column; 
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h1 {
  font-size: 36px;
  color: #333;
}

.timer-display {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.timer-label {
  font-size: 18px;
  color: #888;
}

.timer-value {
  font-size: 48px;
  font-weight: 900;
  color: #FF7222;
}

.stats-row {
  display: flex;
  justify-content: space-around;
  margin-bottom: 20px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-label {
  font-size: 18px;
  color: #888;
}

.stat-value {
  font-size: 36px;
  font-weight: 900;
  color: #333;
}

.stat-value.score {
  color: #FF7222;
}

.game-hint {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #666;
  background: #F9F9F9;
  border-radius: 20px;
  margin-bottom: 20px;
}

.game-controls {
  display: flex;
  justify-content: center;
  gap: 20px;
  padding: 20px;
}

.ctrl-btn {
  padding: 18px 35px;
  border-radius: 30px;
  border: none;
  font-size: 20px;
  font-weight: bold;
  cursor: pointer;
}

.ctrl-btn.pause {
  background: #FFD111;
  color: #333;
}

.ctrl-btn.restart {
  background: #2196F3;
  color: #FFF;
}

.ctrl-btn.exit {
  background: #FB4422;
  color: #FFF;
}

.paused-view { 
  flex: 1;
  display: flex; 
  flex-direction: column;
  align-items: center; 
  justify-content: center; 
  background: rgba(0,0,0,0.1); 
}

.paused-view h1 { 
  font-size: 48px; 
  color: #333; 
  margin-bottom: 40px; 
}

.pause-buttons { 
  display: flex; 
  gap: 20px; 
}

.resume-btn { 
  padding: 20px 40px;
  background: #33B555; 
  color: #FFF; 
  border-radius: 40px; 
  font-size: 24px; 
  font-weight: bold; 
  border: none;
  cursor: pointer;
}

.restart-btn { 
  padding: 20px 40px;
  background: #2196F3; 
  color: #FFF; 
  border-radius: 40px; 
  font-size: 24px; 
  font-weight: bold; 
  border: none;
  cursor: pointer;
}

.exit-btn { 
  padding: 20px 40px;
  background: #FB4422; 
  color: #FFF; 
  border-radius: 40px; 
  font-size: 24px; 
  font-weight: bold; 
  border: none;
  cursor: pointer;
}
</style>
