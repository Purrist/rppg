<template>
  <div class="developer-page">
    <h1>🛠 开发者后台</h1>
    <p class="subtitle">系统级状态监控 | SystemCore v3.0</p>
    
    <!-- ⭐ 系统核心状态面板 -->
    <div class="section">
      <h2>🎯 系统核心状态</h2>
      <div class="core-status-grid">
        <!-- AI模式 -->
        <div class="status-card" :class="{ 'active': aiMode === 'companion' }">
          <div class="card-icon">🤖</div>
          <div class="card-content">
            <div class="card-label">AI模式</div>
            <div class="card-value" :class="aiModeClass">{{ aiModeText }}</div>
          </div>
        </div>
        
        <!-- 当前页面 -->
        <div class="status-card">
          <div class="card-icon">📄</div>
          <div class="card-content">
            <div class="card-label">当前页面</div>
            <div class="card-value">{{ currentPageText }}</div>
          </div>
        </div>
        
        <!-- 游戏状态 -->
        <div class="status-card" :class="{ 'active': gameStatus !== 'IDLE' }">
          <div class="card-icon">🎮</div>
          <div class="card-content">
            <div class="card-label">游戏状态</div>
            <div class="card-value" :class="gameStatusClass">{{ gameStatusText }}</div>
          </div>
        </div>
        
        <!-- 当前游戏 -->
        <div class="status-card" :class="{ 'active': currentGame !== null }">
          <div class="card-icon">🎯</div>
          <div class="card-content">
            <div class="card-label">当前游戏</div>
            <div class="card-value">{{ currentGameText }}</div>
          </div>
        </div>
        
        <!-- 游戏难度 -->
        <div class="status-card">
          <div class="card-icon">⚡</div>
          <div class="card-content">
            <div class="card-label">游戏难度</div>
            <div class="card-value">{{ gameDifficulty }} / 8</div>
          </div>
        </div>
        
        <!-- 确认时间 -->
        <div class="status-card">
          <div class="card-icon">⏱️</div>
          <div class="card-content">
            <div class="card-label">确认时间</div>
            <div class="card-value">{{ (dwellTime / 1000).toFixed(1) }}s</div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- ⭐ 游戏运行时数据 -->
    <div class="section" v-if="gameStatus !== 'IDLE'">
      <h2>📊 游戏运行时数据</h2>
      <div class="runtime-grid">
        <div class="runtime-item">
          <span class="runtime-label">得分</span>
          <span class="runtime-value">{{ gameRuntime.score }}</span>
        </div>
        <div class="runtime-item">
          <span class="runtime-label">剩余时间</span>
          <span class="runtime-value">{{ gameRuntime.timer }}s</span>
        </div>
        <div class="runtime-item">
          <span class="runtime-label">准确率</span>
          <span class="runtime-value">{{ gameRuntime.accuracy.toFixed(1) }}%</span>
        </div>
        <div class="runtime-item">
          <span class="runtime-label">试次</span>
          <span class="runtime-value">{{ gameRuntime.trialCount }}</span>
        </div>
        <div class="runtime-item">
          <span class="runtime-label">正确</span>
          <span class="runtime-value">{{ gameRuntime.correctCount }}</span>
        </div>
      </div>
    </div>
    
    <!-- ⭐ 用户感知状态 -->
    <div class="section">
      <h2>👤 用户感知状态</h2>
      <div class="perception-grid">
        <div class="perception-item" :class="{ detected: perception.personDetected }">
          <span class="perception-icon">👤</span>
          <span class="perception-label">人物检测</span>
          <span class="perception-status">{{ perception.personDetected ? '已检测' : '未检测' }}</span>
        </div>
        <div class="perception-item">
          <span class="perception-icon">😊</span>
          <span class="perception-label">情绪</span>
          <span class="perception-status">{{ perception.emotion }}</span>
        </div>
        <div class="perception-item">
          <span class="perception-icon">👁️</span>
          <span class="perception-label">注意力</span>
          <span class="perception-status">{{ perception.attention }}</span>
        </div>
        <div class="perception-item">
          <span class="perception-icon">😴</span>
          <span class="perception-label">疲劳度</span>
          <span class="perception-status">{{ perception.fatigue }}</span>
        </div>
        <div class="perception-item">
          <span class="perception-icon">❤️</span>
          <span class="perception-label">心率</span>
          <span class="perception-status">{{ perception.heartRate || '--' }}</span>
        </div>
        <div class="perception-item" :class="{ detected: perception.footPosition?.detected }">
          <span class="perception-icon">👣</span>
          <span class="perception-label">脚部位置</span>
          <span class="perception-status">
            {{ perception.footPosition?.detected 
               ? `(${perception.footPosition.x.toFixed(0)}, ${perception.footPosition.y.toFixed(0)})` 
               : '未检测' }}
          </span>
        </div>
      </div>
    </div>
    
    <!-- ⭐ 快速控制 -->
    <div class="section">
      <h2>🎮 快速控制</h2>
      <div class="control-grid">
        <button class="control-btn" :class="{ active: aiMode === 'companion' }" @click="toggleCompanion">
          {{ aiMode === 'companion' ? '关闭智伴' : '开启智伴' }}
        </button>
        <button class="control-btn" @click="navigateTo('/')">首页</button>
        <button class="control-btn" @click="navigateTo('/learning')">益智训练</button>
        <button class="control-btn" @click="navigateTo('/training')">游戏训练</button>
        <button class="control-btn" @click="navigateTo('/projection')">投影</button>
      </div>
    </div>
    
    <!-- ⭐ 原始状态JSON -->
    <div class="section">
      <h2>📋 完整状态数据</h2>
      <pre class="json-display">{{ formattedState }}</pre>
    </div>
    
    <!-- ⭐ 连接状态 -->
    <div class="connection-status" :class="{ connected: isConnected }">
      {{ isConnected ? '🟢 已连接' : '🔴 未连接' }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { initStore, subscribe, setAIMode, setCurrentPage, toggleCompanion } from '../core/systemStore.js'

// Socket
let socket = null
let unsubscribe = null
const isConnected = ref(false)

// 系统状态
const aiMode = ref('basic')
const currentPage = ref('/')
const gameStatus = ref('IDLE')
const currentGame = ref(null)
const gameDifficulty = ref(3)
const gameModule = ref(null)
const dwellTime = ref(2000)
const gameRuntime = ref({
  score: 0,
  timer: 60,
  accuracy: 0,
  trialCount: 0,
  correctCount: 0
})
const perception = ref({
  personDetected: false,
  faceCount: 0,
  bodyDetected: false,
  footPosition: { x: 0, y: 0, detected: false },
  emotion: 'neutral',
  attention: 0,
  fatigue: 0,
  heartRate: null,
  timestamp: 0
})
const fullState = ref({})

// 计算属性
const aiModeText = computed(() => {
  return aiMode.value === 'companion' ? '智伴模式' : '基础模式'
})

const aiModeClass = computed(() => {
  return aiMode.value === 'companion' ? 'mode-companion' : 'mode-basic'
})

const currentPageText = computed(() => {
  const texts = {
    '/': '首页',
    '/health': '健康监测',
    '/learning': '益智训练',
    '/training': '游戏训练',
    '/entertainment': '娱乐',
    '/settings': '设置',
    '/developer': '开发者',
    '/projection': '投影'
  }
  return texts[currentPage.value] || currentPage.value
})

const gameStatusText = computed(() => {
  const texts = {
    'IDLE': '待机',
    'READY': '预备',
    'PLAYING': '游戏中',
    'PAUSED': '暂停',
    'SETTLING': '结算'
  }
  return texts[gameStatus.value] || gameStatus.value
})

const gameStatusClass = computed(() => {
  const classes = {
    'IDLE': 'status-idle',
    'READY': 'status-ready',
    'PLAYING': 'status-playing',
    'PAUSED': 'status-paused',
    'SETTLING': 'status-settling'
  }
  return classes[gameStatus.value] || ''
})

const currentGameText = computed(() => {
  const texts = {
    'whack_a_mole': '打地鼠',
    'processing_speed': '处理速度训练'
  }
  return texts[currentGame.value] || currentGame.value || '无'
})

const formattedState = computed(() => {
  return JSON.stringify(fullState.value, null, 2)
})

// 方法
const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

const navigateTo = (page) => {
  setCurrentPage(page)
}

const toggleCompanionMode = () => {
  const newMode = aiMode.value === 'companion' ? 'basic' : 'companion'
  setAIMode(newMode)
}

// 生命周期
onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  // 初始化Store
  initStore(socket)
  
  socket.on('connect', () => {
    console.log('[developer] 后端已连接')
    isConnected.value = true
    socket.emit('get_system_state')
  })
  
  socket.on('disconnect', () => {
    isConnected.value = false
  })
  
  // 订阅状态更新
  unsubscribe = subscribe((key, value, state) => {
    fullState.value = state
    
    if (key === 'init' || key === 'state') {
      // 完整状态更新
      aiMode.value = state.aiMode || 'basic'
      currentPage.value = state.currentPage || '/'
      gameStatus.value = state.game?.status || 'IDLE'
      currentGame.value = state.game?.currentGame || null
      gameDifficulty.value = state.game?.difficulty || 3
      gameModule.value = state.game?.module || null
      dwellTime.value = state.game?.dwellTime || 2000
      gameRuntime.value = state.gameRuntime || gameRuntime.value
      perception.value = state.perception || perception.value
    }
    
    if (key === 'aiMode') {
      aiMode.value = value
    }
    
    if (key === 'currentPage') {
      currentPage.value = value
    }
    
    if (key === 'game') {
      gameStatus.value = value.status || gameStatus.value
      currentGame.value = value.currentGame || currentGame.value
      gameDifficulty.value = value.difficulty || gameDifficulty.value
      gameModule.value = value.module || gameModule.value
      dwellTime.value = value.dwellTime || dwellTime.value
    }
    
    if (key === 'gameRuntime') {
      gameRuntime.value = value
    }
    
    if (key === 'perception') {
      perception.value = { ...perception.value, ...value }
    }
  })
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
  if (socket) socket.disconnect()
})
</script>

