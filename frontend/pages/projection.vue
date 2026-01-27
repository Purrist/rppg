<template>
  <div class="projection-canvas" :class="{ 'is-sleep': game.status === 'SLEEP' }">
    
    <div v-if="game.status === 'SLEEP'" class="sleep-mode"></div>

    <div v-else-if="game.status === 'READY'" class="ready-mode">
      <div class="trigger-circle">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="48" class="track" />
          <circle cx="50" cy="50" r="48" class="bar"
            :style="{ strokeDashoffset: 301 - (301 * interactProgress[1] / 100) }" />
        </svg>
        <div class="center-text">请将手放入<br>目标区域</div>
      </div>
    </div>

    <div v-else-if="game.status === 'PLAYING'" class="playing-mode">
      <div class="game-header">
        <div class="score-display">得分：{{ game.score }}</div>
        <div class="difficulty-tag">难度：{{ game.difficulty }}</div>
      </div>
      
      <div class="holes-container">
        <div v-for="(hole, i) in 3" :key="i" class="hole-item">
          <div v-if="game.current_mole === i" class="mole-avatar">🐹</div>
          <div class="hit-progress" :style="{ height: interactProgress[i] + '%' }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

const game = ref({ status: 'SLEEP', score: 0, current_mole: -1, difficulty: '正常' })
const interactProgress = ref([0, 0, 0])
let socket = null

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)
  
  socket.on('game_update', (data) => {
    game.value = data
  })

  socket.on('screen_stream', (data) => {
    if (data.interact) {
      interactProgress.value = data.interact.progress
    }
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})
</script>

<style scoped>
/* 投影端样式：严格 16:9 全屏，样式冻结 */
.projection-canvas {
  width: 100vw; height: 100vh; background: #000;
  overflow: hidden; position: relative;
}
.is-sleep { background: #000 !important; }

/* 预备态样式 */
.ready-mode {
  height: 100%; display: flex; align-items: center; justify-content: center;
}
.trigger-circle { position: relative; width: 500px; height: 500px; }
.trigger-circle svg { transform: rotate(-90deg); }
.track { fill: none; stroke: rgba(255,255,255,0.1); stroke-width: 4; }
.bar { 
  fill: none; stroke: #FFF; stroke-width: 4; 
  stroke-dasharray: 301; transition: stroke-dashoffset 0.1s;
}
.center-text {
  position: absolute; inset: 0; display: flex; align-items: center; 
  justify-content: center; text-align: center; color: #FFF; font-size: 40px; font-weight: bold;
}

/* 运行态样式 */
.playing-mode {
  height: 100%; display: flex; flex-direction: column;
}
.game-header {
  padding: 60px 100px; display: flex; justify-content: space-between;
  font-size: 60px; font-weight: 900; color: #FFF;
}
.holes-container {
  flex: 1; display: flex; justify-content: space-around; align-items: center;
}
.hole-item {
  width: 350px; height: 350px; border: 8px solid rgba(255,255,255,0.2);
  border-radius: 50%; position: relative; overflow: hidden;
}
.mole-avatar {
  font-size: 180px; text-align: center; line-height: 350px;
}
.hit-progress {
  position: absolute; bottom: 0; left: 0; width: 100%;
  background: rgba(255, 114, 34, 0.4); transition: height 0.1s;
}
</style>