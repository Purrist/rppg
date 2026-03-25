<template>
  <div class="dev-page">
    <!-- 头部 -->
    <header class="dev-header">
      <h1>🛠 开发者后台</h1>
      <div class="conn-badge" :class="connected ? 'ok' : 'err'">
        {{ connected ? '✅ 已连接' : '❌ 未连接' }}
      </div>
    </header>
    
    <!-- ⭐ 系统全局状态卡片 -->
    <section class="system-status-section">
      <h3>🖥️ 系统全局状态</h3>
      <div class="system-status-grid">
        <!-- AI模式 -->
        <div class="sys-card" :class="systemState.aiMode">
          <div class="sys-label">AI模式</div>
          <div class="sys-value">{{ systemState.aiMode === 'companion' ? '智伴模式' : '基础模式' }}</div>
          <div class="sys-desc">{{ systemState.aiMode === 'companion' ? 'AI主动交互' : '预设程序运行' }}</div>
        </div>
        
        <!-- 当前页面 -->
        <div class="sys-card">
          <div class="sys-label">当前页面</div>
          <div class="sys-value">{{ currentPageText }}</div>
          <div class="sys-desc">{{ systemState.currentPage }}</div>
        </div>
        
        <!-- 游戏状态 -->
        <div class="sys-card" :class="'game-' + systemState.game?.status.toLowerCase()">
          <div class="sys-label">游戏状态</div>
          <div class="sys-value">{{ gameStatusText }}</div>
          <div class="sys-desc">{{ systemState.game?.currentGame || '无' }}</div>
        </div>
        
        <!-- 当前游戏 -->
        <div class="sys-card">
          <div class="sys-label">当前游戏</div>
          <div class="sys-value">{{ currentGameText }}</div>
          <div class="sys-desc">{{ systemState.game?.module || '-' }}</div>
        </div>
        
        <!-- 游戏难度 -->
        <div class="sys-card">
          <div class="sys-label">游戏难度</div>
          <div class="sys-value">{{ systemState.game?.status !== 'IDLE' ? systemState.game?.difficulty + '/8' : '-' }}</div>
          <div class="sys-desc">难度等级</div>
        </div>
        
        <!-- 确认时间 -->
        <div class="sys-card">
          <div class="sys-label">确认时间</div>
          <div class="sys-value">{{ (systemState.game?.dwellTime / 1000).toFixed(1) }}s</div>
          <div class="sys-desc">进度圈填充时间</div>
        </div>
        
        <!-- 游戏得分 -->
        <div class="sys-card" v-if="systemState.game?.status !== 'IDLE'">
          <div class="sys-label">当前得分</div>
          <div class="sys-value">{{ systemState.gameRuntime?.score }}</div>
          <div class="sys-desc">游戏得分</div>
        </div>
        
        <!-- 剩余时间 -->
        <div class="sys-card" v-if="systemState.game?.status !== 'IDLE'">
          <div class="sys-label">剩余时间</div>
          <div class="sys-value">{{ systemState.gameRuntime?.timer }}s</div>
          <div class="sys-desc">游戏倒计时</div>
        </div>
      </div>
    </section>

    <!-- ⭐ 核心状态卡片 -->
    <section class="core-status">
      <!-- 有人/无人 -->
      <div class="person-card" :class="personDetected ? 'detected' : 'not-detected'">
        <div class="person-icon">{{ personDetected ? '👤' : '🚫' }}</div>
        <div class="person-text">{{ personDetected ? '有人' : '无人' }}</div>
        <div class="person-detail" v-if="personDetected">
          人脸: {{ userState.face_count }} | 骨骼: {{ userState.body_detected ? '✓' : '✗' }}
        </div>
        <div class="person-detail" v-else>
          等待检测...
        </div>
      </div>
      
      <!-- 三维指标 -->
      <div class="indicator-cards">
        <!-- 身体负荷 -->
        <div class="indicator-card physical">
          <div class="ind-header">
            <span class="ind-icon">💪</span>
            <span class="ind-title">身体负荷</span>
          </div>
          <div class="ind-value">{{ personDetected ? Math.round(userState.physical_load?.value * 100) : '--' }}%</div>
          <div class="ind-bar">
            <div class="ind-fill physical-fill" :style="{ width: (personDetected ? userState.physical_load?.value * 100 : 0) + '%' }"></div>
          </div>
          <div class="ind-details">
            <div class="ind-row">
              <span>心率</span>
              <span>{{ personDetected && userState.physical_load?.heart_rate ? userState.physical_load.heart_rate + ' BPM' : '--' }}</span>
            </div>
            <div class="ind-row">
              <span>运动强度</span>
              <span>{{ personDetected ? Math.round(userState.physical_load?.movement_intensity * 100) + '%' : '--' }}</span>
            </div>
            <div class="ind-row" :class="{ 'warning': userState.physical_load?.fall_detected }">
              <span>摔倒</span>
              <span>{{ userState.physical_load?.fall_detected ? '⚠️ 检测到!' : '无' }}</span>
            </div>
          </div>
        </div>
        
        <!-- 认知负荷 -->
        <div class="indicator-card cognitive">
          <div class="ind-header">
            <span class="ind-icon">🧠</span>
            <span class="ind-title">认知负荷</span>
          </div>
          <div class="ind-value">{{ personDetected ? Math.round(userState.cognitive_load?.value * 100) : '--' }}%</div>
          <div class="ind-bar">
            <div class="ind-fill cognitive-fill" :style="{ width: (personDetected ? userState.cognitive_load?.value * 100 : 0) + '%' }"></div>
          </div>
          <div class="ind-details">
            <div class="ind-row">
              <span>错误率</span>
              <span>{{ personDetected ? Math.round(userState.cognitive_load?.error_rate * 100) + '%' : '--' }}</span>
            </div>
            <div class="ind-row">
              <span>注意力稳定性</span>
              <span>{{ personDetected ? Math.round(userState.cognitive_load?.attention_stability * 100) + '%' : '--' }}</span>
            </div>
          </div>
        </div>
        
        <!-- 参与意愿 -->
        <div class="indicator-card engagement">
          <div class="ind-header">
            <span class="ind-icon">❤️</span>
            <span class="ind-title">参与意愿</span>
          </div>
          <div class="ind-value">{{ personDetected ? Math.round(userState.engagement?.value * 100) : '--' }}%</div>
          <div class="ind-bar">
            <div class="ind-fill engagement-fill" :style="{ width: (personDetected ? userState.engagement?.value * 100 : 0) + '%' }"></div>
          </div>
          <div class="ind-details">
            <div class="ind-row">
              <span>正面情绪</span>
              <span>{{ personDetected ? Math.round(userState.engagement?.emotion_positive * 100) + '%' : '--' }}</span>
            </div>
            <div class="ind-row">
              <span>主动性</span>
              <span>{{ personDetected ? Math.round(userState.engagement?.initiative_level * 100) + '%' : '--' }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
    
    <!-- 详细数据 -->
    <section class="detail-section">
      <h3>📊 详细数据</h3>
      <div class="detail-grid">
        <div class="detail-card">
          <span class="d-label">情绪</span>
          <span class="d-value">{{ personDetected ? userState.emotion?.primary : '--' }}</span>
        </div>
        <div class="detail-card">
          <span class="d-label">姿态</span>
          <span class="d-value" :class="{ 'falling': userState.posture?.type === 'falling' }">{{ personDetected ? userState.posture?.type : '--' }}</span>
        </div>
        <div class="detail-card">
          <span class="d-label">姿态稳定性</span>
          <span class="d-value">{{ personDetected ? Math.round(userState.posture?.stability * 100) + '%' : '--' }}</span>
        </div>
        <div class="detail-card">
          <span class="d-label">活动水平</span>
          <span class="d-value">{{ personDetected ? Math.round(userState.activity?.level * 100) + '%' : '--' }}</span>
        </div>
        <div class="detail-card">
          <span class="d-label">亮度</span>
          <span class="d-value">{{ lightText[userState.environment?.light_level] || '--' }}</span>
        </div>
        <div class="detail-card">
          <span class="d-label">状态总结</span>
          <span class="d-value">{{ summaryText[userState.overall?.state_summary] || '--' }}</span>
        </div>
      </div>
    </section>
    
    <!-- 游戏状态 -->
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
    
    <div v-if="toast.show" class="toast">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { 
  subscribe,
  getState,
  initStore
} from '../core/systemStore.js'

const getHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const PORT = 5000
const baseUrl = `http://${getHost()}:${PORT}`
const videoUrl = `${baseUrl}/video_feed`
const correctedUrl = `${baseUrl}/corrected_feed`
const tabletVideoUrl = `${baseUrl}/tablet_video_feed`

// Socket.IO 连接
let socket = null
let unsubscribe = null

// ⭐ 系统全局状态（从后端同步）
const systemState = reactive({
  aiMode: 'basic',
  currentPage: '/',
  game: {
    status: 'IDLE',
    currentGame: null,
    difficulty: 3,
    module: null,
    dwellTime: 2000,
  },
  gameRuntime: {
    score: 0,
    timer: 60,
    accuracy: 0,
    trialCount: 0,
    correctCount: 0,
  },
  perception: {
    personDetected: false,
    personCount: 0,
    faceCount: 0,
    bodyDetected: false,
    footPosition: { x: 0, y: 0, detected: false },
    emotion: 'neutral',
    attention: 0,
    fatigue: 0,
    heartRate: null,
    activity: 'unknown',
    speaking: false,
    idleMinutes: 0,
  },
  environment: {
    lightLevel: 'normal',
  },
  settings: {
    dwellTime: 2000,
    soundEnabled: true,
    projectionEnabled: true,
  },
  timeInfo: {
    time: '',
    date: '',
    weekday: '',
  },
  timestamp: 0
})

const lightText = { 'dark': '暗', 'normal': '正常', 'bright': '亮' }
const summaryText = { 'normal': '正常', 'fatigued': '疲劳', 'engaged': '专注', 'struggling': '困难' }

const connected = ref(false)
const rawCanvas = ref(null)
const correctedCanvas = ref(null)
const isEditing = ref(false)
const savedCorners = ref(null)
const corners = ref([[0.15, 0.2], [0.85, 0.2], [0.85, 0.85], [0.15, 0.85]])

// 计算属性
const personDetected = computed(() => systemState.perception?.personDetected || false)
const gameState = computed(() => ({
  status: systemState.game?.status || 'IDLE',
  score: systemState.gameRuntime?.score || 0,
  timer: systemState.gameRuntime?.timer || 60
}))
const status = computed(() => ({
  feet_detected: systemState.perception?.footPosition?.detected || false,
  feet_x: systemState.perception?.footPosition?.x || 320,
  feet_y: systemState.perception?.footPosition?.y || 180
}))
const userState = computed(() => ({
  person_detected: systemState.perception?.personDetected || false,
  face_detected: systemState.perception?.faceCount > 0,
  body_detected: systemState.perception?.bodyDetected || false,
  face_count: systemState.perception?.faceCount || 0,
  physical_load: {
    value: systemState.perception?.fatigue || 0,
    heart_rate: systemState.perception?.heartRate || null,
    movement_intensity: 0,
    fall_detected: false
  },
  cognitive_load: {
    value: systemState.perception?.attention || 0,
    error_rate: 0,
    attention_stability: 1
  },
  engagement: {
    value: 0.5,
    emotion_positive: 0.5,
    initiative_level: 0.5
  },
  emotion: {
    primary: systemState.perception?.emotion || 'neutral'
  },
  posture: {
    type: systemState.perception?.activity || 'unknown',
    stability: 1
  },
  activity: {
    level: 0
  },
  environment: {
    light_level: systemState.environment?.lightLevel || 'normal'
  },
  overall: {
    state_summary: 'normal'
  }
}))

const gameStateText = computed(() => {
  const t = { 'IDLE': '待机', 'READY': '等待', 'PLAYING': '进行中', 'PAUSED': '暂停', 'SETTLING': '结算' }
  return t[gameState.status] || '未知'
})

// ⭐ 系统状态计算属性
const currentPageText = computed(() => {
  const pageMap = {
    '/': '首页',
    '/health': '健康监测',
    '/learning': '益智训练',
    '/training': '游戏训练',
    '/entertainment': '娱乐',
    '/settings': '设置',
    '/developer': '开发者',
    '/projection': '投影'
  }
  return pageMap[systemState.currentPage] || systemState.currentPage
})

const gameStatusText = computed(() => {
  const t = { 'IDLE': '待机', 'READY': '预备', 'PLAYING': '游戏中', 'PAUSED': '暂停', 'SETTLING': '结算' }
  return t[systemState.game?.status] || '未知'
})

const currentGameText = computed(() => {
  const gameMap = {
    'whack_a_mole': '打地鼠',
    'processing_speed': '处理速度训练'
  }
  return gameMap[systemState.game?.currentGame] || (systemState.game?.currentGame || '无')
})

const toast = reactive({ show: false, msg: '' })
const dragging = ref(-1)
const mouseDown = ref(false)
let interval = null

function showToast(msg) {
  toast.msg = msg
  toast.show = true
  setTimeout(() => toast.show = false, 2000)
}

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

async function updateStatus() {
  if (!connected.value) {
    await checkConn()
    if (!connected.value) return
  }
  
  try {
    // 获取脚部位置
    const r = await fetch(`${baseUrl}/api/status`)
    if (r.ok) {
      const d = await r.json()
      if (Number.isFinite(d.feet_x) && Number.isFinite(d.feet_y)) {
        status.feet_x = Math.max(0, Math.min(640, d.feet_x))
        status.feet_y = Math.max(0, Math.min(360, d.feet_y))
      }
      status.feet_detected = d.feet_detected
    }
    
    // 获取游戏状态
    const gr = await fetch(`${baseUrl}/api/system/state`)
    if (gr.ok) {
      const gd = await gr.json()
      if (gd.state) {
        // 直接更新systemState，因为我们现在使用单一状态源
        Object.assign(systemState, gd.state)
      }
    }
    
    // ⭐ 获取用户状态（感知数据）
    const ur = await fetch(`${baseUrl}/api/user_state`)
    if (ur.ok) {
      const ud = await ur.json()
      // 更新所有字段
      userState.person_detected = ud.person_detected || false
      userState.face_detected = ud.face_detected || false
      userState.body_detected = ud.body_detected || false
      userState.face_count = ud.face_count || 0
      
      if (ud.physical_load) {
        userState.physical_load = ud.physical_load
      }
      if (ud.cognitive_load) {
        userState.cognitive_load = ud.cognitive_load
      }
      if (ud.engagement) {
        userState.engagement = ud.engagement
      }
      if (ud.emotion) {
        userState.emotion = ud.emotion
      }
      if (ud.posture) {
        userState.posture = ud.posture
      }
      if (ud.activity) {
        userState.activity = ud.activity
      }
      if (ud.environment) {
        userState.environment = ud.environment
      }
      if (ud.overall) {
        userState.overall = ud.overall
      }
    }
  } catch {
    connected.value = false
  }
}

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

onMounted(async () => {
  const ok = await checkConn()
  if (ok) {
    await fetch(`${baseUrl}/api/load_all`, { method: 'POST' })
    await loadCorners()
  }
  
  // ⭐ 建立 Socket.IO 连接
  socket = io(baseUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  // 连接状态管理
  let reconnectAttempts = 0
  const maxReconnectAttempts = 5
  
  socket.on('connect', () => {
    console.log('[developer] Socket.IO已连接')
    connected.value = true
    reconnectAttempts = 0
    // 请求系统状态
    socket.emit('get_system_state')
  })
  
  socket.on('disconnect', () => {
    console.log('[developer] Socket.IO已断开连接')
    connected.value = false
  })
  
  socket.on('connect_error', (error) => {
    console.error('[developer] Socket.IO连接错误:', error)
    connected.value = false
    reconnectAttempts++
    if (reconnectAttempts > maxReconnectAttempts) {
      console.warn('[developer] 连接尝试次数过多，将停止自动重连')
    }
  })
  
  socket.on('reconnect', (attemptNumber) => {
    console.log('[developer] Socket.IO重连成功，尝试次数:', attemptNumber)
    connected.value = true
    reconnectAttempts = 0
    // 重连后重新请求系统状态
    socket.emit('get_system_state')
  })
  
  // ⭐ 初始化SystemStore
  initStore(socket)
  
  // ⭐ 订阅系统全局状态
  unsubscribe = subscribe((state) => {
    // 更新本地状态 - 完整同步
    if (state) {
      Object.assign(systemState, state)
    }
    console.log('[developer] 系统状态更新')
  })
  
  resize()
  requestAnimationFrame(draw)
  // 移除定期API请求，改为完全依赖Socket.IO实时更新
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  if (unsubscribe) unsubscribe()
  if (socket) socket.disconnect()
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

/* ⭐ 系统全局状态卡片 */
.system-status-section {
  margin-bottom: 25px;
}

.system-status-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: #888;
  margin-bottom: 15px;
}

.system-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.sys-card {
  background: rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 16px 12px;
  text-align: center;
  border: 2px solid transparent;
  transition: all 0.3s;
}

.sys-card:hover {
  transform: translateY(-2px);
  background: rgba(255,255,255,0.08);
}

/* AI模式样式 */
.sys-card.companion {
  border-color: #33B555;
  background: rgba(51, 181, 85, 0.1);
}

.sys-card.basic {
  border-color: #666;
}

/* 游戏状态样式 */
.sys-card.game-idle {
  border-color: #666;
}

.sys-card.game-ready {
  border-color: #FF7222;
}

.sys-card.game-playing {
  border-color: #33B555;
  background: rgba(51, 181, 85, 0.1);
}

.sys-card.game-paused {
  border-color: #FFD111;
}

.sys-card.game-settling {
  border-color: #9C27B0;
}

.sys-label {
  font-size: 11px;
  color: #888;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sys-value {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  margin-bottom: 4px;
}

.sys-card.companion .sys-value {
  color: #33B555;
}

.sys-card.game-playing .sys-value {
  color: #33B555;
}

.sys-desc {
  font-size: 11px;
  color: #666;
}

.dev-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}

.dev-header h1 { font-size: 24px; font-weight: 600; }

.conn-badge { padding: 8px 16px; border-radius: 20px; font-size: 14px; }
.conn-badge.ok { background: rgba(51, 181, 85, 0.2); color: #33B555; }
.conn-badge.err { background: rgba(255, 68, 68, 0.2); color: #ff6b6b; }

/* 核心状态 */
.core-status { display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap; }

.person-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px 30px;
  border-radius: 16px;
  min-width: 140px;
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

.person-icon { font-size: 48px; margin-bottom: 8px; }
.person-text { font-size: 20px; font-weight: 700; }
.person-detail { font-size: 12px; margin-top: 8px; opacity: 0.8; }

/* 指标卡片 */
.indicator-cards { display: flex; flex-wrap: wrap; gap: 15px; flex: 1; }

.indicator-card {
  background: rgba(255,255,255,0.05);
  border-radius: 16px;
  padding: 16px;
  min-width: 200px;
  flex: 1;
}

.ind-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.ind-icon { font-size: 24px; }
.ind-title { font-size: 14px; font-weight: 600; }
.ind-value { font-size: 32px; font-weight: 700; margin-bottom: 8px; }

.ind-bar { height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-bottom: 12px; }
.ind-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.physical-fill { background: linear-gradient(90deg, #33B555, #FFD700, #ff6b6b); }
.cognitive-fill { background: linear-gradient(90deg, #2196F3, #9C27B0, #ff6b6b); }
.engagement-fill { background: linear-gradient(90deg, #ff6b6b, #FFD700, #33B555); }

.ind-details { display: flex; flex-direction: column; gap: 6px; }
.ind-row { display: flex; justify-content: space-between; font-size: 12px; }
.ind-row span:first-child { color: #888; }
.ind-row.warning { color: #ff6b6b; font-weight: bold; }

/* 详细数据 */
.detail-section { margin-bottom: 25px; }
.detail-section h3 { font-size: 16px; margin-bottom: 12px; color: #888; }
.detail-grid { display: flex; flex-wrap: wrap; gap: 10px; }

.detail-card {
  background: rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 12px 16px;
  min-width: 100px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.d-label { font-size: 12px; color: #888; margin-bottom: 4px; }
.d-value { font-size: 16px; font-weight: 600; }
.d-value.falling { color: #ff6b6b; }

/* 状态卡片 */
.status-row { display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap; }
.stat-card { background: rgba(255,255,255,0.05); padding: 15px 20px; border-radius: 12px; min-width: 100px; flex: 1; }
.stat-card .label { display: block; font-size: 12px; color: #888; margin-bottom: 5px; }
.stat-card .val { font-size: 20px; font-weight: 600; }
.ok { color: #33B555; }
.err { color: #ff6b6b; }
.s-IDLE { color: #888; }
.s-READY { color: #FF7222; }
.s-PLAYING { color: #33B555; }
.s-PAUSED { color: #FFD111; }
.s-SETTLING { color: #9C27B0; }

/* 摄像头 */
.cam-row { display: flex; gap: 20px; margin-bottom: 25px; flex-wrap: wrap; }
.cam-box { flex: 1; min-width: 300px; background: rgba(255,255,255,0.05); border-radius: 16px; overflow: hidden; }
.cam-head { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: rgba(0,0,0,0.2); font-size: 14px; }
.cam-head .hint { font-size: 12px; color: #666; }
.cam-view { position: relative; background: #000; width: 100%; aspect-ratio: 4/3; }
.cam-view img { width: 100%; height: 100%; object-fit: cover; }
.cam-view canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; }

/* 校正画面 */
.corr-section { margin-bottom: 25px; }
.corr-section h3 { font-size: 14px; color: #888; margin-bottom: 12px; }
.corr-view { position: relative; background: #000; border-radius: 12px; overflow: hidden; width: 100%; max-width: 640px; aspect-ratio: 16/9; }
.corr-view img { width: 100%; height: 100%; object-fit: cover; }
.corr-view canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }

/* 按钮 */
.btn-row { display: flex; gap: 15px; flex-wrap: wrap; }
.btn { padding: 12px 24px; border: none; border-radius: 10px; font-size: 14px; font-weight: 500; cursor: pointer; transition: transform 0.2s; }
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
