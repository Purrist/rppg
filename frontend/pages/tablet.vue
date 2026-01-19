<template>
  <div class="page-container">
    <!-- 严格2560*1600比例的固定容器，按宽度铺满屏幕 -->
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
      
      <!-- 内容包装器 -->
      <div class="content-wrapper">
        <div class="header">
          <h1>📱 平板控制界面</h1>
          <div class="status-badge" :class="connectionStatus">
            {{ connectionStatusText }}
          </div>
        </div>

        <div class="main-content">
          <div class="camera-panel">
            <h2>📷 平板摄像头（人脸追踪）</h2>
            <div class="camera-area">
              <!-- 只在client mounted之后显示视频流，确保浏览器能正确处理MJPEG -->
              <img 
                v-if="host" 
                :src="`http://${host}:8080/tablet_video_feed`" 
                alt="平板摄像头" 
                class="camera-img"
              />
              <div v-else class="camera-placeholder">
                <div class="placeholder-content">
                  <div class="placeholder-icon">📷</div>
                  <div class="placeholder-text">摄像头连接中...</div>
                </div>
              </div>
            </div>
            <div class="chart-area">
              <canvas ref="chartRef" height="120"></canvas>
            </div>
          </div>

          <div class="physiological-panel">
            <h2>❤️ 生理状态监测</h2>
            
            <div class="metrics-grid">
              <div class="metric-card">
                <div class="metric-icon">💓</div>
                <div class="metric-value">{{ physiologicalState.bpm || '--' }}</div>
                <div class="metric-label">心率 (BPM)</div>
              </div>

              <div class="metric-card">
                <div class="metric-icon">😊</div>
                <div class="metric-value">{{ emotionText }}</div>
                <div class="metric-label">情绪状态</div>
              </div>

              <div class="metric-card">
                <div class="metric-icon">😴</div>
                <div class="metric-value">{{ fatigueText }}</div>
                <div class="metric-label">疲劳程度</div>
              </div>

              <div class="metric-card">
                <div class="metric-icon">🎯</div>
                <div class="metric-value">{{ physiologicalState.attention || '--' }}</div>
                <div class="metric-label">注意力评分</div>
              </div>

              <div class="metric-card">
                <div class="metric-icon">🧘</div>
                <div class="metric-value">{{ postureText }}</div>
                <div class="metric-label">姿态状态</div>
              </div>

              <div class="metric-card">
                <div class="metric-icon">📊</div>
                <div class="metric-value">{{ healthScore }}</div>
                <div class="metric-label">综合健康评分</div>
              </div>
            </div>
          </div>

          <div class="recommendation-panel">
            <h2>💡 推荐行动</h2>
            
            <div class="recommendation-list">
              <div 
                v-for="(rec, index) in recommendations" 
                :key="index"
                class="recommendation-item"
                :class="rec.priority"
              >
                <div class="rec-priority">{{ priorityText(rec.priority) }}</div>
                <div class="rec-content">{{ rec.text }}</div>
              </div>
            </div>
          </div>

          <div class="history-panel">
            <h2>📜 训练历史</h2>
            
            <div class="history-list">
              <div 
                v-for="(history, index) in trainingHistory" 
                :key="index"
                class="history-item"
              >
                <div class="history-info">
                  <div class="history-time">{{ formatTime(history.timestamp) }}</div>
                  <div class="history-stats">
                    <span class="stat-item">{{ history.correct }} 正确</span>
                    <span class="stat-item">{{ history.incorrect }} 错误</span>
                    <span class="stat-item">{{ history.accuracy }}% 准确率</span>
                  </div>
                </div>
                <div class="history-actions">
                  <button class="history-button">查看详情</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// 基本状态
const host = ref('')
const connectionStatus = ref('disconnected')
const physiologicalState = ref({})
const recommendations = ref([])
const trainingHistory = ref([])

// 摄像头 + 面部追踪 refs
const overlayRef = ref(null)
const chartRef = ref(null)

// rPPG 缓冲与绘图数据
const bpmHistory = ref([])
let chartInstance = null
let running = true

const connectionStatusText = computed(() => {
  const statusMap = {
    'connected': '已连接',
    'disconnected': '未连接',
    'error': '连接错误'
  }
  return statusMap[connectionStatus.value] || '未知'
})

const emotionText = computed(() => {
  const emotion = physiologicalState.value.emotion
  const map = {
    'happy': '开心',
    'neutral': '中性',
    'sad': '悲伤',
    'angry': '愤怒',
    'fear': '恐惧',
    'surprise': '惊讶'
  }
  return map[emotion] || '--'
})

const fatigueText = computed(() => {
  const fatigue = physiologicalState.value.fatigue_level
  const map = {
    'low': '低',
    'medium': '中',
    'high': '高',
    'unknown': '--'
  }
  return map[fatigue] || '--'
})

const postureText = computed(() => {
  const posture = physiologicalState.value.posture_state
  const map = {
    'focused': '专注',
    'relaxed': '放松',
    'slouching': '不良',
    'leaning': '倾斜',
    'neutral': '正常',
    'unknown': '--'
  }
  return map[posture] || '--'
})

