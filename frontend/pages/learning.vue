<template>
  <div class="page-body">
    <div class="learning-layout">
      <!-- 左侧面板 -->
      <div class="left-panel">
        <!-- 卡片1：游戏列表 -->
        <div class="left-card">
          <h3 class="card-title">🎮 游戏列表</h3>
          <div class="game-list">
            <div class="game-item" @click="showGameInfo('whack_a_mole')">
              <span class="game-icon">🐹</span>
              <div class="game-info">
                <div class="game-name">趣味打地鼠</div>
                <div class="game-desc">锻炼手眼协调与反应速度</div>
              </div>
            </div>
            <div class="game-item" @click="showGameInfo('processing_speed')">
              <span class="game-icon">⚡</span>
              <div class="game-info">
                <div class="game-name">处理速度训练</div>
                <div class="game-desc">科学提升认知处理速度</div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 卡片2：游戏记录 -->
        <div class="left-card">
          <h3 class="card-title">📝 游戏记录</h3>
          <div class="record-list">
            <div 
              v-for="(session, index) in trainingHistory.slice(0, 5)" 
              :key="index"
              class="record-item"
              @click="toggleExpand(session.session_id)"
            >
              <div class="record-info">
                <div class="record-date">{{ formatDate(session.start_time) }}</div>
                <div class="record-game">{{ formatGameType(session.game_type) }}</div>
              </div>
              <div class="record-accuracy" :class="getAccuracyClass(session.final_accuracy)">
                {{ session.final_accuracy }}%
              </div>
            </div>
          </div>
        </div>
        
        <!-- 卡片3：训练激励 -->
        <div class="left-card">
          <h3 class="card-title">💪 训练激励</h3>
          <div class="motivation-content">
            <span class="motivation-icon">🏆</span>
            <div class="motivation-text">
              <div class="motivation-title">加油！坚持训练</div>
              <div class="motivation-desc">每天坚持10分钟，认知能力显著提升！</div>
              <div v-if="dailyStats.count >= 1" class="motivation-success">
                ✅ 今日已完成 {{ dailyStats.count }} 次训练
              </div>
              <div v-else class="motivation-encourage">
                📅 今天还没有训练，开始你的第一次挑战吧！
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 右侧训练激励和趋势 -->
      <div class="right-panel">
        <!-- ⭐ 训练统计卡片 -->
        <div class="stats-section">
          <h3 class="section-title">📊 训练统计</h3>
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-value">{{ dailyStats.count }}</div>
              <div class="stat-label">今日训练</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ weeklyStats.count }}</div>
              <div class="stat-label">本周训练</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ formatAccuracy(dailyStats.avg_accuracy) }}</div>
              <div class="stat-label">今日准确率</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ formatAccuracy(weeklyStats.avg_accuracy) }}</div>
              <div class="stat-label">本周准确率</div>
            </div>
          </div>
        </div>
        
        <!-- ⭐ 准确率趋势图 -->
        <div class="chart-section" v-if="accuracyTrend.length > 0">
          <h3 class="section-title">📈 准确率趋势（最近7天）</h3>
          <div class="trend-chart">
            <div class="chart-bars">
              <div 
                v-for="(item, index) in accuracyTrend" 
                :key="index"
                class="chart-bar"
                :style="{ height: item.accuracy + '%' }"
              >
                <div class="bar-value" v-if="item.accuracy > 0">{{ Math.round(item.accuracy) }}%</div>
              </div>
            </div>
            <div class="chart-labels">
              <div 
                v-for="(item, index) in accuracyTrend" 
                :key="index"
                class="chart-label"
              >
                {{ item.date }}
              </div>
            </div>
          </div>
        </div>
        
        <!-- ⭐ 反应时间趋势图 -->
        <div class="chart-section" v-if="reactionTimeTrend.length > 0">
          <h3 class="section-title">⚡ 反应时间趋势（最近7天）</h3>
          <div class="trend-chart">
            <div class="chart-bars">
              <div 
                v-for="(item, index) in reactionTimeTrend" 
                :key="index"
                class="chart-bar reaction-time"
                :style="{ height: Math.min(item.reactionTime / 10, 100) + '%' }"
              >
                <div class="bar-value" v-if="item.reactionTime > 0">{{ Math.round(item.reactionTime) }}ms</div>
              </div>
            </div>
            <div class="chart-labels">
              <div 
                v-for="(item, index) in reactionTimeTrend" 
                :key="index"
                class="chart-label"
              >
                {{ item.date }}
              </div>
            </div>
          </div>
        </div>
        
        <!-- ⭐ 训练时长统计 -->
        <div class="chart-section" v-if="trainingDurationStats.count > 0">
          <h3 class="section-title">⏱ 训练时长统计</h3>
          <div class="duration-stats">
            <div class="duration-stat-item">
              <div class="duration-stat-value">{{ trainingDurationStats.totalMinutes }}</div>
              <div class="duration-stat-label">总训练时长（分钟）</div>
            </div>
            <div class="duration-stat-item">
              <div class="duration-stat-value">{{ trainingDurationStats.avgMinutes }}</div>
              <div class="duration-stat-label">平均训练时长（分钟）</div>
            </div>
            <div class="duration-stat-item">
              <div class="duration-stat-value">{{ trainingDurationStats.maxMinutes }}</div>
              <div class="duration-stat-label">最长训练时长（分钟）</div>
            </div>
          </div>
        </div>
        </div>
        
    </div>
    
    <!-- 游戏信息弹窗 -->
    <div v-if="selectedGame" class="game-modal" @click.self="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="modal-icon">{{ gameInfo[selectedGame].icon }}</span>
          <h3>{{ gameInfo[selectedGame].title }}</h3>
          <button class="close-btn" @click="closeModal">×</button>
        </div>
        
        <div class="modal-body">
          <p class="game-desc">{{ gameInfo[selectedGame].description }}</p>
          
          <div class="rules-section">
            <h4>📋 游戏规则</h4>
            <ul>
              <li v-for="(rule, index) in gameInfo[selectedGame].rules" :key="index">
                {{ rule }}
              </li>
            </ul>
          </div>
          
          <!-- ⭐ 处理速度训练时长选择 -->
          <div v-if="selectedGame === 'processing_speed'" class="duration-section">
            <h4>⏱ 训练时长</h4>
            <div class="duration-options">
              <label class="duration-option">
                <input type="radio" v-model="selectedDuration" :value="60" />
                <span>1分钟</span>
              </label>
              <label class="duration-option">
                <input type="radio" v-model="selectedDuration" :value="180" />
                <span>3分钟（默认）</span>
              </label>
            </div>
          </div>
          
          <div class="tips-section">
            <h4>💡 游戏提示</h4>
            <p>{{ gameInfo[selectedGame].tips }}</p>
          </div>
        </div>
        
        <div class="modal-footer">
          <button class="start-btn" @click="confirmStartGame">
            开始游戏
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { initStore, subscribe, gameControl } from '../core/systemStore.js'