<style scoped>
.developer-page {
  padding: 40px;
  max-width: 1200px;
  margin: 0 auto;
}

.developer-page h1 {
  font-size: 36px;
  font-weight: 900;
  color: #333;
  margin-bottom: 10px;
}

.subtitle {
  font-size: 18px;
  color: #888;
  margin-bottom: 40px;
}

.section {
  margin-bottom: 40px;
}

.section h2 {
  font-size: 24px;
  color: #333;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 2px solid #FF7222;
}

/* 核心状态网格 */
.core-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
}

.status-card {
  background: #FFF;
  border-radius: 15px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 15px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: all 0.3s;
  border: 2px solid transparent;
}

.status-card.active {
  border-color: #FF7222;
  background: #FFF5F0;
}

.card-icon {
  font-size: 32px;
}

.card-content {
  flex: 1;
}

.card-label {
  font-size: 14px;
  color: #888;
  margin-bottom: 5px;
}

.card-value {
  font-size: 20px;
  font-weight: 700;
  color: #333;
}

.mode-basic {
  color: #888;
}

.mode-companion {
  color: #33B555;
}

.status-idle {
  color: #888;
}

.status-ready {
  color: #FF7222;
}

.status-playing {
  color: #33B555;
}

.status-paused {
  color: #FFAA00;
}

