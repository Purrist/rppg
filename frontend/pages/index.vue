<template>
  <div class="home-page">
    <div class="welcome-banner">
      <div class="welcome-text">
        <h1>{{ greeting }}，张爷爷</h1>
        <p>{{ currentDate }} {{ currentWeekday }}  {{ currentTime }}</p>
        <div class="weather-widget">
          <div class="weather-top">
            <span class="location">{{ city }}</span>
            <span class="temp">{{ temperature }}°</span>
            <span class="wind" v-if="windPower">{{ windDirection }} {{ windPower }}级</span>
          </div>
          <div class="weather-bottom">
            <div class="weather-bottom-left">
              <span class="weather-icon">{{ weatherIcon }}</span>
              <span class="weather">{{ weather }}</span>
            </div>
            <span class="humidity">空气湿度 {{ humidity }}%</span>
          </div>
        </div>
      </div>
      <div class="akon-card">
          <div class="akon-header">
            <img src="/akon.svg" alt="阿康" class="akon-avatar" />
            <button class="voice-btn" @click="startVoiceInput">
              🎤 说话
            </button>
          </div>
          <div class="akon-tips">
            <div class="tip" @click="handleTipClick(currentTip)">
              {{ currentTip }}
            </div>
          </div>
        </div>
    </div>
    
    <div class="main-grid">
      <div class="card health-summary" @click="handleNavigate('/health')">
        <div class="flip-wrapper" :class="{ flipped: isFlipped }">
          <div class="flip-content front">
            <div class="flip-header">心率 <span class="flip-value">{{ realTimeData.heartRate }} bpm</span></div>
            <canvas ref="hrCanvas" class="flip-canvas"></canvas>
          </div>
          <div class="flip-content back">
            <div class="flip-header">呼吸率 <span class="flip-value">{{ realTimeData.breathRate }} bpm</span></div>
            <canvas ref="brCanvas" class="flip-canvas"></canvas>
          </div>
        </div>
      </div>
      
      <div class="card training-summary" @click="handleNavigate('/learning')">
        <div class="card-icon">🧠</div>
        <div class="card-info">
          <h3>今日训练任务</h3>
          <div class="training-progress">
            <div class="progress-bar-container">
              <div class="progress-bar-fill" style="width: 0%"></div>
            </div>
            <span class="progress-text">0/3</span>
          </div>
        </div>
      </div>
    </div>

    <div class="quick-actions">
      <div class="action-btn call" @click="handleNavigate('/call')">视频通话</div>
      <div class="action-btn sos" @click="handleNavigate('/call/nurse')">紧急呼救</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, nextTick, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { subscribe, getState, initStore } from '../core/systemStore.js'

const router = useRouter()
let socket = null
let unsubscribe = null
const backendConnected = ref(false)
const isListening = ref(false)

const getHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const PORT = 5000
const baseUrl = `http://${getHost()}:${PORT}`

// 翻转相关
const isFlipped = ref(false)
let flipInterval = null
let waveInterval = null

// Canvas引用
const hrCanvas = ref(null)
const brCanvas = ref(null)

// 实时数据
const realTimeData = ref({
  heartRate: '--',
  breathRate: '--',
  hrWave: [],
  brWave: []
})

// 系统状态（从后端SystemCore同步，完整结构像developer.vue一样）
const systemState = reactive({
  perception: {
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
    face: {
      au: {},
      fer: {},
      fusion: {}
    }
  }
})

// 便捷的计算属性获取心率和呼吸率
const heartRate = computed(() => {
  const hr = systemState.perception?.physiology?.raw?.hr
  return (hr !== undefined && hr !== null && hr > 0) ? Math.round(hr) : '--'
})

const breathRate = computed(() => {
  const br = systemState.perception?.physiology?.raw?.br
  return (br !== undefined && br !== null && br > 0) ? Math.round(br) : '--'
})

// 用心率数值生成简单波形
function generateSimpleWave(currentValue, waveArray, baseValue) {
  // 添加新值
  if (currentValue && currentValue !== '--') {
    // 用简单的正弦波模拟，基于当前心率
    const wave = baseValue + Math.sin(Date.now() / 500) * 5
    waveArray.push(wave)
  } else {
    waveArray.push(0)
  }
  
  // 保持数组长度
  if (waveArray.length > 50) {
    waveArray.shift()
  }
}