const router = useRouter()
let socket = null
let unsubscribe = null

// ⭐ 训练统计数据
const dailyStats = ref({ count: 0, avg_accuracy: 0 })
const weeklyStats = ref({ count: 0, avg_accuracy: 0 })
const monthlyStats = ref({ count: 0, avg_accuracy: 0 })
const accuracyTrend = ref([])
const reactionTimeTrend = ref([])
const trainingDurationStats = ref({ count: 0, totalMinutes: 0, avgMinutes: 0, maxMinutes: 0 })
const trainingHistory = ref([])
const expandedRecords = ref({})

const selectedGame = ref(null)
const selectedDuration = ref(180) // 默认3分钟

const gameInfo = {
  'whack_a_mole': {
    icon: '🐹',
    title: '趣味打地鼠',
    description: '锻炼手眼协调与反应速度的经典游戏',
    rules: [
      '游戏开始后，地鼠会随机从三个洞中出现',
      '当🐹出现时，站在对应地鼠洞上停留2秒即可击中',
      '击中地鼠得10分，错过扣5分',
      '游戏时长60秒，尽可能获得高分！'
    ],
    tips: '请站在投影区域的圆圈内，当地鼠出现时快速移动到对应位置并停留确认。'
  },
  'processing_speed': {
    icon: '⚡',
    title: '处理速度训练',
    description: '基于ACTIVE研究的科学认知训练，包含三个模块',
    rules: [
      '【反应控制】绿色区域出现时要快速踩踏，红色区域出现时要忍住不踩',
      '【选择反应】根据提示踩踏对应颜色的区域',
      '【序列学习】按顺序踩踏亮起的区域，完成整个序列',
      '每个模块60秒，站在目标区域停留3秒确认选择',
      '反应越快得分越高，系统会根据表现自动调整难度'
    ],
    tips: '游戏共有8个圆形区域，请根据屏幕提示踩踏正确位置，停留3秒完成确认。'
  }
}