const healthScore = computed(() => {
  const bpm = physiologicalState.value.bpm || 0
  const fatigue = physiologicalState.value.fatigue_level || 'medium'
  const emotion = physiologicalState.value.emotion || 'neutral'
  
  let score = 100
  
  if (typeof bpm === 'number') {
    if (bpm > 100 || bpm < 50) score -= 20
  } else {
    score -= 10
  }
  
  if (fatigue === 'high') score -= 30
  if (fatigue === 'medium') score -= 15
  if (emotion === 'sad' || emotion === 'angry') score -= 20
  
  return Math.max(0, Math.min(100, score))
})

const priorityText = (priority) => {
  const map = {
    'high': '🔴 高',
    'medium': '🟡 中',
    'low': '🟢 低'
  }
  return map[priority] || '--'
}

const fetchPhysiologicalState = async () => {
  try {
    const response = await fetch(`http://${host.value}:8080/api/physiological_state`)
    const data = await response.json()
    physiologicalState.value = data
    connectionStatus.value = 'connected'
    
    // 更新心率图表
    if (data.bpm && typeof data.bpm === 'number') {
      updateBpmHistory(data.bpm)
    }
    
    updateRecommendations(data)
  } catch (e) {
    console.error('获取生理状态失败:', e)
    connectionStatus.value = 'error'
  }
}

const fetchTrainingHistory = async () => {
  try {
    const response = await fetch(`http://${host.value}:8080/api/training_history`)
    const data = await response.json()
    trainingHistory.value = data.sessions || []
  } catch (e) {
    console.error('获取训练历史失败:', e)
  }
}

const updateRecommendations = (state) => {
  const recs = []
  
  if (state.bpm > 100) {
    recs.push({
      priority: 'high',
      text: '心率过高，建议休息片刻'
    })
  }
  
  if (state.bpm < 50) {
    recs.push({
      priority: 'medium',
      text: '心率偏低，建议增加活动量'
    })
  }
  
  if (state.fatigue === 'high') {
    recs.push({
      priority: 'high',
      text: '疲劳程度高，建议立即休息'
    })
  }
  
  if (state.fatigue === 'medium') {
    recs.push({
      priority: 'medium',
      text: '疲劳程度中等，建议适当休息'
    })
  }
  
  if (state.attention < 60) {
    recs.push({
      priority: 'medium',
      text: '注意力较低，建议调整训练难度'
    })
  }
  
  if (state.posture === 'poor') {
    recs.push({
      priority: 'low',
      text: '姿态不良，建议调整坐姿'
    })
  }
  
  if (recs.length === 0) {
    recs.push({
      priority: 'low',
      text: '状态良好，继续训练'
    })
  }
  
  recommendations.value = recs
}

onMounted(() => {
  // 只在客户端mounted之后设置host，确保浏览器能正确处理MJPEG流
  host.value = window.location.hostname
  fetchPhysiologicalState()
  fetchTrainingHistory()

  // 确保DOM渲染完成后再初始化图表
  setTimeout(() => {
    setupChart()
  }, 100)

  setInterval(fetchPhysiologicalState, 1000)
  setInterval(fetchTrainingHistory, 5000)
})

onUnmounted(() => {
  running = false
  
  // 销毁图表实例
  if (chartInstance) {
    try {
      chartInstance.destroy()
    } catch (e) {
      console.error('销毁图表失败', e)
    }
    chartInstance = null
  }
})

// ---------- 下面是图表实现 ----------

const loadChartJs = () => new Promise((res, rej) => {
  if (window.Chart) return res()
  const s = document.createElement('script')
  s.src = '/js/chart.min.js'
  s.onload = res
  s.onerror = rej
  document.head.appendChild(s)
})

const setupChart = async () => {
  try {
    // 检查chartRef是否存在
    if (!chartRef.value) {
      console.error('Chart canvas element not found')
      return
    }
    
    // 动态加载 Chart.js
    await loadChartJs()
    
    // 确保Canvas元素已渲染
    if (!chartRef.value.parentNode) {
      console.error('Chart canvas element not in DOM')
      return
    }
    
    const ctx = chartRef.value.getContext('2d')
    if (!ctx) {
      console.error('Failed to get 2D context from canvas')
      return
    }
    
    // 销毁已存在的图表实例
    if (chartInstance) {
      try {
        chartInstance.destroy()
      } catch (e) {
        console.error('销毁现有图表失败', e)
      }
      chartInstance = null
    }
    
    chartInstance = new window.Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'BPM',
          data: [],
          borderColor: 'rgba(255,99,132,1)',
          backgroundColor: 'rgba(255,99,132,0.2)',
          tension: 0.2,
          pointRadius: 0
        }]
      },
      options: {
        animation: false,
        scales: {
          y: { 
            suggestedMin: 40, 
            suggestedMax: 160,
            responsive: true,
            maintainAspectRatio: false
          },
          x: {
            responsive: true,
            maintainAspectRatio: false
          }
        },
        plugins: { 
          legend: { display: false },
          tooltip: {
            enabled: false
          }
        },
        responsive: true,
        maintainAspectRatio: false,
        events: [] // 禁用所有事件，避免事件绑定问题
      }
    })
  } catch (e) {
    console.error('加载 Chart.js 失败', e)
  }
}

