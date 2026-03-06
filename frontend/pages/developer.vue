<template>
  <div class="admin-page" :style="{ backgroundColor: config.admin_bg }">
    <h1>🛠 开发者后台</h1>
    
    <!-- 连接状态 -->
    <div class="connection-status" :class="connected ? 'connected' : 'disconnected'">
      {{ connected ? '✅ 后端已连接' : '❌ 后端未连接' }}
      <span class="backend-url">({{ backendUrl }})</span>
    </div>
    
    <!-- 游戏状态 -->
    <div class="game-status-bar">
      <span>游戏状态: <strong :class="'status-' + gameState.status">{{ gameStateText }}</strong></span>
      <span>得分: <strong>{{ gameState.score }}</strong></span>
      <span>时间: <strong>{{ gameState.timer }}s</strong></span>
    </div>
    
    <!-- 摄像头画面区域 -->
    <div class="cameras-row">
      <!-- 投影摄像头 -->
      <div class="camera-section">
        <h2>投影摄像头（拖动四角校准）</h2>
        <div class="video-container">
          <img id="video" :src="videoUrl" @load="onVideoLoad" @error="onVideoError">
          <canvas ref="rawCanvas" @mousedown="handleRawMouseDown" @mousemove="handleRawMouseMove" 
                  @mouseup="handleRawMouseUp" @mouseleave="handleRawMouseUp"></canvas>
        </div>
      </div>
      
      <!-- 平板摄像头（rPPG） -->
      <div class="camera-section">
        <h2>平板摄像头（心率检测）</h2>
        <div class="video-container tablet-cam">
          <img id="tablet-video" :src="tabletVideoUrl" @error="onVideoError">
          <div class="rppg-overlay">
            <div class="heart-rate">
              <span class="heart-icon">❤️</span>
              <span class="bpm-value">{{ health.bpm || '--' }}</span>
              <span class="bpm-unit">BPM</span>
            </div>
            <div class="health-stats">
              <span>情绪: {{ health.emotion || '--' }}</span>
              <span>HRV: {{ health.hrv || '--' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 校正后画面 -->
    <div class="video-section">
      <h2>校正后画面</h2>
      <div class="corrected-container">
        <img id="corrected" :src="correctedUrl" @load="onVideoLoad" @error="onVideoError">
        <canvas ref="correctedCanvas"></canvas>
      </div>
    </div>
    
    <!-- 状态栏 -->
    <div class="status-bar">
      <span>脚部: <span :class="status.feet_detected ? 'detected' : 'not-detected'">
        {{ status.feet_detected ? `已检测 (${status.feet_x}, ${status.feet_y})` : '未检测到' }}
      </span></span>
      <span>区域: <span :class="status.active_zones?.length > 0 ? 'detected' : 'not-detected'">
        {{ status.active_zones?.length > 0 ? status.active_zones.join(' - ') : '未进入' }}
      </span></span>
    </div>
    
    <!-- 控制面板 -->
    <div class="control-panel">
      <!-- 配置保存/加载 -->
      <div class="section-title">💾 配置</div>
      <div class="button-row">
        <button class="btn btn-green" @click="saveAllConfig">保存配置</button>
        <button class="btn btn-blue" @click="loadAllConfig">加载配置</button>
        <button class="btn btn-orange" @click="resetCalibration">重置校准</button>
      </div>
    </div>
    
    <!-- Toast -->
    <div v-if="toast.show" class="toast">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'

// ==================== 自动检测后端地址 ====================
const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  const host = window.location.hostname
  return host || 'localhost'
}

const FLASK_PORT = 5000
const backendHost = getBackendHost()
const backendUrl = `http://${backendHost}:${FLASK_PORT}`
const videoUrl = `${backendUrl}/video_feed`
const correctedUrl = `${backendUrl}/corrected_feed`
const tabletVideoUrl = `${backendUrl}/tablet_video_feed`

console.log('[Developer] 后端地址:', backendUrl)

// ==================== 状态 ====================
const connected = ref(false)
const rawCanvas = ref(null)
const correctedCanvas = ref(null)

const config = reactive({
  corners: [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]],
  zones: [],
  zone_id_counter: 4,
  admin_bg: '#ffffff',
  projection_bg: '#000000'
})

const status = reactive({
  feet_detected: false,
  feet_x: 320,
  feet_y: 180,
  active_zones: []
})

const health = reactive({
  bpm: null,
  hrv: null,
  emotion: null
})

const gameState = reactive({
  status: 'IDLE',
  score: 0,
  timer: 60
})

const gameStateText = computed(() => {
  const texts = { 'IDLE': '待机中', 'READY': '等待开始', 'PLAYING': '游戏进行中', 'PAUSED': '已暂停' }
  return texts[gameState.status] || '未知'
})

const toast = reactive({ show: false, msg: '' })
const draggingCorner = ref(-1)
const mouseDown = ref(false)

let statusInterval = null

