<template>
  <div class="tablet-container">
    <div class="header">
      <h1>📱 平板控制界面</h1>
      <div class="status-badge" :class="connectionStatus">
        {{ connectionStatusText }}
      </div>
    </div>

    <div class="main-content">
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
              <div class="history-mode">{{ history.mode }}</div>
              <div class="history-score">得分: {{ history.score }}</div>
            </div>
            <div class="history-details">
              <div class="history-time">时长: {{ history.duration }}分钟</div>
              <div class="history-bpm">平均心率: {{ history.avg_bpm }} BPM</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="footer">
      <p>💡 提示：保持面部在摄像头视野内，避免大幅度头部运动</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const host = ref('')
const connectionStatus = ref('disconnected')
const physiologicalState = ref({})
const recommendations = ref([])
const trainingHistory = ref([])

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
  const fatigue = physiologicalState.value.fatigue
  const map = {
    'low': '低',
    'medium': '中',
    'high': '高'
  }
  return map[fatigue] || '--'
})

const postureText = computed(() => {
  const posture = physiologicalState.value.posture
  const map = {
    'focused': '专注',
    'relaxed': '放松',
    'poor': '不良'
  }
  return map[posture] || '--'
})

const healthScore = computed(() => {
  const bpm = physiologicalState.value.bpm || 0
  const fatigue = physiologicalState.value.fatigue || 'medium'
  const emotion = physiologicalState.value.emotion || 'neutral'
  
  let score = 100
  
  if (bpm > 100 || bpm < 50) score -= 20
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
    trainingHistory.value = data
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
  host.value = window.location.hostname
  
  fetchPhysiologicalState()
  fetchTrainingHistory()
  
  setInterval(fetchPhysiologicalState, 1000)
  setInterval(fetchTrainingHistory, 5000)
})

onUnmounted(() => {
})
</script>

<style scoped>
.tablet-container {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  color: #ffffff;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  padding: 1.5rem;
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
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

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
}

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
}

.metric-value {
  font-size: 1.8rem;
  font-weight: 700;
  margin-bottom: 0.3rem;
}

.metric-label {
  font-size: 0.9rem;
  opacity: 0.9;
}

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
}

.history-score {
  font-size: 0.9rem;
  opacity: 0.9;
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
}

.footer {
  margin-top: 2rem;
  text-align: center;
  font-size: 1rem;
  opacity: 0.8;
}
</style>
