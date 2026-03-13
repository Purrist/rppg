<!--
  WhackAMole.vue - 打地鼠游戏组件
  使用GameFrame框架
-->

<template>
  <GameFrame ref="gameFrameRef" :game-config="gameConfig">
    <template #game-content="{ state, footPosition, ctx, scaleX, scaleY }">
      <!-- 游戏特定内容由drawMoleHoles绘制 -->
    </template>
  </GameFrame>
</template>

<script setup>
import { ref, reactive, watch, onMounted, onUnmounted, computed } from 'vue'
import GameFrame from './GameFrame.vue'

// ==================== 游戏配置 ====================
const gameConfig = {
  game_id: 'whack_a_mole',
  game_name: '趣味打地鼠',
  duration: 60,
  show_timer: true,
  show_score: true,
}

// ==================== 地鼠洞配置 ====================
const holes = [
  { x: 130, y: 240, radius: 80 },
  { x: 320, y: 240, radius: 80 },
  { x: 510, y: 240, radius: 80 }
]

// ==================== 游戏状态 ====================
const gameFrameRef = ref(null)
const gameState = reactive({
  status: 'IDLE',
  current_mole: -1,
})

// ==================== 等待状态 ====================
const readyProgress = ref(0)
const readyStartTime = ref(0)
const readyEnterTime = ref(0)
const READY_DURATION = 3000
const READY_TIMEOUT = 180000

// ==================== 洞状态 ====================
const holeProgress = ref([0, 0, 0])
const holeStartTime = ref([0, 0, 0])
const holeFeedback = ref([null, null, null])
const holeFeedbackTime = ref([0, 0, 0])
const HOLE_DURATION = 2000
const FEEDBACK_DURATION = 1000

// ==================== 粒子系统 ====================
let particles = []

function createParticle() {
  return {
    x: Math.random() * 640,
    y: Math.random() * 360,
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

function initParticles() {
  particles = []
  for (let i = 0; i < 40; i++) {
    particles.push(createParticle())
  }
}

// ==================== 绘制粒子 ====================
function drawParticles(ctx, scaleX, scaleY, footPosition) {
  if (!ctx || gameState.status === 'PLAYING') return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  // 更新粒子
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    p.x += p.vx
    p.y += p.vy
    
    if (footPosition.detected) {
      const dx = p.x - footPosition.x
      const dy = p.y - footPosition.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 120) {
        const force = (120 - dist) / 120 * 0.5
        p.vx += (dx / dist) * force
        p.vy += (dy / dist) * force
        p.life -= 0.01
      }
    }
    
    p.life -= p.decay
    if (p.life <= 0) particles.splice(i, 1)
  }
  
  while (particles.length < 40) {
    particles.push(createParticle())
  }
  
  // 绘制粒子
  particles.forEach(p => {
    const alpha = p.alpha * p.life
    if (alpha <= 0) return
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx.fillStyle = `hsla(${p.hue}, ${p.sat}%, ${p.light}%, ${alpha})`
    ctx.fill()
  })
  
  ctx.restore()
}

// ==================== 绘制等待圈 ====================
function drawReadyCircle(ctx, scaleX, scaleY, canvasWidth, canvasHeight) {
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
  ctx.fillText('请进入圆圈内', canvasWidth / 2, canvasHeight / 2 - 250)
}

// ==================== 绘制地鼠洞 ====================
function drawMoleHoles(ctx, scaleX, scaleY) {
  if (!ctx) return
  
  ctx.save()
  ctx.scale(scaleX, scaleY)
  
  holes.forEach((hole, index) => {
    const hasMole = gameState.current_mole === index
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

// ==================== READY状态逻辑 ====================
function updateReadyState(footPosition) {
  if (gameState.status !== 'READY') return
  
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
      gameFrameRef.value?.sendGameControl('start')
      emit('ready-complete')
    }
  } else {
    readyStartTime.value = 0
    readyProgress.value = 0
  }
  
  // 超时
  if (readyEnterTime.value > 0 && Date.now() - readyEnterTime.value > READY_TIMEOUT) {
    gameState.status = 'IDLE'
    readyEnterTime.value = 0
    readyProgress.value = 0
    readyStartTime.value = 0
    gameFrameRef.value?.sendGameControl('timeout_stop')
  }
}

// ==================== PLAYING状态逻辑 ====================
function updatePlayingState(footPosition) {
  if (gameState.status !== 'PLAYING') return
  
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
        const hit = gameState.current_mole === index
        holeFeedback.value[index] = hit ? 'correct' : 'wrong'
        holeFeedbackTime.value[index] = now
        
        gameFrameRef.value?.sendGameHit(index, hit)
      }
    } else {
      holeProgress.value[index] = 0
      holeStartTime.value[index] = 0
    }
  })
}

// ==================== 监听状态变化 ====================
watch(() => gameState.status, (newStatus) => {
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
  }
})

// ==================== 自定义绘制循环 ====================
let customDrawInterval = null

function startCustomDraw() {
  customDrawInterval = setInterval(() => {
    const frame = gameFrameRef.value
    if (!frame) return
    
    const { ctx, scaleX, scaleY, footPosition, canvasWidth, canvasHeight } = frame
    
    // 更新游戏状态
    if (frame.gameState) {
      gameState.status = frame.gameState.status
      gameState.current_mole = frame.gameState.extra?.current_mole ?? -1
    }
    
    // 根据状态绘制
    if (gameState.status === 'IDLE') {
      drawParticles(ctx, scaleX, scaleY, footPosition)
    } else if (gameState.status === 'READY') {
      drawParticles(ctx, scaleX, scaleY, footPosition)
      drawReadyCircle(ctx, scaleX, scaleY, canvasWidth, canvasHeight)
      updateReadyState(footPosition)
    } else if (gameState.status === 'PLAYING') {
      drawMoleHoles(ctx, scaleX, scaleY)
      updatePlayingState(footPosition)
    }
  }, 16)
}

// ==================== Emits ====================
const emit = defineEmits(['ready-complete', 'game-over'])

// ==================== 生命周期 ====================
onMounted(() => {
  initParticles()
  setTimeout(startCustomDraw, 200)
})

onUnmounted(() => {
  if (customDrawInterval) clearInterval(customDrawInterval)
})
</script>