// ==================== 工具函数 ====================
function showToast(msg) {
  toast.msg = msg
  toast.show = true
  setTimeout(() => toast.show = false, 2000)
}

// ==================== 连接检查 ====================
async function checkConnection() {
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 3000)
    
    const res = await fetch(`${backendUrl}/api/config`, {
      method: 'GET',
      signal: controller.signal
    })
    
    clearTimeout(timeoutId)
    connected.value = res.ok
    return res.ok
  } catch (e) {
    connected.value = false
    return false
  }
}

// ==================== 配置加载/保存 ====================
async function loadConfig() {
  try {
    const res = await fetch(`${backendUrl}/api/config`)
    if (!res.ok) throw new Error('请求失败')
    const data = await res.json()
    if (data.corners) config.corners = data.corners
    if (data.zones) config.zones = data.zones
    if (data.zone_id_counter) config.zone_id_counter = data.zone_id_counter
    if (data.admin_bg) config.admin_bg = data.admin_bg
    if (data.projection_bg) config.projection_bg = data.projection_bg
    connected.value = true
    return true
  } catch (e) {
    connected.value = false
    return false
  }
}

async function saveCorners() {
  if (!connected.value) return
  try {
    await fetch(`${backendUrl}/api/corners`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ corners: config.corners })
    })
  } catch (e) {}
}

async function saveAllConfig() {
  if (!connected.value) { showToast('后端未连接'); return }
  try {
    const res = await fetch(`${backendUrl}/api/save_all`, { method: 'POST' })
    const data = await res.json()
    showToast(data.msg || '保存成功')
  } catch (e) {
    showToast('保存失败')
  }
}

async function loadAllConfig() {
  if (!connected.value) { showToast('后端未连接'); return }
  try {
    const res = await fetch(`${backendUrl}/api/load_all`, { method: 'POST' })
    const data = await res.json()
    if (data.ok) {
      await loadConfig()
      showToast('配置已加载')
    } else {
      showToast(data.msg || '加载失败')
    }
  } catch (e) {
    showToast('加载失败')
  }
}

async function resetCalibration() {
  config.corners = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]]
  await saveCorners()
  showToast('校准已重置')
}

// ==================== 状态更新 ====================
async function updateStatus() {
  if (!connected.value) {
    await checkConnection()
    if (!connected.value) return
  }
  
  try {
    const res = await fetch(`${backendUrl}/api/status`)
    if (res.ok) {
      const data = await res.json()
      Object.assign(status, data)
    }
    
    const gsRes = await fetch(`${backendUrl}/api/system/state`)
    if (gsRes.ok) {
      const gsData = await gsRes.json()
      if (gsData.state && gsData.state.game) {
        gameState.status = gsData.state.game.status || 'IDLE'
        gameState.score = gsData.state.game.score || 0
        gameState.timer = gsData.state.game.timer || 60
      }
    }
    
    // 获取健康数据
    const healthRes = await fetch(`${backendUrl}/api/health`)
    if (healthRes.ok) {
      const healthData = await healthRes.json()
      Object.assign(health, healthData)
    }
  } catch (e) {
    connected.value = false
  }
}

// ==================== 视频处理 ====================
function onVideoLoad() {
  resize()
}

function onVideoError(e) {
  console.log('视频流加载中...')
}

function resize() {
  const video = document.getElementById('video')
  const corrected = document.getElementById('corrected')
  if (video && rawCanvas.value) {
    rawCanvas.value.width = video.offsetWidth
    rawCanvas.value.height = video.offsetHeight
  }
  if (corrected && correctedCanvas.value) {
    correctedCanvas.value.width = corrected.offsetWidth
    correctedCanvas.value.height = corrected.offsetHeight
  }
}

function draw() {
  if (rawCanvas.value) {
    const ctx = rawCanvas.value.getContext('2d')
    const w = rawCanvas.value.width
    const h = rawCanvas.value.height
    ctx.clearRect(0, 0, w, h)
    
    ctx.strokeStyle = '#0066cc'
    ctx.lineWidth = 3
    ctx.beginPath()
    config.corners.forEach((p, i) => {
      const x = p[0] * w, y = p[1] * h
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.closePath()
    ctx.stroke()
    ctx.fillStyle = 'rgba(0, 102, 204, 0.1)'
    ctx.fill()
    
    config.corners.forEach((p, i) => {
      const x = p[0] * w, y = p[1] * h
      ctx.beginPath()
      ctx.arc(x, y, 15, 0, Math.PI * 2)
      ctx.fillStyle = '#0066cc'
      ctx.fill()
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 14px Arial'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(i + 1, x, y)
    })
  }
  
  if (correctedCanvas.value) {
    const ctx = correctedCanvas.value.getContext('2d')
    const scaleX = correctedCanvas.value.width / 640
    const scaleY = correctedCanvas.value.height / 360
    ctx.clearRect(0, 0, correctedCanvas.value.width, correctedCanvas.value.height)
    
    if (status.feet_detected) {
      const fx = status.feet_x * scaleX
      const fy = status.feet_y * scaleY
      ctx.beginPath()
      ctx.arc(fx, fy, 15, 0, Math.PI * 2)
      ctx.fillStyle = '#33B555'
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 3
      ctx.stroke()
    }
  }
  
  requestAnimationFrame(draw)
}

// ==================== 鼠标事件 ====================
function handleRawMouseDown(e) {
  const rect = rawCanvas.value.getBoundingClientRect()
  const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }
  for (let i = 0; i < config.corners.length; i++) {
    if (Math.hypot(config.corners[i][0] - pos.x, config.corners[i][1] - pos.y) < 0.05) {
      draggingCorner.value = i
      mouseDown.value = true
      break
    }
  }
}

function handleRawMouseMove(e) {
  if (!mouseDown.value || draggingCorner.value < 0) return
  const rect = rawCanvas.value.getBoundingClientRect()
  const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }
  config.corners[draggingCorner.value] = [
    Math.max(0.02, Math.min(0.98, pos.x)),
    Math.max(0.02, Math.min(0.98, pos.y))
  ]
}

