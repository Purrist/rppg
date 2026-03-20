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
const currentGame = ref('whack_a_mole')  // 当前游戏类型
const game = ref({
  status: 'IDLE',
  score: 0,
  timer: 60,
  current_mole: -1,
  accuracy: 0
})

// ==================== 处理速度训练状态 ====================
const psStimulus = ref(null)  // 处理速度训练刺激
const psFeedback = ref(null)  // 处理速度训练反馈
const psModule = ref('go_no_go')  // 当前模块
const psZoneProgress = ref({})  // 区域停留进度
const psZoneStartTime = ref({})  // 区域停留开始时间
const PS_DWELL_DURATION = 3000  // 停留确认时间（3秒）

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
  
  let x = Math.max(50, Math.min(590, footPosition.x))
  let y = Math.max(50, Math.min(310, footPosition.y))
  
  if (!Number.isFinite(x)) x = 320
  if (!Number.isFinite(y)) y = 180
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  ctx.beginPath()
  ctx.arc(x, y, 40, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(51, 181, 85, 0.25)'
  ctx.fill()
  
  ctx.beginPath()
  ctx.arc(x, y, 25, 0, Math.PI * 2)
  const gradient = ctx.createRadialGradient(x, y, 0, x, y, 25)
  gradient.addColorStop(0, '#55ee77')
  gradient.addColorStop(1, '#228B22')
  ctx.fillStyle = gradient
  ctx.fill()
  
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
  ctx.scale(scaleX, scaleY)
  
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
  if (!ctx) return
  if (gameState.value !== 'PLAYING' && gameState.value !== 'PAUSED') return
  
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
  ctx.scale(scaleX, scaleY)
  
  ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
  ctx.fillRect(0, 0, canvasWidth, canvasHeight)
  
  ctx.font = 'bold 72px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.fillText('已暂停', canvasWidth / 2, canvasHeight / 2)
  
  ctx.restore()
}

// ==================== 处理速度训练区域 ====================
const psZones = [
  { id: 1, x: 159, y: 255 },   // 区域1中心
  { id: 2, x: 623, y: 255 },   // 区域2中心
  { id: 3, x: 1087, y: 255 },  // 区域3中心
  { id: 4, x: 1551, y: 255 },  // 区域4中心
  { id: 5, x: 159, y: 702 },   // 区域5中心
  { id: 6, x: 623, y: 702 },   // 区域6中心
  { id: 7, x: 1087, y: 702 },  // 区域7中心
  { id: 8, x: 1551, y: 702 },  // 区域8中心
]

// 将投影坐标转换为画布坐标
function projToCanvas(x, y) {
  return {
    x: x * canvasWidth / 1920,
    y: y * canvasHeight / 1080
  }
}

// 绘制处理速度训练界面
function drawProcessingSpeed() {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  // 绘制8个区域
  const zoneRadius = 105 * canvasWidth / 1920
  
  for (let i = 0; i < 8; i++) {
    const zone = psZones[i]
    const pos = projToCanvas(zone.x, zone.y)
    
    // 获取区域状态
    let color = '#D9D9D9'  // 默认灰色
    let active = false
    
    if (psStimulus.value?.zones) {
      const zoneState = psStimulus.value.zones[i + 1]
      if (zoneState?.active) {
        color = zoneState.color || '#D9D9D9'
        active = true
      }
    }
    
    // 绘制区域
    ctx.beginPath()
    ctx.arc(pos.x, pos.y, zoneRadius, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
    
    // 绘制边框
    ctx.beginPath()
    ctx.arc(pos.x, pos.y, zoneRadius, 0, Math.PI * 2)
    ctx.strokeStyle = active ? '#fff' : '#888'
    ctx.lineWidth = 3
    ctx.stroke()
    
    // 绘制停留进度
    const progress = psZoneProgress.value[i] || 0
    if (progress > 0 && active) {
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, zoneRadius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * progress / 100))
      ctx.strokeStyle = '#FFD700'
      ctx.lineWidth = 8
      ctx.lineCap = 'round'
      ctx.stroke()
    }
    
    // 绘制区域编号
    ctx.font = 'bold 24px Arial'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = active ? '#fff' : '#666'
    ctx.fillText(i + 1, pos.x, pos.y)
  }
  
  // 绘制模块指示
  const moduleNames = {
    'go_no_go': '反应控制',
    'choice_reaction': '选择反应',
    'serial_reaction': '序列学习'
  }
  
  ctx.font = 'bold 28px Arial'
  ctx.textAlign = 'center'
  ctx.fillStyle = '#fff'
  ctx.fillText(moduleNames[psModule.value] || '处理速度训练', canvasWidth / 2, 30)
  
  // 绘制指令
  if (psStimulus.value?.instruction) {
    ctx.font = 'bold 36px Arial'
    ctx.fillStyle = '#FFD700'
    ctx.fillText(psStimulus.value.instruction, canvasWidth / 2, canvasHeight - 50)
  }
  
  // 绘制反馈
  if (psFeedback.value) {
    ctx.font = 'bold 48px Arial'
    ctx.fillStyle = psFeedback.value.correct ? '#33B555' : '#FF4444'
    ctx.fillText(psFeedback.value.message, canvasWidth / 2, canvasHeight / 2)
  }
  
  ctx.restore()
}

