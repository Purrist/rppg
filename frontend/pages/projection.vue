<template>
  <div class="projection-page" ref="pageRef">
    <!-- 主Canvas - 绘制所有内容 -->
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

console.log('[Projection] 后端地址:', backendUrl)

// ==================== Canvas ====================
const mainCanvas = ref(null)
const pageRef = ref(null)
let ctx = null
let animationId = null

// ==================== 游戏状态 ====================
const gameState = ref('IDLE')  // IDLE, READY, PLAYING
const game = ref({
  status: 'IDLE',
  score: 0,
  timer: 60,
  current_mole: -1
})

// ==================== 用户位置（平滑处理）====================
const rawPosition = reactive({ x: 320, y: 180, detected: false })
const smoothPosition = reactive({ x: 320, y: 180, detected: false })
const positionHistory = []

// ==================== 等待状态 ====================
const readyProgress = ref(0)
const readyStartTime = ref(0)
const readyEnterTime = ref(0)
const READY_DURATION = 3000    // 3秒
const READY_TIMEOUT = 300000   // 5分钟超时

// ==================== 地鼠洞配置（三按钮模板）====================
const holes = [
  { x: 130, y: 240, radius: 80 },
  { x: 320, y: 240, radius: 80 },
  { x: 510, y: 240, radius: 80 }
]

// 洞的进度
const holeProgress = ref([0, 0, 0])
const holeStartTime = ref([0, 0, 0])
const HOLE_DURATION = 1000

// ==================== 粒子系统 ====================
let particles = []
const MAX_PARTICLES = 80

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
  const containerWidth = container.clientWidth
  const containerHeight = container.clientHeight
  
  // 设置canvas尺寸为容器尺寸
  mainCanvas.value.width = containerWidth
  mainCanvas.value.height = containerHeight
  
  // 计算缩放比例（保持16:9）
  scaleX = containerWidth / canvasWidth
  scaleY = containerHeight / canvasHeight
  
  ctx = mainCanvas.value.getContext('2d')
  
  // 初始化粒子
  initParticles()
  
  console.log('[Projection] Canvas初始化:', containerWidth, 'x', containerHeight)
}

// ==================== 粒子系统 ====================
function initParticles() {
  particles = []
  const count = gameState.value === 'IDLE' ? 50 : 30
  
  for (let i = 0; i < count; i++) {
    particles.push(createParticle())
  }
}

function createParticle(fromCircle = false, circleX = 0, circleY = 0, circleRadius = 0) {
  const hue = 220 + Math.random() * 60
  const saturation = 60 + Math.random() * 40
  const lightness = 40 + Math.random() * 30
  
  let x, y
  if (fromCircle) {
    const angle = Math.random() * Math.PI * 2
    const dist = circleRadius + 10 + Math.random() * 30
    x = circleX + Math.cos(angle) * dist
    y = circleY + Math.sin(angle) * dist
  } else {
    x = Math.random() * canvasWidth
    y = Math.random() * canvasHeight
  }
  
  return {
    x,
    y,
    vx: (Math.random() - 0.5) * 0.4,
    vy: (Math.random() - 0.5) * 0.4,
    radius: 4 + Math.random() * 8,
    alpha: 0.3 + Math.random() * 0.5,
    hue,
    saturation,
    lightness,
    life: 1,
    decay: 0.001 + Math.random() * 0.002
  }
}

function updateParticles() {
  // 游戏进行中不显示粒子
  if (gameState.value === 'PLAYING') {
    particles = []
    return
  }
  
  const footX = smoothPosition.detected ? smoothPosition.x : -1000
  const footY = smoothPosition.detected ? smoothPosition.y : -1000
  
  const emitFromCircle = gameState.value === 'READY'
  const circleX = 320
  const circleY = 180
  const circleRadius = 80
  
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    
    p.x += p.vx
    p.y += p.vy
    
    // 脚踩驱散
    if (smoothPosition.detected) {
      const dx = p.x - footX
      const dy = p.y - footY
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 100) {
        const force = (100 - dist) / 100 * 0.6
        p.vx += (dx / dist) * force
        p.vy += (dy / dist) * force
        p.life -= 0.015
      }
    }
    
    // 边缘消散
    const margin = 30
    if (p.x < margin || p.x > canvasWidth - margin || 
        p.y < margin || p.y > canvasHeight - margin) {
      p.life -= 0.02
    }
    
    p.life -= p.decay
    
    if (p.life <= 0 || p.alpha <= 0) {
      particles.splice(i, 1)
    }
  }
  
  const targetCount = gameState.value === 'IDLE' ? 50 : 30
  while (particles.length < targetCount) {
    if (emitFromCircle) {
      particles.push(createParticle(true, circleX, circleY, circleRadius))
    } else {
      particles.push(createParticle())
    }
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
    ctx.fillStyle = `hsla(${p.hue}, ${p.saturation}%, ${p.lightness}%, ${alpha})`
    ctx.fill()
    
    if (p.radius > 5) {
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius * 2, 0, Math.PI * 2)
      ctx.fillStyle = `hsla(${p.hue}, ${p.saturation}%, ${p.lightness}%, ${alpha * 0.15})`
      ctx.fill()
    }
  })
  
  ctx.restore()
}

