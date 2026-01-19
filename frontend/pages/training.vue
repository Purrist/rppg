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
        <div class="welcome-screen" v-if="!gameStarted">
          <h1 class="main-title">色词测试 · 认知训练</h1>
          <p class="instructions-text">反应力挑战！你需要选择文字呈现的颜色，而不是文字的内容，每题仅有2秒反应时间，看看你能在三分钟内答对多少吧！</p>
          
          <div class="start-button-container">
            <button 
              class="start-button" 
              @click="startGame"
            >
              <span class="button-text">开始测试</span>
            </button>
            <p class="button-hint">点击按钮开始测试</p>
          </div>
        </div>

        <div class="game-screen" v-else>
          <div class="top-bar">
            <div class="progress-bar" :class="{danger: isTimeRunning}"></div>
          </div>

          <div class="main-content">
            <div class="stats-column left-stats">
              <div class="stat-item">
                <span class="value">{{ correctCount }}</span>
                <span class="label">答对</span>
              </div>
              <div class="stat-item">
                <span class="value">{{ incorrectCount }}</span>
                <span class="label">答错</span>
              </div>
              <div class="stat-item">
                <span class="value">{{ missedCount }}</span>
                <span class="label">遗漏</span>
              </div>
            </div>

            <div class="word-display-area">
              <div class="word-box">
                <div class="word-text" :style="{color: currentWordColor}">{{ currentWord }}</div>
              </div>
              
              <div class="feedback-container" v-if="showFeedback" :class="feedbackType">
                <div class="feedback-icon">{{ feedbackIcon }}</div>
                <div class="feedback-text">{{ feedbackText }}</div>
                <div class="feedback-reaction" v-if="reactionTime > 0">
                  反应时间: {{ reactionTime }}ms
                </div>
              </div>
            </div>

            <div class="stats-column right-stats">
              <div class="stat-item">
                <span class="value">{{ accuracy }}%</span>
                <span class="label">准确率</span>
              </div>
              <div class="stat-item">
                <span class="value">{{ avgReactionTime }}ms</span>
                <span class="label">平均反应时间</span>
              </div>
            </div>
          </div>

          <div class="options-container">
            <div 
              v-for="(word, index) in words" 
              :key="word.text"
              class="option-btn"
              :class="{active: selectedOptionIndex === index, selected: screenState.selected_region === word.text}"
              @click="selectWord(word)"
            >
              <div class="option-content">
                <span class="option-text">{{ word.text }}</span>
                <div class="selection-indicator" v-if="screenState.selected_region === word.text">
                  <span class="indicator-icon">✓</span>
                  <span class="indicator-text">已选择</span>
                </div>
              </div>
            </div>
          </div>

          <div class="bottom-bar">
            <span class="timer-display">{{ formattedTime }}</span>
            <button class="restart-button" @click="restartGame">重新开始</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const host = ref('')
const gameStarted = ref(false)
const isTimeRunning = ref(false)
const correctCount = ref(0)
const incorrectCount = ref(0)
const missedCount = ref(0)
const currentWord = ref('')
const currentWordColor = ref('#000000')
const showFeedback = ref(false)
const feedbackText = ref('')
const feedbackIcon = ref('')
const feedbackType = ref('')
const reactionTime = ref(0)
const selectedOptionIndex = ref(-1)
const screenState = ref({})

const words = ref([
  { text: '红', color: '#ff0000' },
  { text: '黄', color: '#ffff00' },
  { text: '绿', color: '#00ff00' },
  { text: '蓝', color: '#0000ff' },
  { text: '紫', color: '#800080' },
  { text: '橙', color: '#ff8000' }
])

const GAME_DURATION = 180
const TRIAL_DURATION = 2000
const FEEDBACK_DURATION = 1500

let gameTimer = null
let trialTimer = null
let trialTimeout = null
let trialStartTime = 0
let totalReactionTime = 0
let timeLeft = GAME_DURATION
let screenStateInterval = null

const accuracy = computed(() => {
  const total = correctCount.value + incorrectCount.value + missedCount.value
  return total > 0 ? Math.round((correctCount.value / total) * 100) : 0
})

const avgReactionTime = computed(() => {
  return correctCount.value > 0 ? Math.round(totalReactionTime / correctCount.value) : 0
})

const formattedTime = computed(() => {
  const minutes = Math.floor(timeLeft / 60)
  const seconds = timeLeft % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})

const startGame = () => {
  gameStarted.value = true
  correctCount.value = 0
  incorrectCount.value = 0
  missedCount.value = 0
  totalReactionTime = 0
  timeLeft = GAME_DURATION
  
  prepareNextRound()
  startMainTimer()
}

