<template>
  <div class="projection-canvas" :class="{ 'game-active': game.playing }">
    <div v-if="!game.playing" class="standby-screen">
      <div class="start-trigger">
        <svg viewBox="0 0 100 100" class="trigger-svg">
          <circle cx="50" cy="50" r="48" class="bg-ring" />
          <circle cx="50" cy="50" r="48" class="progress-ring"
            :style="{ strokeDashoffset: 301 - (301 * startProgress / 100) }" />
        </svg>
        <div class="trigger-label">将手放于此处<br>1秒后开始</div>
      </div>
      
      <div v-if="lastScore !== null" class="result-overlay">
        <h2>太棒了！</h2>
        <div class="final-score">最终得分：{{ lastScore }}</div>
      </div>
    </div>

    <template v-else>
      <div class="header">
        <div class="stat-item">倒计时: {{ game.timer }}s</div>
        <div class="stat-item score">得分: {{ game.score }}</div>
      </div>

      <div class="game-area">
        <div v-for="i in 3" :key="i" class="mole-hole">
          <div class="ring-box">
            <svg viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="45" class="game-bg-circle" />
              <circle cx="50" cy="50" r="45" class="game-progress-bar"
                :style="{ strokeDashoffset: 283 - (283 * holeProgress[i-1] / 100) }" />
            </svg>
          </div>
          <transition name="mole-jump">
            <div v-if="game.current_mole === i-1" class="mole-actor">🐹</div>
          </transition>
          <div class="hole-base"></div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { io } from 'socket.io-client'

const socket = io(`http://${window.location.hostname}:8080`)
const game = ref({ score: 0, timer: 0, playing: false, current_mole: -1 })
const holeProgress = ref([0, 0, 0])
const startProgress = ref(0)
const lastScore = ref(null)

socket.on('game_update', (data) => {
  // 监测游戏从 运行 -> 停止 的瞬间，记录分数
  if (game.value.playing && !data.playing) {
    lastScore.value = game.value.score
  }
  game.value = data
})

socket.on('screen_stream', (res) => {
  holeProgress.value = res.interact.progress
  // 使用中间那个“洞”（索引1）的进度作为开始触发器
  if (!game.value.playing) {
    startProgress.value = res.interact.progress[1] 
    if (startProgress.value >= 100) {
      socket.emit('start_game')
      lastScore.value = null // 开始新游戏时清空旧分
    }
  }
})
</script>

<style scoped>
.projection-canvas {
  width: 1920px; height: 1080px; background: #000; color: #fff;
  position: fixed; inset: 0; overflow: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  transition: background 0.5s;
}
.projection-canvas.game-active { background: #FFFFFF; color: #333; }

/* 待机界面样式 */
.standby-screen { display: flex; flex-direction: column; align-items: center; gap: 50px; }
.start-trigger { position: relative; width: 400px; height: 400px; }
.trigger-svg { transform: rotate(-90deg); }
.bg-ring { fill: none; stroke: rgba(255,255,255,0.1); stroke-width: 4; }
.progress-ring { 
  fill: none; stroke: #FFFFFF; stroke-width: 6; 
  stroke-dasharray: 301; transition: stroke-dashoffset 0.1s;
}
.trigger-label {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  text-align: center; font-size: 32px; color: #fff; line-height: 1.5;
}

/* 结算显示 */
.result-overlay { text-align: center; animation: fadeIn 0.5s; }
.result-overlay h2 { font-size: 80px; color: #FFD111; margin-bottom: 20px; }
.final-score { font-size: 50px; }

/* 游戏过程样式 */
.header { width: 100%; padding: 60px 100px; display: flex; justify-content: space-between; font-size: 70px; font-weight: 900; }
.score { color: #FF7222; }
.game-area { flex: 1; width: 100%; display: flex; justify-content: space-around; align-items: center; }
.mole-hole { width: 400px; height: 500px; position: relative; }
.ring-box { position: absolute; top: 0; left: 0; width: 400px; height: 400px; z-index: 10; }
.game-bg-circle { fill: none; stroke: rgba(0,0,0,0.05); stroke-width: 8; }
.game-progress-bar { fill: none; stroke: #FF7222; stroke-width: 10; stroke-dasharray: 283; transform: rotate(-90deg); transform-origin: 50% 50%; }
.mole-actor { position: absolute; top: 50px; left: 50px; width: 300px; height: 300px; font-size: 200px; display: flex; align-items: center; justify-content: center; z-index: 5; }
.hole-base { position: absolute; bottom: 50px; width: 400px; height: 100px; background: #EEE; border-radius: 50%; }

@keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
</style>