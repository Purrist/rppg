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
    
    <!-- 原始摄像头画面 -->
    <div class="video-section">
      <h2>原始摄像头画面（拖动四角校准）</h2>
      <div class="video-container">
        <img id="video" :src="videoUrl" @load="onVideoLoad" @error="onVideoError">
        <canvas ref="rawCanvas" @mousedown="handleRawMouseDown" @mousemove="handleRawMouseMove" 
                @mouseup="handleRawMouseUp" @mouseleave="handleRawMouseUp"></canvas>
      </div>
    </div>
    
    <!-- 校正后画面 -->
    <div class="video-section">
      <h2>校正后画面（显示区域配置）</h2>
      <div class="corrected-container">
        <img id="corrected" :src="correctedUrl" @load="onVideoLoad" @error="onVideoError">
        <canvas ref="correctedCanvas" @mousedown="handleCorrectedMouseDown" @mousemove="handleCorrectedMouseMove"
                @mouseup="handleCorrectedMouseUp" @mouseleave="handleCorrectedMouseUp"></canvas>
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
      </div>
      
      <!-- 添加区域 -->
      <div class="section-title">➕ 添加区域 ({{ config.zones.length }}/12)</div>
      <div class="button-row">
        <button class="btn" @click="addZone('rect')">▢ 矩形</button>
        <button class="btn" @click="addZone('circle')">○ 圆形</button>
        <button class="btn" @click="addZone('triangle')">△ 三角形</button>
      </div>
      
      <!-- 区域列表 -->
      <div class="section-title">📋 区域列表</div>
      <div class="zone-list">
        <div v-for="zone in config.zones" :key="zone.id" 
             class="zone-item" :class="{ editing: editingZone === zone.id }">
          <div class="zone-header">
            <span class="zone-dot" :style="{ backgroundColor: zone.color }"></span>
            <input class="zone-name" :value="zone.name" @change="renameZone(zone.id, $event.target.value)">
            <span class="zone-type">({{ typeNames[zone.type] }})</span>
            <div class="zone-actions">
              <button v-if="editingZone === zone.id" class="btn-small btn-green" @click="confirmEdit(zone.id)">确定</button>
              <button v-else class="btn-small btn-orange" @click="startEdit(zone.id)">编辑</button>
              <button class="btn-small btn-red" @click="deleteZone(zone.id)">删除</button>
            </div>
          </div>
        </div>
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

console.log('[Developer] 后端地址:', backendUrl)

const COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B", "#4CAF50", "#3F51B5"]
const typeNames = { 'rect': '矩形', 'triangle': '三角形', 'circle': '圆形', 'quad': '四边形' }

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
const editingZone = ref(null)
const draggingCorner = ref(-1)
const mouseDown = ref(false)
const dragMode = ref(null)
const dragStartPos = ref(null)
const dragStartData = ref(null)

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

async function saveZones() {
  if (!connected.value) return
  try {
    await fetch(`${backendUrl}/api/zones`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zones: config.zones, zone_id_counter: config.zone_id_counter })
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
    ctx.lineWidth = 2
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
      ctx.arc(x, y, 12, 0, Math.PI * 2)
      ctx.fillStyle = '#0066cc'
      ctx.fill()
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 12px Arial'
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
    
    config.zones.forEach(zone => {
      drawZone(ctx, zone, scaleX, scaleY, editingZone.value === zone.id)
    })
    
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

function drawZone(ctx, zone, scaleX, scaleY, isEditing) {
  ctx.strokeStyle = zone.color
  ctx.lineWidth = isEditing ? 3 : 2
  
  if (zone.type === 'circle') {
    const cx = zone.center[0] * scaleX
    const cy = zone.center[1] * scaleY
    const r = zone.radius * Math.min(scaleX, scaleY)
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.stroke()
    if (isEditing) {
      ctx.beginPath()
      ctx.arc(cx, cy, 12, 0, Math.PI * 2)
      ctx.fillStyle = '#fff'
      ctx.fill()
      ctx.strokeStyle = zone.color
      ctx.lineWidth = 3
      ctx.stroke()
    }
    ctx.fillStyle = zone.color
    ctx.font = 'bold 16px Arial'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(zone.name, cx, cy)
  } else {
    const points = zone.points.map(p => [p[0] * scaleX, p[1] * scaleY])
    ctx.beginPath()
    points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]))
    ctx.closePath()
    ctx.stroke()
    if (isEditing) {
      ctx.fillStyle = zone.color + '30'
      ctx.fill()
      ctx.strokeStyle = zone.color
      ctx.lineWidth = 2
      points.forEach(p => {
        ctx.beginPath()
        ctx.arc(p[0], p[1], 8, 0, Math.PI * 2)
        ctx.fillStyle = '#fff'
        ctx.fill()
        ctx.stroke()
      })
    }
    const cx = points.reduce((s, p) => s + p[0], 0) / points.length
    const cy = points.reduce((s, p) => s + p[1], 0) / points.length
    ctx.fillStyle = zone.color
    ctx.font = 'bold 16px Arial'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(zone.name, cx, cy)
  }
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