// 监听系统状态变化
function updateFromSystemState(state) {
  console.log('收到系统状态:', state)
  
  // 完整更新 systemState，像developer.vue一样
  if (state) {
    Object.assign(systemState, state)
    if (state.perception?.physiology) {
      systemState.perception.physiology = state.perception.physiology
    }
    if (state.perception?.face) {
      systemState.perception.face = state.perception.face
    }
  }
  
  // 更新实时数据
  realTimeData.value.heartRate = heartRate.value
  realTimeData.value.breathRate = breathRate.value
  
  // 从 systemState 获取相位数据绘制波形
  if (state?.perception?.physiology?.raw?.hph !== undefined && 
      state?.perception?.physiology?.raw?.hph !== null) {
    hrPhaseWave.value.push(state.perception.physiology.raw.hph)
    if (hrPhaseWave.value.length > 300) {
      hrPhaseWave.value.shift()
    }
  }
  
  if (state?.perception?.physiology?.raw?.bph !== undefined && 
      state?.perception?.physiology?.raw?.bph !== null) {
    brPhaseWave.value.push(state.perception.physiology.raw.bph)
    if (brPhaseWave.value.length > 300) {
      brPhaseWave.value.shift()
    }
  }
  
  // 立即绘制
  nextTick(() => {
    drawPhaseWave(hrCanvas.value, hrPhaseWave.value, '#FF4D4D')
    drawPhaseWave(brCanvas.value, brPhaseWave.value, '#33B555')
  })
}

// 健康数据引用
const healthData = ref({
  time: 0,
  hr: 72,
  br: 16,
  hph: 0,
  bph: 0,
  is_human: 0,
  distance: 0,
  distance_valid: 0,
  signal_state: 'INIT',
  hr_valid: false,
  br_valid: false,
  phase_valid: false,
  hrr: 0,
  hrr_label: '',
  slope: 0,
  slope_label: '',
  brv: 0,
  brv_label: '',
  brel: 0,
  brel_label: '',
  cr: 0,
  cr_label: '',
  plv: 0.9,
  plv_label: ''
})

// 相位波形数据（保存300个点，约1分钟数据，每200ms一个点）
const hrPhaseWave = ref([])
const brPhaseWave = ref([])

const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  const host = window.location.hostname
  return host || 'localhost'
}

const BACKEND_PORT = 5000
const HLKK_PORT = 5020
const backendHost = getBackendHost()
const backendUrl = `http://${backendHost}:${BACKEND_PORT}`
const hlkkUrl = `http://${backendHost}:${HLKK_PORT}`

async function fetchHealthJson() {
  try {
    const res = await fetch(`${backendUrl}/core/health.json?` + Date.now())
    if (res.ok) {
      const data = await res.json()
      healthData.value = data
      
      // 更新实时数据
      realTimeData.value.heartRate = (data.hr !== undefined && data.hr !== null && data.hr > 0) ? Math.round(data.hr) : '--'
      realTimeData.value.breathRate = (data.br !== undefined && data.br !== null && data.br > 0) ? Math.round(data.br) : '--'
      
      // 收集相位数据绘制波形
      if (data.hph !== null && data.hph !== undefined) {
        hrPhaseWave.value.push(data.hph)
        if (hrPhaseWave.value.length > 300) {
          hrPhaseWave.value.shift()
        }
      }
      
      if (data.bph !== null && data.bph !== undefined) {
        brPhaseWave.value.push(data.bph)
        if (brPhaseWave.value.length > 300) {
          brPhaseWave.value.shift()
        }
      }
      
      // 立即绘制
      nextTick(() => {
        drawPhaseWave(hrCanvas.value, hrPhaseWave.value, '#FF4D4D')
        drawPhaseWave(brCanvas.value, brPhaseWave.value, '#33B555')
      })
    }
  } catch (e) {
    console.warn('[Index] 无法读取 health.json:', e.message)
  }
}

async function fetchRealTimeData() {
  try {
    await fetchHealthJson()
  } catch (e) {
    console.error('获取数据失败:', e.message)
  }
}