// ==================== 主绘制循环 ====================
function draw() {
  if (!ctx) return
  
  ctx.clearRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  
  drawBackground()
  updateParticles()
  drawParticles()
  
  // ⭐ 根据游戏类型选择绘制
  if (currentGame.value === 'processing_speed') {
    // 处理速度训练
    if (gameState.value === 'READY') {
      drawReadyCircle()
    } else if (gameState.value === 'PLAYING') {
      drawProcessingSpeed()
      drawGameInfo()
    } else if (gameState.value === 'PAUSED') {
      drawProcessingSpeed()
      drawGameInfo()
      drawPauseOverlay()
    } else if (gameState.value === 'SETTLING') {
      drawSettling()
    }
  } else {
    // 打地鼠（默认）
    if (gameState.value === 'READY') {
      drawReadyCircle()
    } else if (gameState.value === 'PLAYING') {
      drawMoleHoles()
      drawGameInfo()
    } else if (gameState.value === 'PAUSED') {
      drawMoleHoles()
      drawGameInfo()
      drawPauseOverlay()
    } else if (gameState.value === 'SETTLING') {
      drawSettling()
    }
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

// ==================== PLAYING状态逻辑 ====================
function updatePlayingState() {
  if (gameState.value !== 'PLAYING') return
  
  const now = Date.now()
  
  // 处理速度训练的停留检测
  if (currentGame.value === 'processing_speed') {
    updateProcessingSpeedState(now)
    return
  }
  
  // 打地鼠的停留检测
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

// ==================== 处理速度训练停留检测 ====================
function updateProcessingSpeedState(now) {
  if (!psStimulus.value?.zones) return
  
  const zoneRadius = 105 * canvasWidth / 1920
  
  // 检查每个区域
  for (let i = 0; i < 8; i++) {
    const zone = psZones[i]
    const pos = projToCanvas(zone.x, zone.y)
    
    // 只检测激活的区域
    const zoneState = psStimulus.value.zones[i + 1]
    if (!zoneState?.active) continue
    
    const dx = footPosition.x - pos.x
    const dy = footPosition.y - pos.y
    const inZone = footPosition.detected && (dx * dx + dy * dy <= zoneRadius * zoneRadius)
    
    if (inZone) {
      if (!psZoneStartTime.value[i]) {
        psZoneStartTime.value[i] = now
      }
      
      const elapsed = now - psZoneStartTime.value[i]
      psZoneProgress.value[i] = Math.min(100, (elapsed / PS_DWELL_DURATION) * 100)
      
      if (psZoneProgress.value[i] >= 100) {
        // 停留完成，发送事件
        if (socket) {
          socket.emit('game_action', {
            action: 'zone_dwell_completed',
            zone_id: i + 1,
            dwell_time: elapsed
          })
        }
        
        // 重置
        psZoneProgress.value[i] = 0
        psZoneStartTime.value[i] = 0
      }
    } else {
      psZoneProgress.value[i] = 0
      psZoneStartTime.value[i] = 0
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
    psZoneProgress.value = {}
    psZoneStartTime.value = {}
    initParticles()
  } else if (newStatus === 'READY') {
    readyProgress.value = 0
    readyStartTime.value = 0
    readyEnterTime.value = Date.now()
  } else if (newStatus === 'PLAYING') {
    holeProgress.value = [0, 0, 0]
    holeStartTime.value = [0, 0, 0]
    holeFeedback.value = [null, null, null]
    psZoneProgress.value = {}
    psZoneStartTime.value = {}
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
    // 更新游戏状态
    game.value.status = data.status || 'IDLE'
    game.value.score = data.score || 0
    game.value.timer = data.timer || 60
    
    // ⭐ 根据module判断游戏类型
    if (data.module) {
      currentGame.value = 'processing_speed'
      psModule.value = data.module
    } else {
      currentGame.value = 'whack_a_mole'
    }
    
    // 打地鼠数据
    if (data.extra) {
      game.value.current_mole = data.extra.current_mole ?? -1
    }
    if (data.stats) {
      game.value.accuracy = Math.round((data.stats.accuracy || 0) * 100)
    }
    
    // 处理速度训练数据
    if (data.stimulus) {
      psStimulus.value = data.stimulus
    }
    if (data.feedback) {
      psFeedback.value = data.feedback
      setTimeout(() => {
        psFeedback.value = null
      }, 2000)
    }
  })
  
  socket.on('system_state', (data) => {
    // 不做处理
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
