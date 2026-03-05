<template>
  <div class="projection-page">
    <!-- 状态文字 -->
    <div id="status-text" :class="{ 'in-zone': status.active_zones?.length > 0 }">
      {{ statusText }}
    </div>
    
    <!-- 脚部位置指示器 -->
    <div id="foot-point" :style="footPointStyle"></div>
    
    <!-- 区域画布 -->
    <canvas ref="zonesCanvas"></canvas>
    
    <!-- 加载圆环 -->
    <svg id="loading-ring" viewBox="0 0 100 100" :style="loadingRingStyle">
      <circle cx="50" cy="50" r="45" fill="none" stroke="#333" stroke-width="3" opacity="0.3"/>
      <circle id="progress-circle" cx="50" cy="50" r="45" fill="none" 
              :stroke="progressColor" stroke-width="6" stroke-linecap="round" 
              stroke-dasharray="283" :stroke-dashoffset="progressOffset"
              transform="rotate(-90 50 50)"/>
    </svg>
    
    <!-- 得分反馈 -->
    <div id="score-feedback" :style="scoreFeedbackStyle">{{ scoreText }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const projW = 640
const projH = 360
const LOADING_DURATION = 3000

// Flask 后端运行在端口 5000
const FLASK_PORT = 5000

const zonesCanvas = ref(null)

const config = ref({
  zones: [],
  projection_bg: '#000000'
})

const status = ref({
  feet_detected: false,
  feet_x: 320,
  feet_y: 180,
  active_zones: []
})

const loadingZone = ref(null)
const loadingProgress = ref(0)
const loadingStartTime = ref(0)
const canTriggerAgain = ref(true)

const scoreFeedback = ref({
  show: false,
  text: '',
  color: '#33B555',
  x: 50,
  y: 38
})

const apiBase = `http://${window.location.hostname}:${FLASK_PORT}`

// 计算属性
const statusText = computed(() => {
  if (status.value.active_zones?.length > 0) {
    const names = status.value.active_zones.map(id => {
      const z = config.value.zones.find(zone => zone.id === id)
      return z ? (z.name || z.id) : id
    })
    return `已进入 ${names.join(' - ')} 区域`
  }
  return '未进入区域'
})

const footPointStyle = computed(() => {
  if (!status.value.feet_detected) {
    return { display: 'none' }
  }
  return {
    display: 'block',
    left: `${(status.value.feet_x / projW) * 100}%`,
    top: `${(status.value.feet_y / projH) * 100}%`
  }
})

const loadingRingStyle = computed(() => {
  if (loadingZone.value === null) {
    return { display: 'none' }
  }
  return {
    display: 'block',
    left: `${(status.value.feet_x / projW) * 100}%`,
    top: `${(status.value.feet_y / projH) * 100}%`
  }
})

const progressOffset = computed(() => {
  return 283 - (283 * loadingProgress.value / 100)
})

const progressColor = computed(() => {
  const zone = config.value.zones.find(z => z.id === loadingZone.value)
  return zone ? zone.color : '#33B555'
})

const scoreFeedbackStyle = computed(() => {
  if (!scoreFeedback.value.show) {
    return { display: 'none' }
  }
  return {
    display: 'block',
    color: scoreFeedback.value.color,
    left: `${scoreFeedback.value.x}%`,
    top: `${scoreFeedback.value.y}%`
  }
})

const scoreText = computed(() => scoreFeedback.value.text)

// 方法
async function loadConfig() {
  try {
    const res = await fetch(`${apiBase}/api/config`)
    const data = await res.json()
    config.value.zones = data.zones || []
    if (data.projection_bg) {
      config.value.projection_bg = data.projection_bg
    }
  } catch (e) {
    console.error('加载配置失败', e)
  }
}

async function updateStatus() {
  try {
    const res = await fetch(`${apiBase}/api/status`)
    const data = await res.json()
    const prevZones = status.value.active_zones || []
    status.value = data
    
    // 处理加载逻辑
    handleLoading(data.active_zones || [], data.feet_x, data.feet_y, data.feet_detected)
    
    // 如果区域变化，重绘
    if (JSON.stringify(prevZones) !== JSON.stringify(data.active_zones)) {
      drawZones()
    }
  } catch (e) {}
}

function handleLoading(currentZones, feetX, feetY, feetDetected) {
  if (!feetDetected) {
    resetLoading()
    return
  }
  
  if (currentZones.length > 0) {
    const zoneId = currentZones[0]
    const zone = config.value.zones.find(z => z.id === zoneId)
    
    if (loadingZone.value !== zoneId) {
      resetLoading()
      loadingZone.value = zoneId
      loadingStartTime.value = Date.now()
      loadingProgress.value = 0
      canTriggerAgain.value = true
    }
    
    // 更新进度
    loadingProgress.value = Math.min(100, ((Date.now() - loadingStartTime.value) / LOADING_DURATION) * 100)
    
    if (loadingProgress.value >= 100 && canTriggerAgain.value) {
      showFeedback(zoneId, feetX, feetY)
      canTriggerAgain.value = false
      
      // 准备下一次加载
      setTimeout(() => {
        if (loadingZone.value === zoneId) {
          loadingStartTime.value = Date.now()
          loadingProgress.value = 0
          canTriggerAgain.value = true
        }
      }, 500)
    }
  } else {
    resetLoading()
  }
}

function resetLoading() {
  if (loadingZone.value !== null) {
    loadingZone.value = null
    loadingProgress.value = 0
    scoreFeedback.value.show = false
    canTriggerAgain.value = true
  }
}

function showFeedback(zoneId, feetX, feetY) {
  const zone = config.value.zones.find(z => z.id === zoneId)
  if (!zone) return
  
  const isCircle = zone.type === 'circle'
  
  scoreFeedback.value = {
    show: true,
    text: isCircle ? '+5' : '-5',
    color: isCircle ? '#33B555' : '#ff4444',
    x: (feetX / projW) * 100,
    y: ((feetY / projH) * 100) - 12
  }
  
  setTimeout(() => {
    scoreFeedback.value.show = false
  }, 1000)
}

function resize() {
  if (zonesCanvas.value) {
    zonesCanvas.value.width = window.innerWidth
    zonesCanvas.value.height = window.innerHeight
    drawZones()
  }
}

function drawZones() {
  if (!zonesCanvas.value) return
  
  const ctx = zonesCanvas.value.getContext('2d')
  const scaleX = zonesCanvas.value.width / projW
  const scaleY = zonesCanvas.value.height / projH
  
  ctx.clearRect(0, 0, zonesCanvas.value.width, zonesCanvas.value.height)
  
  config.value.zones.forEach(zone => {
    drawZone(ctx, zone, scaleX, scaleY, status.value.active_zones?.includes(zone.id))
  })
}

function drawZone(ctx, zone, scaleX, scaleY, isActive) {
  ctx.strokeStyle = zone.color
  ctx.lineWidth = isActive ? 5 : 3
  
  if (zone.type === 'circle') {
    const cx = zone.center[0] * scaleX
    const cy = zone.center[1] * scaleY
    const r = zone.radius * Math.min(scaleX, scaleY)
    
    if (isActive) {
      ctx.fillStyle = zone.color + '40'
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()
    }
    
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.stroke()
    
    ctx.fillStyle = zone.color
    ctx.font = `bold ${20 * Math.min(scaleX, scaleY)}px Arial`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(zone.name || zone.id, cx, cy)
  } else {
    const points = zone.points.map(p => [p[0] * scaleX, p[1] * scaleY])
    
    if (isActive) {
      ctx.fillStyle = zone.color + '40'
      ctx.beginPath()
      points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]))
      ctx.closePath()
      ctx.fill()
    }
    
    ctx.beginPath()
    points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]))
    ctx.closePath()
    ctx.stroke()
    
    const cx = points.reduce((s, p) => s + p[0], 0) / points.length
    const cy = points.reduce((s, p) => s + p[1], 0) / points.length
    ctx.fillStyle = zone.color
    ctx.font = `bold ${20 * Math.min(scaleX, scaleY)}px Arial`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(zone.name || zone.id, cx, cy)
  }
}