// 绘制相位波形（hph和bph范围0-2π）
function drawPhaseWave(canvasRef, waveData, color) {
  const canvas = canvasRef
  if (!canvas) return
  
  const ctx = canvas.getContext('2d')
  const width = canvas.width || 300
  const height = canvas.height || 40
  
  ctx.clearRect(0, 0, width, height)
  
  let dataToDraw = waveData
  if (!dataToDraw || dataToDraw.length < 2) {
    // 如果没有数据，画一个简单的横线
    dataToDraw = []
    for (let i = 0; i < 10; i++) {
      dataToDraw.push(Math.PI)
    }
  }
  
  ctx.beginPath()
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  
  // 相位范围是0-2π，绘制正弦波
  dataToDraw.forEach((phase, i) => {
    const x = (i / (dataToDraw.length - 1)) * width
    // 相位到正弦值：值范围 -1 到 1，转换为画布坐标
    const normalizedSin = Math.sin(phase)
    const y = height/2 - normalizedSin * height * 0.35
    
    if (i === 0) {
      ctx.moveTo(x, y)
    } else {
      ctx.lineTo(x, y)
    }
  })
  
  ctx.stroke()
}

function drawWave(canvasRef, waveData, color) {
  const canvas = canvasRef
  if (!canvas) return
  
  const ctx = canvas.getContext('2d')
  const width = canvas.width || 300
  const height = canvas.height || 40
  
  ctx.clearRect(0, 0, width, height)
  
  let dataToDraw = waveData
  if (!dataToDraw || dataToDraw.length < 2) {
    // 如果没有数据，画一个简单的横线
    dataToDraw = []
    for (let i = 0; i < 10; i++) {
      dataToDraw.push(0)
    }
  }
  
  const min = Math.min(...dataToDraw)
  const max = Math.max(...dataToDraw)
  const range = max - min || 1
  
  ctx.beginPath()
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  
  dataToDraw.forEach((val, i) => {
    const x = (i / (dataToDraw.length - 1)) * width
    const y = height - ((val - min) / range) * height * 0.7 - height * 0.15
    if (i === 0) {
      ctx.moveTo(x, y)
    } else {
      ctx.lineTo(x, y)
    }
  })
  
  ctx.stroke()
}

function initCanvas() {
  nextTick(() => {
    if (hrCanvas.value) {
      hrCanvas.value.width = 300
      hrCanvas.value.height = 40
    }
    if (brCanvas.value) {
      brCanvas.value.width = 300
      brCanvas.value.height = 40
    }
  })
}

// 动态提示
const tips = ref([
  '今天感觉怎么样？',
  '需要查看健康数据吗？',
  '想玩个小游戏吗？',
  '想听点音乐放松一下吗？'
])

// 当前显示的提示
const currentTip = ref(tips.value[0])

// 实时日期和时间
const currentDate = ref('')
const currentWeekday = ref('')
const currentTime = ref('')

// 真实地理位置和天气数据
const city = ref('加载中...')
const temperature = ref('--')
const weather = ref('...')
const humidity = ref('--')
const windDirection = ref('')
const windPower = ref('')
const windIcon = ref('')
const weatherIcon = ref('')
const greeting = ref('早安')

// 更新日期和时间
function updateDateTime() {
  const now = new Date()
  // 日期：2026年3月27日
  currentDate.value = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
  // 星期
  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  currentWeekday.value = weekdays[now.getDay()]
  // 时间：19:35
  const hours = String(now.getHours()).padStart(2, '0')
  const minutes = String(now.getMinutes()).padStart(2, '0')
  currentTime.value = `${hours}:${minutes}`
  
  // 更新问候语
  const hour = now.getHours()
  if (hour < 6) {
    greeting.value = '晚安'
  } else if (hour < 12) {
    greeting.value = '早上好'
  } else if (hour < 18) {
    greeting.value = '中午好'
  } else {
    greeting.value = '晚上好'
  }
}

