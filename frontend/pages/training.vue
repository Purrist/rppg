<template>
  <div class="training-container">
    
    <!-- 结算状态 -->
    <div v-if="game.status === 'SETTLING'" class="settling-view">
      <h1 class="settling-title">{{ gameTitle }}结束</h1>
      <div class="settling-score">
        <span class="label">最终得分</span>
        <span class="value">{{ game.score }}</span>
      </div>
      <div class="settling-accuracy" v-if="game.accuracy > 0">
        <span class="label">准确率</span>
        <span class="value">{{ game.accuracy }}%</span>
      </div>
      <div class="settling-buttons">
        <button @click="restartGame" class="restart-btn">🔄 再来一次</button>
        <button @click="endGame" class="exit-btn">✖ 返回列表</button>
      </div>
    </div>

    <!-- 准备状态 -->
    <div v-else-if="game.status === 'READY'" class="ready-view">
      <div class="center-hint">请在投影区域开始{{ gameTitle }}</div>
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
        <h1>{{ gameIcon }} {{ gameTitle }}</h1>
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
        <div class="stat-item" v-if="game.accuracy > 0">
          <span class="stat-label">准确率</span>
          <span class="stat-value">{{ game.accuracy }}%</span>
        </div>
        <div class="stat-item" v-if="game.module">
          <span class="stat-label">当前模块</span>
          <span class="stat-value">{{ moduleName }}</span>
        </div>
        <div class="stat-item" v-if="game.difficultyLevel">
          <span class="stat-label">难度</span>
          <span class="stat-value">{{ game.difficultyLevel }}</span>
        </div>
      </div>

      <!-- 处理速度训练特有：显示指令 -->
      <div v-if="game.gameType === 'processing_speed' && stimulus" class="instruction-area">
        <div class="instruction-box" :class="stimulus.module">
          <div v-if="stimulus.module === 'go_no_go'" class="instruction-text">
            {{ stimulus.is_go ? '踩绿色区域！' : '不要踩！' }}
          </div>
          <div v-else-if="stimulus.module === 'choice_reaction'" class="instruction-text">
            {{ stimulus.instruction || '踩指定颜色' }}
          </div>
          <div v-else-if="stimulus.module === 'serial_reaction'" class="instruction-text">
            按顺序踩踏 ({{ stimulus.sequence_progress }})
          </div>
        </div>
      </div>

      <!-- 反馈显示 -->
      <div v-if="feedback" class="feedback-overlay" :class="feedback.correct ? 'correct' : 'error'">
        <div class="feedback-content">
          <div class="feedback-icon">{{ feedback.correct ? '✓' : '✗' }}</div>
          <div class="feedback-message">{{ feedback.message }}</div>
          <div class="feedback-rt" v-if="feedback.rt > 0">
            反应时间: {{ Math.round(feedback.rt) }}ms
          </div>
        </div>
      </div>

      <div class="game-hint">
        💡 {{ gameHint }}
      </div>

      <div class="game-controls">
        <button @click="pauseGame" class="ctrl-btn pause">⏸ 暂停</button>
        <button @click="restartGame" class="ctrl-btn restart">🔄 重新开始</button>
        <button @click="endGame" class="ctrl-btn exit">✖ 结束游戏</button>
      </div>
    </div>
    
    <!-- 暂停状态 -->
    <div v-else-if="game.status === 'PAUSED'" class="paused-view">
      <h1>⏸ {{ gameTitle }}已暂停</h1>
      <div class="pause-info">
        <span>得分: {{ game.score }}</span>
        <span>剩余: {{ game.timer }}s</span>
      </div>
      <div class="pause-buttons">
        <button @click="resumeGame" class="resume-btn">▶ 继续游戏</button>
        <button @click="restartGame" class="restart-btn">🔄 重新开始</button>
        <button @click="endGame" class="exit-btn">✖ 结束游戏</button>
      </div>
    </div>
    
    <!-- 其他状态 -->
    <div v-else class="ready-view">
      <div class="center-hint">请在投影区域开始{{ gameTitle }}</div>
      <div class="hint-sub">站在投影区域的圆圈内即可开始</div>
      <div class="bottom-bar">
        <button @click="exitGame" class="big-exit-btn" :disabled="isExiting">
          {{ isExiting ? '退出中...' : '退出游戏' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { useRouter } from 'vue-router'

const router = useRouter()
const game = ref({ 
  status: 'READY', 
  score: 0, 
  timer: 60, 
  accuracy: 0,
  gameType: 'whack_a_mole',
  module: null,
  difficultyLevel: 5
})
const stimulus = ref(null)
const feedback = ref(null)
const isExiting = ref(false)
let socket = null
let feedbackTimeout = null

const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

// 游戏信息
const gameInfo = {
  'whack_a_mole': { title: '打地鼠', icon: '🐹', hint: '请在投影区域踩踏地鼠所在的洞' },
  'processing_speed': { title: '处理速度训练', icon: '⚡', hint: '根据提示踩踏目标区域，停留3秒确认' }
}

const moduleNames = {
  'go_no_go': '反应控制',
  'choice_reaction': '选择反应',
  'serial_reaction': '序列学习'
}

const gameTitle = computed(() => gameInfo[game.value.gameType]?.title || '游戏')
const gameIcon = computed(() => gameInfo[game.value.gameType]?.icon || '🎮')
const gameHint = computed(() => gameInfo[game.value.gameType]?.hint || '')
const moduleName = computed(() => moduleNames[game.value.module] || '')

onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  socket.on('connect', () => {
    console.log('[训练页] 后端已连接')
    socket.emit('get_state', { client: 'training' })
  })
  
  socket.on('game_update', (data) => {
    console.log('[训练页] game_update:', data.status)
    
    game.value = {
      status: data.status || 'READY',
      score: data.score || 0,
      timer: data.timer || 60,
      accuracy: data.stats?.accuracy || 0,
      gameType: data.module ? 'processing_speed' : 'whack_a_mole',
      module: data.module || null,
      difficultyLevel: data.difficulty_level || 5
    }
    
    // 处理速度训练数据
    if (data.stimulus) {
      stimulus.value = data.stimulus
    }
    
    if (data.feedback) {
      feedback.value = data.feedback
      if (feedbackTimeout) clearTimeout(feedbackTimeout)
      feedbackTimeout = setTimeout(() => {
        feedback.value = null
      }, 2000)
    }
  })
  
  socket.on('system_state', (data) => {
    if (data.state?.game) {
      if (data.state.game.active === false && data.state.game.status === 'IDLE') {
        console.log('[训练页] 游戏已停止，返回游戏列表')
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
  if (feedbackTimeout) clearTimeout(feedbackTimeout)
})

// 游戏控制
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
    socket.emit('game_control', { action: 'restart' })
  }
}

const endGame = () => {
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'stop' })
  }
}