let statusInterval = null
let configInterval = null

onMounted(() => {
  loadConfig()
  resize()
  
  // 定时更新
  statusInterval = setInterval(updateStatus, 30)
  configInterval = setInterval(loadConfig, 2000)
  
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  if (statusInterval) clearInterval(statusInterval)
  if (configInterval) clearInterval(configInterval)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
/* 彻底重置所有样式 */
.projection-page {
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  outline: 0 !important;
  box-sizing: border-box !important;
  width: 100vw !important;
  height: 100vh !important;
  overflow: hidden !important;
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  background: #000 !important;
}

#status-text {
  position: absolute;
  top: 2%;
  left: 50%;
  transform: translateX(-50%);
  font-size: 2vw;
  font-weight: bold;
  color: #333;
  z-index: 100;
  white-space: nowrap;
}

#status-text.in-zone {
  color: #33B555;
}

#foot-point {
  width: 80px;
  height: 80px;
  background: radial-gradient(circle, #33B555 0%, #228B22 100%);
  border-radius: 50%;
  position: absolute;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 25px rgba(51, 181, 85, 0.5);
  z-index: 50;
}

#foot-point::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 25px;
  height: 25px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 50%;
}

#zones-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
}

#loading-ring {
  position: absolute;
  width: 150px;
  height: 150px;
  transform: translate(-50%, -50%);
  z-index: 60;
}

#score-feedback {
  position: absolute;
  transform: translate(-50%, -50%);
  font-size: 4vw;
  font-weight: bold;
  z-index: 70;
  text-shadow: 0 0 30px currentColor;
}
</style>