// 根据天气代码获取天气图标
function getWeatherIcon(iconCode) {
  const iconMap = {
    '100': '☀️', // 晴
    '101': '⛅', // 多云
    '102': '⛅', // 少云
    '103': '⛅', // 晴间多云
    '104': '☁️', // 阴
    '200': '🌫️', // 有风
    '201': '🌬️', // 平静
    '202': '🌬️', // 微风
    '203': '💨', // 和风
    '204': '💨', // 清风
    '205': '🌪️', // 强风
    '206': '🌪️', // 疾风
    '207': '🌪️', // 大风
    '208': '🌪️', // 烈风
    '209': '🌀', // 狂风
    '210': '🌀', // 暴风
    '211': '🌀', // 台风
    '212': '🌀', // 飓风
    '300': '🌧️', // 阵雨
    '301': '🌧️', // 强阵雨
    '302': '⛈️', // 雷阵雨
    '303': '⛈️', // 强雷阵雨
    '304': '⛈️', // 雷阵雨伴有冰雹
    '305': '🌦️', // 小雨
    '306': '🌦️', // 中雨
    '307': '🌧️', // 大雨
    '308': '🌧️', // 极端降雨
    '309': '🌧️', // 毛毛雨
    '310': '🌧️', // 暴雨
    '311': '🌧️', // 大暴雨
    '312': '🌧️', // 特大暴雨
    '400': '🌨️', // 小雪
    '401': '❄️', // 中雪
    '402': '❄️', // 大雪
    '403': '❄️', // 暴雪
    '404': '🌨️', // 雨夹雪
    '405': '🌨️', // 雨雪天气
    '406': '🌨️', // 阵雨夹雪
    '407': '🌨️', // 阵雪
    '500': '🌫️', // 薄雾
    '501': '🌫️', // 雾
    '502': '🌫️', // 霾
    '503': '🌫️', // 扬沙
    '504': '🌫️', // 浮尘
    '507': '🌫️', // 沙尘暴
    '508': '🌫️', // 强沙尘暴
    '999': '☁️' // 未知
  }
  return iconMap[iconCode] || '☁️'
}

function saveWeatherCache(data) {
  const cache = {
    city: data.city,
    temperature: data.temperature,
    weather: data.weather,
    humidity: data.humidity,
    windDirection: data.windDirection,
    windPower: data.windPower,
    weatherIcon: data.weatherIcon,
    timestamp: Date.now()
  }
  localStorage.setItem('weatherCache', JSON.stringify(cache))
}

function loadWeatherCache() {
  const cacheStr = localStorage.getItem('weatherCache')
  if (!cacheStr) return null
  try {
    const cache = JSON.parse(cacheStr)
    // 缓存有效期5分钟
    if (Date.now() - cache.timestamp < 5 * 60 * 1000) {
      return cache
    }
    return null
  } catch (e) {
    return null
  }
}

// 国内可用免费天气API（自动IP定位，无需Key）
async function fetchWeather(forceRefresh = false) {
  if (!forceRefresh) {
    const cache = loadWeatherCache()
    if (cache) {
      city.value = cache.city
      temperature.value = cache.temperature
      weather.value = cache.weather
      humidity.value = cache.humidity
      windDirection.value = cache.windDirection
      windPower.value = cache.windPower
      weatherIcon.value = cache.weatherIcon
      console.log('[Weather] 使用缓存数据')
      return
    }
  }
  
  try {
    const res = await fetch('https://uapis.cn/api/v1/misc/weather?lang=zh')
    const data = await res.json()
    console.log('Weather API response:', data)
    let result = null
    
    if (data.code === 0 && data.data) {
      city.value = data.data.city
      temperature.value = data.data.temperature
      weather.value = data.data.weather
      humidity.value = data.data.humidity
      windDirection.value = data.data.wind_direction || ''
      let rawWindPower = data.data.wind_power || ''
      if (rawWindPower) {
        rawWindPower = rawWindPower.replace(/级$/, '')
      }
      windPower.value = rawWindPower
      weatherIcon.value = getWeatherIcon(data.data.weather_icon || '999')
      result = {
        city: data.data.city,
        temperature: data.data.temperature,
        weather: data.data.weather,
        humidity: data.data.humidity,
        windDirection: data.data.wind_direction || '',
        windPower: rawWindPower,
        weatherIcon: weatherIcon.value
      }
    } else if (data.city) {
      city.value = data.city
      temperature.value = data.temperature
      weather.value = data.weather
      humidity.value = data.humidity
      windDirection.value = data.wind_direction || ''
      let rawWindPower = data.wind_power || ''
      if (rawWindPower) {
        rawWindPower = rawWindPower.replace(/级$/, '')
      }
      windPower.value = rawWindPower
      weatherIcon.value = getWeatherIcon(data.weather_icon || '999')
      result = {
        city: data.city,
        temperature: data.temperature,
        weather: data.weather,
        humidity: data.humidity,
        windDirection: data.wind_direction || '',
        windPower: rawWindPower,
        weatherIcon: weatherIcon.value
      }
    } else {
      city.value = '获取失败'
      weatherIcon.value = '☁️'
    }
    
    if (result) {
      saveWeatherCache(result)
    }
  } catch (e) {
    city.value = '网络异常'
    weatherIcon.value = '☁️'
    console.error(e)
  }
}

