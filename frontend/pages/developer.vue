<template>
  <div class="dev-page">
    <div class="top-nav">
      <h2>🛠 视觉引擎控制台</h2>
      <div class="nav-buttons">
        <button @click="toggleCalibrationMode" :class="{ active: calibrationMode }">
          {{ calibrationMode ? '🎯 校准模式' : '📷 监控模式' }}
        </button>
        <button v-if="calibrationMode" @click="saveCalibration" class="save-btn">💾 保存</button>
        <button v-if="calibrationMode" @click="resetCalibration" class="reset-btn">🔄 重置</button>
        <button @click="$router.push('/')">退出后台</button>
      </div>
    </div>

    <div class="video-grid">
      <div class="monitor-card">
        <h3>平板端摄像头 (生理/情绪)</h3>
        <img v-if="tabletImg" :src="'data:image/jpeg;base64,' + tabletImg" />
        <div v-else class="placeholder">等待平板视频流...</div>
      </div>

      <div class="monitor-card">
        <h3>外接摄像头 (投影区域识别)</h3>
        <div class="video-wrapper" ref="videoWrapper">
          <canvas 
            v-if="screenImg && calibrationMode" 
            ref="calibCanvas"
            @mousedown="handleMouseDown"
            @mousemove="handleMouseMove"
            @mouseup="handleMouseUp"
            @mouseleave="handleMouseUp"
          ></canvas>
          <img v-else-if="screenImg" :src="'data:image/jpeg;base64,' + screenImg" />
          <div v-else class="placeholder">等待投影视频流...</div>
        </div>
      </div>
    </div>
    
    <div v-if="calibrationMode" class="calibration-panel">
      <div class="panel-section">
        <h3>📐 投影区域校准 (4个顶点)</h3>
        <p class="hint">点击画布上的4个角点，或拖拽已有的点</p>
        <div class="points-list">
          <div 
            v-for="(point, idx) in projectionPoints" 
            :key="'proj-' + idx"
            class="point-item"
            :class="{ active: selectedType === 'projection' && selectedIndex === idx }"
            @click="selectPoint('projection', idx)"
          >
            <span class="point-label" :style="{ color: projColors[idx] }">投影点 {{ idx + 1 }}</span>
            <span class="point-coords">{{ point ? `${point[0]}, ${point[1]}` : '未设置' }}</span>
          </div>
        </div>
      </div>
      
      <div class="panel-section holes-section">
        <h3>🎮 地鼠洞区域</h3>
        <div class="hole-tabs">
          <div 
            v-for="(hole, idx) in holes" 
            :key="'hole-tab-' + idx"
            class="hole-tab"
            :class="{ active: selectedHole === idx }"
            @click="selectedHole = idx"
          >
            洞 {{ idx + 1 }}
          </div>
        </div>
        
        <div v-if="selectedHole !== null" class="hole-detail">
          <p class="hint">拖拽画布上的4个顶点调整洞 {{ selectedHole + 1 }}</p>
          <div class="hole-points">
            <div 
              v-for="(point, idx) in holePoints[selectedHole]" 
              :key="'hole-' + selectedHole + '-' + idx"
              class="point-item small"
              :class="{ active: selectedType === 'hole' && selectedIndex === idx }"
              @click="selectPoint('hole', idx)"
            >
              <span class="point-label" :style="{ color: holeColors[selectedHole] }">点 {{ idx + 1 }}</span>
              <span class="point-coords">{{ point ? `${point[0].toFixed(2)}, ${point[1].toFixed(2)}` : '未设置' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { io } from 'socket.io-client'

const tabletImg = ref('')
const screenImg = ref('')
const calibrationMode = ref(false)
const projectionPoints = ref([null, null, null, null])

const holes = ref([
  {"id": 0, "norm_rect": [0.08, 0.28, 0.45, 0.85]},
  {"id": 1, "norm_rect": [0.36, 0.64, 0.45, 0.85]},
  {"id": 2, "norm_rect": [0.72, 0.92, 0.45, 0.85]}
])

const holePoints = ref([
  [null, null, null, null],
  [null, null, null, null],
  [null, null, null, null]
])

const selectedType = ref(null)
const selectedIndex = ref(-1)
const selectedHole = ref(0)
const isDragging = ref(false)
const calibCanvas = ref(null)

let socket = null
const projColors = ['#FF7222', '#33B555', '#2AAADD', '#FB4422']
const holeColors = ['#FF7222', '#33B555', '#2AAADD']

const toggleCalibrationMode = () => {
  calibrationMode.value = !calibrationMode.value
  if (calibrationMode.value) {
    initHolePoints()
    nextTick(() => {
      drawCalibrationCanvas()
    })
  }
}

const initHolePoints = () => {
  holes.value.forEach((hole, hIdx) => {
    const [x1, x2, y1, y2] = hole.norm_rect
    holePoints.value[hIdx] = [
      [x1, y1],
      [x2, y1],
      [x2, y2],
      [x1, y2]
    ]
  })
}

const rectToPoints = (rect) => {
  const [x1, x2, y1, y2] = rect
  return [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2]
  ]
}

const pointsToRect = (points) => {
  const xs = points.map(p => p[0])
  const ys = points.map(p => p[1])
  return [
    Math.min(...xs),
    Math.max(...xs),
    Math.min(...ys),
    Math.max(...ys)
  ]
}

const selectPoint = (type, idx) => {
  selectedType.value = type
  selectedIndex.value = idx
}

const handleMouseDown = (e) => {
  const rect = calibCanvas.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  
  const scaleX = calibCanvas.value.width / rect.width
  const scaleY = calibCanvas.value.height / rect.height
  const canvasX = Math.round(x * scaleX)
  const canvasY = Math.round(y * scaleY)
  
  // 先检查投影点
  for (let i = 0; i < 4; i++) {
    if (projectionPoints.value[i]) {
      const px = projectionPoints.value[i][0]
      const py = projectionPoints.value[i][1]
      const dist = Math.sqrt((canvasX - px) ** 2 + (canvasY - py) ** 2)
      if (dist < 25) {
        selectedType.value = 'projection'
        selectedIndex.value = i
        isDragging.value = true
        return
      }
    }
  }
  
  // 再检查地鼠洞的点（检查所有洞）
  for (let hIdx = 0; hIdx < 3; hIdx++) {
    const w = calibCanvas.value.width
    const h = calibCanvas.value.height
    
    for (let i = 0; i < 4; i++) {
      if (holePoints.value[hIdx][i]) {
        const px = holePoints.value[hIdx][i][0] * w
        const py = holePoints.value[hIdx][i][1] * h
        const dist = Math.sqrt((canvasX - px) ** 2 + (canvasY - py) ** 2)
        if (dist < 25) {
          selectedType.value = 'hole'
          selectedHole.value = hIdx
          selectedIndex.value = i
          isDragging.value = true
          return
        }
      }
    }
  }
  
  // 如果没有选中任何点，检查是否需要设置投影点
  if (selectedType.value === 'projection') {
    const emptyIdx = projectionPoints.value.findIndex(p => p === null)
    if (emptyIdx !== -1) {
      projectionPoints.value[emptyIdx] = [canvasX, canvasY]
      selectedIndex.value = emptyIdx
      updateProjection()
    }
  }
}

const handleMouseMove = (e) => {
  if (!isDragging.value || selectedIndex.value === -1) return
  
  const rect = calibCanvas.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  
  const scaleX = calibCanvas.value.width / rect.width
  const scaleY = calibCanvas.value.height / rect.height
  const canvasX = Math.round(x * scaleX)
  const canvasY = Math.round(y * scaleY)
  
  if (selectedType.value === 'projection') {
    projectionPoints.value[selectedIndex.value] = [canvasX, canvasY]
    updateProjection()
  } else if (selectedType.value === 'hole' && selectedHole.value !== null) {
    const w = calibCanvas.value.width
    const h = calibCanvas.value.height
    const normX = Math.max(0, Math.min(1, canvasX / w))
    const normY = Math.max(0, Math.min(1, canvasY / h))
    holePoints.value[selectedHole.value][selectedIndex.value] = [normX, normY]
    updateHole(selectedHole.value)
  }
  
  drawCalibrationCanvas()
}

const handleMouseUp = () => {
  isDragging.value = false
  drawCalibrationCanvas()
}

const updateProjection = () => {
  const validPoints = projectionPoints.value.filter(p => p !== null)
  if (validPoints.length === 4) {
    for (let i = 0; i < 4; i++) {
      socket.emit('update_calibration_point', { 
        index: i, 
        x: projectionPoints.value[i][0], 
        y: projectionPoints.value[i][1] 
      })
    }
  }
}

const updateHole = (idx) => {
  const rect = pointsToRect(holePoints.value[idx])
  holes.value[idx].norm_rect = rect
  socket.emit('update_hole', {
    index: idx,
    x1: rect[0],
    x2: rect[1],
    y1: rect[2],
    y2: rect[3]
  })
}

const saveCalibration = () => {
  socket.emit('save_calibration')
  alert('✅ 校准配置已保存！')
}

const resetCalibration = () => {
  if (confirm('确定要重置校准吗？')) {
    socket.emit('reset_calibration')
    projectionPoints.value = [null, null, null, null]
    holes.value = [
      {"id": 0, "norm_rect": [0.08, 0.28, 0.45, 0.85]},
      {"id": 1, "norm_rect": [0.36, 0.64, 0.45, 0.85]},
      {"id": 2, "norm_rect": [0.72, 0.92, 0.45, 0.85]}
    ]
    initHolePoints()
    drawCalibrationCanvas()
  }
}

const drawCalibrationCanvas = () => {
  if (!calibCanvas.value || !screenImg.value) return
  
  const canvas = calibCanvas.value
  const ctx = canvas.getContext('2d')
  
  const img = new Image()
  img.onload = () => {
    canvas.width = img.width
    canvas.height = img.height
    ctx.drawImage(img, 0, 0)
    
    for (let i = 0; i < 4; i++) {
      if (projectionPoints.value[i]) {
        const [x, y] = projectionPoints.value[i]
        ctx.beginPath()
        ctx.arc(x, y, 18, 0, Math.PI * 2)
        ctx.fillStyle = projColors[i]
        ctx.fill()
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 3
        ctx.stroke()
        
        ctx.fillStyle = '#fff'
        ctx.font = 'bold 14px Arial'
        ctx.textAlign = 'center'
        ctx.fillText(i + 1, x, y + 5)
      }
    }
    
    const validProjPoints = projectionPoints.value.filter(p => p !== null)
    if (validProjPoints.length >= 2) {
      ctx.beginPath()
      ctx.strokeStyle = '#FF7222'
      ctx.lineWidth = 3
      ctx.setLineDash([10, 5])
      for (let i = 0; i < validProjPoints.length; i++) {
        const [x, y] = validProjPoints[i]
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      if (validProjPoints.length === 4) ctx.closePath()
      ctx.stroke()
      ctx.setLineDash([])
    }
    
    for (let hIdx = 0; hIdx < 3; hIdx++) {
      const color = holeColors[hIdx]
      const points = holePoints.value[hIdx]
      
      if (points.every(p => p !== null)) {
        ctx.beginPath()
        ctx.strokeStyle = color
        ctx.lineWidth = hIdx === selectedHole.value ? 5 : 3
        for (let i = 0; i < 4; i++) {
          const x = points[i][0] * canvas.width
          const y = points[i][1] * canvas.height
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.closePath()
        ctx.stroke()
        
        for (let i = 0; i < 4; i++) {
          const x = points[i][0] * canvas.width
          const y = points[i][1] * canvas.height
          ctx.beginPath()
          ctx.arc(x, y, 12, 0, Math.PI * 2)
          ctx.fillStyle = color
          ctx.fill()
          ctx.strokeStyle = '#fff'
          ctx.lineWidth = 2
          ctx.stroke()
          
          if (hIdx === selectedHole.value) {
            ctx.fillStyle = '#fff'
            ctx.font = 'bold 10px Arial'
            ctx.textAlign = 'center'
            ctx.fillText(i + 1, x, y + 4)
          }
        }
        
        const cx = (points[0][0] + points[1][0]) / 2 * canvas.width
        const cy = (points[0][1] + points[2][1]) / 2 * canvas.height
        ctx.fillStyle = color
        ctx.font = 'bold 16px Arial'
        ctx.textAlign = 'center'
        ctx.fillText(`Hole ${hIdx + 1}`, cx, cy)
      }
    }
  }
  img.src = 'data:image/jpeg;base64,' + screenImg.value
}

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)

  socket.on('tablet_stream', (data) => {
    tabletImg.value = data.image
  })

  socket.on('screen_stream', (data) => {
    screenImg.value = data.image
    if (data.calibration) {
      if (data.calibration.points && data.calibration.points.length === 4) {
        projectionPoints.value = data.calibration.points
      }
      if (data.calibration.holes) {
        holes.value = data.calibration.holes
        if (calibrationMode.value) {
          initHolePoints()
        }
      }
    }
    if (calibrationMode.value) {
      nextTick(() => {
        drawCalibrationCanvas()
      })
    }
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})
</script>

<style scoped>
.dev-page { 
  background: #fff; 
  height: 100vh; 
  width: 100vw; 
  padding: 30px; 
  color: #000; 
  overflow-y: auto; 
}
.top-nav { 
  display: flex; 
  justify-content: space-between; 
  align-items: center; 
  margin-bottom: 25px; 
  flex-wrap: wrap;
  gap: 15px;
}
.nav-buttons {
  display: flex;
  gap: 15px;
  align-items: center;
}
.nav-buttons button {
  padding: 12px 24px;
  border-radius: 12px;
  border: none;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s;
}
.nav-buttons button.active {
  background: #FF7222;
  color: #fff;
}
.save-btn {
  background: #33B555 !important;
  color: #fff !important;
}
.reset-btn {
  background: #FB4422 !important;
  color: #fff !important;
}
.video-grid { 
  display: grid; 
  grid-template-columns: 1fr 1fr; 
  gap: 25px; 
}
.monitor-card { 
  background: #f4f4f4; 
  padding: 20px; 
  border-radius: 16px; 
}
.monitor-card h3 {
  margin-bottom: 15px;
  font-size: 20px;
}
.monitor-card img, .monitor-card canvas { 
  width: 100%; 
  border-radius: 12px; 
  background: #000; 
  min-height: 350px; 
}
.video-wrapper {
  position: relative;
}
.video-wrapper canvas {
  position: absolute;
  top: 0;
  left: 0;
  cursor: crosshair;
}
.placeholder { 
  height: 350px; 
  display: flex; 
  align-items: center; 
  justify-content: center; 
  color: #999; 
  font-size: 18px;
}

.calibration-panel {
  margin-top: 30px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 25px;
}
.panel-section {
  background: #F8F9FA;
  padding: 25px;
  border-radius: 16px;
}
.panel-section h3 {
  margin-bottom: 10px;
  font-size: 22px;
  color: #333;
}
.hint {
  color: #888;
  margin-bottom: 20px;
  font-size: 15px;
}
.points-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.point-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  background: #fff;
  border-radius: 12px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s;
}
.point-item:hover {
  border-color: #FF7222;
}
.point-item.active {
  border-color: #FF7222;
  background: #FFF9F6;
}
.point-item.small {
  padding: 10px 15px;
}
.point-label {
  font-weight: bold;
  font-size: 16px;
}
.point-coords {
  color: #666;
  font-family: monospace;
  font-size: 13px;
}

.holes-section {
  display: flex;
  flex-direction: column;
}
.hole-tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.hole-tab {
  padding: 12px 24px;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  font-weight: bold;
  border: 2px solid #eee;
  transition: all 0.2s;
}
.hole-tab:hover {
  border-color: #FF7222;
}
.hole-tab.active {
  background: #FF7222;
  color: #fff;
  border-color: #FF7222;
}
.hole-detail {
  flex: 1;
}
.hole-points {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
</style>