const updateBpmHistory = (bpm) => {
  if (!chartInstance) return
  
  const t = new Date()
  bpmHistory.value.push({t, bpm})
  if (bpmHistory.value.length > 100) bpmHistory.value.shift()
  
  try {
    chartInstance.data.labels.push(t.toLocaleTimeString())
    chartInstance.data.datasets[0].data.push(bpm)
    if (chartInstance.data.labels.length > 60) {
      chartInstance.data.labels.shift()
      chartInstance.data.datasets[0].data.shift()
    }
    chartInstance.update('none') // 使用none动画，避免性能问题
  } catch (e) {
    console.error('更新图表失败', e)
  }
}
</script>

<style scoped>
/* 页面容器，确保内容居中显示 */
.page-container {
  width: 100%;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #1a1a2e;
  overflow: hidden;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

/* 严格2560*1600比例的固定容器，按宽度铺满屏幕 */
.fixed-ratio-container {
  position: relative;
  width: 100vw;
  /* 2560:1600 = 1.6:1 = 8:5 */
  height: calc(100vw * 5 / 8);
  max-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 10px 50px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 四个角的视觉定位点（用于摄像头视觉定位与透视校正） */
.visual-marker {
  position: absolute;
  width: 30px;
  height: 30px;
  z-index: 100;
  display: flex;
  justify-content: center;
  align-items: center;
}

.marker-inner {
  width: 20px;
  height: 20px;
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
  width: 12px;
  height: 2px;
}

.marker-inner::after {
  width: 2px;
  height: 12px;
}

/* 定位点位置 - 固定在四个角落 */
.visual-marker.top-left {
  top: 10px;
  left: 10px;
}

.visual-marker.top-right {
  top: 10px;
  right: 10px;
  transform: rotate(90deg);
}

.visual-marker.bottom-left {
  bottom: 10px;
  left: 10px;
  transform: rotate(-90deg);
}

.visual-marker.bottom-right {
  bottom: 10px;
  right: 10px;
  transform: rotate(180deg);
}

/* 内容包装器，所有内容都在这个容器内 */
.content-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
  overflow-y: auto;
}

/* 头部样式 */
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
  color: #ffffff;
}

/* 状态徽章 */
.status-badge {
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 600;
  color: white;
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

/* 主内容区域 */
.main-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  flex: 1;
  overflow-y: auto;
}

/* 面板样式 */
.physiological-panel,
.recommendation-panel,
.history-panel {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 1.5rem;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.physiological-panel h2,
.recommendation-panel h2,
.history-panel h2 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 1.5rem;
  margin-top: 0;
  color: #ffffff;
}

/* 指标网格 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.metric-card {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 15px;
  padding: 1rem;
  text-align: center;
  transition: all 0.3s ease;
}

.metric-card:hover {
  transform: translateY(-4px);
  background: rgba(255, 255, 255, 0.2);
}

.metric-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  color: #ffffff;
}

.metric-value {
  font-size: 1.8rem;
  font-weight: 700;
  margin-bottom: 0.3rem;
  color: #ffffff;
}

.metric-label {
  font-size: 0.9rem;
  opacity: 0.9;
  color: #ffffff;
}

/* 推荐列表 */
.recommendation-list {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.recommendation-item {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  color: #ffffff;
}

.recommendation-item.high {
  border-left: 4px solid #ef4444;
}

.recommendation-item.medium {
  border-left: 4px solid #f59e0b;
}

.recommendation-item.low {
  border-left: 4px solid #10b981;
}

.rec-priority {
  font-size: 0.9rem;
  font-weight: 600;
  white-space: nowrap;
}

.rec-content {
  font-size: 1rem;
  line-height: 1.5;
}

/* 历史列表 */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.history-item {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.history-mode {
  font-size: 1.1rem;
  font-weight: 600;
  color: #ffffff;
}

.history-score {
  font-size: 0.9rem;
  opacity: 0.9;
  color: #ffffff;
}

.history-details {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  text-align: right;
}

.history-time,
.history-bpm {
  font-size: 0.9rem;
  opacity: 0.9;
  color: #ffffff;
}

/* 摄像头面板 */
.camera-panel {
  background: rgba(255,255,255,0.04);
  border-radius: 16px;
  padding: 1rem;
  border: 1px solid rgba(255,255,255,0.08);
}

.camera-area {
  position: relative;
  width: 100%;
  max-width: 640px;
  margin-bottom: 0.8rem;
}

.camera-area video,
.camera-area .camera-img {
  width: 100%;
  border-radius: 12px;
  display: block;
}

.camera-placeholder {
  width: 100%;
  height: 480px;
  background: rgba(0, 0, 0, 0.8);
  border-radius: 12px;
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

/* 图表区域 */
.chart-area {
  max-width: 640px;
  background: rgba(0,0,0,0.15);
  padding: 0.6rem;
  border-radius: 10px;
}
</style>
