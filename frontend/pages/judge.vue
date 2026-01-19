<template>
  <!-- 页面容器，确保内容居中显示 -->
  <div class="page-container">
    <!-- 严格16:10比例的固定容器，所有内容都在这个容器内 -->
    <div class="fixed-ratio-container">
      <!-- 四个角的视觉定位点（用于摄像头定位） -->
      <div class="visual-marker top-left">
        <div class="marker-inner"></div>
      </div>
      <div class="visual-marker top-right">
        <div class="marker-inner"></div>
      </div>
      <div class="visual-marker bottom-left">
        <div class="marker-inner"></div>
      </div>
      <div class="visual-marker bottom-right">
        <div class="marker-inner"></div>
      </div>
      
      <!-- 内容包装器，所有内容都使用百分比宽高 -->
      <div class="content-wrapper">
        <div class="header">
          <h1>👁 屏幕识别结果</h1>
          <div class="status-badge" :class="connectionStatus">
            {{ connectionStatusText }}
          </div>
        </div>

        <div class="main-content">
          <!-- 阶段状态显示 -->
          <div class="stage-status">
            <h2>📋 识别阶段状态</h2>
            <div class="stage-list">
              <!-- 阶段 1: 视频输入稳定性 -->
              <div class="stage-item" :class="{active: videoStable}">
                <div class="stage-number">1</div>
                <div class="stage-content">
                  <div class="stage-label">视频输入稳定性</div>
                  <div class="stage-status-text">{{ videoStatus }}</div>
                </div>
              </div>

              <!-- 阶段 2: 目标区域检测 -->
              <div class="stage-item" :class="{active: regionsDetected}">
                <div class="stage-number">2</div>
                <div class="stage-content">
                  <div class="stage-label">目标区域检测</div>
                  <div class="stage-status-text">{{ regionStatus }}</div>
                </div>
              </div>

              <!-- 阶段 3: 手部检测 -->
              <div class="stage-item" :class="{active: handDetected}">
                <div class="stage-number">3</div>
                <div class="stage-content">
                  <div class="stage-label">手部检测</div>
                  <div class="stage-status-text">{{ handStatus }}</div>
                </div>
              </div>

              <!-- 阶段 4: 食指定位与区域归属 -->
              <div class="stage-item" :class="{active: fingerLocated}">
                <div class="stage-number">4</div>
                <div class="stage-content">
                  <div class="stage-label">食指定位</div>
                  <div class="stage-status-text">{{ fingerStatus }}</div>
                </div>
              </div>

              <!-- 阶段 5: 进度圆环 -->
              <div class="stage-item" :class="{active: progressActive}">
                <div class="stage-number">5</div>
                <div class="stage-content">
                  <div class="stage-label">进度确认</div>
                  <div class="stage-status-text">{{ progressStatus }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 摄像头预览 -->
          <div class="video-section">
            <h2>📹 摄像头预览</h2>
            <div class="video-container">
              <!-- 只在client mounted之后显示视频流，确保浏览器能正确处理MJPEG -->
              <img 
                v-if="host" 
                ref="cameraImg" 
                :src="videoSrc" 
                alt="手机摄像头" 
                class="camera-img"
                @error="handleVideoError"
                @load="handleVideoLoad"
              />
              <div v-else class="camera-placeholder">
                <div class="placeholder-content">
                  <div class="placeholder-icon">📷</div>
                  <div class="placeholder-text">摄像头连接中...</div>
                </div>
              </div>
              
              <div class="overlay-info">
                <div class="info-item">
                  <span class="info-label">当前游戏:</span>
                  <span class="info-value">{{ currentGame || '未检测到' }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">目标区域数:</span>
                  <span class="info-value">{{ targetRegions || 0 }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">当前指向:</span>
                  <span class="info-value">{{ currentPointing || '无' }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">连接状态:</span>
                  <span class="info-value" :class="connectionStatus">{{ connectionStatusText }}</span>
                </div>
                <div class="info-item" v-if="reconnectAttempts > 0">
                  <span class="info-label">重连次数:</span>
                  <span class="info-value">{{ reconnectAttempts }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 详细状态信息 -->
      <div class="detailed-status">
        <h2>📊 详细识别状态</h2>
        
        <div class="status-grid">
          <div class="status-card" :class="{active: screenState.regions_detected}">
            <div class="status-icon">🎯</div>
            <div class="status-label">区域检测</div>
            <div class="status-value">
              {{ screenState.regions_detected ? '已识别3个区域' : `已识别${screenState.detected_regions_count || 0}/3个区域` }}
            </div>
          </div>

          <div class="status-card" :class="{active: screenState.hand_detected}">
            <div class="status-icon">👋</div>
            <div class="status-label">手部检测</div>
            <div class="status-value">
              {{ screenState.hand_detected ? '已检测到手' : '未检测到手' }}
            </div>
          </div>

          <div class="status-card" :class="{active: screenState.index_finger_detected}">
            <div class="status-icon">👉</div>
            <div class="status-label">食指检测</div>
            <div class="status-value">
              {{ screenState.index_finger_detected ? '已检测到食指' : '未检测到食指' }}
            </div>
          </div>

          <div class="status-card" :class="{active: screenState.selected_region}">
            <div class="status-icon">📍</div>
            <div class="status-label">当前指向</div>
            <div class="status-value">
              {{ regionMap[screenState.selected_region] || '无' }}
            </div>
          </div>

          <div class="status-card" :class="{active: screenState.selection_confidence > 0}">
            <div class="status-icon">⏳</div>
            <div class="status-label">进度</div>
            <div class="status-value">
              {{ Math.round(screenState.selection_confidence * 100) }}%
            </div>
          </div>

          <div class="status-card">
            <div class="status-icon">🎮</div>
            <div class="status-label">当前游戏</div>
            <div class="status-value">
              {{ currentGame || '未检测到' }}
            </div>
          </div>
        </div>
      </div>

      <!-- 调试信息 -->
      <div class="debug-section">
        <h2>🔍 调试信息</h2>
        <div class="debug-content">
          {{ screenState.debug_info || '无调试信息' }}
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
const videoSrc = ref('')
const reconnectAttempts = ref(0)
const cameraImg = ref(null)
const reconnectTimeout = ref(null)
const maxReconnectAttempts = 10
const baseReconnectDelay = 1000 // 初始重连延迟1秒

// 区域映射：颜色到位置
const regionMap = {
  'red': '左',
  'yellow': '中',
  'blue': '右'
}

// 阶段状态计算

// 阶段 1: 视频输入稳定性
const videoStable = computed(() => {
  return connectionStatus.value === 'connected'
})

const videoStatus = computed(() => {
  return connectionStatus.value === 'connected' ? '视频稳定' : 
         connectionStatus.value === 'error' ? '视频断开，正在重连' : '正在连接视频'
})

// 阶段 2: 目标区域检测
const regionsDetected = computed(() => {
  return screenState.value.regions_detected || false
})

const regionStatus = computed(() => {
  if (screenState.value.regions_detected) {
    return '已识别到3个目标区域'
  } else {
    return `已识别${screenState.value.detected_regions_count || 0}/3个目标区域`
  }
})

// 阶段 3: 手部检测
const handDetected = computed(() => {
  return screenState.value.hand_detected || false
})

const handStatus = computed(() => {
  return screenState.value.hand_detected ? '已检测到手在画面内' : '未检测到手在画面内'
})

// 阶段 4: 食指定位与区域归属
const fingerLocated = computed(() => {
  return !!screenState.value.selected_region
})

const fingerStatus = computed(() => {
  if (!screenState.value.hand_detected) {
    return '未检测到手，无法定位食指'
  } else if (!screenState.value.index_finger_detected) {
    return '未检测到食指'
  } else if (screenState.value.selected_region) {
    return `食指指向${regionMap[screenState.value.selected_region] || '未知'}区域`
  } else {
    return '食指指向非目标区域'
  }
})

// 阶段 5: 进度圆环
const progressActive = computed(() => {
  return screenState.value.selection_confidence > 0
})

const progressStatus = computed(() => {
  const confidence = Math.round(screenState.value.selection_confidence * 100)
  if (!screenState.value.hand_detected) {
    return '未检测到手，禁止交互'
  } else if (confidence === 100) {
    return '进度确认完成'
  } else if (confidence > 0) {
    return `正在确认: ${confidence}%`
  } else {
    return '等待手指稳定指向'
  }
})

// 游戏信息
const currentGame = computed(() => {
  // 根据区域数量猜测当前游戏
  const regionCount = screenState.value.detected_regions_count || 0
  if (regionCount === 3) {
    return '打地鼠'
  } else {
    return '未检测到'
  }
})

const targetRegions = computed(() => {
  return screenState.value.regions_detected ? 3 : screenState.value.detected_regions_count || 0
})

const currentPointing = computed(() => {
  return regionMap[screenState.value.selected_region] || '无'
})

const connectionStatusText = computed(() => {
  const statusMap = {
    'connected': '已连接',
    'disconnected': '未连接',
    'error': '连接错误'
  }
  return statusMap[connectionStatus.value] || '未知'
})

// 视频重连函数
const reconnectVideo = () => {
  if (reconnectAttempts.value >= maxReconnectAttempts) {
    console.error('达到最大重连次数，停止重连')
    connectionStatus.value = 'disconnected'
    return
  }
  
  reconnectAttempts.value++
  console.log(`尝试重连视频流 (${reconnectAttempts.value}/${maxReconnectAttempts})`)
  
  // 使用时间戳作为查询参数，避免浏览器缓存
  const timestamp = new Date().getTime()
  videoSrc.value = `http://${host.value}:8080/screen_video_feed?t=${timestamp}`
  
  // 指数退避重连
  const delay = baseReconnectDelay * Math.pow(1.5, reconnectAttempts.value - 1)
  reconnectTimeout.value = setTimeout(() => {
    if (cameraImg.value && cameraImg.value.complete) {
      // 如果图像已完成加载，不需要重连
      handleVideoLoad()
    } else {
      // 否则继续重连
      reconnectVideo()
    }
  }, delay)
}

// 处理视频加载错误
const handleVideoError = () => {
  console.error('视频加载错误，尝试重连')
  connectionStatus.value = 'error'
  reconnectVideo()
}

// 处理视频加载成功
const handleVideoLoad = () => {
  console.log('视频加载成功')
  reconnectAttempts.value = 0
  connectionStatus.value = 'connected'
  
  // 清除任何待处理的重连计时器
  if (reconnectTimeout.value) {
    clearTimeout(reconnectTimeout.value)
    reconnectTimeout.value = null
  }
}

const fetchScreenState = async () => {
  if (!host.value) return
  
  try {
    const response = await fetch(`http://${host.value}:8080/api/screen_state`)
    const data = await response.json()
    screenState.value = data
    
    // 只有在API连接成功时才更新连接状态
    // 视频流状态由handleVideoLoad和handleVideoError管理
  } catch (e) {
    console.error('获取屏幕状态失败:', e)
  }
}

onMounted(() => {
  // 只在客户端mounted之后设置host，确保浏览器能正确处理MJPEG流
  host.value = window.location.hostname
  
  // 初始化视频源
  const timestamp = new Date().getTime()
  videoSrc.value = `http://${host.value}:8080/screen_video_feed?t=${timestamp}`
  
  fetchScreenState()
  setInterval(fetchScreenState, 200) // 提高刷新频率，获得更实时的状态
})

onUnmounted(() => {
  // 清理资源
  if (reconnectTimeout.value) {
    clearTimeout(reconnectTimeout.value)
    reconnectTimeout.value = null
  }
})
</script>

<style scoped>
.judge-container {
  background-color: #1a1a2e;
  width: 100%;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  overflow: hidden;
}

/* 页面容器，确保内容居中显示 */
.page-container {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #1a1a2e;
  padding: 20px;
  overflow: hidden;
}

/* 严格固定16:10比例的容器，不允许拉伸 */
.fixed-ratio-container {
  position: relative;
  width: 90vw;
  max-width: 1600px;
  /* 严格保持16:10比例：高度 = 宽度 * 10/16 */
  height: calc(90vw * 10 / 16);
  max-height: 1000px;
  min-width: 960px;
  min-height: 600px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 10px 50px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 内容包装器，所有内容都使用百分比宽高 */
.content-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 3%;
  overflow-y: auto;
}

/* 四个角的视觉定位点（用于摄像头视觉定位与透视校正） */
.visual-marker {
  position: absolute;
  width: 5%;
  height: 5%;
  z-index: 100;
  display: flex;
  justify-content: center;
  align-items: center;
}

.marker-inner {
  width: 60%;
  height: 60%;
  background-color: #000;
  border: 3px solid #fff;
  border-radius: 5px;
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 十字标记 */
.marker-inner::before, .marker-inner::after {
  content: '';
  position: absolute;
  background-color: #fff;
}

.marker-inner::before {
  width: 40%;
  height: 8%;
}

.marker-inner::after {
  width: 8%;
  height: 40%;
}

/* 定位点位置 - 固定在四个角落 */
.visual-marker.top-left {
  top: 2%;
  left: 2%;
}

.visual-marker.top-right {
  top: 2%;
  right: 2%;
  transform: rotate(90deg);
}

.visual-marker.bottom-left {
  bottom: 2%;
  left: 2%;
  transform: rotate(-90deg);
}

.visual-marker.bottom-right {
  bottom: 2%;
  right: 2%;
  transform: rotate(180deg);
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

.video-container img,
.video-container .camera-img {
  width: 100%;
  display: block;
}

.camera-placeholder {
  width: 100%;
  height: 100%;
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

/* 阶段状态样式 */
.stage-status {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
}

.stage-status h2 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: #ffffff;
}

.stage-list {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.stage-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 15px;
  transition: all 0.3s ease;
  border: 2px solid rgba(255, 255, 255, 0.2);
}

.stage-item.active {
  background: rgba(16, 185, 129, 0.3);
  border-color: #10b981;
}

.stage-number {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 1.1rem;
  font-weight: 700;
  color: #ffffff;
  flex-shrink: 0;
}

.stage-item.active .stage-number {
  background: #10b981;
  color: white;
}

.stage-content {
  flex: 1;
}

.stage-label {
  font-size: 1rem;
  font-weight: 600;
  color: #ffffff;
  margin-bottom: 0.25rem;
}

.stage-status-text {
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.8);
}

.stage-item.active .stage-status-text {
  color: #10b981;
}

/* 详细状态样式 */
.detailed-status {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
}

.detailed-status h2 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: #ffffff;
}

.detailed-status .status-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

/* 调试信息样式 */
.debug-section {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.debug-section h2 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: #ffffff;
}

.debug-content {
  background: rgba(0, 0, 0, 0.3);
  padding: 1rem;
  border-radius: 10px;
  font-family: monospace;
  font-size: 0.9rem;
  color: #ffffff;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

/* 覆盖信息样式优化 */
.overlay-info {
  grid-template-columns: 1fr;
  gap: 0.5rem;
}

/* 主内容布局 */
.main-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .detailed-status .status-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .detailed-status .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