// ==================== 绘制背景 ====================
function drawBackground() {
  if (!ctx) return
  
  // 黑色背景
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  
  // 游戏进行中纯黑底
  if (gameState.value === 'PLAYING') return
  
  // 中心渐变光晕
  const centerX = mainCanvas.value.width / 2
  const centerY = mainCanvas.value.height / 2
  const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, centerX)
  gradient.addColorStop(0, 'rgba(60, 20, 100, 0.25)')
  gradient.addColorStop(0.5, 'rgba(30, 10, 60, 0.15)')
  gradient.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
}

// ==================== 绘制绿点 ====================
function drawFootPoint() {
  if (!ctx || !smoothPosition.detected) return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  const x = smoothPosition.x
  const y = smoothPosition.y
  
  // 外发光
  ctx.beginPath()
  ctx.arc(x, y, 35, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(51, 181, 85, 0.25)'
  ctx.fill()
  
  // 主圆
  ctx.beginPath()
  ctx.arc(x, y, 22, 0, Math.PI * 2)
  const gradient = ctx.createRadialGradient(x, y, 0, x, y, 22)
  gradient.addColorStop(0, '#55ee77')
  gradient.addColorStop(1, '#228B22')
  ctx.fillStyle = gradient
  ctx.fill()
  
  // 中心白点
  ctx.beginPath()
  ctx.arc(x, y, 7, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.85)'
  ctx.fill()
  
  ctx.restore()
}

// ==================== 绘制等待圈 ====================
function drawReadyCircle() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  const cx = 320
  const cy = 180
  const radius = 80
  
  // 灰色底圈
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.strokeStyle = 'rgba(120, 120, 120, 0.9)'
  ctx.lineWidth = 12
  ctx.stroke()
  
  // 进度圈
  if (readyProgress.value > 0) {
    ctx.beginPath()
    ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * readyProgress.value / 100))
    ctx.strokeStyle = '#FF7222'
    ctx.lineWidth = 12
    ctx.lineCap = 'round'
    ctx.stroke()
  }
  
  ctx.restore()
  
  // 提示文字（放在下面）
  ctx.font = 'bold 28px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.fillText('请进入圆圈内', mainCanvas.value.width / 2, mainCanvas.value.height / 2 + 150)
}

// ==================== 绘制地鼠洞 ====================
function drawMoleHoles() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  holes.forEach((hole, index) => {
    const hasMole = game.value.current_mole === index
    const progress = holeProgress.value[index]
    
    // 洞的背景
    ctx.beginPath()
    ctx.arc(hole.x, hole.y, hole.radius, 0, Math.PI * 2)
    ctx.fillStyle = '#1a1a1a'
    ctx.fill()
    
    // 洞的边框
    ctx.beginPath()
    ctx.arc(hole.x, hole.y, hole.radius, 0, Math.PI * 2)
    ctx.strokeStyle = hasMole ? '#8B4513' : '#444'
    ctx.lineWidth = 4
    ctx.stroke()
    
    // 地鼠
    if (hasMole) {
      ctx.font = '55px Arial'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText('🐹', hole.x, hole.y)
    }
    
    // 进度圈（和洞重合，粗圈）
    if (progress > 0) {
      ctx.beginPath()
      ctx.arc(hole.x, hole.y, hole.radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * progress / 100))
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 12
      ctx.lineCap = 'round'
      ctx.stroke()
    }
  })
  
  ctx.restore()
}

// ==================== 绘制游戏信息 ====================
function drawGameInfo() {
  if (!ctx || gameState.value !== 'PLAYING') return
  
  ctx.font = 'bold 36px Arial'
  ctx.textAlign = 'center'
  ctx.fillStyle = '#ffffff'
  ctx.fillText(`${game.value.timer}s`, mainCanvas.value.width / 2, 50)
  
  ctx.font = 'bold 32px Arial'
  ctx.fillStyle = '#FFD700'
  ctx.fillText(`得分: ${game.value.score}`, mainCanvas.value.width / 2, 100)
}

