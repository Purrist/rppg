<template>
  <div class="page-body">
    <main class="main-content">
      <div class="split-layout">
        <!-- ========== 左列 ========== -->
        <div class="left-col">
          <!-- 游戏列表 -->
          <div class="card fade-up">
            <div class="card-header">
              <div class="card-icon">🎮</div>
              <h3 class="card-title">训练项目</h3>
            </div>
            <div class="game-list">
              <div class="game-item" @click="showGameInfo('whack_a_mole')">
                <div class="game-icon-wrap" style="background: linear-gradient(135deg, #FDE68A, #FBBF24);">
                  <span>🐹</span>
                </div>
                <div class="game-info">
                  <div class="game-name">趣味打地鼠</div>
                  <div class="game-desc">锻炼手眼协调与反应速度</div>
                </div>
                <i class="fas fa-chevron-right"></i>
              </div>
              <div class="game-item" @click="showGameInfo('processing_speed')">
                <div class="game-icon-wrap" style="background: linear-gradient(135deg, #C4B5FD, #8B5CF6);">
                  <span>⚡</span>
                </div>
                <div class="game-info">
                  <div class="game-name">处理速度训练</div>
                  <div class="game-desc">科学提升认知处理速度</div>
                </div>
                <i class="fas fa-chevron-right"></i>
              </div>
            </div>
          </div>

          <!-- 训练计划 -->
          <div class="card fade-up fade-up-d1 training-plan-card">
            <div class="card-header">
              <div class="header-left">
                <span class="header-emoji">🔥</span>
                <h3 class="card-title">今日训练计划</h3>
              </div>
              <span class="training-status" :class="dailyStats.count >= 3 ? 'complete' : 'incomplete'">
                {{ dailyStats.count >= 3 ? '已完成' : '进行中' }}
              </span>
            </div>
            
            <div class="plan-main">
              <div class="plan-left">
                <div class="big-progress-ring">
                  <div class="ring-value">{{ dailyStats.count }}</div>
                  <div class="ring-label">/ 3</div>
                </div>
              </div>
              <div class="plan-right">
                <div class="progress-item">
                  <span class="progress-label">今日目标</span>
                  <span class="progress-highlight">3次</span>
                </div>
                <div class="progress-item">
                  <span class="progress-label">已完成</span>
                  <span class="progress-highlight">{{ dailyStats.count }}次</span>
                </div>
                <div class="progress-item">
                  <span class="progress-label">连续天数</span>
                  <span class="progress-highlight streak">{{ streakDays }}天</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 训练激励 -->
          <div class="motivation-banner fade-up fade-up-d3">
            <div class="motivation-inner">
              <div class="motivation-icon">🏆</div>
              <div class="motivation-text">
                <div class="motivation-title">坚持训练，超越自我</div>
                <div class="motivation-desc">每天坚持10分钟，认知能力显著提升</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ========== 右列 ========== -->
        <div class="right-col">
          <!-- 统计卡片行 -->
          <div class="stats-grid fade-up">
            <div class="stat-mini" style="background: linear-gradient(135deg, #0D9488, #0F766E);">
              <div class="stat-row">
                <div class="stat-label">今日训练</div>
                <div class="stat-num">{{ dailyStats.count }}</div>
              </div>
            </div>
            <div class="stat-mini" style="background: linear-gradient(135deg, #F97316, #EA580C);">
              <div class="stat-row">
                <div class="stat-label">本周训练</div>
                <div class="stat-num">{{ weeklyStats.count }}</div>
              </div>
            </div>
            <div class="stat-mini" style="background: linear-gradient(135deg, #6366F1, #4F46E5);">
              <div class="stat-row">
                <div class="stat-label">今日准确率</div>
                <div class="stat-num">{{ formatAccuracy(dailyStats.avg_accuracy) }}</div>
              </div>
            </div>
            <div class="stat-mini" style="background: linear-gradient(135deg, #0EA5E9, #0284C7);">
              <div class="stat-row">
                <div class="stat-label">本周准确率</div>
                <div class="stat-num">{{ formatAccuracy(weeklyStats.avg_accuracy) }}</div>
              </div>
            </div>
          </div>

          <!-- 认知表现趋势（双柱状图） -->
          <div class="card fade-up fade-up-d1">
            <div class="card-header">
              <div class="card-icon">📊</div>
              <h3 class="card-title">认知表现趋势</h3>
              <span class="card-subtitle">最近7天</span>
              <div class="custom-legend">
                <div class="legend-item">
                  <span class="legend-color legend-accuracy"></span>
                  <span class="legend-text">准确率(%)</span>
                </div>
                <div class="legend-item">
                  <span class="legend-color legend-reaction"></span>
                  <span class="legend-text">反应时间(ms)</span>
                </div>
              </div>
            </div>
            <div class="chart-container">
              <canvas id="cognitiveChart"></canvas>
            </div>
          </div>

          <!-- 训练时长统计 -->
          <div class="card fade-up fade-up-d2">
            <div class="card-header">
              <div class="card-icon">⏱</div>
              <h3 class="card-title">训练时长统计</h3>
            </div>
            <div class="duration-list">
              <div class="duration-item">
                <div class="duration-label">总训练时长</div>
                <div class="duration-value">
                  {{ trainingDurationStats.totalMinutes }}
                  <span class="duration-unit">分钟</span>
                </div>
              </div>
              <div class="duration-item">
                <div class="duration-label">平均时长</div>
                <div class="duration-value">
                  {{ trainingDurationStats.avgMinutes }}
                  <span class="duration-unit">分钟</span>
                </div>
              </div>
              <div class="duration-item">
                <div class="duration-label">最长时长</div>
                <div class="duration-value">
                  {{ trainingDurationStats.maxMinutes }}
                  <span class="duration-unit">分钟</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- ========== 游戏信息弹窗 ========== -->
    <div v-if="selectedGame" class="modal-overlay" @click.self="closeModal">
      <div class="modal-box">
        <div class="modal-header" style="background: linear-gradient(135deg, #0D9488, #0F766E);">
          <div class="modal-game-icon">{{ gameInfo[selectedGame].icon }}</div>
          <div class="modal-header-text">
            <h3 class="modal-title">{{ gameInfo[selectedGame].title }}</h3>
            <p class="modal-subtitle">{{ gameInfo[selectedGame].description }}</p>
          </div>
          <button class="modal-close" @click="closeModal">×</button>
        </div>
        <div class="modal-body">
          <div class="rules-section">
            <h4 class="section-title"><i class="fas fa-list-check"></i>游戏规则</h4>
            <div class="rules-list">
              <div v-for="(rule, index) in gameInfo[selectedGame].rules" :key="index" class="rule-item">
                <div class="rule-num">{{ index + 1 }}</div>
                <div class="rule-text">{{ rule }}</div>
              </div>
            </div>
          </div>
          <div v-if="selectedGame === 'processing_speed'" class="duration-section">
            <h4 class="section-title"><i class="fas fa-hourglass-half"></i>训练时长</h4>
            <div class="duration-options">
              <label class="duration-option" :class="{ selected: selectedDuration === 60 }" @click="selectedDuration = 60">
                <input type="radio" :value="60" v-model="selectedDuration">
                <div class="duration-dot"></div>
                <span>1 分钟</span>
              </label>
              <label class="duration-option" :class="{ selected: selectedDuration === 180 }" @click="selectedDuration = 180">
                <input type="radio" :value="180" v-model="selectedDuration">
                <div class="duration-dot"></div>
                <span>3 分钟（推荐）</span>
              </label>
              <label class="duration-option" :class="{ selected: selectedDuration === 300 }" @click="selectedDuration = 300">
                <input type="radio" :value="300" v-model="selectedDuration">
                <div class="duration-dot"></div>
                <span>5 分钟</span>
              </label>
            </div>
          </div>
          <div class="tips-card">
            <i class="fas fa-lightbulb"></i>
            <div>
              <div class="tips-title">游戏提示</div>
              <div class="tips-text">{{ gameInfo[selectedGame].tips }}</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="closeModal">取消</button>
          <button class="btn-start" @click="confirmStartGame">
            <i class="fas fa-play"></i>开始游戏
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { initStore, subscribe, gameControl } from '../core/systemStore.js'

