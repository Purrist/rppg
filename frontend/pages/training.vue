<template>
  <div class="training-container">
    <div class="header-control">
      <div class="info">
        <h1>状态感知：{{ game.status === 'PAUSED' ? '已暂停' : (game.status === 'PLAYING' ? '运行中' : '待机') }}</h1>
        <p v-if="game.status === 'READY'" class="hint">请进入投影区域激活启动</p>
      </div>
      <div class="btns">
        <button @click="togglePause" class="btn-huge pause">{{ game.status === 'PAUSED' ? '继 续' : '暂 停' }}</button>
        <button @click="exit" class="btn-huge exit">退 出</button>
      </div>
    </div>

    <div class="metrics-row">
      <div class="m-card"><span>当前难度</span><p>{{ game.difficulty }}</p></div>
      <div class="m-card"><span>心率 (BPM)</span><p>{{ health.bpm }}</p></div>
      <div class="m-card"><span>当前情绪</span><p>{{ health.emotionCn }}</p></div>
      <div class="m-card"><span>参与意愿</span><p>{{ game.engagement }}</p></div>
    </div>

    <div class="charts-section">
      <div class="chart-box">
        <h3>实时心率图 (状态感知)</h3>
        <svg viewBox="0 0 400 150" class="realtime-svg">
          <path d="M0,75 L40,75 L50,30 L65,120 L75,75 L120,75" class="heart-line" />
        </svg>
      </div>
      <div class="chart-box">
        <h3>情绪变化趋势</h3>
        <div class="emotion-bar-container">
          <div v-for="e in 5" :key="e" class="emo-bar" :style="{ height: (Math.random()*80+20)+'%' }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

const game = ref({ status: 'SLEEP', difficulty: '正常', engagement: '高' })
const health = ref({ bpm: '--', emotionCn: '感知中' })
let socket = null

const emotionMap = { 'happy': '愉悦', 'neutral': '平静', 'sad': '低落', 'angry': '焦虑' }

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)
  socket.emit('game_control', { action: 'ready' })
  socket.on('game_update', d => game.value = d)
  socket.on('tablet_stream', res => {
    if (res.state) {
      health.value = { ...res.state, emotionCn: emotionMap[res.state.emotion] || '平静' }
    }
  })
})

const togglePause = () => socket.emit('game_control', { action: 'pause' })
const exit = () => { socket.emit('game_control', { action: 'stop' }); useRouter().back() }
</script>

<style scoped>
.training-container {
  height: 100%; overflow-y: auto; padding: 40px; display: flex; flex-direction: column; gap: 30px;
  -ms-overflow-style: none; scrollbar-width: none; /* 隐藏滚动条 */
}
.training-container::-webkit-scrollbar { display: none; }

.header-control { display: flex; justify-content: space-between; align-items: center; background: #F9F9F9; padding: 30px; border-radius: 30px; }
.btn-huge { width: 220px; height: 100px; border-radius: 50px; font-size: 32px; font-weight: 900; border: none; }
.pause { background: #FFD111; }
.exit { background: #333; color: #FFF; }

.metrics-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
.m-card { background: #FFF; border: 2px solid #F0F0F0; padding: 25px; border-radius: 25px; }
.m-card span { color: #888; font-size: 18px; }
.m-card p { font-size: 40px; font-weight: 900; color: #FF7222; margin-top: 10px; }

.charts-section { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 1; min-height: 400px; }
.chart-box { background: #F9F9F9; border-radius: 30px; padding: 25px; }
.heart-line { fill: none; stroke: #FF3B30; stroke-width: 3; stroke-linecap: round; }
.emotion-bar-container { height: 200px; display: flex; align-items: flex-end; gap: 15px; justify-content: center; }
.emo-bar { width: 30px; background: #FF7222; border-radius: 15px 15px 0 0; }
</style>