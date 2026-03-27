<template>
  <div class="home-page">
    <div class="welcome-banner">
      <div class="welcome-text">
        <h1>{{ greeting }}，张爷爷</h1>
        <p>{{ currentDate }} {{ currentWeekday }}  {{ currentTime }}</p>
        <div class="weather-widget">
          <div class="location">{{ city }}</div>
          <div class="weather-main">
            <span class="temp">{{ temperature }}°</span>
            <span class="weather-icon">{{ weatherIcon }}</span>
            <span class="weather">{{ weather }}</span>
          </div>
        </div>
      </div>
      <div class="akon-card">
          <div class="akon-header">
            <div class="akon-avatar">🤖</div>
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
        <div class="card-icon">❤️</div>
        <div class="card-info">
          <h3>生理信号监测</h3>
          <p>当前解析稳定，波动率正常</p>
        </div>
      </div>
      
      <div class="card training-summary" @click="handleNavigate('/learning')">
        <div class="card-icon">🧠</div>
        <div class="card-info">
          <h3>今日训练任务</h3>
          <p>色词识别挑战（待开始）</p>
        </div>
      </div>
    </div>

    <div class="quick-actions">
      <div class="action-btn call">视频通话</div>
      <div class="action-btn sos">紧急呼救</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'

const router = useRouter()
let socket = null
const backendConnected = ref(false)
const isListening = ref(false)

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

// 国内可用免费天气API（自动IP定位，无需Key）
async function fetchWeather() {
  try {
    const res = await fetch('https://uapis.cn/api/v1/misc/weather?lang=zh')
    const data = await res.json()
    console.log('Weather API response:', data)
    if (data.code === 0 && data.data) {
      city.value = data.data.city
      temperature.value = data.data.temperature
      weather.value = data.data.weather
      humidity.value = data.data.humidity
      weatherIcon.value = getWeatherIcon(data.data.weather_icon || '999')
    } else if (data.city) {
      // 直接返回数据的情况
      city.value = data.city
      temperature.value = data.temperature
      weather.value = data.weather
      humidity.value = data.humidity
      weatherIcon.value = getWeatherIcon(data.weather_icon || '999')
    } else {
      city.value = '获取失败'
      weatherIcon.value = '☁️'
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
  
  // 获取真实地理位置和天气数据
  fetchWeather()
  // 每10分钟刷新一次天气数据
  const weatherInterval = setInterval(fetchWeather, 10 * 60 * 1000)
  
  // 初始化Socket连接
  try {
    socket = io(`http://localhost:${FLASK_PORT}`, {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionAttempts: 3,
      timeout: 5000
    })
    
    socket.on('connect', () => {
      backendConnected.value = true
      console.log('后端连接成功')
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
  margin-bottom: 50px;
  flex-wrap: nowrap;
  width: 100%;
}

.weather-widget {
  padding: 20px 24px;
  background: #0f172a;
  color: #fff;
  border-radius: 16px;
  width: 100%;
  font-family: system-ui, sans-serif;
  display: flex;
  align-items: center;
  gap: 25px;
  margin-top: 0;
}

.location {
  font-size: 28px;
  font-weight: 600;
  flex-shrink: 0;
}

.weather-main {
  display: flex;
  align-items: center;
  gap: 20px;
  flex: 1;
}

.weather-icon {
  font-size: 48px;
}

.temp {
  font-size: 56px;
  font-weight: 700;
}

.weather {
  font-size: 28px;
  font-weight: 500;
}

.humidity {
  font-size: 12px;
  opacity: 0.7;
  flex-shrink: 0;
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
  min-height: 250px;
  height: 100%;
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

.main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 50px; }
.card { background: #FFF; border: 2px solid #F0F0F0; border-radius: 35px; padding: 40px; display: flex; align-items: center; gap: 25px; cursor: pointer; transition: 0.3s; }
.card:hover { border-color: #FF7222; background: #FFF9F6; }
.card-icon { font-size: 50px; }
.card-info h3 { font-size: 28px; color: #333; }
.card-info p { font-size: 18px; color: #777; margin-top: 5px; }

.quick-actions { margin-top: 40px; display: flex; gap: 30px; }
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