// Flask 后端端口
const FLASK_PORT = 5000

// 初始化
onMounted(() => {
  // 更新日期时间
  updateDateTime()
  const timer = setInterval(updateDateTime, 1000)
  
  // 动态更新提示
  const tipInterval = setInterval(() => {
    const currentIndex = tips.value.indexOf(currentTip.value)
    const nextIndex = (currentIndex + 1) % tips.value.length
    currentTip.value = tips.value[nextIndex]
  }, 10000)
  
  // 获取真实地理位置和天气数据（优先使用缓存）
  fetchWeather()
  // 每10分钟强制刷新一次天气数据
  const weatherInterval = setInterval(() => fetchWeather(true), 10 * 60 * 1000)
  
  // 初始化Canvas
  initCanvas()
  
  // 自动翻转
  flipInterval = setInterval(() => {
    isFlipped.value = !isFlipped.value
  }, 8000)
  
  // 波形流畅更新
  waveInterval = setInterval(() => {
    fetchHealthJson()
  }, 200)
  
  // 初始化Socket连接
  try {
    socket = io(baseUrl, {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionAttempts: 3,
      timeout: 5000
    })
    
    socket.on('connect', () => {
      backendConnected.value = true
      console.log('后端连接成功')
      // 初始化store
      initStore(socket)
      // 订阅状态变化
      unsubscribe = subscribe(updateFromSystemState)
    })
    
    socket.on('disconnect', () => {
      backendConnected.value = false
      console.log('后端连接断开')
    })
    
    socket.on('connect_error', (error) => {
      backendConnected.value = false
      console.error('后端连接失败:', error)
    })
    
    // 监听导航事件
    socket.on('navigate_to', (data) => {
      router.push(data.page)
    })
    
    // 语音状态
    socket.on('voice_status', (data) => {
      if (data.status === 'listening') {
        isListening.value = true
      } else {
        isListening.value = false
      }
    })
  } catch (e) {
    console.error('Socket初始化失败', e)
  }
  
  return () => {
    clearInterval(timer)
    clearInterval(tipInterval)
    clearInterval(weatherInterval)
    if (flipInterval) clearInterval(flipInterval)
    if (waveInterval) clearInterval(waveInterval)
    if (unsubscribe) unsubscribe()
    if (socket) socket.disconnect()
  }
})



// 统一导航（带降级处理）
const handleNavigate = (page) => {
  if (backendConnected.value && socket) {
    socket.emit('navigate', { page, source: 'user' })
  } else {
    // 后端未连接，降级为本地导航
    router.push(page)
  }
}

// 处理提示点击
const handleTipClick = (tip) => {
  console.log('用户点击了提示:', tip)
  // 这里可以根据提示内容执行不同的操作
  if (tip.includes('健康')) {
    handleNavigate('/health')
  } else if (tip.includes('游戏')) {
    handleNavigate('/learning')
  } else if (tip.includes('音乐')) {
    handleNavigate('/entertainment')
  }
}

// 开始语音输入
const startVoiceInput = () => {
  // 无论后端是否连接，都打开Akon面板并开始录音
  // 通过全局事件触发app组件打开Akon面板并开始录音
  if (window && window.dispatchEvent) {
    window.dispatchEvent(new CustomEvent('openAkon', {
      detail: { startRecording: true }
    }))
  }
  
  console.log('打开Akon面板并开始录音')
}
</script>

<style scoped>
.home-page { padding: 80px 40px 40px; }
.welcome-banner {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
  gap: 30px;
  margin-top: -40px;
  margin-bottom: 30px;
  flex-wrap: nowrap;
  width: 100%;
}

.weather-widget {
  padding: 16px 20px;
  background: #0f172a;
  color: #fff;
  border-radius: 16px;
  width: 100%;
  font-family: system-ui, sans-serif;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 0;
}

.weather-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 16px;
}

.weather-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-top: 8px;
}

