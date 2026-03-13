<!--
  GameFrame.vue - 通用游戏框架组件
  
  功能：
  1. 统一的游戏状态管理
  2. 通用的UI元素（计时器、分数、结算界面）
  3. 脚部位置检测和绘制
  4. Socket通信
  
  使用方式：
  <GameFrame :game-config="config" @game-event="onEvent">
    <template #game-content="{ state, footPosition }">
      <- 游戏特定内容 ->
    </template>
  </GameFrame>
-->

<template>
  <div class="game-frame" ref="frameRef">
    <canvas ref="mainCanvas"></canvas>
    
    <!-- 游戏特定内容插槽 -->
    <slot name="game-content" 
          :state="gameState" 
          :footPosition="footPosition"
          :ctx="ctx"
          :scaleX="scaleX"
          :scaleY="scaleY">
    </slot>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, watch, computed } from 'vue'
import { io } from 'socket.io-client'

// ==================== Props ====================
const props = defineProps({
  gameConfig: {
    type: Object,
    default: () => ({
      game_id: 'default',
      game_name: '游戏',
      duration: 60,
      zones: [],
      show_timer: true,
      show_score: true,
    })
  },
  backendUrl: {
    type: String,
    default: ''
  }
})

// ==================== Emits ====================
const emit = defineEmits([
  'state-change',
  'game-update',
  'foot-update',
  'ready-complete',
  'game-over',
])

// ==================== 配置 ====================
const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = computed(() => 
  props.backendUrl || `http://${getBackendHost()}:${FLASK_PORT}`
)

// ==================== Canvas ====================
const mainCanvas = ref(null)
const frameRef = ref(null)
let ctx = null
let animationId = null

// ==================== 画布尺寸 ====================
let canvasWidth = 640
let canvasHeight = 360
let scaleX = 1
let scaleY = 1

// ==================== 游戏状态 ====================
const gameState = reactive({
  status: 'IDLE',
  score: 0,
  timer: 60,
  difficulty: 'normal',
  extra: {},
  stats: {},
})

// ==================== 用户位置 ====================
const footPosition = reactive({ 
  x: 320, 
  y: 180, 
  detected: false 
})

// ==================== Socket ====================
let socket = null
let statusInterval = null

// ==================== 初始化Canvas ====================
function initCanvas() {
  if (!mainCanvas.value || !frameRef.value) return
  
  const container = frameRef.value
  mainCanvas.value.width = container.clientWidth
  mainCanvas.value.height = container.clientHeight
  
  scaleX = container.clientWidth / canvasWidth
  scaleY = container.clientHeight / canvasHeight
  
  ctx = mainCanvas.value.getContext('2d')
}

// ==================== 绘制背景 ====================
function drawBackground() {
  if (!ctx) return
  
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
}

