<template>
  <div class="admin-page" :style="{ backgroundColor: config.admin_bg }">
    <h1>摄像头校准管理</h1>
    
    <!-- 连接状态提示 -->
    <div v-if="!connected" class="connection-error">
      ⚠️ 无法连接到后端服务，请确保 Flask 后端正在运行（端口 5000）
      <br><br>
      <code>cd backend && python app.py</code>
    </div>
    
    <!-- 原始摄像头画面 -->
    <div class="video-container">
      <img id="video" :src="videoUrl" @load="resize" @error="handleVideoError">
      <canvas ref="rawCanvas" @mousedown="handleRawMouseDown" @mousemove="handleRawMouseMove" 
              @mouseup="handleRawMouseUp" @mouseleave="handleRawMouseUp"></canvas>
    </div>
    
    <p class="hint">↓ 矫正后的16:9画面 ↓</p>
    
    <!-- 校正后画面 -->
    <div class="corrected-container">
      <img id="corrected" :src="correctedUrl" @load="resize" @error="handleVideoError">
      <canvas ref="correctedCanvas" @mousedown="handleCorrectedMouseDown" @mousemove="handleCorrectedMouseMove"
              @mouseup="handleCorrectedMouseUp" @mouseleave="handleCorrectedMouseUp"></canvas>
    </div>
    
    <!-- 状态栏 -->
    <div class="status-bar">
      <span>脚部: <span :class="status.feet_detected ? 'detected' : 'not-detected'">
        {{ status.feet_detected ? '已检测' : '未检测到' }}
      </span></span>
      <span>区域: <span :class="status.active_zones?.length > 0 ? 'detected' : 'not-detected'">
        {{ status.active_zones?.length > 0 ? status.active_zones.join(' - ') : '未进入' }}
      </span></span>
    </div>
    
    <!-- 控制面板 -->
    <div class="control-panel">
      <!-- 设置 -->
      <div class="section-title">⚙️ 设置</div>
      <div class="settings-row">
        <div class="setting-item">
          <label>Admin背景:</label>
          <input type="color" v-model="config.admin_bg" @change="updateSettings">
        </div>
        <div class="setting-item">
          <label>Projection背景:</label>
          <input type="color" v-model="config.projection_bg" @change="updateSettings">
        </div>
      </div>
      
      <!-- 配置保存/加载 -->
      <div class="section-title">💾 配置保存/加载</div>
      <div class="save-load-row">
        <button class="save-btn btn-save-all" @click="saveAllConfig">保存全部</button>
        <button class="save-btn btn-load-all" @click="loadAllConfig">加载全部</button>
      </div>
      
      <!-- 添加区域 -->
      <div class="section-title">添加区域 ({{ config.zones.length }}/12)</div>
      <div class="add-buttons">
        <button class="add-btn" @click="addZone('rect')">▢ 矩形</button>
        <button class="add-btn" @click="addZone('triangle')">△ 三角形</button>
        <button class="add-btn" @click="addZone('circle')">○ 圆形</button>
        <button class="add-btn" @click="addZone('quad')">◇ 四边形</button>
      </div>
      
      <!-- 区域列表 -->
      <div class="section-title">区域列表</div>
      <div class="zone-list">
        <div v-for="zone in config.zones" :key="zone.id" 
             class="zone-item" 
             :class="{ editing: editingZone === zone.id }"
             draggable="true"
             @dragstart="handleDragStart($event, zone.id)"
             @dragover.prevent
             @drop="handleDrop($event, zone.id)"
             @dragend="handleDragEnd">
          <div class="zone-header">
            <span class="drag-handle">☰</span>
            <span class="zone-dot" :style="{ backgroundColor: zone.color }"></span>
            <input class="zone-name-input" :value="zone.name" 
                   @change="renameZone(zone.id, $event.target.value)"
                   @click.stop>
            <span class="zone-type">({{ typeNames[zone.type] }})</span>
            <div class="zone-actions">
              <button v-if="editingZone === zone.id" class="zone-btn btn-confirm" 
                      @click="confirmEdit(zone.id)">确定</button>
              <button v-else class="zone-btn btn-edit" @click="startEdit(zone.id)">编辑</button>
              <button class="zone-btn btn-copy" @click="copyZone(zone.id)">复制</button>
              <button class="zone-btn btn-delete" @click="deleteZone(zone.id)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Toast提示 -->
    <div v-if="toast.show" class="toast">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'

