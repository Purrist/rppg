<template>
  <div class="projection-page" ref="pageRef">
    <!-- 底层：主Canvas（背景、粒子、绿点等） -->
    <canvas ref="mainCanvas" class="main-canvas"></canvas>
    
    <!-- 中层：游戏内容（处理速度训练的8个区域） -->
    <ProcessingSpeedGame
      v-if="gameState === 'PLAYING' && currentGame === 'processing_speed'"
      :game-state="game"
      :foot-position="footPosition"
      :canvas-width="containerWidth"
      :canvas-height="containerHeight"
      :scale-x="scaleX"
      :scale-y="scaleY"
      @action="handleGameAction"
      class="game-layer"
    />
    
    <!-- 顶层：绿点（始终显示在最上层） -->
    <canvas ref="footCanvas" class="foot-canvas"></canvas>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import { io } from 'socket.io-client'
import { initStore, subscribe, gameControl, gameAction, getState } from '../core/systemStore.js'
import ProcessingSpeedGame from '../components/ProcessingSpeedGame.vue'

// Socket和订阅
let socket = null
let unsubscribe = null

// ==================== 配置 ====================
const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`
const apiUrl = backendUrl

// ==================== Canvas ====================
const mainCanvas = ref(null)
const footCanvas = ref(null)
const pageRef = ref(null)
let ctx = null
let footCtx = null
let animationId = null
let footAnimationId = null

// ==================== 画布尺寸 ====================
const canvasWidth = 640
const canvasHeight = 360
const scaleX = ref(1)
const scaleY = ref(1)
// ⭐ 实际容器尺寸（用于传递给游戏组件）
const containerWidth = ref(1920)
const containerHeight = ref(1080)

// ==================== 游戏状态 ====================
const gameState = ref('IDLE')
const currentGame = ref(null)  // ⭐ 初始为 null，等待后端确认
const game = ref({
  status: 'IDLE',
  score: 0,
  timer: 60,
  current_mole: -1,
  accuracy: 0,
  module: null,
  difficulty_level: 3,
  stimulus: null,
  feedback: null,
  dwell_time: 3.0,  // ⭐ 确认时间（秒）
  in_interval: true,  // ⭐ 是否在间隔期
  question: null,  // ⭐ 当前题目
  remaining_time: 0  // ⭐ 剩余作答时间
})

// ==================== 处理速度训练状态（通过组件处理）====================
// 注意：游戏中内容在ProcessingSpeedGame.vue组件中处理

// ==================== 用户位置 ====================
const footPosition = reactive({ x: 320, y: 180, detected: false })

// ==================== 等待状态 ====================
const readyProgress = ref(0)
const readyStartTime = ref(0)
const readyEnterTime = ref(0)
const READY_DURATION = 3000
const READY_TIMEOUT = 180000

// ==================== 地鼠洞配置 ====================
const holes = [
  { x: 130, y: 240, radius: 80 },
  { x: 320, y: 240, radius: 80 },
  { x: 510, y: 240, radius: 80 }
]

const holeProgress = ref([0, 0, 0])
const holeStartTime = ref([0, 0, 0])
const holeFeedback = ref([null, null, null])
const holeFeedbackTime = ref([0, 0, 0])
// ⭐ 从后端状态读取确认时间
const getHoleDuration = () => {
  const state = getState()
  return state.value?.settings?.dwellTime || 2000
}
const FEEDBACK_DURATION = 1000

// 注意：处理速度训练的游戏内容在ProcessingSpeedGame.vue组件中处理

// ==================== 粒子系统 ====================
let particles = []

// ==================== Socket ====================
let statusInterval = null

// ==================== 初始化Canvas ====================
// ⭐ 设计尺寸（16:9 比例）
const DESIGN_WIDTH = 640
const DESIGN_HEIGHT = 360
const DESIGN_RATIO = DESIGN_WIDTH / DESIGN_HEIGHT  // 16:9 = 1.777...

function initCanvas() {
  if (!mainCanvas.value || !pageRef.value) return
  
  const container = pageRef.value
  const containerW = container.clientWidth
  const containerH = container.clientHeight
  const containerRatio = containerW / containerH

  // ⭐ 计算等比例缩放的尺寸（保持16:9，添加黑边）
  let renderWidth, renderHeight
  if (containerRatio > DESIGN_RATIO) {
    // 屏幕太宽，以高度为基准，左右加黑边
    renderHeight = containerH
    renderWidth = containerH * DESIGN_RATIO
  } else {
    // 屏幕太高或正好，以宽度为基准，上下加黑边
    renderWidth = containerW
    renderHeight = containerW / DESIGN_RATIO
  }

  // 设置Canvas尺寸为实际渲染尺寸
  mainCanvas.value.width = renderWidth
  mainCanvas.value.height = renderHeight

  // ⭐ 更新容器尺寸（传递给子组件）
  containerWidth.value = renderWidth
  containerHeight.value = renderHeight

  // ⭐ 等比例缩放（scaleX === scaleY）
  const scale = renderWidth / DESIGN_WIDTH
  scaleX.value = scale
  scaleY.value = scale

  // ⭐ 居中显示
  const offsetX = (containerW - renderWidth) / 2
  const offsetY = (containerH - renderHeight) / 2
  mainCanvas.value.style.left = offsetX + 'px'
  mainCanvas.value.style.top = offsetY + 'px'
  
  ctx = mainCanvas.value.getContext('2d')
  
  // 初始化绿点Canvas（同样居中）
  if (footCanvas.value) {
    footCanvas.value.width = renderWidth
    footCanvas.value.height = renderHeight
    footCanvas.value.style.left = offsetX + 'px'
    footCanvas.value.style.top = offsetY + 'px'
    footCtx = footCanvas.value.getContext('2d')
  }
  
  if (particles.length === 0) {
    initParticles()
  }
}

// ==================== 粒子系统 ====================
function initParticles() {
  if (particles.length > 0) return
  
  for (let i = 0; i < 40; i++) {
    particles.push(createParticle())
  }
}

function createParticle() {
  return {
    x: Math.random() * canvasWidth,
    y: Math.random() * canvasHeight,
    vx: (Math.random() - 0.5) * 0.3,
    vy: (Math.random() - 0.5) * 0.3,
    radius: 4 + Math.random() * 8,
    alpha: 0.4 + Math.random() * 0.5,
    hue: 220 + Math.random() * 60,
    sat: 60 + Math.random() * 40,
    light: 50 + Math.random() * 30,
    life: 1,
    decay: 0.001 + Math.random() * 0.002
  }
}

function updateParticles() {
  if (gameState.value === 'PLAYING') {
    particles = []
    return
  }
  
  const footX = footPosition.x
  const footY = footPosition.y
  const hasFoot = footPosition.detected
  
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    p.x += p.vx
    p.y += p.vy
    
    if (hasFoot) {
      const dx = p.x - footX
      const dy = p.y - footY
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 120) {
        const force = (120 - dist) / 120 * 0.5
        p.vx += (dx / dist) * force
        p.vy += (dy / dist) * force
        p.life -= 0.01
      }
    }
    
    const margin = 30
    if (p.x < margin || p.x > canvasWidth - margin || p.y < margin || p.y > canvasHeight - margin) {
      p.life -= 0.03
    }
    p.life -= p.decay
    if (p.life <= 0) particles.splice(i, 1)
  }
  
  while (particles.length < 40) {
    particles.push(createParticle())
  }
}

function drawParticles() {
  if (!ctx || gameState.value === 'PLAYING') return
  
  ctx.save()
  ctx.scale(scaleX.value, scaleY.value)
  
  particles.forEach(p => {
    const alpha = p.alpha * p.life
    if (alpha <= 0) return
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx.fillStyle = `hsla(${p.hue}, ${p.sat}%, ${p.light}%, ${alpha})`
    ctx.fill()
    if (p.radius > 5) {
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius * 2, 0, Math.PI * 2)
      ctx.fillStyle = `hsla(${p.hue}, ${p.sat}%, ${p.light}%, ${alpha * 0.15})`
      ctx.fill()
    }
  })
  
  ctx.restore()
}

// ==================== 绘制背景 ====================
function drawBackground() {
  if (!ctx) return
  
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  
  if (gameState.value === 'PLAYING') return
  
  const centerX = mainCanvas.value.width / 2
  const centerY = mainCanvas.value.height / 2
  const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, centerX)
  gradient.addColorStop(0, 'rgba(60, 20, 100, 0.2)')
  gradient.addColorStop(0.5, 'rgba(30, 10, 60, 0.1)')
  gradient.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
}

// ==================== 绘制绿点（独立Canvas，始终在最上层） ====================
function drawFootPoint() {
  if (!footCtx || !footPosition.detected) return
  
  // 清空绿点Canvas
  footCtx.clearRect(0, 0, footCanvas.value.width, footCanvas.value.height)
  
  let x = Math.max(50, Math.min(590, footPosition.x))
  let y = Math.max(50, Math.min(310, footPosition.y))
  
  if (!Number.isFinite(x)) x = 320
  if (!Number.isFinite(y)) y = 180
  
  footCtx.save()
  footCtx.scale(scaleX.value, scaleY.value)
  
  // 外圈光晕
  footCtx.beginPath()
  footCtx.arc(x, y, 40, 0, Math.PI * 2)
  footCtx.fillStyle = 'rgba(51, 181, 85, 0.25)'
  footCtx.fill()
  
  // 中圈
  footCtx.beginPath()
  footCtx.arc(x, y, 25, 0, Math.PI * 2)
  const gradient = footCtx.createRadialGradient(x, y, 0, x, y, 25)
  gradient.addColorStop(0, '#55ee77')
  gradient.addColorStop(1, '#228B22')
  footCtx.fillStyle = gradient
  footCtx.fill()
  
  // 内圈高光
  footCtx.beginPath()
  footCtx.arc(x, y, 9, 0, Math.PI * 2)
  footCtx.fillStyle = 'rgba(255, 255, 255, 0.95)'
  footCtx.fill()
  
  footCtx.restore()
}

// ==================== 绿点动画循环 ====================
function drawFootLoop() {
  if (footPosition.detected) {
    drawFootPoint()
  } else if (footCtx && footCanvas.value) {
    // 没有检测到人时清空
    footCtx.clearRect(0, 0, footCanvas.value.width, footCanvas.value.height)
  }
  footAnimationId = requestAnimationFrame(drawFootLoop)
}

// ==================== 绘制等待圈 ====================
function drawReadyCircle() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX.value, scaleY.value)
  
  const cx = 320, cy = 180, radius = 80
  
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.strokeStyle = 'rgba(120, 120, 120, 0.9)'
  ctx.lineWidth = 14
  ctx.stroke()
  
  if (readyProgress.value > 0) {
    ctx.beginPath()
    ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * readyProgress.value / 100))
    ctx.strokeStyle = '#FF7222'
    ctx.lineWidth = 14
    ctx.lineCap = 'round'
    ctx.stroke()
  }
  
  ctx.restore()
  
  ctx.font = 'bold 48px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.fillText('请进入圆圈内', mainCanvas.value.width / 2, mainCanvas.value.height / 2 - 250)
}

// ==================== 绘制结算界面 ====================
function drawSettling() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX.value, scaleY.value)
  
  ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
  ctx.fillRect(0, 0, canvasWidth, canvasHeight)
  
  ctx.font = 'bold 72px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#FFD700'
  ctx.fillText('游戏结束', canvasWidth / 2, canvasHeight / 2 - 60)
  
  ctx.font = 'bold 48px Arial'
  ctx.fillStyle = '#ffffff'
  ctx.fillText(`得分: ${game.value.score}`, canvasWidth / 2, canvasHeight / 2 + 20)
  
  ctx.font = 'bold 36px Arial'
  ctx.fillStyle = '#888888'
  ctx.fillText(`准确率: ${game.value.accuracy}%`, canvasWidth / 2, canvasHeight / 2 + 80)
  
  ctx.restore()
}

// ==================== 绘制地鼠洞 (打地鼠游戏) ====================
function drawMoleHoles() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX.value, scaleY.value)
  
  holes.forEach((hole, index) => {
    const hasMole = game.value.current_mole === index
    const progress = holeProgress.value[index]
    const feedback = holeFeedback.value[index]
    
    let holeColor = '#444'
    let glowColor = null
    if (feedback === 'correct') {
      holeColor = '#33B555'
      glowColor = 'rgba(51, 181, 85, 0.5)'
    } else if (feedback === 'wrong') {
      holeColor = '#ff4444'
      glowColor = 'rgba(255, 68, 68, 0.5)'
    }
    
    if (glowColor) {
      ctx.beginPath()
      ctx.arc(hole.x, hole.y, hole.radius + 25, 0, Math.PI * 2)
      ctx.fillStyle = glowColor
      ctx.fill()
    }
    
    ctx.beginPath()
    ctx.arc(hole.x, hole.y, hole.radius, 0, Math.PI * 2)
    ctx.fillStyle = '#1a1a1a'
    ctx.fill()
    
    ctx.beginPath()
    ctx.arc(hole.x, hole.y, hole.radius, 0, Math.PI * 2)
    ctx.strokeStyle = hasMole ? '#8B4513' : holeColor
    ctx.lineWidth = 5
    ctx.stroke()
    
    if (hasMole && !feedback) {
      ctx.font = '60px Arial'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText('🐹', hole.x, hole.y)
    }
    
    if (progress > 0 && !feedback) {
      ctx.beginPath()
      ctx.arc(hole.x, hole.y, hole.radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * progress / 100))
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 14
      ctx.lineCap = 'round'
      ctx.stroke()
    }
  })
  
  ctx.restore()
}

// ==================== 绘制游戏信息 ====================
function drawGameInfo() {
  if (!ctx) return
  if (gameState.value !== 'PLAYING' && gameState.value !== 'PAUSED') return
  
  // 处理速度训练有自己的游戏信息显示
  if (currentGame.value === 'processing_speed') return
  
  ctx.font = 'bold 40px Arial'
  ctx.textAlign = 'center'
  ctx.fillStyle = '#ffffff'
  ctx.fillText(`${game.value.timer}s`, mainCanvas.value.width / 2, 55)
  
  ctx.font = 'bold 36px Arial'
  ctx.fillStyle = '#FFD700'
  ctx.fillText(`得分: ${game.value.score}`, mainCanvas.value.width / 2, 110)
}

// ==================== 绘制暂停遮罩 ====================
function drawPauseOverlay() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX.value, scaleY.value)
  
  ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
  ctx.fillRect(0, 0, canvasWidth, canvasHeight)
  
  ctx.font = 'bold 72px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.fillText('已暂停', canvasWidth / 2, canvasHeight / 2)
  
  ctx.restore()
}

// ==================== 主绘制循环 ====================
function draw() {
  if (!ctx) return
  
  ctx.clearRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  
  drawBackground()
  updateParticles()
  drawParticles()
  
  // 根据游戏类型和状态选择绘制
  if (gameState.value === 'READY') {
    drawReadyCircle()
  } else if (gameState.value === 'PLAYING') {
    // 打地鼠游戏在主Canvas绘制
    if (currentGame.value === 'whack_a_mole') {
      drawMoleHoles()
      drawGameInfo()
    }
    // 注意：处理速度训练在ProcessingSpeedGame.vue组件中绘制
  } else if (gameState.value === 'PAUSED') {
    if (currentGame.value === 'whack_a_mole') {
      drawMoleHoles()
      drawGameInfo()
    }
    // 注意：处理速度训练在ProcessingSpeedGame.vue组件中绘制
    drawPauseOverlay()
  } else if (gameState.value === 'SETTLING') {
    drawSettling()
  }
  
  // ⭐ 绿点现在由独立的 footCanvas 绘制，始终在最上层
  
  animationId = requestAnimationFrame(draw)
}

// ==================== READY状态逻辑 ====================
function updateReadyState() {
  if (gameState.value !== 'READY') return
  
  const centerX = 320, centerY = 180, radius = 80
  const dx = footPosition.x - centerX
  const dy = footPosition.y - centerY
  const inZone = footPosition.detected && (dx * dx + dy * dy <= radius * radius)
  
  if (inZone) {
    if (readyStartTime.value === 0) {
      readyStartTime.value = Date.now()
    }
    readyProgress.value = Math.min(100, ((Date.now() - readyStartTime.value) / READY_DURATION) * 100)
    
    if (readyProgress.value >= 100) {
      if (socket) {
        socket.emit('game_control', { action: 'start' })
      }
    }
  } else {
    readyStartTime.value = 0
    readyProgress.value = 0
  }
  
  if (readyEnterTime.value > 0 && Date.now() - readyEnterTime.value > READY_TIMEOUT) {
    console.log('[投影] 准备超时，回到待机状态')
    gameState.value = 'IDLE'
    game.value.status = 'IDLE'
    readyEnterTime.value = 0
    readyProgress.value = 0
    readyStartTime.value = 0
    if (socket) {
      socket.emit('game_control', { action: 'timeout_stop' })
    }
  }
}

// ==================== PLAYING状态逻辑 (打地鼠) ====================
function updatePlayingState() {
  if (gameState.value !== 'PLAYING') return

  const now = Date.now()

  // 处理打地鼠游戏的交互
  if (currentGame.value === 'whack_a_mole') {
    holes.forEach((hole, index) => {
      const feedback = holeFeedback.value[index]
      const feedbackTime = holeFeedbackTime.value[index]

      if (feedback) {
        if (now - feedbackTime > FEEDBACK_DURATION) {
          holeFeedback.value[index] = null
          holeProgress.value[index] = 0
          holeStartTime.value[index] = 0
        }
        return
      }

      const dx = footPosition.x - hole.x
      const dy = footPosition.y - hole.y
      const inHole = footPosition.detected && (dx * dx + dy * dy <= hole.radius * hole.radius)

      if (inHole) {
        if (holeStartTime.value[index] === 0) {
          holeStartTime.value[index] = now
        }

        const elapsed = now - holeStartTime.value[index]
        const holeDuration = getHoleDuration()
        holeProgress.value[index] = Math.min(100, (elapsed / holeDuration) * 100)

        if (holeProgress.value[index] >= 100) {
          const hit = game.value.current_mole === index
          holeFeedback.value[index] = hit ? 'correct' : 'wrong'
          holeFeedbackTime.value[index] = now

          if (socket) {
            socket.emit('game_hit', { hole: index, hit })
          }
        }
      } else {
        holeProgress.value[index] = 0
        holeStartTime.value[index] = 0
      }
    })
  }

  // 注意：处理速度训练的交互在ProcessingSpeedGame.vue组件中处理
}

// ==================== 处理游戏组件事件 ====================
function handleGameAction(action) {
  if (action.type === 'zone_dwell_completed') {
    if (socket) {
      socket.emit('game_action', {
        action: 'zone_dwell_completed',
        zone_id: action.zone_id,
        dwell_time: action.dwell_time
      })
    }
  }
}

// ==================== 状态更新 ====================
async function updateStatus() {
  try {
    const res = await fetch(`${apiUrl}/api/status`)
    if (res.ok) {
      const data = await res.json()
      let x = data.feet_x
      let y = data.feet_y
      if (Number.isFinite(x) && Number.isFinite(y)) {
        footPosition.x = Math.max(50, Math.min(590, x))
        footPosition.y = Math.max(50, Math.min(310, y))
      }
      footPosition.detected = data.feet_detected
    }
  } catch (e) {}
}

// ==================== 监听游戏状态变化 ====================
watch(() => game.value.status, (newStatus, oldStatus) => {
  console.log('[投影] 状态变化:', oldStatus, '->', newStatus)
  
  gameState.value = newStatus
  
  if (newStatus === 'IDLE') {
    readyEnterTime.value = 0
    readyProgress.value = 0
    readyStartTime.value = 0
    holeProgress.value = [0, 0, 0]
    holeStartTime.value = [0, 0, 0]
    holeFeedback.value = [null, null, null]
    initParticles()
  } else if (newStatus === 'READY') {
    readyProgress.value = 0
    readyStartTime.value = 0
    readyEnterTime.value = Date.now()
  } else if (newStatus === 'PLAYING') {
    holeProgress.value = [0, 0, 0]
    holeStartTime.value = [0, 0, 0]
    holeFeedback.value = [null, null, null]
    particles = []
  } else if (newStatus === 'PAUSED') {
    console.log('[投影] 游戏暂停')
  }
})

// ==================== 生命周期 ====================
onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  socket.on('connect', () => {
    console.log('[投影] 后端已连接')
    socket.emit('get_state', { client: 'projection' })
  })
  
  socket.on('game_update', (data) => {
    console.log('[projection] game_update:', data)

    // 更新游戏状态
    game.value.status = data.status || 'IDLE'
    game.value.score = data.score || 0
    game.value.timer = data.timer || 60

    // ⭐ 严格根据 game_id 判断游戏类型
    const gameId = data.game_id || ''
    console.log('[projection] game_id:', gameId, 'currentGame:', currentGame.value)

    if (gameId === 'processing_speed') {
      currentGame.value = 'processing_speed'
      game.value.module = data.module || 'go_no_go'
      console.log('[projection] 切换到处理速度训练')
    } else if (gameId === 'whack_a_mole') {
      currentGame.value = 'whack_a_mole'
      game.value.module = null
      console.log('[projection] 切换到打地鼠')
    }
    // 注意：不再使用 data.module 来判断，避免误判

    // ⭐ 更新游戏状态（通过systemStore发送到后端）
    if (data.game_id) {
      // 使用systemStore更新
    }

    // 更新难度等级
    if (data.difficulty_level) {
      game.value.difficulty_level = data.difficulty_level
    }

    // ⭐ 更新确认时间（关键！）
    if (data.dwell_time !== undefined) {
      game.value.dwell_time = data.dwell_time
      console.log('[projection] 更新确认时间:', data.dwell_time)
    }

    // 更新间隔状态
    if (data.in_interval !== undefined) {
      game.value.in_interval = data.in_interval
    }

    // 更新题目
    if (data.question !== undefined) {
      game.value.question = data.question
    }

    // 更新剩余时间
    if (data.remaining_time !== undefined) {
      game.value.remaining_time = data.remaining_time
    }

    // 打地鼠数据
    if (data.extra) {
      game.value.current_mole = data.extra.current_mole ?? -1
    }
    if (data.stats) {
      game.value.accuracy = Math.round((data.stats.accuracy || 0) * 100)
    }

    // 注意：处理速度训练的数据处理在ProcessingSpeedGame.vue组件中进行
  })
  
  socket.on('system_state', (data) => {
    // 不做处理
  })
  
  setTimeout(() => {
    initCanvas()
    draw()
    drawFootLoop() // ⭐ 启动绿点动画循环
  }, 100)
  
  statusInterval = setInterval(() => {
    updateStatus()
    if (gameState.value === 'READY') updateReadyState()
    else if (gameState.value === 'PLAYING') updatePlayingState()
  }, 16)
  
  window.addEventListener('resize', initCanvas)
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  if (footAnimationId) cancelAnimationFrame(footAnimationId)
  if (statusInterval) clearInterval(statusInterval)
  if (socket) socket.disconnect()
  window.removeEventListener('resize', initCanvas)
})
</script>

<style scoped>
.projection-page {
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

/* 主Canvas（底层） */
.main-canvas {
  position: absolute;
  /* top和left由JS动态设置以实现居中 */
  display: block !important;
  z-index: 1;
}

/* 游戏层（中层） */
.game-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100% !important;
  height: 100% !important;
  z-index: 2;
}

/* 绿点Canvas（顶层） */
.foot-canvas {
  position: absolute;
  /* top和left由JS动态设置以实现居中 */
  display: block !important;
  z-index: 10;
  pointer-events: none; /* 让点击事件穿透 */
}
</style>
