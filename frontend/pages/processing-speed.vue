<template>
  <div class="training-container">
    
    <!-- 结算状态 -->
    <div v-if="game.status === 'SETTLING'" class="settling-view">
      <h1 class="settling-title">训练完成</h1>
      <div class="settling-score">
        <span class="label">总得分</span>
        <span class="value">{{ game.score }}</span>
      </div>
      
      <!-- 各模块统计 -->
      <div class="module-stats" v-if="summary">
        <div class="stat-module" v-if="summary.go_no_go">
          <h3>反应控制</h3>
          <div class="stat-row">
            <span>正确率</span>
            <span>{{ (summary.go_no_go.accuracy * 100).toFixed(1) }}%</span>
          </div>
          <div class="stat-row" v-if="summary.go_no_go.avg_go_rt">
            <span>平均反应时</span>
            <span>{{ summary.go_no_go.avg_go_rt.toFixed(0) }}ms</span>
          </div>
        </div>
        
        <div class="stat-module" v-if="summary.choice_reaction">
          <h3>选择反应</h3>
          <div class="stat-row">
            <span>正确率</span>
            <span>{{ (summary.choice_reaction.accuracy * 100).toFixed(1) }}%</span>
          </div>
          <div class="stat-row" v-if="summary.choice_reaction.avg_rt">
            <span>平均反应时</span>
            <span>{{ summary.choice_reaction.avg_rt.toFixed(0) }}ms</span>
          </div>
        </div>
        
        <div class="stat-module" v-if="summary.serial_reaction">
          <h3>序列学习</h3>
          <div class="stat-row">
            <span>正确率</span>
            <span>{{ (summary.serial_reaction.accuracy * 100).toFixed(1) }}%</span>
          </div>
          <div class="stat-row">
            <span>完成序列</span>
            <span>{{ summary.serial_reaction.sequences_completed }}个</span>
          </div>
        </div>
      </div>
      
      <div class="settling-buttons">
        <button @click="restartGame" class="restart-btn">🔄 再来一次</button>
        <button @click="exitGame" class="exit-btn">✖ 返回列表</button>
      </div>
    </div>

    <!-- 准备状态 -->
    <div v-else-if="game.status === 'READY'" class="ready-view">
      <div class="center-hint">请在投影区域开始训练</div>
      <div class="hint-sub">站在投影区域的圆圈内即可开始</div>
      <div class="bottom-bar">
        <button @click="exitGame" class="big-exit-btn" :disabled="isExiting">
          {{ isExiting ? '退出中...' : '退出训练' }}
        </button>
      </div>
    </div>

    <!-- 游戏中 -->
    <div v-else-if="game.status === 'PLAYING'" class="playing-view">
      <div class="header">
        <div class="module-info">
          <h1>{{ moduleName }}</h1>
          <span class="module-hint">{{ moduleHint }}</span>
        </div>
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
          <span class="stat-label">试次</span>
          <span class="stat-value">{{ game.trialId }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">难度</span>
          <span class="stat-value">{{ game.difficulty }}</span>
        </div>
      </div>

      <!-- 刺激显示区域 -->
      <div class="stimulus-area">
        <!-- Go/No-Go 指示 -->
        <div v-if="game.module === 'go_no_go'" class="instruction-box">
          <div class="instruction" :class="stimulus?.is_go ? 'go' : 'no-go'">
            {{ stimulus?.is_go ? '踩绿色区域！' : '不要踩！' }}
          </div>
        </div>
        
        <!-- 选择反应指示 -->
        <div v-else-if="game.module === 'choice_reaction'" class="instruction-box">
          <div class="instruction choice">
            {{ stimulus?.instruction || '踩指定颜色' }}
          </div>
          <div class="color-indicator" :style="{ backgroundColor: targetColorHex }"></div>
        </div>
        
        <!-- 序列反应指示 -->
        <div v-else-if="game.module === 'serial_reaction'" class="instruction-box">
          <div class="instruction serial">
            按顺序踩踏
          </div>
          <div class="sequence-progress">
            {{ stimulus?.sequence_progress || '1/8' }}
          </div>
        </div>
      </div>

      <!-- 反馈显示 -->
      <div v-if="feedback" class="feedback-overlay" :class="feedback.type">
        <div class="feedback-content">
          <div class="feedback-icon">{{ feedback.type === 'correct' ? '✓' : '✗' }}</div>
          <div class="feedback-message">{{ feedback.message }}</div>
          <div class="feedback-rt" v-if="feedback.reaction_time">
            反应时间: {{ feedback.reaction_time.toFixed(0) }}ms
          </div>
        </div>
      </div>

      <div class="game-hint">
        💡 站在目标区域停留3秒确认选择
      </div>

      <div class="game-controls">
        <button @click="pauseGame" class="ctrl-btn pause">⏸ 暂停</button>
        <button @click="restartGame" class="ctrl-btn restart">🔄 重新开始</button>
        <button @click="exitGame" class="ctrl-btn exit">✖ 结束训练</button>
      </div>
    </div>
    
    <!-- 暂停状态 -->
    <div v-else-if="game.status === 'PAUSED'" class="paused-view">
      <h1>⏸ 训练已暂停</h1>
      <div class="pause-info">
        <span>得分: {{ game.score }}</span>
        <span>剩余: {{ game.timer }}s</span>
      </div>
      <div class="pause-buttons">
        <button @click="resumeGame" class="resume-btn">▶ 继续训练</button>
        <button @click="restartGame" class="restart-btn">🔄 重新开始</button>
        <button @click="exitGame" class="exit-btn">✖ 结束训练</button>
      </div>
    </div>
    
    <!-- 其他状态（IDLE等）显示准备界面 -->
    <div v-else class="ready-view">
      <div class="center-hint">请在投影区域开始训练</div>
      <div class="hint-sub">站在投影区域的圆圈内即可开始</div>
      <div class="bottom-bar">
        <button @click="exitGame" class="big-exit-btn" :disabled="isExiting">
          {{ isExiting ? '退出中...' : '退出训练' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { useRouter } from 'vue-router'

const router = useRouter()
const game = reactive({
  status: 'READY',
  score: 0,
  timer: 60,
  difficulty: 5,
  module: 'go_no_go',
  moduleName: '反应控制',
  trialId: 0
})

const stimulus = ref(null)
const feedback = ref(null)
const summary = ref(null)
const isExiting = ref(false)
let socket = null
let feedbackTimeout = null

const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

const moduleName = computed(() => {
  const names = {
    'go_no_go': '反应控制',
    'choice_reaction': '选择反应',
    'serial_reaction': '序列学习'
  }
  return names[game.module] || '处理速度训练'
})

const moduleHint = computed(() => {
  const hints = {
    'go_no_go': '绿色踩，红色不踩',
    'choice_reaction': '踩指定颜色的区域',
    'serial_reaction': '按顺序踩踏亮起的区域'
  }
  return hints[game.module] || ''
})

const targetColorHex = computed(() => {
  if (!stimulus.value?.target_color) return '#fff'
  const colors = {
    'blue': '#2196F3',
    'yellow': '#FFD111',
    'purple': '#9C27B0',
    'orange': '#FF7222'
  }
  return colors[stimulus.value.target_color] || '#fff'
})

onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  socket.on('connect', () => {
    console.log('[处理速度训练] 后端已连接')
    socket.emit('get_state', { client: 'processing_speed' })
  })
  
  socket.on('game_update', (data) => {
    console.log('[处理速度训练] game_update:', data)
    
    if (data.status) {
      game.status = data.status
    }
    
    if (data.score !== undefined) {
      game.score = data.score
    }
    
    if (data.timer !== undefined) {
      game.timer = data.timer
    }
    
    if (data.module) {
      game.module = data.module
    }
    
    if (data.module_name) {
      game.moduleName = data.module_name
    }
    
    if (data.trial_id !== undefined) {
      game.trialId = data.trial_id
    }
    
    if (data.difficulty !== undefined) {
      game.difficulty = data.difficulty
    }
    
    if (data.stimulus) {
      stimulus.value = data.stimulus
      feedback.value = null
    }
    
    if (data.feedback) {
      feedback.value = data.feedback
      if (feedbackTimeout) clearTimeout(feedbackTimeout)
      feedbackTimeout = setTimeout(() => {
        feedback.value = null
      }, 2000)
    }
    
    if (data.summary) {
      summary.value = data.summary
    }
  })
  
  socket.on('system_state', (data) => {
    if (data.state?.game) {
      // 只有当 active=false 且 status=IDLE 时才返回游戏列表
      if (data.state.game.active === false && data.state.game.status === 'IDLE') {
        console.log('[处理速度训练] 游戏已停止，返回列表')
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

const pauseGame = () => {
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'pause' })
  }
}

const resumeGame = () => {
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'pause' })  // 再次发送pause切换回PLAYING
  }
}

const restartGame = () => {
  if (socket && socket.connected) {
    socket.emit('game_control', { action: 'restart', game: 'processing_speed' })
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
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
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
  padding: 40px;
}

.settling-title {
  font-size: 48px;
  font-weight: 900;
  color: #FFD700;
  margin-bottom: 30px;
}

.settling-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 30px;
}

.settling-score .label {
  font-size: 20px;
  color: #888;
  margin-bottom: 10px;
}

.settling-score .value {
  font-size: 72px;
  font-weight: 900;
  color: #FFD700;
}

.module-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 40px;
  flex-wrap: wrap;
  justify-content: center;
}

