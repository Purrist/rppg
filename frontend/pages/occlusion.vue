<template>
  <div class="occlusion-container">
    <div class="header">
      <h1 class="title">基于视觉遮挡的无接触按钮选择</h1>
      <div class="status-badge" :class="connectionStatus">
        {{ connectionStatusText }}
      </div>
    </div>

    <div class="status-text-container">
      <h2 class="status-text">{{ statusText }}</h2>
    </div>

    <div class="main-content">
      <div class="buttons-section">
        <h3 class="section-title">选择按钮</h3>
        <div class="buttons-container">
          <div class="button-wrapper" v-for="button in buttons" :key="button.id">
            <button class="button" :class="button.id">
              {{ button.name }}
            </button>
            
            <!-- 进度环 -->
            <div class="progress-ring" v-if="occludedButton === button.id">
              <svg width="180" height="180">
                <circle
                  class="progress-ring-circle"
                  stroke="#fff"
                  fill="transparent"
                  r="86"
                  cx="90"
                  cy="90"
                  :style="getProgressStyle(progress)"
                />
              </svg>
              <div class="progress-text">{{ Math.round(progress * 100) }}%</div>
            </div>
          </div>
        </div>
      </div>

      <div class="camera-section">
        <h3 class="section-title">摄像头实时画面</h3>
        <div class="camera-container">
          <img v-if="host" :src="`http://${host}:8080/screen_video_feed`" alt="外接摄像头" class="camera-img" />
          <div v-else class="camera-placeholder">
            <div class="placeholder-content">
              <div class="placeholder-icon">📷</div>
              <div class="placeholder-text">摄像头连接中...</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="instructions-section">
      <h3 class="section-title">使用说明</h3>
      <ul class="instructions-list">
        <li>左手持手机对准电脑屏幕，确保手机摄像头能看到屏幕上的按钮</li>
        <li>右手伸到镜头前，遮挡屏幕上的某个按钮区域</li>
        <li>观察按钮上方的进度环，持续遮挡3秒直到进度环满</li>
        <li>进度环达到100%后，系统确认选择该按钮</li>
        <li>中途移开手，进度环会立即清零</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// 基本状态
const host = ref('')
const connectionStatus = ref('disconnected')
const screenState = ref({})

// 按钮配置
const buttons = ref([
  { id: 'button1', name: '按钮1', color: '#FFA500' },
  { id: 'button2', name: '按钮2', color: '#4CAF50' },
  { id: 'button3', name: '按钮3', color: '#2196F3' }
])

// 遮挡检测状态
const occludedButton = ref(null)
const progress = ref(0)
const statusText = ref('尚未选择')

// 配置参数
const CONFIRMATION_TIME = 3.0 // 确认选择所需的时间（秒）

// 计算连接状态文本
const connectionStatusText = computed(() => {
  const statusMap = {
    'connected': '已连接',
    'disconnected': '未连接',
    'error': '连接错误'
  }
  return statusMap[connectionStatus.value] || '未知'
})

// 计算进度环样式
const getProgressStyle = (progress) => {
  const radius = 86
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (progress / 1.0) * circumference
  
  return {
    strokeDasharray: `${circumference} ${circumference}`,
    strokeDashoffset: offset,
    transition: 'stroke-dashoffset 0.35s ease'
  }
}

// 获取屏幕状态
const fetchScreenState = async () => {
  try {
    const response = await fetch(`http://${host.value}:8080/api/screen_state`)
    const data = await response.json()
    screenState.value = data
    connectionStatus.value = 'connected'
    
    // 更新遮挡状态
    if (data.selected_region) {
      // 映射区域名称到按钮ID
      const regionMap = {
        'red': 'button1',
        'yellow': 'button2',
        'blue': 'button3'
      }
      
      const detectedButton = regionMap[data.selected_region] || null
      if (detectedButton) {
        occludedButton.value = detectedButton
        
        // 更新进度
        if (data.selection_confidence >= 1.0) {
          progress.value = 1.0
          statusText.value = `你正在选择：${buttons.value.find(b => b.id === detectedButton).name}`
        } else {
          progress.value = data.selection_confidence
          statusText.value = `正在选择：${buttons.value.find(b => b.id === detectedButton).name}`
        }
      }
    } else {
      // 没有检测到遮挡
      occludedButton.value = null
      progress.value = 0
      statusText.value = '尚未选择'
    }
  } catch (e) {
    console.error('获取屏幕状态失败:', e)
    connectionStatus.value = 'error'
  }
}

onMounted(() => {
  // 只在客户端mounted之后设置host，确保浏览器能正确处理MJPEG流
  host.value = window.location.hostname
  
  // 开始轮询屏幕状态
  fetchScreenState()
  const interval = setInterval(fetchScreenState, 100) // 10fps
  
  onUnmounted(() => {
    clearInterval(interval)
  })
})
</script>

<style scoped>
.occlusion-container {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  color: #ffffff;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  max-width: 1200px;
  margin-bottom: 2rem;
}

.title {
  font-size: 2rem;
  font-weight: 700;
  margin: 0;
  text-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}

.status-badge {
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 600;
}

.status-badge.connected {
  background: #10b981;
}

.status-badge.disconnected {
  background: #ef4444;
}

.status-badge.error {
  background: #f59e0b;
}

.status-text-container {
  text-align: center;
  margin-bottom: 2rem;
  width: 100%;
  max-width: 1200px;
}

.status-text {
  font-size: 1.8rem;
  font-weight: 600;
  color: #ffffff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.main-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
  width: 100%;
  max-width: 1200px;
  margin-bottom: 2rem;
}

.section-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin-bottom: 1.5rem;
  color: #ffffff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.buttons-section,
.camera-section,
.instructions-section {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 2rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  width: 100%;
}

.buttons-container {
  display: flex;
  justify-content: center;
  gap: 40px;
  flex-wrap: wrap;
}

.button-wrapper {
  position: relative;
  width: 200px;
  height: 120px;
}

.button {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 10px;
  font-size: 24px;
  font-weight: bold;
  color: white;
  cursor: pointer;
  transition: transform 0.2s ease;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.button:hover {
  transform: scale(1.05);
}

.button1 {
  background-color: #FFA500;
}

.button2 {
  background-color: #4CAF50;
}

.button3 {
  background-color: #2196F3;
}

/* 进度环样式 */
.progress-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 180px;
  height: 180px;
  pointer-events: none;
}

.progress-ring-circle {
  transform: rotate(-90deg);
  transform-origin: 50% 50%;
  stroke-width: 8;
  stroke-linecap: round;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 20px;
  font-weight: bold;
  color: white;
  text-shadow: 0 0 5px rgba(0, 0, 0, 0.5);
}

.camera-container {
  position: relative;
  background: #000;
  border-radius: 10px;
  overflow: hidden;
  width: 100%;
  max-width: 640px;
  margin: 0 auto;
}

.camera-img {
  width: 100%;
  display: block;
}

.camera-placeholder {
  width: 100%;
  height: 480px;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
}

.placeholder-content {
  text-align: center;
  color: #ffffff;
}

.placeholder-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.placeholder-text {
  font-size: 1.2rem;
  opacity: 0.8;
}

.instructions-section {
  max-width: 1200px;
  width: 100%;
}

.instructions-list {
  list-style-type: disc;
  padding-left: 2rem;
  font-size: 1.1rem;
  line-height: 1.8;
  color: #ffffff;
  opacity: 0.9;
}

.instructions-list li {
  margin-bottom: 1rem;
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .main-content {
    grid-template-columns: 1fr;
  }
  
  .buttons-container {
    gap: 20px;
  }
}
</style>