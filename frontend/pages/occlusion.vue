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
      
      <!-- 页面内容容器，所有内容都使用百分比宽度 -->
      <div class="content-wrapper">
        <!-- 顶部状态栏 -->
        <div class="top-status">
          <h1 class="page-title">基于视觉遮挡的无接触按钮选择交互</h1>
          <div class="status-bar">
            <div class="status-item">
              <span class="status-label">当前指向:</span>
              <span class="status-value">{{ currentPointing }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">交互结果:</span>
              <span class="status-value" :class="resultClass">{{ resultText }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">区域检测:</span>
              <span class="status-value" :class="regionsDetected ? 'detected' : 'not-detected'">
                {{ regionsDetected ? '✓ 已识别三个区域' : `✗ 已识别 ${detectedRegionsCount}/3 个区域` }}
              </span>
            </div>
            <div class="status-item">
              <span class="status-label">手检测:</span>
              <span class="status-value" :class="detectedHand ? 'detected' : 'not-detected'">
                {{ detectedHand ? '✓ 已检测' : '✗ 未检测' }}
              </span>
            </div>
            <div class="status-item">
              <span class="status-label">食指检测:</span>
              <span class="status-value" :class="detectedIndexFinger ? 'detected' : 'not-detected'">
                {{ detectedIndexFinger ? '✓ 已检测' : '✗ 未检测' }}
              </span>
            </div>
            <div class="status-badge" :class="connectionStatus">
              {{ connectionStatusText }}
            </div>
          </div>
          <!-- 调试信息 -->
          <div class="debug-info">
            {{ debugInfo }}
          </div>
        </div>

        <!-- 游戏区域 -->
        <div class="game-container">
          <h2 class="game-title">投影式认知训练交互</h2>
          
          <div class="game-area">
            <div class="mole-holes">
              <div 
                v-for="hole in holes" 
                :key="hole.id" 
                class="mole-hole"
                :class="{ 'active': hole.active }"
                :style="{ left: `${hole.x * 100}%` }"
              >
                <!-- 地鼠 -->
                <div class="mole" v-if="hole.active">
                  <div class="mole-head"></div>
                  <div class="mole-eyes"></div>
                </div>
                
                <!-- 进度圆环（扇形增长效果） -->
                <div class="progress-ring-wrapper" v-if="pointingHole === hole.id">
                  <svg class="progress-ring" viewBox="0 0 200 200">
                    <!-- 背景圆环 -->
                    <circle
                      class="progress-ring-bg"
                      stroke="rgba(255, 255, 255, 0.3)"
                      fill="transparent"
                      r="85"
                      cx="100"
                      cy="100"
                      stroke-width="15"
                    />
                    <!-- 进度圆环 -->
                    <circle
                      class="progress-ring-progress"
                      :stroke="progressColor"
                      fill="transparent"
                      r="85"
                      cx="100"
                      cy="100"
                      stroke-width="15"
                      :stroke-dasharray="circumference"
                      :stroke-dashoffset="progressOffset"
                      stroke-linecap="round"
                      transform="rotate(-90 100 100)"
                    />
                  </svg>
                  <div class="progress-text">{{ Math.round(progress * 100) }}%</div>
                </div>
                
                <!-- 命中/未命中指示器 -->
                <div class="hit-indicator" :class="hitIndicatorClass" v-if="showHitIndicator && lastHitHole === hole.id">
                  {{ hitIndicatorText }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 控制按钮 -->
        <div class="controls">
          <button class="control-button" @click="startGame" v-if="!gameStarted">
            开始测试
          </button>
          <button class="control-button" @click="restartGame" v-else>
            重新测试
          </button>
        </div>

        <!-- 手指检测状态 -->
        <div class="finger-status" v-if="gameStarted">
          <div class="status-item">
            <span class="status-label">手检测:</span>
            <span class="status-value" :class="detectedHand ? 'detected' : 'not-detected'">
              {{ detectedHand ? '✓ 已检测' : '✗ 未检测' }}
            </span>
          </div>
          <div class="status-item">
            <span class="status-label">食指检测:</span>
            <span class="status-value" :class="detectedIndexFinger ? 'detected' : 'not-detected'">
              {{ detectedIndexFinger ? '✓ 已检测' : '✗ 未检测' }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

// 基本状态
const host = ref('')
const connectionStatus = ref('disconnected')
const screenState = ref({})

// 16:10固定比例配置
const aspectRatio = ref('16:10') // 进度圆环配置
const circumference = ref(2 * Math.PI * 85) // 进度圆环周长
const progressOffset = computed(() => {
  return circumference.value - (progress.value * circumference.value)
})

// 游戏状态
const gameStarted = ref(false)
const hits = ref(0)
const activeMoleTimeout = ref(null)
const showHitIndicator = ref(false)
const lastHitHole = ref(null)
const hitResult = ref(null) // 'hit' or 'miss'

// 手势检测状态
const detectedHand = ref(false)
const detectedIndexFinger = ref(false)
const pointingHole = ref(null)
const progress = ref(0)
const progressStartTime = ref(null)
const progressInterval = ref(null)
const progressColor = ref('#4CAF50') // 进度圆环颜色

// 区域检测状态
const regionsDetected = ref(false)
const detectedRegionsCount = ref(0)
const debugInfo = ref('初始化中...')

// 交互状态
const currentPointing = ref('无')
const resultText = ref('等待开始')
const resultClass = ref('')

// 配置参数
const CONFIRMATION_TIME = 1.5 // 确认选择所需的时间（秒），从3秒缩短到1.5秒
const MOLE_STAY_TIME = 5000 // 地鼠停留时间（毫秒），固定5秒
const MOLE_INTERVAL = 2000 // 地鼠出现间隔（毫秒），节奏较慢
const SCREEN_STATE_INTERVAL = 200 // 屏幕状态轮询间隔（毫秒），降低频率减少卡顿

// 地鼠洞配置（3个洞，固定左/中/右）
const holes = ref([
  { id: 'hole1', active: false, region: 'red', name: '左', x: 0.25 },
  { id: 'hole2', active: false, region: 'yellow', name: '中', x: 0.5 },
  { id: 'hole3', active: false, region: 'blue', name: '右', x: 0.75 }
])

// 计算属性
const connectionStatusText = computed(() => {
  const statusMap = {
    'connected': '摄像头已连接',
    'disconnected': '摄像头未连接',
    'error': '连接错误'
  }
  return statusMap[connectionStatus.value] || '未知状态'
})

const hitIndicatorClass = computed(() => {
  return hitResult.value === 'hit' ? 'hit' : 'miss'
})

const hitIndicatorText = computed(() => {
  return hitResult.value === 'hit' ? '✓ 命中' : '✗ 未命中'
})

// 随机激活一个地鼠洞（一次只激活一个）
const activateRandomHole = () => {
  // 检查是否已有活跃的地鼠，确保任意时刻只允许出现一只地鼠
  const activeHole = holes.value.find(hole => hole.active)
  if (activeHole) return
  
  // 找到所有未激活的洞
  const inactiveHoles = holes.value.filter(hole => !hole.active)
  if (inactiveHoles.length === 0) return
  
  // 随机选择一个洞
  const randomIndex = Math.floor(Math.random() * inactiveHoles.length)
  const selectedHole = inactiveHoles[randomIndex]
  
  // 激活该洞
  selectedHole.active = true
  
  // 设置地鼠消失时间（固定5秒，确保停留时间 > 3秒）
  if (activeMoleTimeout.value) {
    clearTimeout(activeMoleTimeout.value)
  }
  
  activeMoleTimeout.value = setTimeout(() => {
    selectedHole.active = false
    // 地鼠消失后，较长延迟再激活下一个，确保节奏慢
    setTimeout(activateRandomHole, MOLE_INTERVAL * 2)
  }, MOLE_STAY_TIME)
}

// 开始测试
const startGame = () => {
  // 初始化游戏状态
  gameStarted.value = true
  hits.value = 0
  resultText.value = '测试开始！请将手指指向地鼠洞'
  resultClass.value = ''
  pointingHole.value = null
  progress.value = 0
  progressColor.value = '#4CAF50'
  
  // 重置所有地鼠洞
  holes.value.forEach(hole => {
    hole.active = false
  })
  
  // 停止任何现有计时器
  if (activeMoleTimeout.value) {
    clearTimeout(activeMoleTimeout.value)
    activeMoleTimeout.value = null
  }
  if (progressInterval.value) {
    clearInterval(progressInterval.value)
    progressInterval.value = null
  }
  
  // 立即激活第一个地鼠
  activateRandomHole()
}

// 结束测试
const endGame = () => {
  gameStarted.value = false
  resultText.value = `测试结束！共命中 ${hits.value} 次`
  resultClass.value = 'game-over'
  
  // 停止所有计时器
  if (activeMoleTimeout.value) {
    clearTimeout(activeMoleTimeout.value)
    activeMoleTimeout.value = null
  }
  if (progressInterval.value) {
    clearInterval(progressInterval.value)
    progressInterval.value = null
  }
  
  // 隐藏所有地鼠
  holes.value.forEach(hole => {
    hole.active = false
  })
  
  // 重置进度和指向
  pointingHole.value = null
  progress.value = 0
  currentPointing.value = '无'
  detectedHand.value = false
  detectedIndexFinger.value = false
}

// 重新开始测试
const restartGame = () => {
  endGame()
  // 短暂延迟后开始新游戏，给用户准备时间
  setTimeout(startGame, 1000)
}

// 处理手指指向事件
const handleFingerPointing = (holeId) => {
  if (!gameStarted.value) return
  
  const hole = holes.value.find(h => h.id === holeId)
  if (!hole) return
  
  // 更新当前指向
  currentPointing.value = hole.name
  
  // 如果指向新的洞，重置进度
  if (pointingHole.value !== holeId) {
    pointingHole.value = holeId
    progress.value = 0
    progressStartTime.value = Date.now()
    progressColor.value = '#4CAF50' // 重置为绿色
    
    // 停止现有进度更新
    if (progressInterval.value) {
      clearInterval(progressInterval.value)
    }
    
    // 启动新的进度更新，精确控制3秒内完成
    progressInterval.value = setInterval(() => {
      if (!pointingHole.value) {
        // 如果手指移出区域，清除进度
        clearInterval(progressInterval.value)
        progressInterval.value = null
        return
      }
      
      // 计算已过去的时间占总时间的比例
      const elapsed = (Date.now() - progressStartTime.value) / 1000
      const newProgress = Math.min(elapsed / CONFIRMATION_TIME, 1.0)
      progress.value = newProgress
      
      // 进度达到100%，完成选择
      if (newProgress >= 1.0) {
        clearInterval(progressInterval.value)
        progressInterval.value = null
        completeSelection(hole)
      }
    }, 50) // 20fps更新，平滑动画效果
  }
}

// 处理手指离开事件
const handleFingerLeave = () => {
  // 手指移出区域，立即重置进度
  pointingHole.value = null
  progress.value = 0
  currentPointing.value = '无'
  
  if (progressInterval.value) {
    clearInterval(progressInterval.value)
    progressInterval.value = null
  }
  
  // 立即清除进度圆环
  progressColor.value = '#4CAF50'
}

// 完成选择判定
const completeSelection = (hole) => {
  const hasMole = hole.active
  
  if (hasMole) {
    // 命中：地鼠存在且3秒内保持指向
    hits.value++
    hitResult.value = 'hit'
    resultText.value = '命中！'
    resultClass.value = 'hit'
    progressColor.value = '#4CAF50' // 绿色表示成功
    
    // 隐藏地鼠
    hole.active = false
    
    // 清除地鼠超时
    if (activeMoleTimeout.value) {
      clearTimeout(activeMoleTimeout.value)
      activeMoleTimeout.value = null
    }
    
    // 短暂延迟后激活下一个地鼠
    setTimeout(activateRandomHole, MOLE_INTERVAL)
  } else {
    // 未命中：地鼠不存在
    hitResult.value = 'miss'
    resultText.value = '未命中！'
    resultClass.value = 'miss'
    progressColor.value = '#f44336' // 红色表示失败
  }
  
  // 显示命中指示器
  lastHitHole.value = hole.id
  showHitIndicator.value = true
  
  // 2秒后隐藏指示器
  setTimeout(() => {
    showHitIndicator.value = false
  }, 2000)
  
  // 重置进度和指向状态
  setTimeout(() => {
    pointingHole.value = null
    progress.value = 0
    currentPointing.value = '无'
  }, 500)
}

// 手势检测处理
const handleGestureDetection = (data) => {
  // 更新区域检测状态
  regionsDetected.value = data.regions_detected || false
  detectedRegionsCount.value = data.detected_regions_count || 0
  debugInfo.value = data.debug_info || '初始化中...'
  
  // 更新手检测状态
  detectedHand.value = data.hand_detected || false
  detectedIndexFinger.value = data.index_finger_detected || false
  
  // 检查是否检测到区域（手/手指）
  if (!data.selected_region || data.selected_region === 'none') {
    // 未检测到手或手指，更新状态
    handleFingerLeave()
    return
  }
  
  // 映射检测区域到地鼠洞
  const regionMap = {
    'red': 'hole1',
    'yellow': 'hole2',
    'blue': 'hole3'
  }
  
  const detectedHoleId = regionMap[data.selected_region] || null
  if (detectedHoleId) {
    // 食指指向某个地鼠洞
    handleFingerPointing(detectedHoleId)
  } else {
    // 食指指向其他区域
    handleFingerLeave()
  }
}

// 获取屏幕状态（降低轮询频率减少摄像头卡顿）
const fetchScreenState = async () => {
  if (!host.value) return
  
  try {
    const response = await fetch(`http://${host.value}:8080/api/screen_state`, {
      timeout: 1000 // 设置1秒超时
    })
    
    if (!response.ok) {
      throw new Error(`HTTP错误！状态: ${response.status}`)
    }
    
    const data = await response.json()
    screenState.value = data
    connectionStatus.value = 'connected'
    
    // 处理手势检测
    handleGestureDetection(data)
  } catch (e) {
    console.error('获取屏幕状态失败:', e)
    connectionStatus.value = 'error'
    handleFingerLeave()
  }
}

onMounted(() => {
  // 只在客户端mounted之后设置host，确保浏览器能正确处理API请求
  host.value = window.location.hostname
  
  // 开始轮询屏幕状态，降低频率减少卡顿
  const screenStateInterval = setInterval(() => {
    try {
      fetchScreenState()
    } catch (e) {
      console.error('获取屏幕状态失败:', e)
    }
  }, SCREEN_STATE_INTERVAL)
  
  onUnmounted(() => {
    // 清理所有资源
    clearInterval(screenStateInterval)
    endGame()
  })
})
</script>

<style scoped>
/* 重置默认样式，确保页面不被拉伸 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background-color: #1a1a2e;
  display: flex;
  justify-content: center;
  align-items: center;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
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

/* 顶部状态栏 */
.top-status {
  text-align: center;
  margin-bottom: 30px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.page-title {
  font-size: 1.8rem;
  font-weight: bold;
  color: #ffffff;
  margin-bottom: 15px;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.status-bar {
  display: flex;
  justify-content: center;
  gap: 2rem;
  align-items: center;
  flex-wrap: wrap;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  font-size: 1.1rem;
}

.status-label {
  color: rgba(255, 255, 255, 0.9);
  font-weight: 500;
}

.status-value {
  color: #ffffff;
  font-weight: bold;
  font-size: 1.2rem;
}

.status-value.hit {
  color: #4CAF50;
}

.status-value.miss {
  color: #f44336;
}

.status-value.game-over {
  color: #ffeb3b;
}

.status-badge {
  padding: 0.5rem 1.2rem;
  border-radius: 25px;
  font-size: 0.9rem;
  font-weight: 600;
  color: white;
}

.status-badge.connected {
  background: #4CAF50;
}

.status-badge.disconnected {
  background: #f44336;
}

.status-badge.error {
  background: #ff9800;
}

/* 调试信息样式 */
.debug-info {
  margin-top: 15px;
  padding: 10px 20px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 10px;
  color: #ffffff;
  font-size: 1rem;
  text-align: center;
  font-family: monospace;
  white-space: pre-wrap;
  max-width: 100%;
  overflow-x: auto;
}

/* 游戏容器 */
.game-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin-bottom: 30px;
}

.game-title {
  font-size: 1.5rem;
  font-weight: bold;
  color: #ffffff;
  margin-bottom: 30px;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

/* 游戏区域 */
.game-area {
  width: 100%;
  height: 40%;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 5%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 地鼠洞布局 - 水平排列3个 */
.mole-holes {
  display: flex;
  justify-content: space-around;
  align-items: center;
  width: 100%;
  height: 100%;
  position: relative;
}

/* 地鼠洞样式 */
.mole-hole {
  position: absolute;
  width: 20%;
  height: 60%;
  background-color: #4a3728;
  border-radius: 50%;
  overflow: hidden;
  box-shadow: inset 0 0 30px rgba(0, 0, 0, 0.6);
  display: flex;
  justify-content: center;
  align-items: flex-end;
  transition: all 0.3s ease;
  transform: translateX(-50%);
  bottom: 0;
}

.mole-hole::before {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 25%;
  background-color: #3a2a1e;
  border-top: 5px solid #2a1f16;
  z-index: 1;
}

.mole-hole.active {
  background-color: #5a4534;
  box-shadow: inset 0 0 40px rgba(0, 0, 0, 0.4), 0 0 25px rgba(255, 215, 0, 0.4);
}

/* 地鼠样式 */
.mole {
  position: relative;
  width: 80%;
  height: 80%;
  background-color: #8b4513;
  border-radius: 50% 50% 0 0;
  bottom: -15%;
  transition: transform 0.6s ease-out;
  z-index: 2;
  animation: popUp 0.6s ease-out forwards;
}

@keyframes popUp {
  0% {
    transform: translateY(100%);
  }
  100% {
    transform: translateY(0);
  }
}

.mole-head {
  position: absolute;
  top: 10px;
  left: 15px;
  width: 90px;
  height: 90px;
  background-color: #a0522d;
  border-radius: 50%;
}

.mole-eyes {
  position: absolute;
  top: 35px;
  left: 30px;
  width: 40px;
  height: 10px;
  display: flex;
  justify-content: space-between;
}

.mole-eyes::before, .mole-eyes::after {
  content: '';
  width: 8px;
  height: 8px;
  background-color: #000;
  border-radius: 50%;
}

/* 进度圆环（扇形增长效果） */
.progress-ring-wrapper {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 200px;
  height: 200px;
  z-index: 10;
  pointer-events: none;
}

.progress-ring {
  width: 100%;
  height: 100%;
}

/* 背景圆环 */
.progress-ring-bg {
  stroke: rgba(255, 255, 255, 0.3);
  fill: transparent;
  stroke-linecap: round;
}

/* 进度圆环（扇形增长） */
.progress-ring-progress {
  fill: transparent;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.05s ease-out;
  transform-origin: center;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 24px;
  font-weight: bold;
  color: #ffffff;
  text-shadow: 0 2px 5px rgba(0, 0, 0, 0.5);
  pointer-events: none;
}

/* 命中/未命中指示器 */
.hit-indicator {
  position: absolute;
  top: -40px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 1.5rem;
  font-weight: bold;
  padding: 0.6rem 1.5rem;
  border-radius: 30px;
  animation: fadeInOut 2s ease;
  z-index: 20;
  min-width: 120px;
  text-align: center;
}

.hit-indicator.hit {
  background: rgba(76, 175, 80, 0.9);
  color: white;
  box-shadow: 0 4px 15px rgba(76, 175, 80, 0.5);
}

.hit-indicator.miss {
  background: rgba(244, 67, 54, 0.9);
  color: white;
  box-shadow: 0 4px 15px rgba(244, 67, 54, 0.5);
}

@keyframes fadeInOut {
  0% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
  20% { opacity: 1; transform: translateX(-50%) translateY(0); }
  80% { opacity: 1; transform: translateX(-50%) translateY(0); }
  100% { opacity: 0; transform: translateX(-50%) translateY(20px); }
}

/* 摄像头区域 */
.camera-section {
  margin: 30px 0;
  padding: 25px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.section-title {
  font-size: 1.3rem;
  font-weight: bold;
  color: #ffffff;
  margin-bottom: 15px;
  text-align: center;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.camera-container {
  background: #000;
  border-radius: 10px;
  overflow: hidden;
  height: 250px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.camera-feed {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background-color: #000;
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
  font-size: 4rem;
  margin-bottom: 1.5rem;
}

.placeholder-text {
  font-size: 1.3rem;
  opacity: 0.8;
}

/* 控制按钮 */
.controls {
  display: flex;
  justify-content: center;
  margin: 30px 0;
}

.control-button {
  background: linear-gradient(45deg, #667eea, #764ba2);
  color: white;
  border: none;
  border-radius: 50px;
  padding: 1.2rem 3rem;
  font-size: 1.3rem;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
  min-width: 200px;
}

.control-button:hover {
  transform: translateY(-4px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
}

.control-button:active {
  transform: translateY(-1px);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
}

/* 手指检测状态 */
.finger-status {
  display: flex;
  justify-content: center;
  gap: 2.5rem;
  margin-top: 20px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.finger-status .status-item {
  font-size: 1rem;
}

.status-value.detected {
  color: #4CAF50;
}

.status-value.not-detected {
  color: #f44336;
}

/* 滚动条样式 */
.page-content::-webkit-scrollbar {
  width: 10px;
}

.page-content::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 5px;
}

.page-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 5px;
}

.page-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.5);
}
</style>