function handleCorrectedMouseDown(e) {
  if (!editingZone.value) return
  const rect = correctedCanvas.value.getBoundingClientRect()
  const pos = { x: (e.clientX - rect.left) / rect.width * 640, y: (e.clientY - rect.top) / rect.height * 360 }
  const zone = config.zones.find(z => z.id === editingZone.value)
  if (!zone) return
  
  dragStartPos.value = { x: pos.x, y: pos.y }
  dragStartData.value = JSON.parse(JSON.stringify(zone))
  mouseDown.value = true
  
  if (zone.type === 'circle') {
    const dCenter = Math.hypot(pos.x - zone.center[0], pos.y - zone.center[1])
    if (dCenter < 20) dragMode.value = 'move'
    else mouseDown.value = false
  } else {
    const centerX = zone.points.reduce((s, p) => s + p[0], 0) / zone.points.length
    const centerY = zone.points.reduce((s, p) => s + p[1], 0) / zone.points.length
    if (Math.hypot(pos.x - centerX, pos.y - centerY) < 30) dragMode.value = 'move'
    else mouseDown.value = false
  }
}

function handleCorrectedMouseMove(e) {
  if (!mouseDown.value || !editingZone.value || !dragMode.value) return
  const rect = correctedCanvas.value.getBoundingClientRect()
  const pos = { x: (e.clientX - rect.left) / rect.width * 640, y: (e.clientY - rect.top) / rect.height * 360 }
  const zone = config.zones.find(z => z.id === editingZone.value)
  if (!zone) return
  
  const dx = pos.x - dragStartPos.value.x
  const dy = pos.y - dragStartPos.value.y
  
  if (zone.type === 'circle') {
    if (dragMode.value === 'move') {
      zone.center[0] = Math.max(50, Math.min(590, dragStartData.value.center[0] + dx))
      zone.center[1] = Math.max(50, Math.min(310, dragStartData.value.center[1] + dy))
    }
  } else {
    if (dragMode.value === 'move') {
      zone.points = dragStartData.value.points.map(p => [
        Math.max(10, Math.min(630, p[0] + dx)),
        Math.max(10, Math.min(350, p[1] + dy))
      ])
    }
  }
}

function handleCorrectedMouseUp() {
  if (mouseDown.value) saveZones()
  mouseDown.value = false
  dragMode.value = null
}

// ==================== 区域操作 ====================
function addZone(type) {
  if (config.zones.length >= 12) { alert('最多12个区域'); return }
  const id = config.zone_id_counter++
  const color = COLORS[(id - 1) % COLORS.length]
  const baseX = 100 + Math.random() * 400
  const baseY = 100 + Math.random() * 150
  let newZone
  if (type === 'rect') newZone = { id, name: String(id), type: 'rect', points: [[baseX, baseY], [baseX+100, baseY], [baseX+100, baseY+100], [baseX, baseY+100]], color }
  else if (type === 'triangle') newZone = { id, name: String(id), type: 'triangle', points: [[baseX+50, baseY], [baseX+100, baseY+100], [baseX, baseY+100]], color }
  else newZone = { id, name: String(id), type: 'circle', center: [baseX+50, baseY+50], radius: 50, color }
  config.zones.push(newZone)
  saveZones()
}

function deleteZone(id) {
  if (config.zones.length <= 1) { alert('至少保留1个区域'); return }
  config.zones = config.zones.filter(z => z.id !== id)
  if (editingZone.value === id) editingZone.value = null
  saveZones()
}

function startEdit(id) { editingZone.value = id }
function confirmEdit(id) { editingZone.value = null; saveZones() }
function renameZone(id, name) {
  const zone = config.zones.find(z => z.id === id)
  if (zone) { zone.name = name.substring(0, 10); saveZones() }
}

// ==================== 生命周期 ====================
onMounted(async () => {
  const ok = await checkConnection()
  if (ok) {
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

.video-section {
  margin-bottom: 15px;
}

.video-container, .corrected-container {
  width: 640px;
  max-width: 100%;
  position: relative;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.video-container img, .corrected-container img {
  display: block;
  width: 100%;
}

.video-container canvas, .corrected-container canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.video-container canvas {
  cursor: crosshair;
}

.corrected-container canvas {
  cursor: move;
}

.corrected-container {
  background: #f0f0f0;
  border: 2px solid #33B555;
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
  margin: 15px 0 10px;
  padding-bottom: 5px;
  border-bottom: 1px solid #eee;
}

.section-title:first-child {
  margin-top: 0;
}

.button-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.btn {
  flex: 1;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
}

.btn:hover {
  background: #f5f5f5;
}

.btn-green { background: #33B555; color: #fff; border-color: #33B555; }
.btn-blue { background: #2196F3; color: #fff; border-color: #2196F3; }
.btn-orange { background: #FF7222; color: #fff; border-color: #FF7222; }
.btn-red { background: #f44336; color: #fff; border-color: #f44336; }

.zone-list {
  max-height: 200px;
  overflow-y: auto;
}

.zone-item {
  background: #f9f9f9;
  border: 1px solid #eee;
  border-radius: 6px;
  margin-bottom: 5px;
}

.zone-item.editing {
  border-color: #FF7222;
  background: #fff5f0;
}

.zone-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
}

.zone-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
}

.zone-name {
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: bold;
  width: 40px;
}

.zone-name:focus {
  outline: none;
  background: #fff;
  border-radius: 4px;
  padding: 2px 5px;
}

.zone-type {
  font-size: 12px;
  color: #888;
}

.zone-actions {
  margin-left: auto;
  display: flex;
  gap: 5px;
}

.btn-small {
  padding: 4px 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #fff;
}

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
