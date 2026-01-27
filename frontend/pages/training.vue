<template>
  <div class="training-page">
    <div class="header-control-area">
      <div class="status-info">
        <h1>互动状态：{{ game.status === 'PLAYING' ? '运行中' : '待机中' }}</h1>
        <p v-if="game.status === 'READY'" class="hint-text">请进入目标区域开始游戏</p>
      </div>
      <div class="top-btns">
        <button v-if="game.status === 'PLAYING'" @click="pauseGame" class="btn-large pause-btn">暂 停</button>
        <button @click="exitGame" class="btn-large exit-btn">退 出</button>
      </div>
    </div>

    <div class="metrics-grid">
      <div class="metric-card">
        <span class="label">当前难度</span>
        <span class="value accent">{{ game.difficulty }}</span>
      </div>
      <div class="metric-card">
        <span class="label">实时心率</span>
        <span class="value">{{ health.bpm }} <small>BPM</small></span>
      </div>
      <div class="metric-card">
        <span class="label">状态感知</span>
        <span class="value">{{ health.emotionCn }}</span>
      </div>
      <div class="metric-card">
        <span class="label">参与意愿</span>
        <span class="value accent">{{ game.engagement }}</span>
      </div>
      <div class="metric-card">
        <span class="label">活动负荷</span>
        <span class="value">{{ game.load }}</span>
      </div>
      <div class="metric-card">
        <span class="label">累计得分</span>
        <span class="value accent">{{ game.score }}</span>
      </div>
    </div>

    <div class="visual-charts">
      <div class="chart-container">
        <h3>生理状态变化图 (实时)</h3>
        <div class="chart-mock">图表渲染中...</div>
      </div>
      <div class="chart-container">
        <h3>动态负荷分布</h3>
        <div class="chart-mock">数据分析中...</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { useRouter } from 'vue-router'

const router = useRouter()
const game = ref({ status: 'SLEEP', score: 0, difficulty: '正常', engagement: '中', load: '正常' })
const health = ref({ bpm: '--', emotionCn: '感知中' })

const emotionMap = {
  'angry': '焦虑', 'disgust': '不适', 'fear': '紧张',
  'happy': '愉悦', 'sad': '低落', 'surprise': '惊讶', 'neutral': '平静'
}

let socket = null

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)
  
  // 载入页面即通知后端进入预备状态（显示白圈）
  socket.emit('game_control', { action: 'ready' })

  socket.on('game_update', (data) => {
    game.value = data
  })

  socket.on('tablet_stream', (res) => {
    if (res.state) {
      const cn = emotionMap[res.state.emotion] || '平静'
      health.value = { ...res.state, emotionCn: cn }
    }
  })
})

onUnmounted(() => {
  if (socket) {
    socket.emit('game_control', { action: 'stop' })
    socket.disconnect()
  }
})

const pauseGame = () => {
  socket.emit('game_control', { action: 'pause' })
}

const exitGame = () => {
  socket.emit('game_control', { action: 'stop' })
  router.back()
}
</script>

<style scoped>
/* 严格保持 16:10 布局，禁止滚动 */
.training-page {
  height: 100%; display: flex; flex-direction: column; gap: 30px;
  padding: 40px; overflow: hidden; background: #FFF;
}
.header-control-area {
  display: flex; justify-content: space-between; align-items: center;
  padding: 30px; background: #F9F9F9; border-radius: 30px;
}
.status-info h1 { font-size: 36px; color: #333; }
.hint-text { font-size: 24px; color: #FF7222; font-weight: bold; margin-top: 10px; }
.top-btns { display: flex; gap: 20px; }
.btn-large {
  width: 220px; height: 90px; border-radius: 45px; font-size: 32px; 
  font-weight: 900; border: none; cursor: pointer;
}
.pause-btn { background: #FFD111; color: #333; }
.exit-btn { background: #333; color: #FFF; }

.metrics-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 25px;
}
.metric-card {
  background: #FFF; border: 2px solid #F0F0F0; padding: 30px; 
  border-radius: 25px; display: flex; flex-direction: column; gap: 10px;
}
.metric-card .label { font-size: 20px; color: #888; }
.metric-card .value { font-size: 48px; font-weight: 900; color: #333; }
.metric-card .value.accent { color: #FF7222; }

.visual-charts { display: grid; grid-template-columns: 1fr 1fr; gap: 25px; flex: 1; }
.chart-container { 
  background: #F9F9F9; border-radius: 30px; padding: 25px; 
  display: flex; flex-direction: column; 
}
.chart-mock { flex: 1; display: flex; align-items: center; justify-content: center; color: #CCC; font-size: 20px; }
</style>