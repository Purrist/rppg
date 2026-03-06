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
const readyEnterTime = ref(0)  // 进入READY状态的时间
const READY_DURATION = 3000    // 3秒
const READY_TIMEOUT = 60000    // 60秒超时

// ==================== 地鼠洞配置（三按钮模板）====================
// 1920x1080 -> 640x360 转换
const holes = [
  { x: 130, y: 240, radius: 80 },   // 左
  { x: 320, y: 240, radius: 80 },   // 中
  { x: 510, y: 240, radius: 80 }    // 右
]

// 洞的进度
const holeProgress = ref([0, 0, 0])
const holeStartTime = ref([0, 0, 0])
const HOLE_DURATION = 1000  // 1秒踩中判定

// ==================== 粒子系统 ====================
let particles = []
const MAX_PARTICLES = 100  // 限制粒子数量

// ==================== Socket ====================
let socket = null
let statusInterval = null

// ==================== 画布尺寸 ====================
let canvasWidth = 640
let canvasHeight = 360

// ==================== 初始化Canvas ====================
function initCanvas() {
  if (!mainCanvas.value || !pageRef.value) return
  
  mainCanvas.value.width = pageRef.value.clientWidth
  mainCanvas.value.height = pageRef.value.clientHeight
  canvasWidth = 640
  canvasHeight = 360
  
  ctx = mainCanvas.value.getContext('2d')
  
  // 初始化粒子
  initParticles()
}

// ==================== 粒子系统 ====================
function initParticles() {
  particles = []
  const count = gameState.value === 'IDLE' ? 60 : 40
  
  for (let i = 0; i < count; i++) {
    particles.push(createParticle())
  }
}

function createParticle(fromCircle = false, circleX = 0, circleY = 0, circleRadius = 0) {
  // 蓝紫色范围
  const hue = 220 + Math.random() * 60  // 220-280 蓝到紫
  const saturation = 60 + Math.random() * 40
  const lightness = 40 + Math.random() * 30
  
  let x, y
  if (fromCircle) {
    // 从圆边缘发散
    const angle = Math.random() * Math.PI * 2
    const dist = circleRadius + Math.random() * 20
    x = circleX + Math.cos(angle) * dist
    y = circleY + Math.sin(angle) * dist
  } else {
    x = Math.random() * canvasWidth
    y = Math.random() * canvasHeight
  }
  
  return {
    x,
    y,
    vx: (Math.random() - 0.5) * 0.5,
    vy: (Math.random() - 0.5) * 0.5,
    radius: 3 + Math.random() * 6,
    alpha: 0.2 + Math.random() * 0.5,
    hue,
    saturation,
    lightness,
    life: 1,
    decay: 0.001 + Math.random() * 0.002
  }
}

function updateParticles() {
  const footX = smoothPosition.detected ? smoothPosition.x : -1000
  const footY = smoothPosition.detected ? smoothPosition.y : -1000
  
  // 根据状态决定是否从圆边缘发散
  const emitFromCircle = gameState.value === 'READY'
  const circleX = 320
  const circleY = 180
  const circleRadius = 80
  
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    
    // 移动
    p.x += p.vx
    p.y += p.vy
    
    // 脚踩驱散
    if (smoothPosition.detected) {
      const dx = p.x - footX
      const dy = p.y - footY
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 80) {
        const force = (80 - dist) / 80 * 0.5
        p.vx += (dx / dist) * force
        p.vy += (dy / dist) * force
        p.life -= 0.02
      }
    }
    
    // 边缘消散
    const margin = 50
    if (p.x < margin || p.x > canvasWidth - margin || 
        p.y < margin || p.y > canvasHeight - margin) {
      p.life -= 0.03
    }
    
    // 生命衰减
    p.life -= p.decay
    
    // 移除死亡粒子
    if (p.life <= 0 || p.alpha <= 0) {
      particles.splice(i, 1)
    }
  }
  
  // 补充粒子
  const targetCount = gameState.value === 'IDLE' ? 60 : 40
  while (particles.length < targetCount) {
    if (emitFromCircle) {
      particles.push(createParticle(true, circleX, circleY, circleRadius))
    } else {
      particles.push(createParticle())
    }
  }
}

function drawParticles() {
  if (!ctx) return
  
  particles.forEach(p => {
    const alpha = p.alpha * p.life
    if (alpha <= 0) return
    
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx.fillStyle = `hsla(${p.hue}, ${p.saturation}%, ${p.lightness}%, ${alpha})`
    ctx.fill()
    
    // 发光效果
    if (p.radius > 4) {
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius * 2, 0, Math.PI * 2)
      ctx.fillStyle = `hsla(${p.hue}, ${p.saturation}%, ${p.lightness}%, ${alpha * 0.2})`
      ctx.fill()
    }
  })
}

// ==================== 绘制背景 ====================
function drawBackground() {
  if (!ctx) return
  
  // 黑色背景
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, canvasWidth, canvasHeight)
  
  // 中心渐变光晕
  const gradient = ctx.createRadialGradient(
    canvasWidth / 2, canvasHeight / 2, 0,
    canvasWidth / 2, canvasHeight / 2, canvasWidth / 2
  )
  gradient.addColorStop(0, 'rgba(60, 20, 100, 0.3)')
  gradient.addColorStop(0.5, 'rgba(30, 10, 60, 0.2)')
  gradient.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, canvasWidth, canvasHeight)
}