const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

// ⭐ 获取训练统计数据
const fetchTrainingStats = async () => {
  try {
    const response = await fetch(`${backendUrl}/api/training/stats`)
    const data = await response.json()
    
    dailyStats.value = data.daily || { count: 0, avg_accuracy: 0 }
    weeklyStats.value = data.weekly || { count: 0, avg_accuracy: 0 }
    monthlyStats.value = data.monthly || { count: 0, avg_accuracy: 0 }
    accuracyTrend.value = data.trend || []
    
    // 生成反应时间趋势（模拟数据，实际应该从后端获取）
    reactionTimeTrend.value = accuracyTrend.value.map(item => ({
      date: item.date,
      reactionTime: Math.random() * 500 + 300 // 300-800ms的随机值
    }))
    
    // 计算训练时长统计
    const totalSeconds = trainingHistory.value.reduce((sum, session) => sum + (session.duration || 0), 0)
    const totalMinutes = Math.round(totalSeconds / 60)
    const avgMinutes = trainingHistory.value.length > 0 ? Math.round(totalMinutes / trainingHistory.value.length) : 0
    const maxMinutes = Math.max(...trainingHistory.value.map(session => Math.round((session.duration || 0) / 60)), 0)
    
    trainingDurationStats.value = {
      count: trainingHistory.value.length,
      totalMinutes,
      avgMinutes,
      maxMinutes
    }
    
    console.log('[learning] 训练统计:', data)
  } catch (e) {
    console.log('[learning] 获取训练统计失败:', e)
  }
}

// ⭐ 获取训练历史
const fetchTrainingHistory = async () => {
  try {
    const response = await fetch(`${backendUrl}/api/training/history`)
    const data = await response.json()
    
    trainingHistory.value = data.sessions || []
    
    // 重新计算训练时长统计
    const totalSeconds = trainingHistory.value.reduce((sum, session) => sum + (session.duration || 0), 0)
    const totalMinutes = Math.round(totalSeconds / 60)
    const avgMinutes = trainingHistory.value.length > 0 ? Math.round(totalMinutes / trainingHistory.value.length) : 0
    const maxMinutes = Math.max(...trainingHistory.value.map(session => Math.round((session.duration || 0) / 60)), 0)
    
    trainingDurationStats.value = {
      count: trainingHistory.value.length,
      totalMinutes,
      avgMinutes,
      maxMinutes
    }
    
    console.log('[learning] 训练历史:', data)
  } catch (e) {
    console.log('[learning] 获取训练历史失败:', e)
  }
}

// ⭐ 格式化准确率
const formatAccuracy = (accuracy) => {
  if (!accuracy) return '0%'
  return Math.round(accuracy * 100) + '%'
}

// ⭐ 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
}

// ⭐ 格式化游戏类型
const formatGameType = (gameType) => {
  const map = {
    'processing_speed': '处理速度训练',
    'whack_a_mole': '趣味打地鼠'
  }
  return map[gameType] || gameType
}

// ⭐ 根据准确率获取样式类
const getAccuracyClass = (accuracy) => {
  if (accuracy >= 80) return 'accuracy-high'
  if (accuracy >= 60) return 'accuracy-medium'
  return 'accuracy-low'
}

onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  // ⭐ 关键修复：初始化systemStore
  initStore(socket)
  
  socket.on('connect', () => {
    console.log('[益智] 后端已连接')
  })
  
  socket.on('navigate_to', (data) => {
    router.push(data.page)
  })
  
  // 监听游戏状态变化
  socket.on('game_update', (data) => {
    console.log('[learning] game_update:', data)
    
    // 如果状态变为READY，跳转到training页面
    if (data.status === 'READY') {
      router.push('/training')
    }
  })
  
  socket.on('system_state', (data) => {
    if (data.game?.status === 'IDLE') {
      // 游戏已停止，已经在 learning 页面，不需要跳转
    }
  })
  
  // ⭐ 加载训练统计数据
  fetchTrainingStats()
  fetchTrainingHistory()
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

