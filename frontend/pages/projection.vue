<template>
  <div class="projection-page" ref="pageRef">
    <canvas ref="mainCanvas"></canvas>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import { io } from 'socket.io-client'

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
const pageRef = ref(null)
let ctx = null
let animationId = null

// ==================== 游戏状态 ====================
const gameState = ref('IDLE')
const game = ref({
  status: 'IDLE',
  score: 0,
  timer: 60,
  current_mole: -1
})

// ==================== 用户位置 ====================
const footPosition = reactive({ x: 320, y: 180, detected: false })

// ==================== 等待状态 ====================
const readyProgress = ref(0)
const readyStartTime = ref(0)
const readyEnterTime = ref(0)
const READY_DURATION = 3000
const READY_TIMEOUT = 300000

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
const HOLE_DURATION = 2000
const FEEDBACK_DURATION = 1000

// ==================== 粒子系统 ====================
let particles = []

// ==================== Socket ====================
let socket = null
let statusInterval = null

// ==================== 画布尺寸 ====================
let canvasWidth = 640
let canvasHeight = 360
let scaleX = 1
let scaleY = 1

// ==================== 初始化Canvas ====================
function initCanvas() {
  if (!mainCanvas.value || !pageRef.value) return
  
  const container = pageRef.value
  mainCanvas.value.width = container.clientWidth
  mainCanvas.value.height = container.clientHeight
  
  scaleX = container.clientWidth / canvasWidth
  scaleY = container.clientHeight / canvasHeight
  
  ctx = mainCanvas.value.getContext('2d')
  
  // ⭐ 只在粒子为空时初始化
  if (particles.length === 0) {
    initParticles()
  }
}

// ==================== 粒子系统 ====================
function initParticles() {
  // ⭐ 只有粒子为空时才初始化
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
  // ⭐ 只有PLAYING状态才清除粒子
  if (gameState.value === 'PLAYING') {
    particles = []
    return
  }
  
  // ⭐ IDLE和READY状态都有粒子效果，保持延续性
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
  
  // 补充粒子
  while (particles.length < 40) {
    particles.push(createParticle())
  }
}

function drawParticles() {
  if (!ctx || gameState.value === 'PLAYING') return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
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
  
  // ⭐ IDLE和READY状态都有渐变背景
  const centerX = mainCanvas.value.width / 2
  const centerY = mainCanvas.value.height / 2
  const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, centerX)
  gradient.addColorStop(0, 'rgba(60, 20, 100, 0.2)')
  gradient.addColorStop(0.5, 'rgba(30, 10, 60, 0.1)')
  gradient.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
}

// ==================== 绘制绿点 ====================
function drawFootPoint() {
  if (!ctx || !footPosition.detected) return
  
  // ⭐ 严格边界检查，防止绿点破裂
  let x = Math.max(50, Math.min(590, footPosition.x))
  let y = Math.max(50, Math.min(310, footPosition.y))
  
  // 确保坐标是有效数字
  if (!Number.isFinite(x)) x = 320
  if (!Number.isFinite(y)) y = 180
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  // 外发光
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
  
  // 中心白点
  ctx.beginPath()
  ctx.arc(x, y, 9, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.95)'
  ctx.fill()
  
  ctx.restore()
}

// ==================== 绘制等待圈 ====================
function drawReadyCircle() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
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
  
  // ⭐ 文字位置控制
  // 改这个数值可以调整文字上下位置
  // 数值越小（更负），文字越往上
  const textYOffset = -250
  
  ctx.font = 'bold 48px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.fillText('请进入圆圈内', mainCanvas.value.width / 2, mainCanvas.value.height / 2 + textYOffset)
}

// ==================== 绘制地鼠洞 ====================
function drawMoleHoles() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
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
  if (!ctx || gameState.value !== 'PLAYING') return
  
  ctx.font = 'bold 40px Arial'
  ctx.textAlign = 'center'
  ctx.fillStyle = '#ffffff'
  ctx.fillText(`${game.value.timer}s`, mainCanvas.value.width / 2, 55)
  
  ctx.font = 'bold 36px Arial'
  ctx.fillStyle = '#FFD700'
  ctx.fillText(`得分: ${game.value.score}`, mainCanvas.value.width / 2, 110)
}

// ==================== 主绘制循环 ====================
function draw() {
  if (!ctx) return
  
  ctx.clearRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  
  drawBackground()
  updateParticles()
  drawParticles()
  
  // ⭐ IDLE状态：只有粒子
  // ⭐ READY状态：粒子 + 等待圈
  if (gameState.value === 'READY') {
    drawReadyCircle()
  } else if (gameState.value === 'PLAYING') {
    drawMoleHoles()
    drawGameInfo()
  }
  
  drawFootPoint()
  
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
    gameState.value = 'IDLE'
    game.value.status = 'IDLE'
    readyEnterTime.value = 0
    readyProgress.value = 0
    readyStartTime.value = 0
    // ⭐ 不重新初始化粒子，保持延续性
    if (socket) {
      socket.emit('game_control', { action: 'stop' })
    }
  }
}

// ==================== PLAYING状态逻辑 ====================
function updatePlayingState() {
  if (gameState.value !== 'PLAYING') return
  
  const now = Date.now()
  
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
      holeProgress.value[index] = Math.min(100, (elapsed / HOLE_DURATION) * 100)
      
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

// ==================== 状态更新 ====================
async function updateStatus() {
  try {
    const res = await fetch(`${apiUrl}/api/status`)
    if (res.ok) {
      const data = await res.json()
      // ⭐ 边界检查
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
  if (newStatus === 'IDLE') {
    gameState.value = 'IDLE'
    readyEnterTime.value = 0
    readyProgress.value = 0
    readyStartTime.value = 0
    holeProgress.value = [0, 0, 0]
    holeStartTime.value = [0, 0, 0]
    holeFeedback.value = [null, null, null]
    // ⭐ 不重新初始化粒子，保持延续性
  } else if (newStatus === 'READY') {
    gameState.value = 'READY'
    readyProgress.value = 0
    readyStartTime.value = 0
    readyEnterTime.value = Date.now()
    // ⭐ READY状态保持粒子效果，不重新初始化
  } else if (newStatus === 'PLAYING') {
    gameState.value = 'PLAYING'
    holeProgress.value = [0, 0, 0]
    holeStartTime.value = [0, 0, 0]
    holeFeedback.value = [null, null, null]
    // ⭐ 只有PLAYING状态才清除粒子
    particles = []
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
    // ⭐ 连接时获取当前状态
    socket.emit('get_state')
  })
  
  socket.on('game_update', (data) => {
    game.value = data
  })
  
  socket.on('system_state', (data) => {
    if (data.state && data.state.game) {
      game.value.status = data.state.game.status || 'IDLE'
      game.value.score = data.state.game.score || 0
      game.value.timer = data.state.game.timer || 60
    }
  })
  
  setTimeout(() => {
    initCanvas()
    draw()
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

.projection-page canvas {
  width: 100% !important;
  height: 100% !important;
  display: block !important;
}
</style>
