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
          <div class="sys-value">{{ systemGameStatusText }}</div>
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
        
        <!-- ⭐ 语音状态 -->
        <div class="sys-card voice-card" :class="'voice-' + (systemState.voice?.state || 'STANDBY').toLowerCase()">
          <div class="sys-label">🎤 语音状态</div>
          <div class="sys-value">{{ voiceStateText }}</div>
          <div class="sys-desc voice-desc">
            <span v-if="systemState.voice?.isRecording" class="recording-indicator">🔴 录音中</span>
            <span v-if="systemState.voice?.isPlaying" class="playing-indicator">🔊 播放中</span>
            <span v-if="!systemState.voice?.isRecording && !systemState.voice?.isPlaying">
              {{ systemState.voice?.message || '等待唤醒...' }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- ⭐ 综合情绪与生理监测 -->
    <div class="main-container">
      <div class="left-panel">
        <!-- ⭐ 完整HLKK生理数据卡片 -->
        <div class="panel-card" style="flex:0 0 auto">
          <div class="panel-header">
            <span class="panel-title">HLKK 完整生理数据 (SystemCore)</span>
          </div>
          <div class="panel-body">
            <div class="data-grid">
              <div class="data-row">
                <span class="data-label">心率 (HR):</span>
                <span class="data-value">{{ systemState.perception.physiology.raw.hr ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">呼吸率 (BR):</span>
                <span class="data-value">{{ systemState.perception.physiology.raw.br ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">距离:</span>
                <span class="data-value">{{ systemState.perception.physiology.raw.distance ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">信号状态:</span>
                <span class="data-value">{{ systemState.perception.physiology.raw.signal_state ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">HR 有效:</span>
                <span class="data-value">{{ systemState.perception.physiology.raw.hr_valid ? '是' : '否' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">HRR (%):</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.hrr ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">HRR 标签:</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.hrr_label ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">斜率:</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.slope ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">斜率标签:</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.slope_label ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">呼吸变异性 (BRV):</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.brv ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">BRV 标签:</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.brv_label ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">呼吸熵 (BRE):</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.brel ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">复杂度 (CR):</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.cr ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">耦合度 (PLV):</span>
                <span class="data-value">{{ systemState.perception.physiology.analysis.plv ?? '--' }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ⭐ 完整情绪/面部数据卡片 -->
        <div class="panel-card" style="flex:0 0 auto">
          <div class="panel-header">
            <span class="panel-title">Emotion 完整数据 (SystemCore)</span>
          </div>
          <div class="panel-body">
            <div class="section-title">AU (Action Units) 数据</div>
            <div class="data-grid">
              <div class="data-row">
                <span class="data-label">情绪:</span>
                <span class="data-value">{{ systemState.perception.face.au.emotion ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">置信度:</span>
                <span class="data-value">{{ systemState.perception.face.au.confidence ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">姿态:</span>
                <span class="data-value">{{ systemState.perception.face.au.pose ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">Pitch:</span>
                <span class="data-value">{{ systemState.perception.face.au.pitch ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">Yaw:</span>
                <span class="data-value">{{ systemState.perception.face.au.yaw ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">Roll:</span>
                <span class="data-value">{{ systemState.perception.face.au.roll ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">投入度:</span>
                <span class="data-value">{{ systemState.perception.face.au.engagement ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">检测到人脸:</span>
                <span class="data-value">{{ systemState.perception.face.au.face_detected ? '是' : '否' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">人脸数量:</span>
                <span class="data-value">{{ systemState.perception.face.au.face_count ?? '--' }}</span>
              </div>
            </div>
            <div class="section-title">FER (Face Expression Recognition) 数据</div>
            <div class="data-grid">
              <div class="data-row">
                <span class="data-label">标签:</span>
                <span class="data-value">{{ systemState.perception.face.fer.label ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">置信度:</span>
                <span class="data-value">{{ systemState.perception.face.fer.conf ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">中性概率:</span>
                <span class="data-value">{{ systemState.perception.face.fer.probs_3?.neutral ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">积极概率:</span>
                <span class="data-value">{{ systemState.perception.face.fer.probs_3?.positive ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">消极概率:</span>
                <span class="data-value">{{ systemState.perception.face.fer.probs_3?.negative ?? '--' }}</span>
              </div>
            </div>
            <div class="section-title">Fusion 数据</div>
            <div class="data-grid">
              <div class="data-row">
                <span class="data-label">情绪:</span>
                <span class="data-value">{{ systemState.perception.face.fusion.emotion ?? '--' }}</span>
              </div>
              <div class="data-row">
                <span class="data-label">置信度:</span>
                <span class="data-value">{{ systemState.perception.face.fusion.confidence ?? '--' }}</span>
              </div>
            </div>
          </div>
        </div>

      </div>

      <div class="right-panel">
        <!-- DDA难度调整中枢 -->
        <div class="panel-card" style="flex:1">
          <div class="panel-header">
            <span class="panel-title">DDA难度调整中枢</span>
          </div>
          <div class="panel-body dda-panel">
            <div class="dda-section">
              <div class="dda-section-title">📊 生理数据 → DDA</div>
              <div class="dda-item"><span class="dda-label">hrr_pct:</span><span class="dda-value">{{ ddaData.hrr_pct !== undefined ? ddaData.hrr_pct.toFixed(1) + '%' : '--' }}</span></div>
              <div class="dda-item"><span class="dda-label">hrr:</span><span class="dda-value">{{ ddaData.hrr || '--' }}</span></div>
              <div class="dda-item"><span class="dda-label">hr_slope:</span><span class="dda-value">{{ ddaData.hr_slope !== undefined ? ddaData.hr_slope.toFixed(2) : '--' }}</span></div>
              <div class="dda-item"><span class="dda-label">slope_label:</span><span class="dda-value">{{ ddaData.slope_label || '--' }}</span></div>
            </div>
            <div class="dda-section">
              <div class="dda-section-title">😊 情绪数据 → DDA</div>
              <div class="dda-item"><span class="dda-label">emotion_cn:</span><span class="dda-value">{{ ddaData.emotion_cn || '--' }}</span></div>
              <div class="dda-item"><span class="dda-label">confidence:</span><span class="dda-value">{{ ddaData.confidence !== undefined ? (ddaData.confidence * 100).toFixed(0) + '%' : '--' }}</span></div>
            </div>
            <div class="dda-section">
              <div class="dda-section-title">🎮 游戏数据 → DDA</div>
              <div class="dda-item"><span class="dda-label">timeLeft:</span><span class="dda-value">{{ ddaTimeLeftText }}</span></div>
              <div class="dda-item"><span class="dda-label">score:</span><span class="dda-value">{{ ddaData.score !== undefined ? ddaData.score : '--' }}</span></div>
              <div class="dda-item"><span class="dda-label">difficulty:</span><span class="dda-value">{{ ddaData.difficulty !== undefined ? ddaData.difficulty : '--' }}</span></div>
              <div class="dda-item"><span class="dda-label">accuracy:</span><span class="dda-value">{{ ddaData.accuracy || '--' }}</span></div>
            </div>
            <div class="dda-section">
              <div class="dda-section-title">🎯 最新结果 → DDA</div>
              <div class="dda-item"><span class="dda-label">type:</span><span class="dda-value">{{ ddaData.last_result?.type || '--' }}</span></div>
              <div class="dda-item"><span class="dda-label">time:</span><span class="dda-value">{{ ddaData.last_result?.time ? ddaData.last_result.time + 'ms' : '--' }}</span></div>
            </div>
            <div class="dda-section">
              <div class="dda-section-title">⚙️ DDA 输出</div>
              <div class="dda-item"><span class="dda-label">建议难度:</span><span class="dda-value highlight">{{ ddaOutputDiff }}</span></div>
              <div class="dda-item"><span class="dda-label">flow_state:</span><span class="dda-value">{{ ddaOutputFlow }}</span></div>
              <div class="dda-item"><span class="dda-label">adjustment:</span><span class="dda-value">{{ ddaOutputAdj }}</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
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
      // ⭐ 完整生理数据
      physiology: {
        raw: {
          hr: null,
          br: null,
          hph: null,
          bph: null,
          is_human: 0,
          distance: 0,
          distance_valid: 0,
          signal_state: 'INIT',
          hr_valid: false,
          br_valid: false,
          phase_valid: false
        },
        analysis: {
          hrr: null,
          hrr_label: null,
          slope: null,
          slope_label: null,
          brv: null,
          brv_label: null,
          brel: null,
          brel_label: null,
          cr: null,
          cr_label: null,
          plv: null,
          plv_label: null,
          mean_phase_diff: null
        }
      },
      // ⭐ 完整面部/情绪数据
      face: {
        au: {
          emotion: 'no_face',
          confidence: 0.0,
          scores: { neutral: 0, positive: 0, negative: 0 },
          pose: '-',
          pitch: 0,
          yaw: 0,
          roll: 0,
          au_features: {},
          engagement: 'None',
          face_detected: false,
          face_count: 0,
          speaking: false
        },
        fer: {
          label: 'neutral',
          conf: 0.0,
          probs_3: { neutral: 0, positive: 0, negative: 0 },
          has_face: false
        },
        fusion: {
          emotion: 'no_face',
          confidence: 0.0,
          scores: { neutral: 0, positive: 0, negative: 0 }
        }
      }
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
    value: systemState.perception?.physicalLoad ?? (systemState.perception?.fatigue || 0),
    heart_rate: systemState.perception?.heartRate || null,
    movement_intensity: systemState.perception?.activity === 'active' ? 0.8 : (systemState.perception?.activity === 'sitting' ? 0.2 : 0),
    fall_detected: false
  },
  cognitive_load: {
    value: systemState.perception?.cognitiveLoad ?? (1 - (systemState.perception?.attention || 0.5)),
    error_rate: 0,
    attention_stability: systemState.perception?.attention || 0.5
  },
  engagement: {
    value: systemState.perception?.engagement ?? (systemState.perception?.attention || 0.5),
    emotion_positive: systemState.perception?.emotion === 'happy' ? 0.8 : (systemState.perception?.emotion === 'neutral' ? 0.5 : 0.3),
    initiative_level: systemState.perception?.activity === 'active' ? 0.7 : 0.3
  },
  emotion: {
    primary: systemState.perception?.emotion || 'neutral'
  },
  posture: {
    type: systemState.perception?.activity || 'unknown',
    stability: systemState.perception?.bodyDetected ? 0.8 : 0
  },
  activity: {
    level: systemState.perception?.activity === 'active' ? 0.8 : (systemState.perception?.activity === 'sitting' ? 0.2 : 0)
  },
  environment: {
    light_level: systemState.perception?.lightLevel || systemState.environment?.lightLevel || 'normal'
  },
  overall: {
    state_summary: systemState.perception?.fatigue > 0.6 ? 'fatigued' : (systemState.perception?.attention > 0.7 ? 'engaged' : 'normal')
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

const systemGameStatusText = computed(() => {
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

// ⭐ 语音状态文本
const voiceStateText = computed(() => {
  const stateMap = {
    'STANDBY': '待机',
    'RESPONDING': '回应中',
    'LISTENING': '聆听中',
    'PROCESSING': '处理中'
  }
  return stateMap[systemState.voice?.state] || '未知'
})

const toast = reactive({ show: false, msg: '' })
const dragging = ref(-1)
const mouseDown = ref(false)
let interval = null

// ⭐ 综合情绪与生理监测数据
const physioConnected = ref(false)
const lastUpdateTime = ref('--')
const currentModel = ref('deepface')
const gateEnabled = ref(true)
const emotionChart = ref(null)

const physioData = reactive({
  heart: '--',
  hrr_pct: 0,
  hr_slope: 0,
  hr_valid: false
})

const emotionData = reactive({
  positive: 0,
  neutral: 0,
  negative: 0
})

const processedEmotion = reactive({
  label: 'neutral',
  value: 0
})

const personData = reactive({
  face_count: 0,
  face_detected: false,
  gender: '--',
  gender_confidence: undefined,
  age: '--',
  age_confidence: undefined,
  pose: '--'
})

const hlkkData = reactive({
  gender: '--',
  age: '--'
})

const gameData = reactive({
  timeLeft: 0,
  status: 'idle',
  score: 0,
  difficulty: 1,
  difficultyName: '简单',
  accuracy: '--',
  results: []
})

const ddaData = reactive({
  hrr_pct: undefined,
  hrr: undefined,
  hr_slope: undefined,
  slope_label: '--',
  emotion_cn: '--',
  confidence: undefined,
  timeLeft: undefined,
  score: undefined,
  difficulty: undefined,
  accuracy: '--',
  last_result: null,
  game_status: 'idle',
  dda_output: {}
})

// ⭐ 计算属性
const hrrStatus = computed(() => {
  const hrr = physioData.hrr_pct || 0
  if (hrr < 40) return '低强度'
  else if (hrr <= 60) return '中强度'
  else return '高强度'
})

const hrSlopeColor = computed(() => {
  const slope = physioData.hr_slope || 0
  if (slope > 2.0) return '#EA4335'
  else if (slope > 0.5) return '#f59e0b'
  else if (slope < -0.5) return '#34A853'
  else return '#4285F4'
})

const hrSlopeStatus = computed(() => {
  const slope = physioData.hr_slope || 0
  if (slope > 2.0) return '快速上升'
  else if (slope > 0.5) return '缓慢上升'
  else if (slope < -0.5) return '快速下降'
  else return '平稳'
})

const humanText = computed(() => {
  const faceCount = personData.face_count !== undefined ? personData.face_count : (personData.face_detected ? 1 : 0)
  if (faceCount === 0) return '无人'
  else if (faceCount === 1) return '1人'
  else return faceCount + '人'
})

const poseText = computed(() => {
  const poseMap = {
    'front': '正脸',
    'up': '抬头',
    'down': '低头',
    'side_left': '左侧脸',
    'side_right': '右侧脸',
    '-': '--',
    'unknown': '--'
  }
  return poseMap[personData.pose] || personData.pose || '--'
})

const genderText = computed(() => {
  const isFrontFace = personData.pose === 'front' && (!isNaN(personData.age) && personData.age > 0)
  const gender = isFrontFace ? (personData.gender || '--') : '--'
  return gender.toLowerCase() === 'man' ? '男' : gender.toLowerCase() === 'woman' ? '女' : gender
})

const genderConfText = computed(() => {
  const isFrontFace = personData.pose === 'front' && (!isNaN(personData.age) && personData.age > 0)
  const genderConf = isFrontFace ? personData.gender_confidence : undefined
  if (genderConf === undefined) return '--%'
  let conf = genderConf
  if (conf > 1.5) {
    conf = Math.min(100, Math.round(conf))
  } else {
    conf = Math.min(100, Math.round(conf * 100))
  }
  return conf + '%'
})

const ageText = computed(() => {
  const isFrontFace = personData.pose === 'front' && (!isNaN(personData.age) && personData.age > 0)
  return isFrontFace ? personData.age : '--'
})

const ageConfText = computed(() => {
  const isFrontFace = personData.pose === 'front' && (!isNaN(personData.age) && personData.age > 0)
  const ageConf = isFrontFace ? personData.age_confidence : undefined
  if (ageConf === undefined) return '--%'
  let conf = ageConf
  if (conf > 1.5) {
    conf = Math.min(100, Math.round(conf))
  } else {
    conf = Math.min(100, Math.round(conf * 100))
  }
  return conf + '%'
})

const hlkkGenderText = computed(() => {
  const gender = hlkkData.gender || '--'
  return gender === 'male' ? '男' : gender === 'female' ? '女' : '--'
})

const hlkkAgeText = computed(() => {
  return hlkkData.age > 0 ? hlkkData.age + '岁' : '--'
})

const emotionCardClass = computed(() => {
  const label = processedEmotion.label || 'neutral'
  const specialStates = ['no_face', 'out_of_range', 'speaking', 'uncalibrated']
  if (specialStates.includes(label)) return 'neutral'
  
  const classMap = {
    'positive_high': 'positive',
    'positive_low': 'positive',
    'negative_high': 'negative',
    'negative_low': 'negative',
    'neutral_high': 'neutral',
    'neutral': 'neutral',
    'positive': 'positive',
    'negative': 'negative'
  }
  return classMap[label] || 'neutral'
})

const emotionLabelText = computed(() => {
  const label = processedEmotion.label || 'neutral'
  const specialStates = ['no_face', 'out_of_range', 'speaking', 'uncalibrated']
  if (specialStates.includes(label)) return '中性'
  
  const labelMap = {
    'positive_high': '积极高信度',
    'positive_low': '积极低信度',
    'negative_high': '消极高信度',
    'negative_low': '消极低信度',
    'neutral_high': '中性高信度',
    'neutral': '中性',
    'positive': '积极',
    'negative': '消极'
  }
  return labelMap[label] || '中性'
})

const gameTimeText = computed(() => {
  const mins = Math.floor((gameData.timeLeft || 0) / 60)
  const secs = (gameData.timeLeft || 0) % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
})

const gameStatusText = computed(() => {
  const statusMap = {
    'idle': '未开始',
    'playing': '进行中',
    'paused': '已暂停'
  }
  return statusMap[gameData.status] || (gameData.running ? '进行中' : '未开始')
})

const gameDiffName = computed(() => {
  const diffMap = {
    1: '简单',
    2: '较简单',
    3: '中等',
    4: '较困难',
    5: '困难',
    6: '较难',
    7: '非常困难',
    8: '极限'
  }
  return diffMap[gameData.difficulty] || '简单'
})

const gameRecords = computed(() => {
  return (gameData.results || []).reverse().map(r => {
    let typeClass = 'game-record-hit'
    let typeText = '✓ 打中'
    if (r.type === 'miss') {
      typeClass = 'game-record-miss'
      typeText = '○ 漏打'
    } else if (r.type === 'error') {
      typeClass = 'game-record-error'
      typeText = '✗ 打错'
    } else if (r.type === 'bomb') {
      typeClass = 'game-record-bomb'
      typeText = '💣 炸弹'
    }
    return {
      typeClass,
      typeText,
      time: r.time,
      difficulty: r.difficulty || 1,
      score: r.score || 0
    }
  })
})

const ddaTimeLeftText = computed(() => {
  const tl = ddaData.timeLeft || 0
  const mins = Math.floor(tl / 60)
  const secs = tl % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
})

const ddaOutputDiff = computed(() => {
  const gameStatus = ddaData.game_status || 'idle'
  const isGamePlaying = gameStatus === 'playing'
  const ddaOutput = ddaData.dda_output || {}
  
  if (isGamePlaying && ddaOutput) {
    return ddaOutput.current_difficulty !== undefined ? ddaOutput.current_difficulty : '--'
  } else {
    return gameStatus === 'idle' ? '等待游戏开始' : (gameStatus === 'paused' ? '游戏已暂停' : '--')
  }
})

const ddaOutputFlow = computed(() => {
  const gameStatus = ddaData.game_status || 'idle'
  const isGamePlaying = gameStatus === 'playing'
  const ddaOutput = ddaData.dda_output || {}
  
  if (isGamePlaying && ddaOutput) {
    return ddaOutput.flow_state || '--'
  } else {
    return gameStatus === 'idle' ? '等待游戏开始' : (gameStatus === 'paused' ? '游戏已暂停' : '--')
  }
})

const ddaOutputAdj = computed(() => {
  const gameStatus = ddaData.game_status || 'idle'
  const isGamePlaying = gameStatus === 'playing'
  const ddaOutput = ddaData.dda_output || {}
  
  if (isGamePlaying && ddaOutput) {
    return ddaOutput.adjustment !== undefined ? (ddaOutput.adjustment > 0 ? '+' + ddaOutput.adjustment : ddaOutput.adjustment) : '--'
  } else {
    return gameStatus === 'idle' ? '等待游戏开始' : (gameStatus === 'paused' ? '游戏已暂停' : '--')
  }
})

// ⭐ 方法
let emotionHistory = []
let chartInstance = null
let chartInitAttempts = 0
const maxChartInitAttempts = 10
let chartLoaded = false

function loadChartLibrary(callback) {
  if (window.Chart) {
    chartLoaded = true
    callback(true)
    return
  }
  
  const script = document.createElement('script')
  script.src = '/js/chart.min.js'
  script.onload = () => {
    chartLoaded = true
    callback(true)
  }
  script.onerror = () => {
    console.error('[developer] Chart.js 加载失败')
    callback(false)
  }
  document.head.appendChild(script)
}

function initEmotionChart() {
  const ctx = emotionChart.value?.getContext('2d')
  if (!ctx) {
    chartInitAttempts++
    if (chartInitAttempts < maxChartInitAttempts) {
      setTimeout(initEmotionChart, 100)
    }
    return
  }
  
  if (!window.Chart) {
    loadChartLibrary((success) => {
      if (success) {
        initEmotionChart()
      }
    })
    return
  }
  
  if (chartInstance) {
    chartInstance.destroy()
  }
  
  chartInstance = new window.Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: '情绪值',
        data: [],
        borderColor: '#4285F4',
        backgroundColor: 'rgba(66,133,244,0.1)',
        fill: true,
        tension: 0.3,
        borderWidth: 2,
        pointRadius: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 0 },
      scales: {
        x: { display: false, type: 'linear' },
        y: { min: -1.2, max: 1.2, ticks: { display: false }, grid: { color: '#1a2236' } }
      },
      plugins: { legend: { display: false } }
    }
  })
  
  console.log('[developer] 情绪图表初始化成功')
}

function updateEmotionChart(value) {
  emotionHistory.push(value)
  if (emotionHistory.length > 100) emotionHistory.shift()
  
  if (chartInstance) {
    chartInstance.data.datasets[0].data = emotionHistory
    chartInstance.data.labels = Array.from({length: emotionHistory.length}, (_, i) => i)
    chartInstance.options.scales.x.max = Math.max(emotionHistory.length - 1, 0)
    chartInstance.update('none')
  }
}

async function fetchPerceptionData() {
  try {
    const resp = await fetch(`${baseUrl}/api/current`)
    if (!resp.ok) {
      console.error('Perception API 响应失败:', resp.status)
      physioConnected.value = false
      return
    }
    
    const data = await resp.json()
    
    if (data && data.physio) {
      physioData.heart = data.physio.heart !== undefined && data.physio.heart !== null ? data.physio.heart : '--'
      physioData.hrr_pct = typeof data.physio.hrr_pct === 'number' ? data.physio.hrr_pct : 0
      physioData.hr_slope = typeof data.physio.hr_slope === 'number' ? data.physio.hr_slope : 0
      physioData.hr_valid = !!data.physio.hr_valid
      physioConnected.value = true
    }
    
    if (data) {
      emotionData.positive = typeof data.emotion?.positive === 'number' ? data.emotion.positive : 0
      emotionData.neutral = typeof data.emotion?.neutral === 'number' ? data.emotion.neutral : 0
      emotionData.negative = typeof data.emotion?.negative === 'number' ? data.emotion.negative : 0
      
      if (data.processed) {
        processedEmotion.label = data.processed.label || 'neutral'
        processedEmotion.value = typeof data.processed.value === 'number' ? data.processed.value : 0
        updateEmotionChart(processedEmotion.value)
      }
    }
    
    lastUpdateTime.value = new Date().toLocaleTimeString()
    
    await fetchDDAData()
  } catch (e) {
    console.error('Perception API Error:', e)
    physioConnected.value = false
  }
}

async function fetchPersonData() {
  try {
    const resp = await fetch(`${baseUrl}/api/data`)
    if (!resp.ok) {
      console.error('Person API 响应失败:', resp.status)
      return
    }
    
    const data = await resp.json()
    
    personData.face_count = data.face_count !== undefined ? data.face_count : (data.face_detected ? 1 : 0)
    personData.face_detected = data.face_detected || false
    personData.pose = data.pose || '--'
    personData.gender = data.gender || '--'
    personData.gender_confidence = data.gender_confidence
    personData.age = data.age || '--'
    personData.age_confidence = data.age_confidence
    
    await fetchHlkkData()
  } catch (e) {
    console.error('Person API Error:', e)
  }
}

function formatConfidence(conf) {
  if (conf === undefined || conf === null) return '--%'
  let value = conf
  if (value > 1.5) {
    value = Math.min(100, Math.round(value))
  } else {
    value = Math.min(100, Math.round(value * 100))
  }
  return value + '%'
}

async function fetchHlkkData() {
  try {
    const resp = await fetch(`${baseUrl}/api/hlkk`)
    if (!resp.ok) {
      console.error('HLKK API 响应失败:', resp.status)
      return
    }
    
    const data = await resp.json()
    const profile = data.profile || {}
    
    hlkkData.gender = profile.gender || '--'
    hlkkData.age = profile.age > 0 ? profile.age : '--'
  } catch (e) {
    console.error('HLKK API Error:', e)
  }
}

async function fetchGameData() {
  try {
    const resp = await fetch(`${baseUrl}/api/game`)
    if (!resp.ok) {
      console.error('Game API 响应失败:', resp.status)
      return
    }
    
    const data = await resp.json()
    
    if (data) {
      gameData.timeLeft = typeof data.timeLeft === 'number' ? data.timeLeft : 0
      gameData.status = data.status || 'idle'
      gameData.score = typeof data.score === 'number' ? data.score : 0
      gameData.difficulty = typeof data.difficulty === 'number' ? data.difficulty : 1
      gameData.difficultyName = data.difficultyName || '简单'
      gameData.accuracy = data.accuracy || '--'
      gameData.results = Array.isArray(data.results) ? data.results : []
    }
  } catch (e) {
    console.error('Game API Error:', e)
  }
}

async function fetchDDAData() {
  try {
    const resp = await fetch(`${baseUrl}/api/dda/input`)
    if (!resp.ok) {
      console.error('DDA API 响应失败:', resp.status)
      return
    }
    const data = await resp.json()
    
    if (data) {
      ddaData.hrr_pct = typeof data.hrr_pct === 'number' ? data.hrr_pct : undefined
      ddaData.hrr = data.hrr
      ddaData.hr_slope = typeof data.hr_slope === 'number' ? data.hr_slope : undefined
      ddaData.slope_label = data.slope_label || '--'
      ddaData.emotion_cn = data.emotion_cn || '--'
      ddaData.confidence = typeof data.confidence === 'number' ? data.confidence : undefined
      ddaData.timeLeft = typeof data.timeLeft === 'number' ? data.timeLeft : undefined
      ddaData.score = typeof data.score === 'number' ? data.score : undefined
      ddaData.difficulty = typeof data.difficulty === 'number' ? data.difficulty : undefined
      ddaData.accuracy = data.accuracy || '--'
      ddaData.last_result = data.last_result || null
      ddaData.game_status = data.game_status || 'idle'
      ddaData.dda_output = data.dda_output || {}
    }
  } catch (e) {
    console.error('DDA API Error:', e)
  }
}

async function fetchCurrentModel() {
  try {
    const resp = await fetch(`${baseUrl}/api/model`)
    const data = await resp.json()
    currentModel.value = data.model || 'deepface'
  } catch (e) {
    console.error('Model API Error', e)
  }
}

async function setModel(model) {
  try {
    const resp = await fetch(`${baseUrl}/api/model`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model: model})
    })
    const data = await resp.json()
    if (data.ok) {
      currentModel.value = model
    }
  } catch (e) {
    console.error('切换模型失败', e)
  }
}

async function toggleGate() {
  gateEnabled.value = !gateEnabled.value
  
  try {
    await fetch(`${baseUrl}/api/gate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: gateEnabled.value })
    })
  } catch (e) {
    console.error('Failed to update gate', e)
  }
}

function showToast(msg) {
  toast.msg = msg
  toast.show = true
  setTimeout(() => toast.show = false, 2000)
}

function startEdit() {
  console.log('[developer] 点击编辑按钮，isEditing变为true')
  isEditing.value = true
  savedCorners.value = JSON.parse(JSON.stringify(corners.value))
  showToast('开始编辑校准区域')
}

async function saveAndExitEdit() {
  console.log('[developer] 点击保存按钮，开始保存校准区域...')
  console.log('[developer] 当前isEditing:', isEditing.value)
  console.log('[developer] 当前corners:', corners.value)
  
  await saveCorners()
  await saveConfig()
  
  isEditing.value = false
  savedCorners.value = null
  showToast('校准区域已保存')
  console.log('[developer] 保存完成，isEditing变为false')
}

async function checkConn() {
  try {
    console.log(`[developer] 尝试连接后端: ${baseUrl}`)
    const c = new AbortController()
    const t = setTimeout(() => c.abort(), 3000)
    const r = await fetch(`${baseUrl}/api/config`, { signal: c.signal })
    clearTimeout(t)
    connected.value = r.ok
    if (r.ok) {
      console.log('[developer] 后端API连接成功')
    } else {
      console.error('[developer] 后端API连接失败:', r.status)
    }
    return r.ok
  } catch (e) {
    console.error('[developer] 后端API连接异常:', e)
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
  if (!connected.value) {
    console.error('[developer] 未连接后端，无法保存校准区域')
    showToast('未连接后端，无法保存')
    return
  }
  try {
    console.log('[developer] 保存校准区域:', corners.value)
    const r = await fetch(`${baseUrl}/api/corners`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ corners: corners.value })
    })
    if (r.ok) {
      console.log('[developer] 校准区域保存成功')
    } else {
      console.error('[developer] 校准区域保存失败:', r.status)
      showToast('保存失败')
    }
  } catch (e) {
    console.error('[developer] 保存校准区域异常:', e)
    showToast('保存失败')
  }
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
      // 使用 Vue 响应式更新：深度合并
      // 首先更新顶级属性
      Object.assign(systemState, state)
      // 确保嵌套的 physiology 和 face 对象也被正确更新
      if (state.perception?.physiology) {
        systemState.perception.physiology = state.perception.physiology
      }
      if (state.perception?.face) {
        systemState.perception.face = state.perception.face
      }
      console.log('[developer] 系统状态更新:', { 
        hasPhysiology: !!state.perception?.physiology, 
        hasFace: !!state.perception?.face 
      })
    }
  })
  
  // ⭐ 初始化情绪图表
  initEmotionChart()
  
  // ⭐ 启动数据轮询
  await fetchPerceptionData()
  await fetchPersonData()
  await fetchCurrentModel()
  await fetchGameData()
  
  setInterval(fetchPerceptionData, 200)
  setInterval(fetchPersonData, 1000)
  setInterval(fetchGameData, 500)
  
  resize()
  requestAnimationFrame(draw)
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

/* ⭐ 语音状态样式 */
.sys-card.voice-card {
  border-color: #666;
}

.sys-card.voice-responding {
  border-color: #FF7222;
  background: rgba(255, 114, 34, 0.1);
  animation: pulse-orange 1.5s infinite;
}

.sys-card.voice-listening {
  border-color: #33B555;
  background: rgba(51, 181, 85, 0.1);
  animation: pulse-green 1s infinite;
}

.sys-card.voice-processing {
  border-color: #2196F3;
  background: rgba(33, 150, 243, 0.1);
  animation: pulse-blue 0.8s infinite;
}

.voice-desc {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.recording-indicator {
  color: #ff4444;
  animation: blink 1s infinite;
}

.playing-indicator {
  color: #33B555;
}

@keyframes pulse-orange {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 114, 34, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(255, 114, 34, 0); }
}

@keyframes pulse-green {
  0%, 100% { box-shadow: 0 0 0 0 rgba(51, 181, 85, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(51, 181, 85, 0); }
}

@keyframes pulse-blue {
  0%, 100% { box-shadow: 0 0 0 0 rgba(33, 150, 243, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(33, 150, 243, 0); }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
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

/* ⭐ 综合情绪与生理监测样式 */
.main-container{display:flex;min-height:calc(100vh - 200px);padding:12px;gap:12px;overflow-y:auto}
.left-panel{flex:0 0 65%;display:flex;flex-direction:column;gap:10px;overflow-y:auto}
.right-panel{flex:1;display:flex;flex-direction:column;gap:12px;overflow-y:auto}
.panel-card{background:linear-gradient(135deg,#151c2c,#1a2236);border-radius:12px;border:1px solid #232e44;overflow:hidden;display:flex;flex-direction:column}
.panel-header{padding:10px 16px;background:rgba(0,0,0,0.2);border-bottom:1px solid #232e44;display:flex;align-items:center;justify-content:space-between}
.panel-title{font-size:13px;font-weight:600;color:#64ffda;letter-spacing:0.5px}
.panel-body{padding:12px;display:flex;flex-direction:column;gap:12px}
.mini-card{background:rgba(0,0,0,0.3);border-radius:8px;padding:10px 12px;border:1px solid #232e44;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px}
.mini-card-title{font-size:10px;color:#6b7a94;text-transform:uppercase;letter-spacing:0.5px}
.mini-card-value{font-size:20px;font-weight:700;color:#fff}
.mini-card-value.heart{color:#EA4335}
.mini-card-value.hrr{color:#34A853}
.mini-card-value.slope{color:#4285F4}
.mini-card-sub{font-size:10px;color:#4a5570}
.row-3cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.person-info{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.info-item{background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;border:1px solid #232e44;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.info-label{font-size:10px;color:#6b7a94;text-transform:uppercase}
.info-value{font-size:16px;font-weight:600;color:#fff}
.info-conf{font-size:11px;color:#4a5570}
.info-sub{font-size:10px;color:#6b7a94;margin-left:auto}
.psychology-layout{display:flex;gap:12px}
.psych-left{flex:0 0 40%;display:flex;flex-direction:column;gap:8px}
.psych-right{flex:1;display:flex;flex-direction:column;gap:10px}
.emotion-chart-box{min-height:180px;background:#050a12;border-radius:8px;overflow:hidden;border:1px solid #232e44;padding:8px}
.emotion-chart-box canvas{width:100%!important;height:100%!important;max-height:180px}
.emotion-3cards{display:flex;gap:8px}
.emotion-item{flex:1;padding:8px;border-radius:8px;border:1px solid #232e44;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px}
.emotion-item.positive{background:rgba(52,168,83,0.15);border-color:#34A853}
.emotion-item.neutral{background:rgba(107,122,148,0.15);border-color:#6b7a94}
.emotion-item.negative{background:rgba(234,67,53,0.15);border-color:#EA4335}
.emotion-item-label{font-size:8px;color:#6b7a94;text-transform:uppercase}
.emotion-item-value{font-size:18px;font-weight:700}
.emotion-item.positive .emotion-item-value{color:#34A853}
.emotion-item.neutral .emotion-item-value{color:#6b7a94}
.emotion-item.negative .emotion-item-value{color:#EA4335}
.psych-bottom{display:flex;gap:8px}
.gate-button{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px;background:rgba(0,0,0,0.3);border:1px solid #374151;border-radius:10px;color:#6b7a94;font-size:10px;font-weight:500;cursor:pointer;transition:all 0.2s ease}
.gate-button:hover{background:rgba(55,65,81,0.5);border-color:#4b5563}
.gate-button.disabled{background:rgba(0,0,0,0.2);border-color:#1f2937;color:#374151}
.gate-label{font-size:9px;color:#6b7a94;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px}
.gate-status{display:flex;align-items:center;gap:5px}
.gate-dot{width:7px;height:7px;border-radius:50%}
.gate-dot-on{background:#34A853;box-shadow:0 0 8px rgba(52,168,83,0.5)}
.gate-dot-off{background:#4b5563}
.gate-status-text{font-size:10px;color:#6b7a94}
.gate-button.disabled .gate-status-text{color:#374151}
.emotion-card{flex:1;background:linear-gradient(135deg,#1a1f35,#252b42);border-radius:10px;border:1px solid #3b82f6;padding:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px}
.emotion-card-label{font-size:8px;color:#6b7a94;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px}
.emotion-card-value{font-size:18px;font-weight:700;color:#fff}
.emotion-card.positive{border-color:#34A853;background:linear-gradient(135deg,rgba(52,168,83,0.15),rgba(52,168,83,0.05))}
.emotion-card.positive .emotion-card-value{color:#34A853}
.emotion-card.negative{border-color:#EA4335;background:linear-gradient(135deg,rgba(234,67,53,0.15),rgba(234,67,53,0.05))}
.emotion-card.negative .emotion-card-value{color:#EA4335}
.emotion-card.neutral{border-color:#6b7a94;background:linear-gradient(135deg,rgba(107,122,148,0.15),rgba(107,122,148,0.05))}
.emotion-card.neutral .emotion-card-value{color:#6b7a94}
.cognitive-panel{display:flex;border:1px solid #232e44;border-radius:10px;overflow:hidden}
.game-stats-left{flex:0 0 40%;display:grid;grid-template-columns:repeat(2,1fr);grid-template-rows:repeat(2,1fr);gap:10px;padding:12px;background:rgba(0,0,0,0.2)}
.game-records-right{flex:1;display:flex;flex-direction:column;padding:12px;background:rgba(0,0,0,0.15);border-left:1px solid #232e44;min-height:200px}
.game-records-list{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:6px}
.game-records-list::-webkit-scrollbar{width:4px}
.game-records-list::-webkit-scrollbar-track{background:#0c1018}
.game-records-list::-webkit-scrollbar-thumb{background:#232e44}
.game-record-item{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:rgba(0,0,0,0.25);border-radius:6px;font-size:11px}
.game-record-hit{color:#34A853;font-weight:600}
.game-record-miss{color:#f59e0b;font-weight:600}
.game-record-error{color:#EA4335;font-weight:600}
.game-record-bomb{color:#EA4335;font-weight:600}
.game-record-time{color:#6b7a94}
.game-record-diff{color:#4285F4}
.game-record-score{color:#f59e0b;font-weight:700}
.dda-panel{display:flex;flex-direction:column;gap:10px;padding:10px}
.dda-section{background:#1a2236;border-radius:8px;padding:10px}
.dda-section-title{font-size:11px;color:#64ffda;margin-bottom:6px;font-weight:600}
.dda-item{display:flex;justify-content:space-between;padding:3px 0;font-size:11px}
.dda-label{color:#8892a4}
.dda-value{color:#e6edf3;font-family:monospace}
.dda-value.highlight{color:#ffd700;font-weight:bold;font-size:14px}
.status-bar{display:flex;align-items:center;gap:16px;padding:8px 12px;background:rgba(0,0,0,0.3);border-radius:8px;font-size:11px;color:#6b7a94}
.status-dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.status-dot.on{background:#34A853}
.status-dot.off{background:#555}
.model-toggle{display:flex;align-items:center;gap:8px;margin-left:auto}
.model-toggle-btn{padding:4px 10px;border-radius:4px;border:1px solid #3a5570;background:#0c1018;color:#6b7a94;cursor:pointer;font-size:10px;transition:all 0.2s}
.model-toggle-btn:hover{border-color:#64ffda;color:#64ffda}
.model-toggle-btn.active{background:#1e3a5f;border-color:#64ffda;color:#64ffda}

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

/* ⭐ 完整数据展示样式 */
.data-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}

.data-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  border: 1px solid #1e293b;
}

.data-label {
  font-size: 10px;
  color: #8892a4;
  text-transform: uppercase;
}

.data-value {
  font-size: 11px;
  color: #e6edf3;
  font-family: monospace;
}

.section-title {
  font-size: 11px;
  color: #64ffda;
  margin-top: 10px;
  margin-bottom: 6px;
  font-weight: 600;
}

/* 滚动条美化 */
.main-container::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.main-container::-webkit-scrollbar-track {
  background: #0c1018;
  border-radius: 4px;
}

.main-container::-webkit-scrollbar-thumb {
  background: #232e44;
  border-radius: 4px;
}

.main-container::-webkit-scrollbar-thumb:hover {
  background: #3a5570;
}

.left-panel::-webkit-scrollbar,
.right-panel::-webkit-scrollbar {
  width: 6px;
}

.left-panel::-webkit-scrollbar-track,
.right-panel::-webkit-scrollbar-track {
  background: transparent;
}

.left-panel::-webkit-scrollbar-thumb,
.right-panel::-webkit-scrollbar-thumb {
  background: #232e44;
  border-radius: 3px;
}

/* 页面主体滚动 */
.dev-page {
  overflow-y: auto;
}

.dev-page::-webkit-scrollbar {
  width: 10px;
}

.dev-page::-webkit-scrollbar-track {
  background: #0a0d14;
}

.dev-page::-webkit-scrollbar-thumb {
  background: #232e44;
  border-radius: 5px;
}

.dev-page::-webkit-scrollbar-thumb:hover {
  background: #3a5570;
}
</style>
