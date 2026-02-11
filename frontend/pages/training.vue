<template>
  <div class="training-container">
    <div v-if="game.status === 'READY'" class="ready-view">
      <div class="center-hint">请进入目标区域开始游戏</div>
      <div class="bottom-bar">
        <span class="status-label">当前状态：待机中</span>
        <button @click="exitGame" class="big-exit-btn">退出游戏</button>
      </div>
    </div>

    <div v-else-if="game.status === 'PLAYING'" class="playing-view">
      <div class="header">
        <div class="title-group">
          <h1>正在游戏：打地鼠</h1>
          <div class="timer-bar"><div class="fill" :style="{width: (game.timer/60*100)+'%'}"></div></div>
        </div>
        <div class="top-btns">
          <button @click="togglePause" class="ctrl-btn">暂停</button>
          <button @click="exitGame" class="ctrl-btn exit">退出</button>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card"><span>心率</span><p>{{ health.bpm }} BPM</p></div>
        <div class="stat-card"><span>情绪</span><p>{{ health.emotionCn }}</p></div>
        <div class="stat-card"><span>得分</span><p>{{ game.score }}</p></div>
        <div class="stat-card"><span>参与意愿</span><p>高</p></div>
      </div>

      <div class="charts-area">
        <div class="chart-box"><h3>实时心率趋势</h3><div class="mock-chart pulse"></div></div>
        <div class="chart-box"><h3>情绪状态分布</h3><div class="mock-chart emotion"></div></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { useRouter } from 'vue-router'

const router = useRouter()
const game = ref({ status: 'SLEEP', score: 0, timer: 60 })
const health = ref({ bpm: '--', emotionCn: '检测中' })
let socket = null

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)
  socket.emit('game_control', { action: 'ready' })
  socket.on('game_update', d => game.value = d)
  socket.on('tablet_stream', res => {
    if (res.state) health.value = { ...res.state, emotionCn: '平静' }
  })
})

const exitGame = () => {
  socket.emit('game_control', { action: 'stop' })
  router.back()
}
</script>

<style scoped>
.training-container { height: 100%; width: 100%; background: #FFF; overflow: hidden; }

/* 待机样式 */
.ready-view { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.center-hint { font-size: 80px; font-weight: 900; color: #333; }
.bottom-bar { position: absolute; bottom: 50px; width: 100%; display: flex; justify-content: space-around; align-items: center; }
.big-exit-btn { width: 300px; height: 100px; background: #333; color: #FFF; border-radius: 50px; font-size: 32px; border: none; }
.status-label { font-size: 28px; color: #999; }

/* 游戏样式 */
.playing-view { padding: 40px; display: flex; flex-direction: column; gap: 30px; height: 100%; overflow-y: auto; }
.header { display: flex; justify-content: space-between; align-items: center; }
.timer-bar { width: 400px; height: 20px; background: #EEE; border-radius: 10px; overflow: hidden; margin-top: 10px; }
.timer-bar .fill { height: 100%; background: #FF7222; transition: width 1s linear; }
.ctrl-btn { width: 150px; height: 70px; border-radius: 35px; border: none; font-size: 24px; font-weight: bold; background: #FFD111; }
.ctrl-btn.exit { background: #EEE; margin-left: 20px; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
.stat-card { background: #F9F9F9; padding: 25px; border-radius: 20px; }
.stat-card span { color: #888; font-size: 18px; }
.stat-card p { font-size: 36px; font-weight: 900; color: #FF7222; }
.charts-area { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 1; min-height: 350px; }
.chart-box { background: #F9F9F9; border-radius: 25px; padding: 20px; }
</style>