function handleRawMouseUp() {
  if (mouseDown.value && draggingCorner.value >= 0) saveCorners()
  mouseDown.value = false
  draggingCorner.value = -1
}

// ==================== 生命周期 ====================
onMounted(async () => {
  // 先尝试加载保存的配置
  const ok = await checkConnection()
  if (ok) {
    // 先尝试加载保存的配置
    await fetch(`${backendUrl}/api/load_all`, { method: 'POST' })
    await loadConfig()
  }
  
  resize()
  requestAnimationFrame(draw)
  statusInterval = setInterval(updateStatus, 500)
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  if (statusInterval) clearInterval(statusInterval)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.admin-page {
  padding: 15px;
  font-family: sans-serif;
  min-height: 100vh;
  background: #f5f5f5;
  width: 100%;
  max-width: 1400px;
  margin: 0 auto;
  box-sizing: border-box;
}

h1 {
  font-size: 20px;
  margin-bottom: 10px;
  color: #333;
}

h2 {
  font-size: 14px;
  margin-bottom: 8px;
  color: #666;
}

.connection-status {
  padding: 10px 15px;
  border-radius: 8px;
  margin-bottom: 15px;
  font-weight: bold;
}

.connection-status.connected {
  background: #d4edda;
  color: #155724;
}

.connection-status.disconnected {
  background: #f8d7da;
  color: #721c24;
}

.backend-url {
  font-weight: normal;
  font-size: 12px;
  opacity: 0.7;
}

.game-status-bar {
  display: flex;
  gap: 20px;
  padding: 10px 15px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 15px;
  font-size: 14px;
}

.status-IDLE { color: #666; }
.status-READY { color: #FF7222; }
.status-PLAYING { color: #33B555; }
.status-PAUSED { color: #FFD111; }

.cameras-row {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
}

.camera-section {
  flex: 1;
}

.video-container {
  width: 100%;
  position: relative;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.video-container img {
  display: block;
  width: 100%;
}

.video-container canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

.tablet-cam {
  background: #1a1a2e;
}

.rppg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.heart-rate {
  display: flex;
  align-items: center;
  gap: 10px;
}

.heart-icon {
  font-size: 40px;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.2); }
}

.bpm-value {
  font-size: 48px;
  font-weight: bold;
  color: #ff6b6b;
}

.bpm-unit {
  font-size: 20px;
  color: #aaa;
}

.health-stats {
  margin-top: 15px;
  display: flex;
  gap: 20px;
  font-size: 16px;
  color: #aaa;
}

.video-section {
  margin-bottom: 15px;
}

.corrected-container {
  width: 100%;
  max-width: 640px;
  position: relative;
  background: #f0f0f0;
  border: 2px solid #33B555;
  border-radius: 8px;
  overflow: hidden;
}

.corrected-container img {
  display: block;
  width: 100%;
}

.corrected-container canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.status-bar {
  display: flex;
  gap: 20px;
  padding: 10px 15px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 15px;
  font-size: 14px;
}

.detected { color: #33B555; font-weight: bold; }
.not-detected { color: #ff6b6b; }

.control-panel {
  background: #fff;
  border-radius: 8px;
  padding: 15px;
}

.section-title {
  font-size: 14px;
  font-weight: bold;
  margin-bottom: 10px;
  padding-bottom: 5px;
  border-bottom: 1px solid #eee;
}

.button-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.btn {
  flex: 1;
  padding: 12px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: bold;
  color: #fff;
}

.btn-green { background: #33B555; }
.btn-blue { background: #2196F3; }
.btn-orange { background: #FF7222; }

.toast {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #333;
  color: #fff;
  padding: 12px 24px;
  border-radius: 8px;
  z-index: 1000;
}
</style>