// ==================== 绘制绿点 ====================
function drawFootPoint() {
  if (!ctx || !footPosition.detected) return
  
  let x = Math.max(50, Math.min(590, footPosition.x))
  let y = Math.max(50, Math.min(310, footPosition.y))
  
  if (!Number.isFinite(x)) x = 320
  if (!Number.isFinite(y)) y = 180
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  // 外圈光晕
  ctx.beginPath()
  ctx.arc(x, y, 40, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(51, 181, 85, 0.25)'
  ctx.fill()
  
  // 主圆
  ctx.beginPath()
  ctx.arc(x, y, 25, 0, Math.PI * 2)
  const gradient = ctx.createRadialGradient(x, y, 0, x, y, 25)
  gradient.addColorStop(0, '#55ee77')
  gradient.addColorStop(1, '#228B22')
  ctx.fillStyle = gradient
  ctx.fill()
  
  // 中心点
  ctx.beginPath()
  ctx.arc(x, y, 9, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.95)'
  ctx.fill()
  
  ctx.restore()
}

// ==================== 绘制游戏信息 ====================
function drawGameInfo() {
  if (!ctx || gameState.status !== 'PLAYING') return
  
  // 计时器
  if (props.gameConfig.show_timer) {
    ctx.font = 'bold 40px Arial'
    ctx.textAlign = 'center'
    ctx.fillStyle = '#ffffff'
    ctx.fillText(`${gameState.timer}s`, mainCanvas.value.width / 2, 55)
  }
  
  // 分数
  if (props.gameConfig.show_score) {
    ctx.font = 'bold 36px Arial'
    ctx.fillStyle = '#FFD700'
    ctx.fillText(`得分: ${gameState.score}`, mainCanvas.value.width / 2, 110)
  }
}

// ==================== 绘制结算界面 ====================
function drawSettling() {
  if (!ctx || gameState.status !== 'SETTLING') return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  // 半透明背景
  ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
  ctx.fillRect(0, 0, canvasWidth, canvasHeight)
  
  // 游戏结束文字
  ctx.font = 'bold 72px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#FFD700'
  ctx.fillText('游戏结束', canvasWidth / 2, canvasHeight / 2 - 60)
  
  // 得分
  ctx.font = 'bold 48px Arial'
  ctx.fillStyle = '#ffffff'
  ctx.fillText(`得分: ${gameState.score}`, canvasWidth / 2, canvasHeight / 2 + 20)
  
  // 准确率
  const accuracy = gameState.stats?.accuracy || 0
  ctx.font = 'bold 36px Arial'
  ctx.fillStyle = '#888888'
  ctx.fillText(`准确率: ${accuracy}%`, canvasWidth / 2, canvasHeight / 2 + 80)
  
  ctx.restore()
}

// ==================== 主绘制循环 ====================
function draw() {
  if (!ctx) return
  
  ctx.clearRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  
  drawBackground()
  
  // 游戏信息
  drawGameInfo()
  
  // 结算界面
  drawSettling()
  
  // 绿点
  drawFootPoint()
  
  animationId = requestAnimationFrame(draw)
}

// ==================== 状态更新 ====================
async function updateStatus() {
  try {
    const res = await fetch(`${backendUrl.value}/api/status`)
    if (res.ok) {
      const data = await res.json()
      let x = data.feet_x
      let y = data.feet_y
      if (Number.isFinite(x) && Number.isFinite(y)) {
        footPosition.x = Math.max(50, Math.min(590, x))
        footPosition.y = Math.max(50, Math.min(310, y))
      }
      footPosition.detected = data.feet_detected
      
      emit('foot-update', { ...footPosition })
    }
  } catch (e) {}
}

// ==================== 监听游戏状态变化 ====================
watch(() => gameState.status, (newStatus, oldStatus) => {
  console.log('[GameFrame] 状态变化:', oldStatus, '->', newStatus)
  emit('state-change', { oldStatus, newStatus, state: { ...gameState } })
  
  if (newStatus === 'SETTLING') {
    emit('game-over', { ...gameState })
  }
})

// ==================== Socket事件处理 ====================
function setupSocket() {
  socket = io(backendUrl.value, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  socket.on('connect', () => {
    console.log('[GameFrame] 后端已连接')
    socket.emit('get_state', { client: 'projection' })
  })
  
  socket.on('game_update', (data) => {
    Object.assign(gameState, data)
    emit('game-update', { ...gameState })
  })
  
  socket.on('system_state', (data) => {
    if (data.state?.game) {
      gameState.status = data.state.game.status || 'IDLE'
      gameState.score = data.state.game.score || 0
      gameState.timer = data.state.game.timer || 60
    }
  })
}

// ==================== 公开方法 ====================
function sendGameControl(action, data = {}) {
  if (socket) {
    socket.emit('game_control', { action, ...data })
  }
}

function sendGameHit(hole, hit) {
  if (socket) {
    socket.emit('game_hit', { hole, hit })
  }
}

// ==================== 生命周期 ====================
onMounted(() => {
  setupSocket()
  
  setTimeout(() => {
    initCanvas()
    draw()
  }, 100)
  
  statusInterval = setInterval(updateStatus, 16)
  
  window.addEventListener('resize', initCanvas)
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  if (statusInterval) clearInterval(statusInterval)
  if (socket) socket.disconnect()
  window.removeEventListener('resize', initCanvas)
})

// ==================== 暴露给父组件 ====================
defineExpose({
  sendGameControl,
  sendGameHit,
  gameState,
  footPosition,
  ctx,
  scaleX,
  scaleY,
  canvasWidth,
  canvasHeight,
})
</script>

<style scoped>
.game-frame {
  margin: 0 !important;
  padding: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  overflow: hidden !important;
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  background: #000 !important;
}

.game-frame canvas {
  width: 100% !important;
  height: 100% !important;
  display: block !important;
}
</style>