const COLORS = ["#33B555", "#FF7222", "#2196F3", "#9C27B0", "#FF5722", "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FFEB3B", "#4CAF50", "#3F51B5"]
const typeNames = { 'rect': '矩形', 'triangle': '三角形', 'circle': '圆形', 'quad': '四边形' }

// Flask 后端运行在端口 5000
const FLASK_PORT = 5000

// 使用 localhost 而不是 window.location.hostname
const apiBase = `http://localhost:${FLASK_PORT}`
const videoUrl = `${apiBase}/video_feed`
const correctedUrl = `${apiBase}/corrected_feed`

const rawCanvas = ref(null)
const correctedCanvas = ref(null)
const connected = ref(false)

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

const toast = reactive({ show: false, msg: '' })

const editingZone = ref(null)
const draggingCorner = ref(-1)
const mouseDown = ref(false)
const dragMode = ref(null)
const dragStartPos = ref(null)
const dragStartData = ref(null)
const draggedZoneId = ref(null)

function showToast(msg) {
  toast.msg = msg
  toast.show = true
  setTimeout(() => toast.show = false, 2000)
}

function handleVideoError(e) {
  console.error('视频流加载失败', e)
}

async function checkConnection() {
  try {
    const res = await fetch(`${apiBase}/api/config`, { 
      method: 'GET',
      signal: AbortSignal.timeout(3000)
    })
    connected.value = res.ok
    return res.ok
  } catch (e) {
    connected.value = false
    console.error('后端连接失败:', e)
    return false
  }
}

async function loadConfig() {
  try {
    const res = await fetch(`${apiBase}/api/config`)
    if (!res.ok) throw new Error('请求失败')
    const data = await res.json()
    if (data.corners) config.corners = data.corners
    if (data.zones) config.zones = data.zones
    if (data.zone_id_counter) config.zone_id_counter = data.zone_id_counter
    if (data.admin_bg) config.admin_bg = data.admin_bg
    if (data.projection_bg) config.projection_bg = data.projection_bg
    connected.value = true
  } catch (e) {
    console.error('加载配置失败', e)
    connected.value = false
  }
}

async function saveCorners() {
  if (!connected.value) return
  try {
    await fetch(`${apiBase}/api/corners`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ corners: config.corners })
    })
  } catch (e) {
    console.error('保存校准点失败', e)
  }
}

async function saveZones() {
  if (!connected.value) return
  try {
    await fetch(`${apiBase}/api/zones`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zones: config.zones, zone_id_counter: config.zone_id_counter })
    })
  } catch (e) {
    console.error('保存区域失败', e)
  }
}

