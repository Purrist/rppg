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

    <!-- 准备状态 - 只显示提示，不显示规则 -->
    <div v-else-if="game.status === 'READY'" class="ready-view">
      <div class="ready-content">
        <div class="ready-hint">请站在区域开始游戏</div>
        <div class="ready-sub">站在投影区域的圆圈内即可开始</div>
        
        <div class="bottom-bar">
          <button @click="exitGame" class="big-exit-btn" :disabled="isExiting">
            {{ isExiting ? '退出中...' : '退出游戏' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 游戏中 - 只显示游戏状态，不显示规则 -->
    <div v-else-if="game.status === 'PLAYING'" class="playing-view">
      <div class="playing-layout">
        <!-- 游戏状态面板 -->
        <div class="status-panel full-width">
          <div class="status-header">
            <h1>{{ gameIcon }} {{ gameTitle }}</h1>
            <div class="timer-display">
              <span class="timer-label">剩余时间</span>
              <span class="timer-value">{{ game.timer }}s</span>
            </div>
          </div>

          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-label">得分</span>
              <span class="stat-value score">{{ game.score }}</span>
            </div>
            <div class="stat-card" v-if="game.accuracy > 0">
              <span class="stat-label">准确率</span>
              <span class="stat-value">{{ game.accuracy }}%</span>
            </div>
            <div class="stat-card" v-if="game.module">
              <span class="stat-label">当前模块</span>
              <span class="stat-value">{{ moduleName }}</span>
            </div>
            <div class="stat-card" v-if="game.difficultyLevel">
              <span class="stat-label">难度</span>
              <span class="stat-value">{{ game.difficultyLevel }}/8</span>
            </div>
          </div>

          <!-- 处理速度训练特有：显示当前指令 -->
          <div v-if="game.gameType === 'processing_speed' && stimulus" class="current-instruction">
            <div class="instruction-label">当前指令</div>
            <div class="instruction-display" :class="stimulus.module">
              <span v-if="stimulus.module === 'go_no_go'">
                {{ stimulus.is_go ? '踩绿色区域！' : '不要踩！' }}
              </span>
              <span v-else-if="stimulus.module === 'choice_reaction'">
                {{ stimulus.instruction || '踩指定颜色' }}
              </span>
              <span v-else-if="stimulus.module === 'serial_reaction'">
                按顺序踩踏 ({{ stimulus.sequence_progress }})
              </span>
            </div>
          </div>



          <div class="game-controls">
            <button @click="pauseGame" class="ctrl-btn pause">⏸ 暂停</button>
            <button @click="restartGame" class="ctrl-btn restart">🔄 重新开始</button>
            <button @click="endGame" class="ctrl-btn exit">✖ 结束游戏</button>
          </div>
        </div>
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
      <div class="ready-content">
        <div class="ready-hint">请在投影区域开始{{ gameTitle }}</div>
        <div class="ready-sub">站在投影区域的圆圈内即可开始</div>
        <div class="bottom-bar">
          <button @click="exitGame" class="big-exit-btn" :disabled="isExiting">
            {{ isExiting ? '退出中...' : '退出游戏' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { initStore, subscribe, gameControl } from '../core/systemStore.js'

const router = useRouter()

// ⭐ 路由守卫 - 离开页面时停止游戏
onBeforeRouteLeave((to, from, next) => {
  if (game.value.status === 'PLAYING') {
    console.log('[训练页] 路由离开，停止游戏')
    gameControl('stop')
  }
  next()
})

// Socket实例
let socket = null
let unsubscribe = null

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
let feedbackTimeout = null

const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

// 游戏信息
const gameInfo = {
  'whack_a_mole': { title: '打地鼠', icon: '🐹' },
  'processing_speed': { title: '处理速度训练', icon: '⚡' }
}

const moduleNames = {
  'go_no_go': '反应控制',
  'choice_reaction': '选择反应',
  'serial_reaction': '序列学习'
}

const gameTitle = computed(() => gameInfo[game.value.gameType]?.title || '游戏')
const gameIcon = computed(() => gameInfo[game.value.gameType]?.icon || '🎮')
const moduleName = computed(() => moduleNames[game.value.module] || '')

// ==================== 页面离开检测 - 立即停止游戏 ====================
function handleBeforeUnload(event) {
  // 页面关闭/刷新时停止游戏
  if (socket?.connected && game.value.status === 'PLAYING') {
    socket.emit('game_control', { action: 'stop' })
  }
}

function handleVisibilityChange() {
  // 页面切换/隐藏时停止游戏
  if (document.hidden && socket?.connected && game.value.status === 'PLAYING') {
    console.log('[训练页] 页面隐藏，停止游戏')
    socket.emit('game_control', { action: 'stop' })
  }
}

onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  // ⭐ 初始化系统Store，让gameControl可以工作
  initStore(socket)
  
  socket.on('connect', () => {
    console.log('[训练页] 后端已连接')
    socket.emit('get_state', { client: 'training' })
  })
  
  socket.on('game_update', (data) => {
    console.log('[训练页] game_update:', data)
    
    const gameId = data.game_id || ''
    const isProcessingSpeed = gameId === 'processing_speed' || data.module
    
    // 更新本地状态
    // ⭐ 准确率转换为整数百分比（0.89 -> 89）
    // 打地鼠游戏后端已经返回百分比值，不需要再乘以100
    let accuracyPercent = 0
    if (data.stats?.accuracy !== undefined) {
      if (isProcessingSpeed) {
        // 处理速度训练返回的是0-1的值，需要乘以100
        accuracyPercent = Math.round(data.stats.accuracy * 100)
      } else {
        // 打地鼠游戏已经返回百分比值，但可能会有异常值
        const rawAccuracy = data.stats.accuracy
        // 确保准确率在合理范围内（0-100）
        accuracyPercent = Math.max(0, Math.min(100, Math.round(rawAccuracy)))
      }
    }
    
    game.value = {
      status: data.status || 'READY',
      score: data.score || 0,
      timer: data.timer || 60,
      accuracy: accuracyPercent,
      gameType: isProcessingSpeed ? 'processing_speed' : 'whack_a_mole',
      module: data.module || null,
      difficultyLevel: data.difficulty_level || 5
    }
    
    // 显示刺激和反馈
    if (data.stimulus) stimulus.value = data.stimulus
    
    if (data.feedback) {
      feedback.value = data.feedback
      if (feedbackTimeout) clearTimeout(feedbackTimeout)
      feedbackTimeout = setTimeout(() => feedback.value = null, 2000)
    }
  })
  
  socket.on('system_state', (data) => {
    // 使用新的数据结构
    // ⭐ 只有当游戏从PLAYING/SETTLING变为IDLE时才跳转（用户主动退出）
    // 游戏正常结束会进入READY状态，不应该跳转
    const oldStatus = game.value.status
    const newStatus = data.game?.status
    
    if (newStatus === 'IDLE' && (oldStatus === 'PLAYING' || oldStatus === 'SETTLING' || oldStatus === 'PAUSED')) {
      console.log('[训练页] 游戏已停止（用户退出），返回游戏列表')
      router.push('/learning')
    }
    
    // ⭐ 更新本地游戏状态
    if (newStatus) {
      game.value.status = newStatus
    }
  })
  
  socket.on('navigate_to', (data) => router.push(data.page))
  
  // ⭐ 添加页面离开检测
  window.addEventListener('beforeunload', handleBeforeUnload)
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  // ⭐ 页面卸载时立即停止游戏
  if (socket?.connected && game.value.status === 'PLAYING') {
    console.log('[训练页] 页面卸载，停止游戏')
    socket.emit('game_control', { action: 'stop' })
  }
  
  if (socket) socket.disconnect()
  if (feedbackTimeout) clearTimeout(feedbackTimeout)
  
  // 移除事件监听
  window.removeEventListener('beforeunload', handleBeforeUnload)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

const pauseGame = () => {
  if (socket?.connected) socket.emit('game_control', { action: 'pause' })
}

const resumeGame = () => {
  if (socket?.connected) socket.emit('game_control', { action: 'pause' })
}

const restartGame = () => {
  if (socket?.connected) {
    // 重新开始游戏
    const currentGameId = game.value.gameType
    console.log('[training] 重新开始游戏:', currentGameId)
    
    gameControl('restart', { game: currentGameId })
  }
}

const endGame = () => {
  gameControl('stop')
}

const exitGame = () => {
  if (isExiting.value) return
  isExiting.value = true
  gameControl('stop')
  setTimeout(() => router.push('/learning'), 100)
}
</script>

<style scoped>
.training-container { 
  height: 100%; 
  width: 100%; 
  background: #FFF; 
  overflow: hidden;
}

/* 结算状态 */
.settling-view {
  height: 100%;
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

/* 准备状态 - 内容居中 */
.ready-view { 
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;  /* 垂直居中 */
  padding: 40px;
}

.ready-content {
  max-width: 1200px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.ready-hint { 
  font-size: 48px;  /* 增大字体 */
  font-weight: 900; 
  color: #333; 
  text-align: center;
  margin-bottom: 20px;
}

.ready-sub {
  font-size: 24px;  /* 增大字体 */
  color: #888;
  text-align: center;
  margin-bottom: 60px;  /* 增大间距 */
}

.bottom-bar { 
  display: flex; 
  justify-content: center;
  padding: 20px 0;
}

.big-exit-btn { 
  padding: 20px 60px;
  background: #333; 
  color: #FFF; 
  border-radius: 50px; 
  font-size: 24px; 
  border: none;
  cursor: pointer;
}

.big-exit-btn:disabled {
  background: #999;
  cursor: not-allowed;
}

/* 游戏中 - 左右布局 */
.playing-view { 
  height: 100%;
  padding: 30px;
}

.playing-layout {
  display: flex;
  gap: 30px;
  height: 100%;
}

/* 左侧规则面板 */
.rules-panel {
  width: 40%;
  min-width: 400px;
  height: 100%;
}

/* 右侧状态面板 */
.status-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 20px;
  border-bottom: 2px solid #EEE;
}

.status-header h1 {
  font-size: 32px;
  color: #333;
  margin: 0;
}

.timer-display {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.timer-label {
  font-size: 16px;
  color: #888;
}

.timer-value {
  font-size: 48px;
  font-weight: 900;
  color: #FF7222;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.stat-card {
  background: #F8F8F8;
  border-radius: 20px;
  padding: 25px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-label {
  font-size: 16px;
  color: #888;
  margin-bottom: 10px;
}

.stat-value {
  font-size: 36px;
  font-weight: 900;
  color: #333;
}

.stat-value.score {
  color: #FF7222;
}

/* 当前指令 */
.current-instruction {
  background: #F8F8F8;
  border-radius: 20px;
  padding: 30px;
  text-align: center;
}

.instruction-label {
  font-size: 18px;
  color: #888;
  margin-bottom: 15px;
}

.instruction-display {
  font-size: 36px;
  font-weight: 900;
  padding: 25px;
  border-radius: 15px;
  color: #fff;
}

.instruction-display.go_no_go {
  background: #33B555;
}

.instruction-display.choice_reaction {
  background: #2196F3;
}

.instruction-display.serial_reaction {
  background: #9C27B0;
}

/* 反馈区域 */
.feedback-area {
  padding: 30px;
  border-radius: 20px;
  text-align: center;
}

.feedback-area.correct {
  background: #E8F5E9;
}

.feedback-area.error {
  background: #FFEBEE;
}

.feedback-icon {
  font-size: 64px;
  margin-bottom: 10px;
}

.feedback-area.correct .feedback-icon {
  color: #33B555;
}

.feedback-area.error .feedback-icon {
  color: #FF4444;
}

.feedback-message {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 10px;
}

.feedback-area.correct .feedback-message {
  color: #33B555;
}

.feedback-area.error .feedback-message {
  color: #FF4444;
}

.feedback-rt {
  font-size: 18px;
  color: #888;
}

/* 游戏控制 */
.game-controls {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: auto;
  padding-top: 20px;
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
  height: 100%;
  display: flex; 
  flex-direction: column;
  align-items: center; 
  justify-content: center; 
  background: rgba(0,0,0,0.05); 
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