const showGameInfo = (gameName) => {
  selectedGame.value = gameName
}

const closeModal = () => {
  selectedGame.value = null
}

const confirmStartGame = () => {
  if (selectedGame.value && socket && socket.connected) {
    const gameId = selectedGame.value
    console.log('[learning] 开始游戏:', gameId)
    
    // 构建游戏参数
    const gameParams = {}
    
    // 处理速度训练添加时长参数
    if (gameId === 'processing_speed') {
      gameParams.duration = selectedDuration.value
      console.log('[learning] 训练时长:', selectedDuration.value, '秒')
    }
    
    // 发送到后端，后端是唯一的真相来源
    gameControl('ready', { game: gameId, ...gameParams })
    selectedGame.value = null
  } else {
    alert('后端未连接，请稍后重试')
  }
}

const handleTodo = () => {
  alert('该功能正在开发中，敬请期待！')
}

// ⭐ 删除训练记录
const deleteRecord = async (sessionId) => {
  if (confirm('确定要删除这条训练记录吗？')) {
    try {
      const response = await fetch(`${backendUrl}/api/training/delete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ session_id: sessionId })
      })
      
      const data = await response.json()
      if (data.success) {
        // 重新获取训练历史
        await fetchTrainingHistory()
        // 重新获取训练统计
        await fetchTrainingStats()
        alert('删除成功！')
      } else {
        alert('删除失败：' + data.message)
      }
    } catch (e) {
      console.error('[learning] 删除训练记录失败:', e)
      alert('删除失败，请稍后重试')
    }
  }
}

// ⭐ 切换训练记录展开状态
const toggleExpand = (sessionId) => {
  expandedRecords.value[sessionId] = !expandedRecords.value[sessionId]
}
</script>

<style scoped>
.page-body { 
  padding: 0;
  margin: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 左右分栏布局 */
.learning-layout {
  display: flex;
  gap: 20px;
  margin: 0;
  flex: 1;
  align-items: flex-start;
}

/* 左侧面板 */
.left-panel {
  width: 30%;
  min-width: 300px;
  background: #FFF;
  border-radius: 30px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
  max-height: calc(100vh - 40px);
  overflow-y: auto;
}

/* 左侧卡片样式 */
.left-card {
  background: #FFF;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
  margin-bottom: 20px;
}

.card-title {
  font-size: 20px;
  color: #333;
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

/* 游戏列表样式 */
.game-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.game-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 15px;
  background: #f8fafc;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.game-item:hover {
  background: #e2e8f0;
  transform: translateX(5px);
}

.game-icon {
  font-size: 32px;
}

.game-info {
  flex: 1;
}

.game-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.game-desc {
  font-size: 13px;
  color: #888;
  margin-top: 2px;
}

/* 游戏记录样式 */
.record-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.record-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 10px;
}

.record-info {
  flex: 1;
}

.record-date {
  font-size: 12px;
  color: #999;
}

.record-game {
  font-size: 14px;
  color: #333;
  margin-top: 2px;
}

.record-accuracy {
  font-size: 16px;
  font-weight: bold;
  padding: 4px 10px;
  border-radius: 15px;
}

.record-accuracy.accuracy-high {
  background: #d4edda;
  color: #155724;
}

.record-accuracy.accuracy-medium {
  background: #fff3cd;
  color: #856404;
}

.record-accuracy.accuracy-low {
  background: #f8d7da;
  color: #721c24;
}

/* 训练激励样式 */
.motivation-content {
  display: flex;
  gap: 15px;
}

.motivation-icon {
  font-size: 48px;
}

.motivation-text {
  flex: 1;
}

.motivation-title {
  font-size: 18px;
  font-weight: bold;
  color: #333;
  margin-bottom: 8px;
}

.motivation-desc {
  font-size: 14px;
  color: #888;
  margin-bottom: 10px;
}

.motivation-success, .motivation-encourage {
  font-size: 14px;
  font-weight: 600;
  color: #22c55e;
}

.motivation-encourage {
  color: #f59e0b;
}

/* 右侧训练激励和趋势 */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 30px;
  overflow-y: auto;
}

/* ⭐ 统计区域样式 */
.stats-section {
  background: #FFF;
  border-radius: 20px;
  padding: 25px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.section-title {
  font-size: 24px;
  color: #333;
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.stat-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 20px;
  padding: 25px;
  text-align: center;
  color: white;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}

.stat-value {
  font-size: 36px;
  font-weight: bold;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 16px;
  opacity: 0.9;
}

/* ⭐ 图表区域样式 */
.chart-section {
  background: #FFF;
  border-radius: 20px;
  padding: 25px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.trend-chart {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 15px;
  height: 200px;
  padding: 20px 0;
  width: 100%;
  justify-content: space-around;
}

.chart-bar {
  width: 60px;
  background: linear-gradient(to top, #667eea, #764ba2);
  border-radius: 8px 8px 0 0;
  position: relative;
  transition: all 0.3s;
  min-height: 10px;
}

.chart-bar.reaction-time {
  background: linear-gradient(to top, #FF7222, #FF9A5C);
}

.chart-bar:hover {
  opacity: 0.8;
}

.bar-value {
  position: absolute;
  top: -25px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 14px;
  font-weight: bold;
  color: #333;
  white-space: nowrap;
}

.chart-labels {
  display: flex;
  justify-content: space-around;
  width: 100%;
  padding-top: 10px;
  border-top: 1px solid #EEE;
}

.chart-label {
  font-size: 14px;
  color: #666;
  text-align: center;
  width: 60px;
}

/* ⭐ 训练时长统计样式 */
.duration-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.duration-stat-item {
  background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
  border-radius: 20px;
  padding: 25px;
  text-align: center;
  color: white;
  box-shadow: 0 4px 15px rgba(76, 175, 80, 0.3);
}

.duration-stat-value {
  font-size: 36px;
  font-weight: bold;
  margin-bottom: 8px;
}

.duration-stat-label {
  font-size: 16px;
  opacity: 0.9;
}

/* ⭐ 历史记录样式 */
.history-section {
  background: #FFF;
  border-radius: 20px;
  padding: 25px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  background: #F8F9FA;
  border-radius: 12px;
  border-left: 4px solid #667eea;
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.history-date {
  font-size: 14px;
  color: #888;
}

.history-game {
  font-size: 16px;
  font-weight: 500;
  color: #333;
}

.history-stats {
  display: flex;
  gap: 20px;
  align-items: center;
}

.history-accuracy {
  font-size: 18px;
  font-weight: bold;
  padding: 5px 12px;
  border-radius: 20px;
}

.accuracy-high {
  background: #D4EDDA;
  color: #155724;
}

.accuracy-medium {
  background: #FFF3CD;
  color: #856404;
}

.accuracy-low {
  background: #F8D7DA;
  color: #721C24;
}

.history-score {
  font-size: 16px;
  color: #667eea;
  font-weight: 500;
}

.delete-btn {
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.delete-btn:hover {
  background: #c82333;
  transform: scale(1.1);
}

/* ⭐ 展开图标样式 */
.expand-icon {
  font-size: 12px;
  color: #667eea;
  margin-left: 10px;
  font-weight: bold;
  transition: transform 0.2s;
}

/* ⭐ 详细信息样式 */
.history-details {
  margin-top: 15px;
  padding: 15px;
  background: #F0F4FF;
  border-radius: 8px;
  border-left: 4px solid #667eea;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.detail-label {
  color: #666;
  font-weight: 500;
}

.detail-value {
  color: #333;
  font-weight: 600;
}

/* 调整历史记录项的样式 */
.history-item {
  cursor: pointer;
  transition: all 0.2s;
}

.history-item:hover {
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
}

.history-stats {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-shrink: 0;
}

/* ⭐ 训练激励样式 */
.motivation-section {
  background: #FFF;
  border-radius: 20px;
  padding: 25px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.motivation-card {
  background: linear-gradient(135deg, #FF7222 0%, #FF9A5C 100%);
  border-radius: 20px;
  padding: 30px;
  color: white;
}

.motivation-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.motivation-icon {
  font-size: 60px;
}

.motivation-text h4 {
  font-size: 24px;
  margin-bottom: 10px;
  margin-top: 0;
}

.motivation-text p {
  font-size: 18px;
  margin-bottom: 10px;
  opacity: 0.9;
}

.motivation-success {
  color: #FFF;
  font-weight: bold;
}

.motivation-encourage {
  color: #FFF;
  font-weight: bold;
}

/* 弹窗样式 - 增大尺寸 */
.game-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 40px;
}

.modal-content {
  background: #FFF;
  border-radius: 40px;
  width: 90%;
  max-width: 900px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px 30px;  /* 减小padding */
  background: linear-gradient(135deg, #FF7222 0%, #FF9A5C 100%);
  color: #FFF;
  flex-shrink: 0;
}

.modal-icon {
  font-size: 40px;  /* 减小图标 */
}

.modal-header h3 {
  flex: 1;
  font-size: 28px;  /* 减小标题 */
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  color: #FFF;
  font-size: 36px;  /* 减小关闭按钮 */
  cursor: pointer;
  padding: 0 10px;
  transition: transform 0.2s;
}

.close-btn:hover {
  transform: scale(1.1);
}

/* ⭐ 可滚动内容区域 - 增大空间 */
.modal-body {
  padding: 30px 40px;
  overflow-y: auto;
  flex: 1;
  max-height: calc(85vh - 160px);  /* 减小减去的值，增大内容区域 */
  scrollbar-width: thin;
  scrollbar-color: #FF7222 #f0f0f0;
}

/* 自定义滚动条样式 */
.modal-body::-webkit-scrollbar {
  width: 10px;
}

.modal-body::-webkit-scrollbar-track {
  background: #f0f0f0;
  border-radius: 5px;
}

.modal-body::-webkit-scrollbar-thumb {
  background: #FF7222;
  border-radius: 5px;
}

.modal-body::-webkit-scrollbar-thumb:hover {
  background: #e66000;
}

.game-desc {
  font-size: 24px;
  color: #666;
  margin-bottom: 30px;
  line-height: 1.6;
}

.rules-section, .tips-section {
  margin-bottom: 30px;
}

.rules-section h4, .tips-section h4 {
  font-size: 28px;
  color: #333;
  margin-bottom: 20px;
}

.rules-section ul {
  list-style: none;
  padding: 0;
}

.rules-section li {
  font-size: 22px;
  color: #555;
  padding: 15px 0;
  padding-left: 40px;
  position: relative;
  line-height: 1.6;
}

.rules-section li::before {
  content: '•';
  position: absolute;
  left: 15px;
  color: #FF7222;
  font-weight: bold;
  font-size: 28px;
}

.tips-section p {
  font-size: 22px;
  color: #FF7222;
  background: #FFF5F0;
  padding: 25px;
  border-radius: 20px;
  line-height: 1.6;
}

/* ⭐ 时长选择样式 */
.duration-section {
  margin-bottom: 30px;
}

.duration-options {
  display: flex;
  gap: 30px;
  margin-top: 15px;
}

.duration-option {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 20px;
  color: #333;
  cursor: pointer;
}

.duration-option input[type="radio"] {
  width: 20px;
  height: 20px;
  cursor: pointer;
}

.modal-footer {
  padding: 20px 30px 25px;  /* 减小padding */
  display: flex;
  justify-content: center;
  flex-shrink: 0;
  border-top: 2px solid #f0f0f0;
}

.start-btn {
  background: #FF7222;
  color: #FFF;
  border: none;
  padding: 18px 60px;  /* 减小按钮 */
  border-radius: 40px;
  font-size: 24px;  /* 减小字体 */
  font-weight: bold;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.start-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 6px 30px rgba(255, 114, 34, 0.5);
}

.start-btn:active {
  transform: scale(0.98);
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .learning-layout {
    gap: 20px;
  }
  
  .left-panel {
    min-width: 300px;
  }
  
  .l-card {
    padding: 20px;
  }
  
  .l-icon {
    font-size: 40px;
  }
  
  .l-text h3 {
    font-size: 20px;
  }
  
  .l-text p {
    font-size: 14px;
  }
}
</style>