.stat-module {
  background: rgba(255,255,255,0.1);
  border-radius: 16px;
  padding: 20px;
  min-width: 150px;
}

.stat-module h3 {
  font-size: 16px;
  color: #FFD700;
  margin-bottom: 12px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  margin-bottom: 8px;
}

.stat-row span:first-child {
  color: #888;
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
  font-size: 20px;
  font-weight: bold;
  border: none;
  cursor: pointer;
}

.exit-btn {
  padding: 20px 40px;
  background: #FB4422;
  color: #FFF;
  border-radius: 40px;
  font-size: 20px;
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
  font-size: 42px; 
  font-weight: 900; 
  color: #fff; 
  text-align: center;
}

.hint-sub {
  font-size: 20px;
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
  font-size: 24px; 
  border: none;
  cursor: pointer;
}

.big-exit-btn:disabled {
  background: #666;
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

.module-info h1 {
  font-size: 32px;
  color: #fff;
  margin: 0;
}

.module-hint {
  font-size: 14px;
  color: #888;
}

.timer-display {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.timer-label {
  font-size: 14px;
  color: #888;
}

.timer-value {
  font-size: 36px;
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
  font-size: 14px;
  color: #888;
}

.stat-value {
  font-size: 28px;
  font-weight: 900;
  color: #fff;
}

.stat-value.score {
  color: #FFD700;
}

/* 刺激区域 */
.stimulus-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.instruction-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.instruction {
  font-size: 48px;
  font-weight: 900;
  padding: 30px 60px;
  border-radius: 20px;
  text-align: center;
}

.instruction.go {
  background: #33B555;
  color: #fff;
}

.instruction.no-go {
  background: #FF4444;
  color: #fff;
}

.instruction.choice {
  background: #2196F3;
  color: #fff;
}

.instruction.serial {
  background: #9C27B0;
  color: #fff;
}

.color-indicator {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 4px solid #fff;
}

.sequence-progress {
  font-size: 24px;
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
  gap: 15px;
  padding: 20px;
}

.ctrl-btn {
  padding: 16px 28px;
  border-radius: 30px;
  border: none;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
}

.ctrl-btn.pause {
  background: #FFD111;
  color: #333;
}

.ctrl-btn.restart {
  background: #FF7222;
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
}

.paused-view h1 { 
  font-size: 42px; 
  color: #fff; 
  margin-bottom: 20px; 
}

.pause-info {
  display: flex;
  gap: 40px;
  font-size: 20px;
  color: #888;
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
  font-size: 20px;
  font-weight: bold; 
  border: none;
  cursor: pointer;
}
</style>