.status-settling {
  color: #6666FF;
}

/* 运行时数据 */
.runtime-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 15px;
}

.runtime-item {
  background: #FFF;
  border-radius: 10px;
  padding: 15px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.runtime-label {
  display: block;
  font-size: 14px;
  color: #888;
  margin-bottom: 8px;
}

.runtime-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: #FF7222;
}

/* 感知状态 */
.perception-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
}

.perception-item {
  background: #FFF;
  border-radius: 10px;
  padding: 15px;
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: all 0.3s;
}

.perception-item.detected {
  background: #E8F5E9;
  border: 2px solid #33B555;
}

.perception-icon {
  font-size: 24px;
}

.perception-label {
  font-size: 14px;
  color: #888;
}

.perception-status {
  margin-left: auto;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

/* 控制按钮 */
.control-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 15px;
}

.control-btn {
  padding: 15px 20px;
  border-radius: 10px;
  border: 2px solid #FF7222;
  background: #FFF;
  color: #FF7222;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.control-btn:hover {
  background: #FF7222;
  color: #FFF;
}

.control-btn.active {
  background: #33B555;
  border-color: #33B555;
  color: #FFF;
}

/* JSON显示 */
.json-display {
  background: #1E1E1E;
  color: #D4D4D4;
  padding: 20px;
  border-radius: 10px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 连接状态 */
.connection-status {
  position: fixed;
  bottom: 20px;
  right: 20px;
  padding: 10px 20px;
  border-radius: 20px;
  background: #FF4444;
  color: #FFF;
  font-weight: 600;
  transition: all 0.3s;
}

.connection-status.connected {
  background: #33B555;
}
</style>