// ==================== 绘制绿点 ====================
function drawFootPoint() {
  if (!ctx || !smoothPosition.detected) return
  
  const x = smoothPosition.x
  const y = smoothPosition.y
  
  // 外发光
  ctx.beginPath()
  ctx.arc(x, y, 30, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(51, 181, 85, 0.3)'
  ctx.fill()
  
  // 主圆
  ctx.beginPath()
  ctx.arc(x, y, 20, 0, Math.PI * 2)
  const gradient = ctx.createRadialGradient(x, y, 0, x, y, 20)
  gradient.addColorStop(0, '#44dd66')
  gradient.addColorStop(1, '#228B22')
  ctx.fillStyle = gradient
  ctx.fill()
  
  // 中心白点
  ctx.beginPath()
  ctx.arc(x, y, 6, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'
  ctx.fill()
}

// ==================== 绘制等待圈 ====================
function drawReadyCircle() {
  if (!ctx) return
  
  const cx = 320
  const cy = 180
  const radius = 80
  
  // 灰色底圈
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.strokeStyle = 'rgba(100, 100, 100, 0.8)'
  ctx.lineWidth = 10
  ctx.stroke()
  
  // 进度圈（只有有进度时才显示）
  if (readyProgress.value > 0) {
    ctx.beginPath()
    ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * readyProgress.value / 100))
    ctx.strokeStyle = '#FF7222'
    ctx.lineWidth = 10
    ctx.lineCap = 'round'
    ctx.stroke()
  }
  
  // 提示文字
  ctx.font = 'bold 24px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.fillText('请进入圆圈内', cx, cy)
}

// ==================== 绘制地鼠洞 ====================
function drawMoleHoles() {
  if (!ctx) return
  
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
      ctx.font = '50px Arial'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText('🐹', hole.x, hole.y)
    }
    
    // 进度圈（白色）
    if (progress > 0) {
      ctx.beginPath()
      ctx.arc(hole.x, hole.y, hole.radius + 10, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * progress / 100))
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 6
      ctx.lineCap = 'round'
      ctx.stroke()
    }
  })
}

// ==================== 绘制游戏信息 ====================
function drawGameInfo() {
  if (!ctx || gameState.value !== 'PLAYING') return
  
  // 时间
  ctx.font = 'bold 32px Arial'
  ctx.textAlign = 'center'
  ctx.fillStyle = '#ffffff'
  ctx.fillText(`${game.value.timer}s`, canvasWidth / 2, 40)
  
  // 分数
  ctx.font = 'bold 28px Arial'
  ctx.fillStyle = '#FFD700'
  ctx.fillText(`得分: ${game.value.score}`, canvasWidth / 2, 80)
}

// ==================== 主绘制循环 ====================
function draw() {
  if (!ctx) return
  
  // 清空
  ctx.clearRect(0, 0, canvasWidth, canvasHeight)
  
  // 绘制背景
  drawBackground()
  
  // 更新和绘制粒子
  updateParticles()
  drawParticles()
  
  // 根据状态绘制
  if (gameState.value === 'READY') {
    drawReadyCircle()
  } else if (gameState.value === 'PLAYING') {
    drawMoleHoles()
    drawGameInfo()
  }
  
  // 始终绘制绿点
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
  
  // 使用历史记录进行平滑
  positionHistory.push({ x: rawPosition.x, y: rawPosition.y, time: Date.now() })
  if (positionHistory.length > 5) {
    positionHistory.shift()
  }
  
  // 加权平均
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
    // 平滑过渡
    const targetX = sumX / totalWeight
    const targetY = sumY / totalWeight
    
    smoothPosition.x += (targetX - smoothPosition.x) * 0.3
    smoothPosition.y += (targetY - smoothPosition.y) * 0.3
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
      console.log('[投影] 用户进入等待圈')
    }
    readyProgress.value = Math.min(100, ((Date.now() - readyStartTime.value) / READY_DURATION) * 100)
    
    if (readyProgress.value >= 100) {
      console.log('[投影] 3秒完成，开始游戏')
      if (socket) {
        socket.emit('game_control', { action: 'start' })
      }
    }
  } else {
    if (readyStartTime.value !== 0) {
      console.log('[投影] 用户离开等待圈')
    }
    readyStartTime.value = 0
    readyProgress.value = 0
  }
  
  // 超时检查
  if (Date.now() - readyEnterTime.value > READY_TIMEOUT) {
    console.log('[投影] 超时，返回待机')
    gameState.value = 'IDLE'
    game.value.status = 'IDLE'
    readyEnterTime.value = 0
    initParticles()
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
  }
})

// ==================== 生命周期 ====================
onMounted(() => {
  // 连接Socket
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
  
  // 初始化Canvas
  setTimeout(() => {
    initCanvas()
    draw()
  }, 100)
  
  // 定时更新
  statusInterval = setInterval(() => {
    updateStatus()
    updateSmoothPosition()
    if (gameState.value === 'READY') updateReadyState()
    else if (gameState.value === 'PLAYING') updatePlayingState()
  }, 30)  // 30ms更新一次，更流畅
  
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
  width: 100%;
  height: 100%;
  display: block;
}
</style>