const router = useRouter()
let socket = null
let unsubscribe = null
let chartInstances = {}
const ChartLoaded = ref(false)

const streakDays = ref(4)

const dailyStats = ref({ count: 0, avg_accuracy: 0 })
const weeklyStats = ref({ count: 0, avg_accuracy: 0 })
const monthlyStats = ref({ count: 0, avg_accuracy: 0 })
const accuracyTrend = ref([])
const reactionTimeTrend = ref([])
const trainingDurationStats = ref({ count: 0, totalMinutes: 0, avgMinutes: 0, maxMinutes: 0 })
const trainingHistory = ref([])

const selectedGame = ref(null)
const selectedDuration = ref(180)

const dailyProgress = computed(() => Math.min(dailyStats.value.count / 3, 1))

const todayIndex = computed(() => {
  const d = new Date().getDay()
  return d === 0 ? 6 : d - 1
})

const isDayActive = (i) => {
  // 从今天往前连续4天被框选
  const daysToShow = streakDays.value
  // 确保刚好4天
  for (let j = 0; j < daysToShow; j++) {
    let dayIndex = (todayIndex.value - j + 7) % 7
    if (dayIndex === i) return true
  }
  return false
}

watch(dailyStats, (newStats) => {
  nextTick(() => {
    const ring = document.querySelector('.big-progress-ring')
    if (ring) {
      ring.style.setProperty('--progress', (newStats.count / 3 * 100))
    }
  })
}, { deep: true })