async function updateSettings() {
  if (!connected.value) return
  try {
    await fetch(`${apiBase}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ admin_bg: config.admin_bg, projection_bg: config.projection_bg })
    })
  } catch (e) {
    console.error('保存设置失败', e)
  }
}

async function saveAllConfig() {
  if (!connected.value) {
    showToast('后端未连接')
    return
  }
  try {
    const res = await fetch(`${apiBase}/api/save_all`, { method: 'POST' })
    const data = await res.json()
    showToast(data.msg || '保存成功')
  } catch (e) {
    showToast('保存失败')
  }
}

async function loadAllConfig() {
  if (!connected.value) {
    showToast('后端未连接')
    return
  }
  try {
    const res = await fetch(`${apiBase}/api/load_all`, { method: 'POST' })
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

async function updateStatus() {
  if (!connected.value) {
    // 尝试重新连接
    const ok = await checkConnection()
    if (!ok) return
  }
  try {
    const res = await fetch(`${apiBase}/api/status`)
    if (!res.ok) throw new Error('请求失败')
    const data = await res.json()
    Object.assign(status, data)
  } catch (e) {
    connected.value = false
  }
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
  // 绘制原始画面上的校准框
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
      ctx.arc(x, y, 10, 0, Math.PI * 2)
      ctx.fillStyle = '#0066cc'
      ctx.fill()
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 10px Arial'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(i + 1, x, y)
    })
  }
  
  // 绘制校正后画面上的区域
  if (correctedCanvas.value) {
    const ctx = correctedCanvas.value.getContext('2d')
    const scaleX = correctedCanvas.value.width / 640
    const scaleY = correctedCanvas.value.height / 360
    ctx.clearRect(0, 0, correctedCanvas.value.width, correctedCanvas.value.height)
    
    config.zones.forEach(zone => {
      drawZone(ctx, zone, scaleX, scaleY, editingZone.value === zone.id)
    })
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
      ctx.beginPath()
      ctx.arc(cx + r, cy, 10, 0, Math.PI * 2)
      ctx.fillStyle = '#fff'
      ctx.fill()
      ctx.stroke()
    }
  } else {
    const points = zone.points.map(p => [p[0] * scaleX, p[1] * scaleY])
    ctx.beginPath()
    points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]))
    ctx.closePath()
    ctx.stroke()
    if (isEditing) {
      ctx.fillStyle = zone.color + '30'
      ctx.fill()
      if (zone.type === 'rect') {
        const centerX = (points[0][0] + points[2][0]) / 2
        const centerY = (points[0][1] + points[2][1]) / 2
        ctx.beginPath()
        ctx.arc(centerX, centerY, 15, 0, Math.PI * 2)
        ctx.fillStyle = '#fff'
        ctx.fill()
        ctx.strokeStyle = zone.color
        ctx.lineWidth = 3
        ctx.stroke()
      }
      ctx.strokeStyle = zone.color
      ctx.lineWidth = 2
      points.forEach(p => {
        ctx.beginPath()
        ctx.arc(p[0], p[1], 10, 0, Math.PI * 2)
        ctx.fillStyle = '#fff'
        ctx.fill()
        ctx.stroke()
      })
    }
  }
}

// 原始画面鼠标事件 - 校准点拖动
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

// 校正后画面鼠标事件 - 区域编辑
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
    if (dCenter < 15) dragMode.value = 'move'
    else if (Math.abs(Math.hypot(pos.x - zone.center[0], pos.y - zone.center[1]) - zone.radius) < 15) dragMode.value = 'resize'
    else mouseDown.value = false
  } else if (zone.type === 'rect') {
    const centerX = (zone.points[0][0] + zone.points[2][0]) / 2
    const centerY = (zone.points[0][1] + zone.points[2][1]) / 2
    if (Math.hypot(pos.x - centerX, pos.y - centerY) < 20) dragMode.value = 'move'
    else {
      let found = -1
      for (let i = 0; i < 4; i++) {
        if (Math.hypot(zone.points[i][0] - pos.x, zone.points[i][1] - pos.y) < 15) {
          found = i
          break
        }
      }
      if (found >= 0) dragMode.value = 'vertex-' + found
      else mouseDown.value = false
    }
  } else {
    let found = -1
    for (let i = 0; i < zone.points.length; i++) {
      if (Math.hypot(zone.points[i][0] - pos.x, zone.points[i][1] - pos.y) < 15) {
        found = i
        break
      }
    }
    if (found >= 0) dragMode.value = 'point-' + found
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
      zone.center[0] = Math.max(30, Math.min(610, dragStartData.value.center[0] + dx))
      zone.center[1] = Math.max(30, Math.min(330, dragStartData.value.center[1] + dy))
    } else if (dragMode.value === 'resize') {
      zone.radius = Math.max(20, Math.min(150, Math.hypot(pos.x - zone.center[0], pos.y - zone.center[1])))
    }
  } else if (zone.type === 'rect') {
    if (dragMode.value === 'move') {
      const w = dragStartData.value.points[2][0] - dragStartData.value.points[0][0]
      const h = dragStartData.value.points[2][1] - dragStartData.value.points[0][1]
      let newX = Math.max(10, Math.min(630 - w, dragStartData.value.points[0][0] + dx))
      let newY = Math.max(10, Math.min(350 - h, dragStartData.value.points[0][1] + dy))
      zone.points = [[newX, newY], [newX + w, newY], [newX + w, newY + h], [newX, newY + h]]
    } else if (dragMode.value.startsWith('vertex-')) {
      const idx = parseInt(dragMode.value.split('-')[1])
      let newX = Math.max(10, Math.min(630, pos.x))
      let newY = Math.max(10, Math.min(350, pos.y))
      if (idx === 0) { zone.points[0] = [newX, newY]; zone.points[1][1] = newY; zone.points[3][0] = newX }
      else if (idx === 1) { zone.points[1] = [newX, newY]; zone.points[0][1] = newY; zone.points[2][0] = newX }
      else if (idx === 2) { zone.points[2] = [newX, newY]; zone.points[1][0] = newX; zone.points[3][1] = newY }
      else if (idx === 3) { zone.points[3] = [newX, newY]; zone.points[0][0] = newX; zone.points[2][1] = newY }
    }
  } else {
    if (dragMode.value.startsWith('point-')) {
      const idx = parseInt(dragMode.value.split('-')[1])
      zone.points[idx] = [Math.max(10, Math.min(630, pos.x)), Math.max(10, Math.min(350, pos.y))]
    }
  }
}

function handleCorrectedMouseUp() {
  if (mouseDown.value) saveZones()
  mouseDown.value = false
  dragMode.value = null
}

// 区域操作
function addZone(type) {
  if (config.zones.length >= 12) { alert('最多12个区域'); return }
  const id = config.zone_id_counter++
  const color = COLORS[(id - 1) % COLORS.length]
  const baseX = 100 + Math.random() * 400
  const baseY = 100 + Math.random() * 150
  let newZone
  if (type === 'rect') newZone = { id, name: String(id), type: 'rect', points: [[baseX, baseY], [baseX+100, baseY], [baseX+100, baseY+100], [baseX, baseY+100]], color }
  else if (type === 'triangle') newZone = { id, name: String(id), type: 'triangle', points: [[baseX+50, baseY], [baseX+100, baseY+100], [baseX, baseY+100]], color }
  else if (type === 'circle') newZone = { id, name: String(id), type: 'circle', center: [baseX+50, baseY+50], radius: 50, color }
  else newZone = { id, name: String(id), type: 'quad', points: [[baseX, baseY], [baseX+120, baseY+20], [baseX+100, baseY+100], [baseX+20, baseY+80]], color }
  config.zones.push(newZone)
  saveZones()
}

function copyZone(id) {
  if (config.zones.length >= 12) { alert('最多12个区域'); return }
  const zone = config.zones.find(z => z.id === id)
  if (!zone) return
  const newId = config.zone_id_counter++
  const newZone = JSON.parse(JSON.stringify(zone))
  newZone.id = newId
  newZone.name = String(newId)
  newZone.color = COLORS[(newId - 1) % COLORS.length]
  if (newZone.type === 'circle') {
    newZone.center[0] = Math.min(600, newZone.center[0] + 30)
    newZone.center[1] = Math.min(320, newZone.center[1] + 30)
  } else {
    newZone.points = newZone.points.map(p => [Math.min(620, p[0] + 30), Math.min(340, p[1] + 30)])
  }
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

function handleDragStart(e, id) {
  draggedZoneId.value = id
  e.dataTransfer.effectAllowed = 'move'
}

function handleDrop(e, targetId) {
  e.preventDefault()
  if (draggedZoneId.value === null || draggedZoneId.value === targetId) return
  const draggedIndex = config.zones.findIndex(z => z.id === draggedZoneId.value)
  const targetIndex = config.zones.findIndex(z => z.id === targetId)
  if (draggedIndex !== -1 && targetIndex !== -1) {
    const [removed] = config.zones.splice(draggedIndex, 1)
    config.zones.splice(targetIndex, 0, removed)
    saveZones()
  }
}

function handleDragEnd() {
  draggedZoneId.value = null
}

onMounted(async () => {
  // 先检查连接
  await checkConnection()
  
  if (connected.value) {
    await loadConfig()
  }
  
  resize()
  requestAnimationFrame(draw)
  setInterval(updateStatus, 500)  // 降低频率
  window.addEventListener('resize', resize)
})
</script>

<style scoped>
.admin-page { padding: 10px; font-family: sans-serif; min-height: 100vh; }
h1 { font-size: 16px; margin-bottom: 8px; }

.connection-error {
  background: #fff3cd;
  border: 1px solid #ffc107;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 15px;
  color: #856404;
  text-align: center;
}

.connection-error code {
  background: #f8f9fa;
  padding: 5px 10px;
  border-radius: 4px;
  font-family: monospace;
}

.video-container { width: 640px; max-width: 100%; position: relative; background: #000; margin-bottom: 10px; }
.video-container img { display: block; width: 100%; }
.video-container canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; }

.corrected-container { width: 640px; max-width: 100%; position: relative; background: #f5f5f5; border: 2px solid #33B555; margin-bottom: 10px; }
.corrected-container img { display: block; width: 100%; }
.corrected-container canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: move; }

.hint { font-size: 11px; color: #666; margin: 5px 0; }

.status-bar { width: 640px; max-width: 100%; background: #f0f0f0; padding: 6px 10px; border-radius: 4px; font-size: 12px; margin-bottom: 10px; display: flex; gap: 15px; }
.detected { color: #33B555; font-weight: bold; }
.not-detected { color: #ff6b6b; }

.control-panel { width: 640px; max-width: 100%; background: #fafafa; border: 1px solid #ddd; border-radius: 6px; padding: 10px; }
.section-title { font-size: 12px; font-weight: bold; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #ddd; }

.settings-row { display: flex; gap: 20px; margin-bottom: 10px; padding: 8px; background: #fff; border-radius: 4px; }
.setting-item { display: flex; align-items: center; gap: 8px; }
.setting-item label { font-size: 12px; }
.setting-item input[type="color"] { width: 40px; height: 30px; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; }

.save-load-row { display: flex; gap: 10px; margin-bottom: 10px; }
.save-btn { flex: 1; padding: 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: bold; color: #fff; }
.btn-save-all { background: #4CAF50; }
.btn-load-all { background: #2196F3; }

.add-buttons { display: flex; gap: 5px; margin-bottom: 10px; }
.add-btn { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 12px; }
.add-btn:hover { background: #e8f5e9; }

.zone-list { max-height: 300px; overflow-y: auto; }
.zone-item { background: #fff; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 5px; }
.zone-item.editing { border-color: #FF7222; }
.zone-header { padding: 6px 8px; display: flex; align-items: center; gap: 6px; cursor: grab; }
.drag-handle { color: #999; cursor: grab; }
.zone-dot { width: 12px; height: 12px; border-radius: 50%; }
.zone-name-input { border: none; background: transparent; font-size: 12px; font-weight: bold; width: 50px; }
.zone-name-input:focus { outline: none; background: #fffde7; }
.zone-type { font-size: 10px; color: #888; }
.zone-actions { margin-left: auto; display: flex; gap: 4px; }
.zone-btn { padding: 3px 8px; border: none; border-radius: 3px; cursor: pointer; font-size: 10px; color: #fff; }
.btn-edit { background: #FF7222; }
.btn-confirm { background: #33B555; }
.btn-delete { background: #f44336; }
.btn-copy { background: #2196F3; }

.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 20px; border-radius: 4px; z-index: 1000; }
</style>