// ==================== 主绘制循环 ====================
function draw() {
  if (!ctx) return
  
  ctx.clearRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  
  drawBackground()
  updateParticles()
  drawParticles()
  
  if (gameState.value === 'READY') {
    drawReadyCircle()
  } else if (gameState.value === 'PLAYING') {
    drawMoleHoles()
    drawGameInfo()
  }
  
  drawFootPoint()
  
  animationId = requestAnimationFrame(draw)
}

// ==================== 位置平滑处理 ====================
function updateSmoothPosition() {
  if (!rawPosition.detected) {
    smoothPosition.detected = false
    return
  }
  
  smoothPosition.detected = true
  
  positionHistory.push({ x: rawPosition.x, y: rawPosition.y, time: Date.now() })
  if (positionHistory.length > 5) {
    positionHistory.shift()
  }
  
  let totalWeight = 0
  let sumX = 0
  let sumY = 0
  
  positionHistory.forEach((pos, i) => {
    const weight = i + 1
    sumX += pos.x * weight
    sumY += pos.y * weight
    totalWeight += weight
  })
  
  if (totalWeight > 0) {
    const targetX = sumX / totalWeight
    const targetY = sumY / totalWeight
    smoothPosition.x += (targetX - smoothPosition.x) * 0.4
    smoothPosition.y += (targetY - smoothPosition.y) * 0.4
  }
}

// ==================== READY状态逻辑 ====================
function updateReadyState() {
  if (gameState.value !== 'READY') return
  
  const centerX = 320, centerY = 180, radius = 80
  const dx = smoothPosition.x - centerX
  const dy = smoothPosition.y - centerY
  const inZone = smoothPosition.detected && (dx * dx + dy * dy <= radius * radius)
  
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
  
  // 超时检查 - 5分钟
  if (readyEnterTime.value > 0 && Date.now() - readyEnterTime.value > READY_TIMEOUT) {
    console.log('[投影] 超时5分钟，返回待机')
    gameState.value = 'IDLE'
    game.value.status = 'IDLE'
    readyEnterTime.value = 0
    readyProgress.value = 0
    readyStartTime.value = 0
    initParticles()
    // 通知后端
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
    const dx = smoothPosition.x - hole.x
    const dy = smoothPosition.y - hole.y
    const inHole = smoothPosition.detected && (dx * dx + dy * dy <= hole.radius * hole.radius)
    
    if (inHole) {
      if (holeStartTime.value[index] === 0) {
        holeStartTime.value[index] = now
      }
      
      const elapsed = now - holeStartTime.value[index]
      holeProgress.value[index] = Math.min(100, (elapsed / HOLE_DURATION) * 100)
      
      if (holeProgress.value[index] >= 100) {
        const hit = game.value.current_mole === index
        
        if (socket) {
          socket.emit('game_hit', { hole: index, hit })
        }
        
        holeProgress.value[index] = 0
        holeStartTime.value[index] = 0
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
      rawPosition.x = data.feet_x
      rawPosition.y = data.feet_y
      rawPosition.detected = data.feet_detected
    }
  } catch (e) {}
}

// ==================== 监听游戏状态变化 ====================
watch(() => game.value.status, (newStatus) => {
  console.log('[投影] 游戏状态变化:', newStatus)
  
  if (newStatus === 'IDLE') {
    gameState.value = 'IDLE'
    readyEnterTime.value = 0
    readyProgress.value = 0
    readyStartTime.value = 0
    initParticles()
  } else if (newStatus === 'READY') {
    gameState.value = 'READY'
    readyProgress.value = 0
    readyStartTime.value = 0
    readyEnterTime.value = Date.now()
    initParticles()
  } else if (newStatus === 'PLAYING') {
    gameState.value = 'PLAYING'
    holeProgress.value = [0, 0, 0]
    holeStartTime.value = [0, 0, 0]
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
  })
  
  socket.on('game_update', (data) => {
    game.value = data
  })
  
  setTimeout(() => {
    initCanvas()
    draw()
  }, 100)
  
  statusInterval = setInterval(() => {
    updateStatus()
    updateSmoothPosition()
    if (gameState.value === 'READY') updateReadyState()
    else if (gameState.value === 'PLAYING') updatePlayingState()
  }, 30)
  
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
