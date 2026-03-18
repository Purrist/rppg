<template>
  <div class="dev-page">
    <!-- 头部 -->
    <header class="dev-header">
      <h1>🛠 开发者后台</h1>
      <div class="conn-badge" :class="connected ? 'ok' : 'err'">
        {{ connected ? '✅ 已连接' : '❌ 未连接' }}
      </div>
    </header>
    
    <!-- ⭐ 核心状态卡片 -->
    <section class="core-status">
      <!-- 有人/无人 -->
      <div class="person-card" :class="personDetected ? 'detected' : 'not-detected'">
        <div class="person-icon">{{ personDetected ? '👤' : '🚫' }}</div>
        <div class="person-text">{{ personDetected ? '有人' : '无人' }}</div>
      </div>
      
      <!-- 10个高价值数据卡片 -->
      <div class="data-cards">
        <div class="data-card">
          <span class="d-label">人数</span>
          <span class="d-value">{{ personDetected ? userState.face_count : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">心率</span>
          <span class="d-value">{{ personDetected && userState.heart_rate ? userState.heart_rate + ' BPM' : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">眨眼</span>
          <span class="d-value">{{ personDetected ? userState.blink_count + '次/30s' : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">眼睛</span>
          <span class="d-value" :class="userState.eye_state">{{ personDetected ? eyeStateText[userState.eye_state] : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">头部</span>
          <span class="d-value">{{ personDetected ? headDirText[userState.head_direction] : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">微笑</span>
          <span class="d-value" :class="userState.is_smiling ? 'smile' : ''">{{ personDetected ? (userState.is_smiling ? '😊 是' : '😐 否') : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">亮度</span>
          <span class="d-value" :class="'light-' + userState.light_level">{{ lightText[userState.light_level] }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">姿态</span>
          <span class="d-value">{{ personDetected ? postureText[userState.posture] : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">活动</span>
          <span class="d-value">{{ personDetected ? Math.round(userState.activity_level * 100) + '%' : '--' }}</span>
        </div>
        <div class="data-card">
          <span class="d-label">注意力</span>
          <span class="d-value">{{ personDetected ? Math.round(userState.attention_score * 100) + '%' : '--' }}</span>
        </div>
      </div>
    </section>
    
    <!-- 状态卡片 -->
    <section class="status-row">
      <div class="stat-card">
        <span class="label">游戏</span>
        <span class="val" :class="'s-' + gameState.status">{{ gameStateText }}</span>
      </div>
      <div class="stat-card">
        <span class="label">得分</span>
        <span class="val">{{ gameState.score }}</span>
      </div>
      <div class="stat-card">
        <span class="label">时间</span>
        <span class="val">{{ gameState.timer }}s</span>
      </div>
      <div class="stat-card">
        <span class="label">脚部</span>
        <span class="val" :class="status.feet_detected ? 'ok' : 'err'">
          {{ status.feet_detected ? '✓' : '✗' }}
        </span>
      </div>
    </section>
    
    <!-- 摄像头 -->
    <section class="cam-row">
      <!-- 投影摄像头 -->
      <div class="cam-box">
        <div class="cam-head">
          <span>投影摄像头</span>
          <span class="hint">拖动四角校准</span>
        </div>
        <div class="cam-view">
          <img :src="videoUrl" @load="resize" @error="() => {}">
          <canvas ref="rawCanvas" 
                  @mousedown="onMouseDown" 
                  @mousemove="onMouseMove" 
                  @mouseup="onMouseUp" 
                  @mouseleave="onMouseUp"></canvas>
        </div>
      </div>
      
      <!-- 平板摄像头 -->
      <div class="cam-box">
        <div class="cam-head">
          <span>平板摄像头</span>
          <span class="hint">感知检测</span>
        </div>
        <div class="cam-view tablet">
          <img :src="tabletVideoUrl" @error="() => {}">
        </div>
      </div>
    </section>
    
    <!-- 校正后画面 -->
    <section class="corr-section">
      <h3>校正后画面</h3>
      <div class="corr-view">
        <img :src="correctedUrl" @load="resize" @error="() => {}">
        <canvas ref="correctedCanvas"></canvas>
      </div>
    </section>
    
    <!-- 按钮 -->
    <section class="btn-row">
      <button v-if="!isEditing" class="btn edit" @click="startEdit">✏️ 编辑校准区域</button>
      <button v-else class="btn save" @click="saveAndExitEdit">💾 保存校准区域</button>
      <button class="btn load" @click="loadConfig">📂 加载配置</button>
      <button class="btn reset" @click="resetCorners">🔄 重置校准</button>
    </section>
    
    <!-- Toast -->
    <div v-if="toast.show" class="toast">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'

// ==================== 配置 ====================
const getHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const PORT = 5000
const baseUrl = `http://${getHost()}:${PORT}`
const videoUrl = `${baseUrl}/video_feed`
const correctedUrl = `${baseUrl}/corrected_feed`
const tabletVideoUrl = `${baseUrl}/tablet_video_feed`

// ==================== 文本映射 ====================
const eyeStateText = { 'open': '睁眼', 'closed': '闭眼', 'partial': '半睁', 'unknown': '未知' }
const headDirText = { 'front': '正面', 'left': '左转', 'right': '右转', 'up': '抬头', 'down': '低头', 'far': '远处', 'unknown': '未知' }
const lightText = { 'dark': '暗', 'normal': '正常', 'bright': '亮' }
const postureText = { 'standing': '站立', 'sitting': '坐着', 'unknown': '未知' }

// ==================== 状态 ====================
const connected = ref(false)
const rawCanvas = ref(null)
const correctedCanvas = ref(null)

// 编辑状态
const isEditing = ref(false)
const savedCorners = ref(null)
const corners = ref([[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]])

const status = reactive({
  feet_detected: false,
  feet_x: 320,
  feet_y: 180
})

// ⭐ 用户状态（简化版 - 10个高价值数据）
const userState = reactive({
  person_detected: false,
  face_count: 0,
  heart_rate: null,
  blink_count: 0,
  eye_state: 'unknown',
  head_direction: 'unknown',
  is_smiling: false,
  light_level: 'normal',
  posture: 'unknown',
  activity_level: 0,
  attention_score: 0,
})

// 计算属性
const personDetected = computed(() => userState.person_detected)

const gameState = reactive({
  status: 'IDLE',
  score: 0,
  timer: 60
})

const gameStateText = computed(() => {
  const t = { 'IDLE': '待机', 'READY': '等待', 'PLAYING': '进行中', 'PAUSED': '暂停', 'SETTLING': '结算' }
  return t[gameState.status] || '未知'
})

const toast = reactive({ show: false, msg: '' })
const dragging = ref(-1)
const mouseDown = ref(false)

let interval = null

// ==================== 工具 ====================
function showToast(msg) {
  toast.msg = msg
  toast.show = true
  setTimeout(() => toast.show = false, 2000)
}

// ==================== 编辑模式 ====================
function startEdit() {
  isEditing.value = true
  savedCorners.value = JSON.parse(JSON.stringify(corners.value))
  showToast('开始编辑校准区域')
}

async function saveAndExitEdit() {
  await saveCorners()
  await saveConfig()
  isEditing.value = false
  savedCorners.value = null
  showToast('校准区域已保存')
}

// ==================== API ====================
async function checkConn() {
  try {
    const c = new AbortController()
    const t = setTimeout(() => c.abort(), 3000)
    const r = await fetch(`${baseUrl}/api/config`, { signal: c.signal })
    clearTimeout(t)
    connected.value = r.ok
    return r.ok
  } catch {
    connected.value = false
    return false
  }
}

async function loadCorners() {
  try {
    const r = await fetch(`${baseUrl}/api/config`)
    if (!r.ok) throw new Error()
    const d = await r.json()
    if (d.corners) corners.value = d.corners
    connected.value = true
    return true
  } catch {
    connected.value = false
    return false
  }
}

async function saveCorners() {
  if (!connected.value) return
  try {
    await fetch(`${baseUrl}/api/corners`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ corners: corners.value })
    })
  } catch {}
}

async function saveConfig() {
  if (!connected.value) { showToast('未连接'); return }
  try {
    const r = await fetch(`${baseUrl}/api/save_all`, { method: 'POST' })
    const d = await r.json()
    showToast(d.msg || '已保存')
  } catch {
    showToast('保存失败')
  }
}

async function loadConfig() {
  if (!connected.value) { showToast('未连接'); return }
  try {
    const r = await fetch(`${baseUrl}/api/load_all`, { method: 'POST' })
    const d = await r.json()
    if (d.ok) {
      await loadCorners()
      showToast('已加载')
    }
  } catch {
    showToast('加载失败')
  }
}

async function resetCorners() {
  corners.value = [[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]]
  await saveCorners()
  showToast('已重置')
}

// ==================== 状态更新 ====================
async function updateStatus() {
  if (!connected.value) {
    await checkConn()
    if (!connected.value) return
  }
  
  try {
    // 投影状态
    const r = await fetch(`${baseUrl}/api/status`)
    if (r.ok) {
      const d = await r.json()
      if (Number.isFinite(d.feet_x) && Number.isFinite(d.feet_y)) {
        status.feet_x = Math.max(0, Math.min(640, d.feet_x))
        status.feet_y = Math.max(0, Math.min(360, d.feet_y))
      }
      status.feet_detected = d.feet_detected
    }
    
    // 游戏状态
    const gr = await fetch(`${baseUrl}/api/system/state`)
    if (gr.ok) {
      const gd = await gr.json()
      if (gd.state?.game) {
        gameState.status = gd.state.game.status || 'IDLE'
        gameState.score = gd.state.game.score || 0
        gameState.timer = gd.state.game.timer || 60
      }
    }
    
    // ⭐ 用户状态（感知信息）
    const ur = await fetch(`${baseUrl}/api/user_state`)
    if (ur.ok) {
      const ud = await ur.json()
      // 直接赋值
      for (const key in ud) {
        if (key in userState) {
          userState[key] = ud[key]
        }
      }
    }
  } catch {
    connected.value = false
  }
}

// ==================== Canvas ====================
function resize() {
  const raw = rawCanvas.value
  const cor = correctedCanvas.value
  const rawImg = raw?.parentElement?.querySelector('img')
  const corImg = cor?.parentElement?.querySelector('img')
  
  if (raw && rawImg) {
    raw.width = rawImg.offsetWidth
    raw.height = rawImg.offsetHeight
  }
  if (cor && corImg) {
    cor.width = corImg.offsetWidth
    cor.height = corImg.offsetHeight
  }
}

function draw() {
  // 原始画面 - 绘制四角
  if (rawCanvas.value) {
    const ctx = rawCanvas.value.getContext('2d')
    const w = rawCanvas.value.width
    const h = rawCanvas.value.height
    
    if (w <= 0 || h <= 0) {
      requestAnimationFrame(draw)
      return
    }
    
    ctx.clearRect(0, 0, w, h)
    
    ctx.strokeStyle = isEditing.value ? '#FF7222' : '#0066cc'
    ctx.lineWidth = isEditing.value ? 4 : 3
    ctx.beginPath()
    corners.value.forEach((p, i) => {
      const x = p[0] * w, y = p[1] * h
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.closePath()
    ctx.stroke()
    ctx.fillStyle = isEditing.value ? 'rgba(255, 114, 34, 0.1)' : 'rgba(0, 102, 204, 0.1)'
    ctx.fill()
    
    corners.value.forEach((p, i) => {
      const x = p[0] * w, y = p[1] * h
      ctx.beginPath()
      ctx.arc(x, y, isEditing.value ? 18 : 15, 0, Math.PI * 2)
      ctx.fillStyle = isEditing.value ? '#FF7222' : '#0066cc'
      ctx.fill()
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 14px Arial'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(i + 1, x, y)
    })
  }
  
  // 校正后画面 - 只绘制绿点
  if (correctedCanvas.value) {
    const ctx = correctedCanvas.value.getContext('2d')
    const sx = correctedCanvas.value.width / 640
    const sy = correctedCanvas.value.height / 360
    
    if (correctedCanvas.value.width <= 0 || correctedCanvas.value.height <= 0) {
      requestAnimationFrame(draw)
      return
    }
    
    ctx.clearRect(0, 0, correctedCanvas.value.width, correctedCanvas.value.height)
    
    if (status.feet_detected) {
      let fx = status.feet_x * sx
      let fy = status.feet_y * sy
      
      if (Number.isFinite(fx) && Number.isFinite(fy)) {
        fx = Math.max(0, Math.min(correctedCanvas.value.width, fx))
        fy = Math.max(0, Math.min(correctedCanvas.value.height, fy))
        
        ctx.beginPath()
        ctx.arc(fx, fy, 15, 0, Math.PI * 2)
        ctx.fillStyle = '#33B555'
        ctx.fill()
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 3
        ctx.stroke()
      }
    }
  }
  
  requestAnimationFrame(draw)
}

// ==================== 鼠标事件 ====================
function onMouseDown(e) {
  if (!isEditing.value) return
  
  const rect = rawCanvas.value.getBoundingClientRect()
  const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }
  for (let i = 0; i < corners.value.length; i++) {
    if (Math.hypot(corners.value[i][0] - pos.x, corners.value[i][1] - pos.y) < 0.05) {
      dragging.value = i
      mouseDown.value = true
      break
    }
  }
}

function onMouseMove(e) {
  if (!mouseDown.value || dragging.value < 0) return
  const rect = rawCanvas.value.getBoundingClientRect()
  const pos = { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }
  corners.value[dragging.value] = [
    Math.max(0.02, Math.min(0.98, pos.x)),
    Math.max(0.02, Math.min(0.98, pos.y))
  ]
}

function onMouseUp() {
  mouseDown.value = false
  dragging.value = -1
}

// ==================== 生命周期 ====================
onMounted(async () => {
  const ok = await checkConn()
  if (ok) {
    await fetch(`${baseUrl}/api/load_all`, { method: 'POST' })
    await loadCorners()
  }
  
  resize()
  requestAnimationFrame(draw)
  interval = setInterval(updateStatus, 500)  // 500ms更新一次
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  if (interval) clearInterval(interval)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.dev-page {
  min-height: 100vh;
  width: 100%;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
  padding: 20px;
  padding-bottom: 60px;
  box-sizing: border-box;
}

.dev-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}

.dev-header h1 {
  font-size: 24px;
  font-weight: 600;
}

.conn-badge {
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 14px;
}

.conn-badge.ok { background: rgba(51, 181, 85, 0.2); color: #33B555; }
.conn-badge.err { background: rgba(255, 68, 68, 0.2); color: #ff6b6b; }

/* ⭐ 核心状态 */
.core-status {
  display: flex;
  gap: 15px;
  margin-bottom: 25px;
  flex-wrap: wrap;
}

/* 有人/无人卡片 */
.person-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px 30px;
  border-radius: 16px;
  min-width: 120px;
  transition: all 0.3s;
}

.person-card.detected {
  background: linear-gradient(135deg, #33B555 0%, #228B22 100%);
  box-shadow: 0 4px 20px rgba(51, 181, 85, 0.3);
}

.person-card.not-detected {
  background: rgba(255,255,255,0.05);
  border: 2px dashed rgba(255,255,255,0.2);
}

.person-icon {
  font-size: 48px;
  margin-bottom: 8px;
}

.person-text {
  font-size: 20px;
  font-weight: 700;
}

/* 数据卡片容器 */
.data-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  flex: 1;
}

.data-card {
  background: rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 12px 16px;
  min-width: 90px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.d-label {
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
}

.d-value {
  font-size: 16px;
  font-weight: 600;
}

.d-value.open { color: #33B555; }
.d-value.closed { color: #ff6b6b; }
.d-value.smile { color: #FFD700; }
.d-value.light-dark { color: #666; }
.d-value.light-normal { color: #33B555; }
.d-value.light-bright { color: #FFD700; }

/* 状态卡片 */
.status-row {
  display: flex;
  gap: 15px;
  margin-bottom: 25px;
  flex-wrap: wrap;
}

.stat-card {
  background: rgba(255,255,255,0.05);
  padding: 15px 20px;
  border-radius: 12px;
  min-width: 100px;
  flex: 1;
}

.stat-card .label {
  display: block;
  font-size: 12px;
  color: #888;
  margin-bottom: 5px;
}

.stat-card .val {
  font-size: 20px;
  font-weight: 600;
}

.ok { color: #33B555; }
.err { color: #ff6b6b; }

.s-IDLE { color: #888; }
.s-READY { color: #FF7222; }
.s-PLAYING { color: #33B555; }
.s-PAUSED { color: #FFD111; }
.s-SETTLING { color: #9C27B0; }

/* 摄像头 */
.cam-row {
  display: flex;
  gap: 20px;
  margin-bottom: 25px;
  flex-wrap: wrap;
}

.cam-box {
  flex: 1;
  min-width: 300px;
  background: rgba(255,255,255,0.05);
  border-radius: 16px;
  overflow: hidden;
}

.cam-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(0,0,0,0.2);
  font-size: 14px;
}

.cam-head .hint {
  font-size: 12px;
  color: #666;
}

.cam-view {
  position: relative;
  background: #000;
  width: 100%;
  aspect-ratio: 4/3;
}

.cam-view img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cam-view canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

/* 校正画面 */
.corr-section {
  margin-bottom: 25px;
}

.corr-section h3 {
  font-size: 14px;
  color: #888;
  margin-bottom: 12px;
}

.corr-view {
  position: relative;
  background: #000;
  border-radius: 12px;
  overflow: hidden;
  width: 100%;
  max-width: 640px;
  aspect-ratio: 16/9;
}

.corr-view img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.corr-view canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

/* 按钮 */
.btn-row {
  display: flex;
  gap: 15px;
  flex-wrap: wrap;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.2s;
}

.btn:hover { transform: translateY(-2px); }
.btn.edit { background: #FF7222; color: #fff; }
.btn.save { background: #33B555; color: #fff; }
.btn.load { background: #2196F3; color: #fff; }
.btn.reset { background: rgba(255,255,255,0.1); color: #fff; }

.toast {
  position: fixed;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0,0,0,0.8);
  color: #fff;
  padding: 12px 24px;
  border-radius: 10px;
  z-index: 1000;
}
</style>
