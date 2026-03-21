<!--
  ProcessingSpeedGame.vue - 处理速度训练游戏组件
  使用Canvas绘制，与打地鼠游戏架构一致
  640x360 坐标系统，通过scaleX/scaleY缩放
-->

<template>
  <div class="processing-speed-game">
    <canvas ref="gameCanvas" class="game-canvas"></canvas>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'

// ==================== Props ====================
const props = defineProps({
  gameState: { type: Object, required: true },
  footPosition: { type: Object, required: true },
  canvasWidth: { type: Number, default: 1920 },
  canvasHeight: { type: Number, default: 1080 },
  scaleX: { type: Number, default: 1 },
  scaleY: { type: Number, default: 1 }
})

const emit = defineEmits(['action'])

// ==================== Canvas ====================
const gameCanvas = ref(null)
let ctx = null
let animationId = null

// ==================== 8个区域配置 (640x360坐标系) ====================
// 2行4列布局，与打地鼠一致
const zones = [
  // 第一行（y = 140）
  { id: 1, x: 80, y: 140, radius: 45 },
  { id: 2, x: 226, y: 140, radius: 45 },
  { id: 3, x: 372, y: 140, radius: 45 },
  { id: 4, x: 518, y: 140, radius: 45 },
  // 第二行（y = 250）
  { id: 5, x: 80, y: 250, radius: 45 },
  { id: 6, x: 226, y: 250, radius: 45 },
  { id: 7, x: 372, y: 250, radius: 45 },
  { id: 8, x: 518, y: 250, radius: 45 },
]

// ==================== 游戏状态 ====================
const zoneProgress = ref([0, 0, 0, 0, 0, 0, 0, 0])
const zoneStartTime = ref([0, 0, 0, 0, 0, 0, 0, 0])
const zoneFeedback = ref([null, null, null, null, null, null, null, null])
const zoneFeedbackTime = ref([0, 0, 0, 0, 0, 0, 0, 0])

const currentQuestion = ref(null)
const inInterval = ref(true)
const remainingTime = ref(0)
const answerTime = ref(5)

// ==================== 确认时间 ====================
const FEEDBACK_DURATION = 1000

function getDwellDuration() {
  if (props.gameState && props.gameState.dwell_time) {
    return props.gameState.dwell_time * 1000 // 转换为毫秒
  }
  const saved = localStorage.getItem('dwellTime')
  return saved ? parseInt(saved) : 3000
}

// ==================== 初始化Canvas ====================
function initCanvas() {
  if (!gameCanvas.value) return
  
  gameCanvas.value.width = props.canvasWidth
  gameCanvas.value.height = props.canvasHeight
  ctx = gameCanvas.value.getContext('2d')
}

// ==================== 更新游戏状态 ====================
function updateGame() {
  // 只有在有题目且不在间隔期时才检测
  if (!props.footPosition.detected || !currentQuestion.value || inInterval.value) {
    // 清空所有进度
    for (let i = 0; i < 8; i++) {
      zoneProgress.value[i] = 0
      zoneStartTime.value[i] = 0
    }
    return
  }

  const now = Date.now()
  const dwellMs = getDwellDuration()

  // 检查所有8个区域
  zones.forEach((zone, index) => {
    const feedback = zoneFeedback.value[index]
    const feedbackTime = zoneFeedbackTime.value[index]

    // 清除过期的反馈
    if (feedback === 'correct' || feedback === 'wrong') {
      if (now - feedbackTime > FEEDBACK_DURATION) {
        zoneFeedback.value[index] = null
        zoneProgress.value[index] = 0
        zoneStartTime.value[index] = 0
      }
      return
    }

    // 检测玩家是否在区域内
    const dx = props.footPosition.x - zone.x
    const dy = props.footPosition.y - zone.y
    const inZone = (dx * dx + dy * dy) <= (zone.radius * zone.radius)

    if (inZone) {
      // 玩家进入区域，开始计时
      if (!zoneStartTime.value[index]) zoneStartTime.value[index] = now
      const elapsed = now - zoneStartTime.value[index]
      const progress = Math.min(100, (elapsed / dwellMs) * 100)

      zoneProgress.value[index] = progress

      // 停留完成（进度达到100%）
      if (progress >= 100) {
        zoneFeedback.value[index] = 'pending'
        zoneFeedbackTime.value[index] = now
        emit('action', { type: 'zone_dwell_completed', zone_id: zone.id, dwell_time: elapsed })
      }
    } else {
      // 玩家离开区域，重置进度
      zoneProgress.value[index] = 0
      zoneStartTime.value[index] = 0
    }
  })
}