const prepareNextRound = () => {
  showFeedback.value = false
  isTimeRunning.value = false
  selectedOptionIndex.value = -1
  
  const randomIndex = Math.floor(Math.random() * words.value.length)
  currentWord.value = words.value[randomIndex].text
  currentWordColor.value = words.value[randomIndex].color
  
  trialTimeout = setTimeout(() => {
    showStimulus()
  }, 1000)
}

const showStimulus = () => {
  isTimeRunning.value = true
  trialStartTime = performance.now()
  
  trialTimer = setInterval(() => {
    if (!gameStarted.value) {
      clearInterval(trialTimer)
      return
    }
    
    const elapsed = performance.now() - trialStartTime
    const remaining = TRIAL_DURATION - elapsed
    
    if (remaining <= 0) {
      handleResponse(null, true)
    }
  }, 100)
}

const selectWord = (word) => {
  if (!isTimeRunning.value || !gameStarted.value) return
  
  const reactionTime = Math.round(performance.now() - trialStartTime)
  
  clearInterval(trialTimer)
  clearTimeout(trialTimeout)
  
  const isCorrect = word.text === currentWord.value
  
  if (isCorrect) {
    correctCount.value++
    totalReactionTime += reactionTime
    displayFeedback('correct', reactionTime)
  } else {
    incorrectCount.value++
    displayFeedback('incorrect', reactionTime)
  }
  
  updateScore(isCorrect)
}

const handleResponse = (event, isTimeout) => {
  if (!gameStarted.value) return
  
  clearInterval(trialTimer)
  clearTimeout(trialTimeout)
  
  if (isTimeout) {
    missedCount.value++
    displayFeedback('missed', 0)
  }
  
  updateScore(false)
}

const displayFeedback = (type, reactionTimeValue) => {
  showFeedback.value = true
  reactionTime.value = reactionTimeValue
  
  switch (type) {
    case 'correct':
      feedbackType.value = 'correct'
      feedbackIcon.value = '✓'
      feedbackText.value = '真棒，答对啦！'
      break
    case 'incorrect':
      feedbackType.value = 'incorrect'
      feedbackIcon.value = '✗'
      feedbackText.value = '诶哟，答错了'
      break
    case 'missed':
      feedbackType.value = 'missed'
      feedbackIcon.value = '✗'
      feedbackText.value = '哎呀，漏答了'
      break
  }
  
  setTimeout(() => {
    showFeedback.value = false
    reactionTime.value = 0
    if (timeLeft > 0) {
      prepareNextRound()
    }
  }, FEEDBACK_DURATION)
}

const updateScore = async (correct) => {
  try {
    await fetch(`http://${host.value}:8080/api/update_score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ correct })
    })
  } catch (e) {
    console.error('更新分数失败:', e)
  }
}

const startMainTimer = () => {
  gameTimer = setInterval(() => {
    if (!gameStarted.value) return
    
    timeLeft--
    
    if (timeLeft <= 0) {
      endGame()
    }
  }, 1000)
}

const endGame = () => {
  gameStarted.value = false
  clearInterval(gameTimer)
  clearInterval(trialTimer)
  clearTimeout(trialTimeout)
  showFeedback.value = false
  isTimeRunning.value = false
}

const restartGame = () => {
  if (confirm('确定要重新开始吗？')) {
    endGame()
    startGame()
  }
}

// 区域名称映射：英文 -> 中文
const regionNameMap = {
  'red': '红',
  'yellow': '黄',
  'blue': '蓝',
  'green': '绿',
  'purple': '紫',
  'orange': '橙'
}

const fetchScreenState = async () => {
  try {
    const response = await fetch(`http://${host.value}:8080/api/interaction_state`)
    const data = await response.json()
    
    // 更新屏幕状态
    screenState.value = data
    
    // 如果检测到手部遮挡（模拟脚踩踏）且置信度足够高，自动选择对应选项
    if (data.interaction_target !== 'none' && data.foot_detected) {
      const chineseRegionName = regionNameMap[data.interaction_target]
      if (chineseRegionName) {
        const selectedWord = words.value.find(w => w.text === chineseRegionName)
        if (selectedWord && isTimeRunning.value && gameStarted.value) {
          selectWord(selectedWord)
        }
      }
    }
  } catch (e) {
    console.error('获取交互状态失败:', e)
  }
}

onMounted(() => {
  host.value = window.location.hostname
  
  fetchScreenState()
  screenStateInterval = setInterval(fetchScreenState, 500)
})

onUnmounted(() => {
  if (gameTimer) clearInterval(gameTimer)
  if (trialTimer) clearInterval(trialTimer)
  if (trialTimeout) clearTimeout(trialTimeout)
  if (screenStateInterval) clearInterval(screenStateInterval)
})
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
  background: #ffffff;
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
  overflow: hidden;
}