const exitGame = () => {
  if (isExiting.value) return
  
  isExiting.value = true
  
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'stop' })
  }
  
  setTimeout(() => {
    router.push('/learning')
  }, 100)
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

/* 结算状态 */
.settling-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
}

.settling-title {
  font-size: 72px;
  font-weight: 900;
  color: #FFD700;
  margin-bottom: 40px;
}

.settling-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 30px;
}

.settling-score .label {
  font-size: 24px;
  color: #888;
  margin-bottom: 10px;
}

.settling-score .value {
  font-size: 96px;
  font-weight: 900;
  color: #FFD700;
}

.settling-accuracy {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 30px;
}

.settling-accuracy .label {
  font-size: 20px;
  color: #888;
  margin-bottom: 5px;
}

.settling-accuracy .value {
  font-size: 48px;
  font-weight: 700;
  color: #fff;
}

.settling-buttons {
  display: flex;
  gap: 20px;
}

.restart-btn { 
  padding: 20px 40px;
  background: #FF7222; 
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

/* 准备状态 */
.ready-view { 
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

/* 游戏中 */
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

/* 指令区域 */
.instruction-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.instruction-box {
  padding: 30px 60px;
  border-radius: 20px;
  text-align: center;
}

.instruction-box.go_no_go {
  background: #33B555;
}

.instruction-box.choice_reaction {
  background: #2196F3;
}

.instruction-box.serial_reaction {
  background: #9C27B0;
}

.instruction-text {
  font-size: 48px;
  font-weight: 900;
  color: #fff;
}

/* 反馈 */
.feedback-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.7);
  z-index: 100;
  animation: fadeIn 0.2s;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.feedback-content {
  text-align: center;
}

.feedback-icon {
  font-size: 80px;
  margin-bottom: 20px;
}

.feedback-message {
  font-size: 32px;
  font-weight: 700;
}

.feedback-rt {
  font-size: 18px;
  color: #888;
  margin-top: 10px;
}

.feedback-overlay.correct .feedback-icon {
  color: #33B555;
}

.feedback-overlay.correct .feedback-message {
  color: #33B555;
}

.feedback-overlay.error .feedback-icon {
  color: #FF4444;
}

.feedback-overlay.error .feedback-message {
  color: #FF4444;
}

.game-hint {
  text-align: center;
  font-size: 18px;
  color: #888;
  padding: 20px;
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

/* 暂停状态 */
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
  margin-bottom: 20px; 
}

.pause-info {
  display: flex;
  gap: 40px;
  font-size: 24px;
  color: #666;
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
</style>
