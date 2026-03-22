<template>
  <div class="processing-speed-game">
    <canvas 
      ref="gameCanvas" 
      class="game-canvas"
      :width="canvasWidth"
      :height="canvasHeight"
    ></canvas>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'

// ==================== Props ====================
const props = defineProps({
  gameState: { type: Object, required: true },
  footPosition: { type: Object, required: true },
  canvasWidth: { type: Number, default: 640 },
  canvasHeight: { type: Number, default: 360 },
  scaleX: { type: Number, default: 1 },
  scaleY: { type: Number, default: 1 }
})

const emit = defineEmits(['action'])

// ==================== Canvas ====================
const gameCanvas = ref(null)
let ctx = null
let animationId = null

// ==================== 8个区域配置（按照UI参考）====================
// 画布尺寸: 640x360
// 圆形直径: 140px, 半径: 70px
// 第一行: y=62+70=132 (圆心)
// 第二行: y=210+70=280 (圆心)
const ZONES = [
  { id: 1, x: 86, y: 132, radius: 70 },   // 第一行第1个 (left: 16+70=86)
  { id: 2, x: 242, y: 132, radius: 70 },  // 第一行第2个 (left: 172+70=242)
  { id: 3, x: 398, y: 132, radius: 70 },  // 第一行第3个 (left: 328+70=398)
  { id: 4, x: 554, y: 132, radius: 70 },  // 第一行第4个 (left: 484+70=554)
  { id: 5, x: 86, y: 280, radius: 70 },   // 第二行第1个
  { id: 6, x: 242, y: 280, radius: 70 },  // 第二行第2个
  { id: 7, x: 398, y: 280, radius: 70 },  // 第二行第3个
  { id: 8, x: 554, y: 280, radius: 70 },  // 第二行第4个
]

// ==================== 游戏状态 ====================
const zoneProgress = ref([0, 0, 0, 0, 0, 0, 0, 0])
const zoneStartTime = ref([0, 0, 0, 0, 0, 0, 0, 0])
const zoneFeedback = ref([null, null, null, null, null, null, null, null])
const zoneFeedbackTime = ref([0, 0, 0, 0, 0, 0, 0, 0])

const FEEDBACK_DURATION = 1000

// ==================== 获取确认时间 ====================
function getDwellDuration() {
  // 从props获取，后端传来的确认时间（秒）转换为毫秒
  if (props.gameState && props.gameState.dwell_time) {
    return props.gameState.dwell_time * 1000
  }
  return 2000 // 默认2秒
}

// ==================== 初始化Canvas ====================
function initCanvas() {
  if (!gameCanvas.value) return
  ctx = gameCanvas.value.getContext('2d')
}

// ==================== 绘制游戏 ====================
function draw() {
  if (!ctx) return

  // 清空画布（黑色背景）
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, props.canvasWidth, props.canvasHeight)

  // ⭐ 应用缩放
  ctx.save()
  ctx.scale(props.scaleX, props.scaleY)

  // 获取游戏数据
  const question = props.gameState?.question
  const zones = question?.zones || {}
  const instruction = question?.instruction || ''
  const score = props.gameState?.score || 0
  const inInterval = props.gameState?.in_interval || false

  // 绘制UI（按照UI参考）
  drawUI(instruction, score, inInterval)

  // 绘制8个区域
  drawZones(zones)

  ctx.restore()

  animationId = requestAnimationFrame(draw)
}

// ==================== 绘制UI（上方信息栏）====================
function drawUI(instruction, score, inInterval) {
  // 绘制顶部信息栏背景
  ctx.fillStyle = 'rgba(0, 0, 0, 0.8)'
  ctx.fillRect(0, 0, props.canvasWidth, 55)

  // 左侧：指令（如"踩紫色"）
  if (instruction && !inInterval) {
    // 绘制图标背景（灰色圆角矩形）
    ctx.fillStyle = '#505050'
    ctx.beginPath()
    ctx.roundRect(11, 11, 42, 42, 8)
    ctx.fill()

    // 绘制指令文字
    ctx.font = 'bold 24px "Alibaba PuHuiTi", sans-serif'
    ctx.fillStyle = '#ffffff'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(instruction, 65, 32)
  }

  // 中间：单题进度条（灰色背景+绿色进度）
  const answerTime = props.gameState?.answer_time || 5
  const remainingTime = props.gameState?.remaining_time || answerTime
  const progress = Math.max(0, Math.min(1, remainingTime / answerTime))
  
  // 进度条背景
  ctx.fillStyle = '#505050'
  ctx.beginPath()
  ctx.roundRect(337, 24, 141, 15, 8)
  ctx.fill()
  
  // 进度条填充（绿色）
  if (!inInterval && remainingTime > 0) {
    ctx.fillStyle = '#46cc41'
    ctx.beginPath()
    ctx.roundRect(337, 24, 141 * progress, 15, 8)
    ctx.fill()
  }

  // 右侧：总分
  ctx.font = 'bold 26px "Alibaba PuHuiTi", sans-serif'
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  ctx.fillText(`总分：${score}`, 625, 32)
}