/* 欢迎屏幕 */
.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2rem;
  text-align: center;
  height: 100%;
  padding: 0 5%;
}

.main-title {
  font-size: 3rem;
  font-weight: 700;
  color: #000000;
  margin-bottom: 1rem;
}

.instructions-text {
  font-size: 1.2rem;
  color: #666666;
  max-width: 60ch;
  line-height: 1.7;
}

.start-button-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.start-button {
  width: 200px;
  height: 200px;
  border-radius: 50%;
  background: linear-gradient(45deg, #00aaff, #0066ff);
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 0 20px rgba(0, 102, 255, 0.3);
  border: none;
  color: #ffffff;
  font-size: 1.5rem;
  font-weight: bold;
}

.start-button:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 25px rgba(0, 102, 255, 0.5);
}

.button-hint {
  font-size: 1rem;
  color: #666666;
}

/* 游戏屏幕 */
.game-screen {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  overflow: hidden;
}

/* 顶部进度条 */
.top-bar {
  width: 100%;
  height: 8px;
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
}

.progress-bar {
  width: 100%;
  height: 100%;
  border-radius: 4px;
  transition: width 0.1s linear, background-color 0.2s ease;
  background: linear-gradient(90deg, #00aaff, #0066ff);
  box-shadow: 0 0 8px #0066ff;
}

.progress-bar.danger {
  background: #ff0000;
  animation: pulse 0.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 主内容区域 */
.main-content {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: 1fr;
  flex: 1;
  gap: 2rem;
  padding: 2rem 3rem;
  position: relative;
  overflow: hidden;
}

/* 统计列 */
.stats-column {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1.5rem;
}

.stat-item {
  text-align: center;
}

.stat-item .value {
  font-size: 2.5rem;
  font-weight: 600;
  color: #000000;
}

.stat-item .label {
  font-size: 1rem;
  color: #666666;
  margin-top: 0.5rem;
  display: block;
}

/* 文字显示区域 */
.word-display-area {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  position: relative;
}

.word-box {
  padding: 2rem;
  background: #f5f5f5;
  border-radius: 20px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.word-text {
  font-size: 6rem;
  font-weight: 700;
  text-align: center;
}

/* 反馈容器 */
.feedback-container {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  z-index: 10;
  background: rgba(255, 255, 255, 0.95);
  padding: 2rem;
  border-radius: 20px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.feedback-icon {
  font-size: 4rem;
  font-weight: 700;
}

.feedback-text {
  font-size: 1.5rem;
  font-weight: 600;
  color: #000000;
  text-align: center;
}

/* 选项容器 */
.options-container {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  padding: 1rem;
  flex-wrap: wrap;
  background: #f8f9fa;
  border-top: 1px solid #e0e0e0;
}

/* 选项按钮 */
.option-btn {
  width: 120px;
  height: 120px;
  font-size: 2rem;
  font-weight: 600;
  color: #ffffff;
  border: 2px solid #000000;
  border-radius: 15px;
  cursor: pointer;
  transition: all 0.15s ease-out;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  flex-shrink: 0;
}

.option-btn.active {
  box-shadow: 0 0 20px rgba(0, 0, 0, 0.3);
  transform: scale(1.05);
}

.option-btn.selected {
  border-color: #10b981;
  border-width: 3px;
  box-shadow: 0 0 25px rgba(16, 185, 129, 0.3);
}

.option-content {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.option-text {
  font-size: 2.5rem;
  font-weight: 700;
  z-index: 1;
}

/* 选择指示器 */
.selection-indicator {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  z-index: 2;
}

.indicator-icon {
  font-size: 2rem;
  font-weight: 700;
  color: #10b981;
}

.indicator-text {
  font-size: 1rem;
  font-weight: 600;
  color: #10b981;
}

/* 底部栏 */
.bottom-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 3rem;
  background: #f5f5f5;
  border-top: 2px solid #e0e0e0;
}

.timer-display {
  font-size: 2rem;
  font-weight: 600;
  color: #000000;
}

.restart-button {
  font-size: 1rem;
  font-weight: bold;
  color: #ffffff;
  background-color: #ff6b6b;
  padding: 0.8rem 1.5rem;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.restart-button:hover {
  background-color: #e55a5a;
}

/* 选项按钮颜色配置 */
.option-btn:nth-child(1) {
  background-color: #ff0000;
}

.option-btn:nth-child(2) {
  background-color: #ffff00;
  color: #000000;
}

.option-btn:nth-child(3) {
  background-color: #00ff00;
  color: #000000;
}

.option-btn:nth-child(4) {
  background-color: #0000ff;
}

.option-btn:nth-child(5) {
  background-color: #800080;
}

.option-btn:nth-child(6) {
  background-color: #ff8000;
}
</style>