// ==================== 绘制游戏 ====================
function draw() {
  if (!ctx) return

  // 清空画布
  ctx.clearRect(0, 0, gameCanvas.value.width, gameCanvas.value.height)

  ctx.save()
  ctx.scale(props.scaleX, props.scaleY)

  // 绘制8个区域
  const questionZones = currentQuestion.value?.zones || {}

  zones.forEach((zone, index) => {
    const zoneState = questionZones[zone.id] || { active: false, color: '#d9d9d9', is_target: false }
    const progress = zoneProgress.value[index]
    const feedback = zoneFeedback.value[index]

    // 确定区域颜色
    let zoneColor = zoneState.color || '#d9d9d9'
    let glowColor = null
    if (feedback === 'correct') {
      zoneColor = '#33B555'
      glowColor = 'rgba(51, 181, 85, 0.5)'
    } else if (feedback === 'wrong') {
      zoneColor = '#FF4444'
      glowColor = 'rgba(255, 68, 68, 0.5)'
    }

    // 绘制发光效果（与打地鼠一致）
    if (glowColor) {
      ctx.beginPath()
      ctx.arc(zone.x, zone.y, zone.radius + 20, 0, Math.PI * 2)
      ctx.fillStyle = glowColor
      ctx.fill()
    }

    // 绘制区域（圆形）
    ctx.beginPath()
    ctx.arc(zone.x, zone.y, zone.radius, 0, Math.PI * 2)
    ctx.fillStyle = zoneColor
    ctx.fill()

    // 绘制边框
    ctx.beginPath()
    ctx.arc(zone.x, zone.y, zone.radius, 0, Math.PI * 2)
    ctx.strokeStyle = zoneState.active ? '#FFFFFF' : '#666666'
    ctx.lineWidth = zoneState.active ? 4 : 2
    ctx.stroke()

    // 绘制进度圈（与打地鼠一致）
    if (progress > 0 && feedback !== 'correct' && feedback !== 'wrong') {
      ctx.beginPath()
      ctx.arc(zone.x, zone.y, zone.radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * progress / 100))
      ctx.strokeStyle = '#FFFFFF'
      ctx.lineWidth = 8
      ctx.lineCap = 'round'
      ctx.stroke()
    }
  })

  // 绘制UI信息
  drawUI()

  ctx.restore()

  animationId = requestAnimationFrame(draw)
}

// ==================== 绘制UI ====================
function drawUI() {
  // 绘制倒计时
  ctx.font = 'bold 30px Arial'
  ctx.fillStyle = '#FFFFFF'
  ctx.textAlign = 'left'
  ctx.fillText(`倒计时: ${Math.floor(props.gameState.timer || 0)}s`, 20, 40)

  // 绘制得分
  ctx.textAlign = 'right'
  ctx.fillText(`得分: ${props.gameState.score || 0}`, 620, 40)

  // 绘制指令（如"踩绿色"）
  if (currentQuestion.value && currentQuestion.value.instruction && !inInterval.value) {
    ctx.textAlign = 'center'
    ctx.font = 'bold 35px Arial'

    const instruction = currentQuestion.value.instruction
    const textWidth = ctx.measureText(instruction).width

    // 绘制背景框
    ctx.fillStyle = 'rgba(255, 114, 34, 0.8)'
    ctx.fillRect(320 - textWidth / 2 - 20, 60, textWidth + 40, 50)

    // 绘制文字
    ctx.fillStyle = '#FFFFFF'
    ctx.fillText(instruction, 320, 95)
  }

  // 绘制作答时间进度条
  if (!inInterval.value) {
    const progressRatio = Math.max(0, Math.min(1, remainingTime.value / answerTime.value))

    // 进度条背景
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)'
    ctx.fillRect(420, 20, 180, 20)

    // 进度条填充
    let progressColor = '#33B555'
    if (progressRatio < 0.3) progressColor = '#FF4444'
    else if (progressRatio < 0.6) progressColor = '#FFD111'

    ctx.fillStyle = progressColor
    ctx.fillRect(420, 20, 180 * progressRatio, 20)
  }
}

// ==================== 监听游戏状态变化 ====================
watch(() => props.gameState, (newState) => {
  // 更新题目状态
  if (newState.question !== undefined) {
    currentQuestion.value = newState.question
  }

  if (newState.in_interval !== undefined) {
    inInterval.value = newState.in_interval

    // 进入间隔期，清除反馈
    if (newState.in_interval) {
      zoneFeedback.value = [null, null, null, null, null, null, null, null]
      zoneProgress.value = [0, 0, 0, 0, 0, 0, 0, 0]
      zoneStartTime.value = [0, 0, 0, 0, 0, 0, 0, 0]
    }
  }

  if (newState.remaining_time !== undefined) {
    remainingTime.value = newState.remaining_time
  }

  if (newState.question && newState.question.answer_time) {
    answerTime.value = newState.question.answer_time
  }

  // 反馈处理
  if (newState.feedback) {
    const fb = newState.feedback

    // 显示区域反馈（正确/错误）
    if (fb.zone_id && fb.zone_id >= 1 && fb.zone_id <= 8) {
      const zoneIndex = fb.zone_id - 1
      zoneFeedback.value[zoneIndex] = fb.correct ? 'correct' : 'wrong'
      zoneFeedbackTime.value[zoneIndex] = Date.now()
      zoneProgress.value[zoneIndex] = 0
      zoneStartTime.value[zoneIndex] = 0
    }

    // 超时反馈，清除所有pending状态
    if (fb.is_timeout) {
      for (let i = 0; i < 8; i++) {
        if (zoneFeedback.value[i] === 'pending') {
          zoneFeedback.value[i] = null
          zoneProgress.value[i] = 0
          zoneStartTime.value[i] = 0
        }
      }
    }
  }
}, { deep: true, immediate: true })

// ==================== 生命周期 ====================
let updateInterval = null

onMounted(() => {
  initCanvas()
  draw()
  updateInterval = setInterval(updateGame, 50) // 每50ms更新一次
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  if (updateInterval) clearInterval(updateInterval)
})
</script>

<style scoped>
.processing-speed-game {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 2;
}

.game-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