// ==================== 绘制8个区域 ====================
function drawZones(questionZones) {
  const now = Date.now()
  const dwellMs = getDwellDuration()

  ZONES.forEach((zone, index) => {
    const zoneData = questionZones[zone.id] || { active: false, color: '#222222' }
    const progress = zoneProgress.value[index]
    const feedback = zoneFeedback.value[index]

    // 确定区域颜色
    let fillColor = zoneData.color || '#222222'
    let borderColor = '#454545'

    // 如果有反馈（正确/错误）
    if (feedback === 'correct') {
      fillColor = '#33B555' // 绿色
      borderColor = '#33B555'
    } else if (feedback === 'wrong') {
      fillColor = '#ff4444' // 红色
      borderColor = '#ff4444'
    }

    // 绘制区域圆形
    ctx.beginPath()
    ctx.arc(zone.x, zone.y, zone.radius, 0, Math.PI * 2)
    ctx.fillStyle = fillColor
    ctx.fill()

    // 绘制边框
    ctx.beginPath()
    ctx.arc(zone.x, zone.y, zone.radius, 0, Math.PI * 2)
    ctx.strokeStyle = borderColor
    ctx.lineWidth = 5
    ctx.stroke()

    // 绘制进度圈（白色圆弧）- 与打地鼠一致，画在区域边缘
    if (progress > 0 && !feedback) {
      ctx.beginPath()
      // 进度环画在区域边缘，与打地鼠一致
      ctx.arc(zone.x, zone.y, zone.radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * progress / 100))
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 8
      ctx.lineCap = 'round'
      ctx.stroke()
    }

    // 清除过期反馈
    if (feedback && now - zoneFeedbackTime.value[index] > FEEDBACK_DURATION) {
      zoneFeedback.value[index] = null
      zoneProgress.value[index] = 0
      zoneStartTime.value[index] = 0
    }
  })
}

// ==================== 更新游戏状态（检测脚部位置）====================
function updateGame() {
  if (!props.footPosition.detected) {
    // 没有检测到脚部，清空所有进度
    for (let i = 0; i < 8; i++) {
      zoneProgress.value[i] = 0
      zoneStartTime.value[i] = 0
    }
    return
  }

  const now = Date.now()
  const dwellMs = getDwellDuration()
  const inInterval = props.gameState?.in_interval || false

  // 检查所有8个区域
  ZONES.forEach((zone, index) => {
    const feedback = zoneFeedback.value[index]
    if (feedback) return // 有反馈时不处理

    // ⭐ 检测玩家是否在区域内
    // footPosition 已经是设计坐标（640x360），直接使用
    const dx = props.footPosition.x - zone.x
    const dy = props.footPosition.y - zone.y
    const inZone = (dx * dx + dy * dy) <= (zone.radius * zone.radius)

    if (inZone) {
      // 玩家进入区域，开始计时
      if (!zoneStartTime.value[index]) zoneStartTime.value[index] = now
      const elapsed = now - zoneStartTime.value[index]
      const progress = Math.min(100, (elapsed / dwellMs) * 100)

      zoneProgress.value[index] = progress

      // 停留完成且不在间隔期时才发送动作
      if (progress >= 100 && !inInterval) {
        zoneFeedback.value[index] = 'pending'
        zoneFeedbackTime.value[index] = now
        emit('action', { 
          type: 'zone_dwell_completed', 
          zone_id: zone.id, 
          dwell_time: elapsed 
        })
      }
    } else {
      // 玩家离开区域，重置进度
      zoneProgress.value[index] = 0
      zoneStartTime.value[index] = 0
    }
  })
}

// ==================== 监听反馈 ====================
watch(() => props.gameState?.feedback, (newFeedback) => {
  if (!newFeedback) return
  
  // 如果有 zone_id，显示区域反馈
  if (newFeedback.zone_id) {
    const zoneIndex = newFeedback.zone_id - 1
    if (zoneIndex >= 0 && zoneIndex < 8) {
      zoneFeedback.value[zoneIndex] = newFeedback.correct ? 'correct' : 'wrong'
      zoneFeedbackTime.value[zoneIndex] = Date.now()
      zoneProgress.value[zoneIndex] = 0
      zoneStartTime.value[zoneIndex] = 0
    }
  } else if (newFeedback.is_timeout && newFeedback.correct) {
    // ⭐ "别踩X"超时正确（成功抑制）- 清除所有区域进度
    for (let i = 0; i < 8; i++) {
      zoneProgress.value[i] = 0
      zoneStartTime.value[i] = 0
    }
  }
}, { deep: true })

// ==================== 生命周期 ====================
onMounted(() => {
  initCanvas()
  draw()
  
  // 启动更新循环
  const updateInterval = setInterval(updateGame, 50) // 50ms更新一次
  
  onUnmounted(() => {
    clearInterval(updateInterval)
    if (animationId) cancelAnimationFrame(animationId)
  })
})
</script>

<style scoped>
.processing-speed-game {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: #000000;
}

.game-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
