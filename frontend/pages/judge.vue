<template>
  <div class="judge-container">
    <div class="header">
      <h1>👁 屏幕识别结果</h1>
      <div class="status-badge" :class="connectionStatus">
        {{ connectionStatusText }}
      </div>
    </div>

    <div class="main-content">
      <div class="video-section">
        <h2>📹 摄像头预览</h2>
        <div class="video-container">
          <img :src="`http://${host}:8080/screen_video_feed`" alt="Camera Preview" />
          
          <div class="overlay-info">
            <div class="info-item">
              <span class="info-label">检测到人:</span>
              <span class="info-value" :class="{detected: screenState.hand_detected}">
                {{ screenState.hand_detected ? '是' : '否' }}
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">选中区域:</span>
              <span class="info-value">
                {{ screenState.selected_region || '无' }}
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">选择置信度:</span>
              <span class="info-value">
                {{ Math.round(screenState.selection_confidence * 100) }}%
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="status-section">
        <h2>📊 识别状态</h2>
        
        <div class="status-grid">
          <div class="status-card" :class="{active: screenState.hand_detected}">
            <div class="status-icon">👁</div>
            <div class="status-label">手遮挡检测</div>
            <div class="status-value">
              {{ screenState.hand_detected ? '已检测' : '未检测' }}
            </div>
          </div>

          <div class="status-card" :class="{active: screenState.selected_region}">
            <div class="status-icon">🎯</div>
            <div class="status-label">选中区域</div>
            <div class="status-value">
              {{ screenState.selected_region || '无' }}
            </div>
          </div>

          <div class="status-card" :class="{active: screenState.selection_confidence > 0.8}">
            <div class="status-icon">✓</div>
            <div class="status-label">选择确认</div>
            <div class="status-value">
              {{ screenState.selection_confidence > 0.8 ? '是' : '否' }}
            </div>
          </div>
        </div>
      </div>

      <div class="region-display">
        <h2>📍 区域显示</h2>
        
        <div class="regions-grid">
          <div 
            v-for="(region, key) in regions" 
            :key="key"
            class="region-item"
            :class="{selected: screenState.selected_region === key, detected: screenState.hand_detected}"
          >
            <div class="region-label">{{ region.label }}</div>
            <div class="region-indicator">
              <div class="indicator-dot" :class="{active: screenState.selected_region === key}"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const host = ref('')
const connectionStatus = ref('disconnected')
const screenState = ref({})

const regions = ref({
  red: { label: '红色按钮', x: 0.2, y: 0.7 },
  yellow: { label: '黄色按钮', x: 0.5, y: 0.7 },
  blue: { label: '蓝色按钮', x: 0.8, y: 0.7 },
  green: { label: '绿色按钮', x: 0.2, y: 0.7 },
  purple: { label: '紫色按钮', x: 0.5, y: 0.7 },
  orange: { label: '橙色按钮', x: 0.8, y: 0.7 }
})

const connectionStatusText = computed(() => {
  const statusMap = {
    'connected': '已连接',
    'disconnected': '未连接',
    'error': '连接错误'
  }
  return statusMap[connectionStatus.value] || '未知'
})

const fetchScreenState = async () => {
  try {
    const response = await fetch(`http://${host.value}:8080/api/screen_state`)
    screenState.value = await response.json()
    connectionStatus.value = 'connected'
  } catch (e) {
    console.error('获取屏幕状态失败:', e)
    connectionStatus.value = 'error'
  }
}

onMounted(() => {
  host.value = window.location.hostname
  
  fetchScreenState()
  setInterval(fetchScreenState, 500)
})

onUnmounted(() => {
})
</script>

<style scoped>
.judge-container {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  color: #ffffff;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  padding: 2rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.header h1 {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0;
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

.main-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
}

.video-section {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.video-section h2 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: #ffffff;
}

.video-container {
  position: relative;
  background: #000000;
  border-radius: 15px;
  overflow: hidden;
}

.video-container img {
  width: 100%;
  display: block;
}

.overlay-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.8);
  padding: 1rem;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.8rem;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.info-label {
  font-size: 0.9rem;
  color: #ffffff;
  opacity: 0.9;
}

.info-value {
  font-size: 1.1rem;
  font-weight: 600;
  color: #ffffff;
}

.info-value.detected {
  color: #10b981;
}

.info-value:not(.detected) {
  color: #ef4444;
}

.status-section {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.status-section h2 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: #ffffff;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
}

.status-card {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 15px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.8rem;
  transition: all 0.3s ease;
}

.status-card.active {
  background: rgba(16, 185, 129, 0.3);
  border-color: #10b981;
}

.status-icon {
  font-size: 2rem;
}

.status-label {
  font-size: 1rem;
  color: #ffffff;
  opacity: 0.9;
}

.status-value {
  font-size: 1.3rem;
  font-weight: 600;
  color: #ffffff;
}

.region-display {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.region-display h2 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: #ffffff;
}

.regions-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.region-item {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 15px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.8rem;
  transition: all 0.3s ease;
  border: 2px solid rgba(255, 255, 255, 0.3);
}

.region-item.selected {
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.3);
}

.region-item.detected {
  border-color: #10b981;
  box-shadow: 0 0 15px rgba(16, 185, 129, 0.5);
}

.region-label {
  font-size: 1.1rem;
  font-weight: 600;
  color: #ffffff;
}

.region-indicator {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.3);
  display: flex;
  justify-content: center;
  align-items: center;
}

.indicator-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.5);
}

.indicator-dot.active {
  background: #10b981;
}
</style>