.weather-bottom-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.right-align {
  margin-left: auto;
}

.location {
  font-size: 26px;
  font-weight: 600;
}

.weather-icon {
  font-size: 40px;
}

.temp {
  font-size: 46px;
  font-weight: 700;
}

.humidity {
  font-size: 24px;
  font-weight: 500;
  color: #fff;
}

.weather {
  font-size: 26px;
  font-weight: 500;
}

.wind {
  font-size: 26px;
  font-weight: 500;
  color: #fff;
}

.welcome-text {
  flex: 0 0 45%;
  min-width: 0;
  margin-top: -10px;
}
.welcome-text h1 { font-size: 48px; color: #333; margin: 0; width: 100%; margin-bottom: 20px; }
.welcome-text p { font-size: 22px; color: #888; margin-top: 0; margin-bottom: 20px; width: 100%; }
.akon-card {
  background: #FFF;
  border: 2px solid #E0E0E0;
  border-radius: 35px;
  padding: 30px;
  width: 406px;
  transition: all 0.3s ease;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 260px;
  height: 270px;
}
.akon-card:hover {
  border-color: #D0D0D0;
  transform: translateY(-2px);
}
.akon-header {
  display: flex;
  align-items: center;
  gap: 40px;
  margin-bottom: 0px;
  flex-wrap: wrap;
  justify-content: center;
}
.akon-avatar {
  font-size: 90px;
  animation: wave 2s infinite ease-in-out;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 0px;
}
@keyframes wave {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}
.voice-btn {
  width: 120px;
  height: 80px;
  background: #4A90E2;
  color: #FFF;
  border: none;
  border-radius: 25px;
  font-size: 24px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-direction: column;
}
.voice-btn:hover {
  background: #357ABD;
  transform: scale(1.05);
}
.voice-btn:active {
  transform: scale(0.98);
}
.tip {
  background: #F5F5F5;
  border: 1px solid #E0E0E0;
  border-radius: 20px;
  padding: 12px 16px;
  font-size: 22px;
  color: #666;
  cursor: pointer;
  transition: all 0.3s;
  text-align: center;
  line-height: 1.4;
  word-wrap: break-word;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: -10px;
}
.tip:hover {
  background: #E8E8E8;
  color: #333;
  transform: scale(1.02);
}

.main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 30px; }
.card { background: #FFF; border: 2px solid #F0F0F0; border-radius: 35px; padding: 20px 25px; display: flex; align-items: center; gap: 25px; cursor: pointer; transition: 0.3s; position: relative; overflow: hidden; perspective: 1000px; }
.card:hover { border-color: #FF7222; background: #FFF9F6; }
.card-icon { font-size: 50px; }
.card-info h3 { font-size: 28px; color: #333; }
.card-info p { font-size: 18px; color: #777; margin-top: 5px; }

.training-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

.progress-bar-container {
  flex: 1;
  height: 12px;
  background: #E5E7EB;
  border-radius: 6px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #0D9488, #10B981);
  border-radius: 6px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 18px;
  font-weight: 600;
  color: #0D9488;
  min-width: 40px;
}

/* 翻转卡片样式 */
.flip-wrapper {
  width: 100%;
  position: relative;
  transition: transform 0.6s;
  transform-style: preserve-3d;
}
.flip-wrapper.flipped {
  transform: rotateY(180deg);
}
.flip-content {
  width: 100%;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}
.flip-content.back {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  transform: rotateY(180deg);
}
.flip-header {
  font-size: 22px;
  color: #333;
  line-height: 1.3;
}
.flip-header .flip-value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
  margin-left: 15px;
}
.flip-canvas {
  width: 100%;
  height: 40px;
  margin-top: 8px;
  display: block;
}

.quick-actions { margin-top: 30px; display: flex; gap: 30px; }
.action-btn { flex: 1; height: 120px; border-radius: 30px; display: flex; align-items: center; justify-content: center; font-size: 30px; font-weight: bold; color: #FFF; cursor: pointer; }
.call { background: #33B555; }
.sos { background: #FF4D4D; }

@media (max-width: 768px) {
  .welcome-banner {
    flex-direction: column;
    align-items: flex-start;
  }
  .weather-widget {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  .weather-main {
    width: 100%;
  }
  .akon-card {
    width: 100%;
    max-width: 400px;
  }
}
</style>