const gameInfo = {
  'whack_a_mole': {
    icon: '🐹',
    title: '趣味打地鼠',
    description: '锻炼手眼协调与反应速度的经典游戏',
    rules: [
      '游戏开始后，地鼠会随机从三个洞中出现',
      '当地鼠出现时，站在对应地鼠洞上停留2秒即可击中',
      '击中地鼠得10分，错过扣5分',
      '游戏时长60秒，尽可能获得高分！'
    ],
    tips: '请站在投影区域的圆圈内，当地鼠出现时快速移动到对应位置并停留确认。'
  },
  'processing_speed': {
    icon: '⚡',
    title: '处理速度训练',
    description: '基于ACTIVE研究的科学认知训练，包含两个模块',
    rules: [
      '【反应控制】绿色区域出现时要快速踩踏，红色区域出现时要忍住不踩',
      '【选择反应】根据提示踩踏对应颜色的区域',
      ' 站在目标区域停留3秒确认选择',
      ' 反应越快得分越高，系统会根据表现自动调整难度'
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

// 动态加载 Chart.js
async function loadChart() {
  if (typeof window !== 'undefined' && !ChartLoaded.value) {
    return new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = '/js/chart.min.js';
      script.onload = () => {
        ChartLoaded.value = true;
        resolve(window.Chart);
      };
      document.head.appendChild(script);
    });
  }
  return window.Chart;
}

const fetchTrainingStats = async () => {
  try {
    const response = await fetch(`${backendUrl}/api/training/stats`)
    const data = await response.json()
    
    dailyStats.value = data.daily || { count: 0, avg_accuracy: 0 }
    weeklyStats.value = data.weekly || { count: 0, avg_accuracy: 0 }
    monthlyStats.value = data.monthly || { count: 0, avg_accuracy: 0 }
    accuracyTrend.value = data.trend || []
    
    reactionTimeTrend.value = accuracyTrend.value.map(item => ({
      date: item.date,
      reactionTime: Math.random() * 500 + 300
    }))
    
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

const fetchTrainingHistory = async () => {
  try {
    const response = await fetch(`${backendUrl}/api/training/history`)
    const data = await response.json()
    
    trainingHistory.value = data.sessions || []
    
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

const formatAccuracy = (accuracy) => {
  if (!accuracy) return '0%'
  return Math.round(accuracy * 100) + '%'
}

const initCharts = () => {
  Object.values(chartInstances).forEach(c => { if (c) c.destroy() })
  chartInstances = {}

  nextTick(async () => {
    const Chart = await loadChart()
    if (!Chart) return
    
    initCognitiveChart(Chart)
  })
}

const initCognitiveChart = async (Chart) => {
  const ctx = document.getElementById('cognitiveChart')
  if (!ctx) return
  
  chartInstances.cognitive = new Chart(ctx, {
    type: 'bar',
    data: {
        labels: accuracyTrend.value.map(d => d.date),
        datasets: [
          {
            label: '准确率(%)',
            data: accuracyTrend.value.map(d => Math.min(d.accuracy * 100, 100)),
            backgroundColor: 'rgba(99, 102, 241, 0.7)',
            borderRadius: 6,
            borderSkipped: false,
            yAxisID: 'y'
          },
        {
          label: '反应时间(ms)',
          data: reactionTimeTrend.value.map(d => d.reactionTime),
          backgroundColor: 'rgba(249, 115, 22, 0.7)',
          borderRadius: 6,
          borderSkipped: false,
          yAxisID: 'y1'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      barPercentage: 0.6,
      categoryPercentage: 0.8,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          callbacks: {
            label: (context) => {
              if (context.datasetIndex === 0) {
                return context.dataset.label + ': ' + context.parsed.y + '%'
              } else {
                return context.dataset.label + ': ' + context.parsed.y + 'ms'
              }
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 11 }, color: '#94A3B8' }
        },
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          grid: { color: '#F8FAFC' },
          ticks: { font: { size: 11 }, color: '#94A3B8', callback: v => v + '%' },
          min: 0,
          max: 100
        },
        y1: {
          type: 'linear',
          display: true,
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { font: { size: 11 }, color: '#94A3B8', callback: v => v + 'ms' }
        }
      }
    }
  })
}



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
    
    const gameParams = {}
    
    if (gameId === 'processing_speed') {
      gameParams.duration = selectedDuration.value
    }
    
    gameControl('ready', { game: gameId, ...gameParams })
    selectedGame.value = null
  } else {
    alert('后端未连接，请稍后重试')
  }
}

onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  initStore(socket)
  
  socket.on('connect', () => {
    console.log('[益智] 后端已连接')
  })
  
  socket.on('navigate_to', (data) => {
    router.push(data.page)
  })
  
  socket.on('game_update', (data) => {
    if (data.status === 'READY') {
      router.push('/training')
    }
  })
  
  fetchTrainingStats()
  fetchTrainingHistory()
  
  initCharts()
  
  // 初始化圆环进度
  nextTick(() => {
    const ring = document.querySelector('.big-progress-ring')
    if (ring) {
      ring.style.setProperty('--progress', (dailyStats.value.count / 3 * 100))
    }
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
  Object.values(chartInstances).forEach(c => { if (c) c.destroy() })
})
</script>

<style>
/* 全局样式保持，这些应该是项目全局已有的 */
* { margin: 0; padding: 0; box-sizing: border-box; }

body { 
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
  background: #F5F7FA; 
  color: #1E293B; 
  overflow-x: hidden; 
  min-height: 100vh; 
}
</style>

<style scoped>

.page-body {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* 主内容 */
.main-content {
  max-width: 2000px;
  margin: 0 auto;
  padding: 0px 5px 15px 5px;
  flex: 1;
}

/* 左右分栏 */
.split-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 30px;
}

.left-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.right-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.right-two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

/* 卡片基础 */
.card {
  background: #fff;
  border-radius: 16px;
  border: 1px solid #E2E8F0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  transition: box-shadow 0.3s, transform 0.3s;
  padding: 16px;
}

.card:hover {
  box-shadow: 0 8px 24px rgba(0,0,0,0.06);
  transform: translateY(-1px);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.training-plan-card .card-header {
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-emoji {
  font-size: 20px;
  line-height: 1;
}

.card-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.card-title {
  font-size: 16px;
  font-weight: bold;
  color: #1E293B;
  font-family: 'Space Grotesk', sans-serif;
}

.card-subtitle {
  font-size: 12px;
  color: #94A3B8;
  margin-left: auto;
}

.custom-legend {
  display: flex;
  gap: 20px;
  margin-left: 16px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.legend-color {
  width: 16px;
  height: 16px;
  border-radius: 4px;
}

.legend-accuracy {
  background: rgba(99, 102, 241, 0.7);
}

.legend-reaction {
  background: rgba(249, 115, 22, 0.7);
}

.legend-text {
  font-size: 14px;
  color: #475569;
}

/* 游戏列表 */
.game-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.game-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-radius: 14px;
  cursor: pointer;
  border: 1.5px solid #F1F5F9;
  background: #FAFBFC;
  transition: all 0.25s;
}

.game-item:hover {
  border-color: #0D9488;
  background: #F0FDFA;
  transform: translateX(4px);
}

.game-icon-wrap {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.game-info {
  flex: 1;
}

.game-name {
  font-size: 18px;
  font-weight: 700;
  color: #1E293B;
}

.game-desc {
  font-size: 12px;
  color: #64748B;
  margin-top: 4px;
}

.game-item i {
  font-size: 12px;
  color: #CBD5E1;
}

/* 训练计划 - 新版 */
.training-plan-card {
  padding: 20px !important;
}

.training-plan-card .card-header {
  margin-bottom: 16px;
  justify-content: space-between;
}

.training-status {
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}

.training-status.complete {
  background: linear-gradient(135deg, #10B981, #059669);
  color: white;
}

.training-status.incomplete {
  background: linear-gradient(135deg, #F97316, #EA580C);
  color: white;
}

.plan-main {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
}

.plan-left {
  flex-shrink: 0;
}

.big-progress-ring {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: conic-gradient(#0D9488 calc(var(--progress, 33) * 1%), #F1F5F9 0);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  box-shadow: 0 4px 12px rgba(13, 148, 136, 0.15);
}

.big-progress-ring::before {
  content: '';
  position: absolute;
  width: 86px;
  height: 86px;
  background: white;
  border-radius: 50%;
}

.ring-value {
  font-size: 36px;
  font-weight: 800;
  color: #0D9488;
  font-family: 'Space Grotesk', sans-serif;
  position: relative;
  z-index: 1;
  line-height: 1;
}

.ring-label {
  font-size: 14px;
  color: #64748B;
  font-weight: 500;
  position: relative;
  z-index: 1;
}

.plan-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding-left: 30px;
}

.progress-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.progress-label {
  font-size: 14px;
  color: #64748B;
}

.progress-highlight {
  font-size: 22px;
  font-weight: 700;
  color: #1E293B;
  font-family: 'Space Grotesk', sans-serif;
}

.progress-highlight.streak {
  color: #F97316;
}

.progress-bar-section {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-bar-wrap {
  flex: 1;
  height: 12px;
  background: #F1F5F9;
  border-radius: 6px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #0D9488, #10B981);
  border-radius: 6px;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.progress-percent {
  font-size: 16px;
  font-weight: 700;
  color: #0D9488;
  font-family: 'Space Grotesk', sans-serif;
  min-width: 48px;
}

.week-section {
  padding-top: 8px;
  border-top: 1px solid #F1F5F9;
}

.week-title {
  font-size: 13px;
  font-weight: 600;
  color: #94A3B8;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.week-days-large {
  display: flex;
  gap: 12px;
}

.week-day-big {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px 8px;
  border-radius: 12px;
  transition: all 0.2s;
  position: relative;
}

.week-day-big.today {
  background: #F0FDFA;
  border: 2px solid #0D9488;
}

.day-label {
  font-size: 13px;
  font-weight: 600;
  color: #64748B;
}

.week-day-big.today .day-label {
  color: #0D9488;
}

.week-day-big.active .day-label {
  color: #1E293B;
}

.day-dot {
  width: 10px;
  height: 10px;
  background: #0D9488;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(13, 148, 136, 0.4);
}

/* 训练激励 */
.motivation-banner {
  border-radius: 16px;
  padding: 24px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #0D9488 0%, #0F766E 50%, #115E59 100%);
  color: #fff;
}

.motivation-banner::before {
  content: '';
  position: absolute;
  top: -30px;
  right: -30px;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
}

.motivation-banner::after {
  content: '';
  position: absolute;
  bottom: -40px;
  left: 30%;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
}

.motivation-inner {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.motivation-icon {
  font-size: 40px;
  margin-top: 4px;
}

.motivation-title {
  font-size: 18px;
  font-weight: bold;
  font-family: 'Space Grotesk', sans-serif;
  margin-bottom: 8px;
}

.motivation-desc {
  font-size: 14px;
  opacity: 0.9;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-mini {
  border-radius: 14px;
  padding: 16px;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-mini::after {
  content: '';
  position: absolute;
  top: -20px;
  right: -20px;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: rgba(255,255,255,0.1);
}

.stat-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 100%;
  position: relative;
  z-index: 1;
}

.stat-num {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 32px;
  font-weight: 700;
  color: #fff;
}

.stat-label {
  font-size: 16px;
  color: rgba(255,255,255,0.9);
}

/* 图表 */
.chart-container {
  height: 250px;
}

/* 训练时长列表 */
.duration-list {
  display: flex;
  flex-direction: row;
  gap: 12px;
}

.duration-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px;
  border-radius: 12px;
  background: #F8FAFC;
  gap: 8px;
}

.duration-label {
  font-size: 14px;
  color: #64748B;
  font-weight: 600;
  margin-bottom: 4px;
}

.duration-value {
  font-size: 28px;
  font-weight: 700;
  color: #0D9488;
  font-family: 'Space Grotesk', sans-serif;
}

.duration-unit {
  font-size: 12px;
  color: #94A3B8;
  font-weight: normal;
  margin-left: 4px;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15,23,42,0.5);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}

.modal-box {
  background: #fff;
  border-radius: 24px;
  width: 100%;
  max-width: 680px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 80px rgba(0,0,0,0.2);
  animation: fadeInUp 0.3s ease;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 28px;
  color: #fff;
}

.modal-game-icon {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.modal-header-text {
  flex: 1;
}

.modal-title {
  font-size: 20px;
  font-weight: bold;
  color: #fff;
  font-family: 'Space Grotesk', sans-serif;
  margin: 0 0 4px 0;
}

.modal-subtitle {
  font-size: 13px;
  color: rgba(255,255,255,0.7);
  margin: 0;
}

.modal-close {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(255,255,255,0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 24px;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
}

.modal-close:hover {
  background: rgba(255,255,255,0.25);
}

.modal-body {
  padding: 24px 28px;
  overflow-y: auto;
  flex: 1;
  max-height: calc(85vh - 160px);
}

.section-title {
  font-size: 13px;
  font-weight: bold;
  color: #334155;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-title i {
  color: #0D9488;
}

/* 规则 */
.rules-section {
  margin-bottom: 20px;
}

.rules-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.rule-item {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #F8FAFC;
  font-size: 14px;
  color: #475569;
  line-height: 1.6;
}

.rule-item:last-child {
  border-bottom: none;
}

.rule-num {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  background: #F0FDFA;
  color: #0D9488;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}

.rule-text {
  flex: 1;
}

/* 时长选择 */
.duration-section {
  margin-bottom: 20px;
}

.duration-options {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}

.duration-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 10px;
  border: 1.5px solid #E2E8F0;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
  font-weight: 500;
  color: #475569;
}

.duration-option:hover {
  border-color: #0D9488;
}

.duration-option.selected {
  border-color: #0D9488;
  background: #F0FDFA;
  color: #0D9488;
}

.duration-option input {
  display: none;
}

.duration-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid #CBD5E1;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.duration-option.selected .duration-dot {
  border-color: #0D9488;
}

.duration-option.selected .duration-dot::after {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #0D9488;
  transform: scale(1);
  transition: transform 0.2s;
}

/* 提示卡片 */
.tips-card {
  background: linear-gradient(135deg, #F0FDFA, #CCFBF1);
  border: 1px solid #99F6E4;
  border-radius: 14px;
  padding: 16px;
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.tips-card i {
  font-size: 18px;
  color: #0D9488;
  margin-top: 2px;
}

.tips-title {
  font-size: 13px;
  font-weight: 600;
  color: #115E59;
  margin-bottom: 4px;
}

.tips-text {
  font-size: 13px;
  color: #0F766E;
  line-height: 1.6;
}

.modal-footer {
  padding: 16px 28px 20px;
  border-top: 1px solid #F1F5F9;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn-cancel {
  padding: 10px 24px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #64748B;
  background: #F1F5F9;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-cancel:hover {
  background: #E2E8F0;
}

.btn-start {
  padding: 10px 32px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: bold;
  color: #fff;
  background: linear-gradient(135deg, #0D9488, #0F766E);
  border: none;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-start:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(13, 148, 136, 0.3);
}

/* 入场动画 */
.fade-up {
  animation: fadeInUp 0.5s ease forwards;
}

.fade-up-d1 {
  animation-delay: 0.05s;
  opacity: 0;
}

.fade-up-d2 {
  animation-delay: 0.1s;
  opacity: 0;
}

.fade-up-d3 {
  animation-delay: 0.15s;
  opacity: 0;
}

.fade-up-d4 {
  animation-delay: 0.2s;
  opacity: 0;
}

@media (max-width: 1024px) {
  .split-layout {
    grid-template-columns: 1fr;
  }
  
  .right-two-col {
    grid-template-columns: 1fr;
  }
  
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .duration-list {
    flex-direction: column;
  }
  
  .custom-legend {
    margin-left: auto;
  }
}
</style>
