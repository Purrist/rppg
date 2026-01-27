<template>
  <div class="proj-screen" :class="{ 'is-playing': game.status === 'PLAYING' }">
    <div v-if="game.status === 'SLEEP'" class="full-black"></div>

    <template v-else>
      <div class="top-bar">
        <div class="timer-wrap">
          <div class="timer-fill" :style="{ width: (game.timer/60*100) + '%' }"></div>
          <span class="timer-text">剩余时间: {{ game.timer }}s</span>
        </div>
        <div class="score-tag">得分: {{ game.score }}</div>
      </div>

      <div class="game-content">
        <div v-for="i in 3" :key="i" class="hole">
          <svg viewBox="0 0 100 100" class="progress-svg">
            <circle cx="50" cy="50" r="45" class="bg" />
            <circle cx="50" cy="50" r="45" class="bar"
              :class="{ 'is-hit': game.current_mole === (i-1), 'is-wrong': progress[i-1] > 0 && game.current_mole !== (i-1) }"
              :style="{ strokeDashoffset: 283 - (283 * progress[i-1] / 100) }" />
          </svg>
          <div v-if="game.current_mole === (i-1)" class="mole">🐹</div>
        </div>
      </div>

      <div v-if="game.status === 'PAUSED'" class="pause-overlay">已 暂 停</div>
      <div v-if="game.status === 'READY'" class="ready-hint">请将手放入中心区域启动</div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { io } from 'socket.io-client'

const game = ref({ status: 'SLEEP', timer: 60, score: 0, current_mole: -1 })
const progress = ref([0, 0, 0])
let socket = null

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)
  socket.on('game_update', d => game.value = d)
  socket.on('screen_stream', data => { if(data.interact) progress.value = data.interact.progress })
})
</script>

<style scoped>
.proj-screen { width: 100vw; height: 100vh; background: #FFF; overflow: hidden; position: relative; }
.full-black { background: #000; width: 100%; height: 100%; }

.top-bar { padding: 40px 80px; display: flex; align-items: center; gap: 40px; }
.timer-wrap { flex: 1; height: 60px; background: #EEE; border-radius: 30px; position: relative; overflow: hidden; }
.timer-fill { height: 100%; background: #FF7222; transition: width 1s linear; }
.timer-text { position: absolute; inset: 0; line-height: 60px; text-align: center; font-size: 30px; font-weight: bold; color: #333; }
.score-tag { font-size: 50px; font-weight: 900; color: #FF7222; }

.game-content { height: 70%; display: flex; justify-content: space-around; align-items: center; padding: 0 50px; }
.hole { width: 300px; height: 300px; position: relative; }
.progress-svg { transform: rotate(-90deg); }
.progress-svg .bg { fill: none; stroke: #F0F0F0; stroke-width: 8; }
.progress-svg .bar { 
  fill: none; stroke: #CCC; stroke-width: 8; stroke-dasharray: 283; 
  transition: stroke-dashoffset 0.1s; stroke-linecap: round;
}
.bar.is-hit { stroke: #4CAF50; } /* 目标地鼠：绿色 */
.bar.is-wrong { stroke: #FF3B30; } /* 错位：红色 */

.mole { position: absolute; inset: 0; font-size: 150px; text-align: center; line-height: 300px; }
.pause-overlay { position: absolute; inset: 0; background: rgba(255,255,255,0.9); display: flex; align-items: center; justify-content: center; font-size: 120px; font-weight: 900; color: #333; }
.ready-hint { position: absolute; bottom: 100px; width: 100%; text-align: center; font-size: 40px; color: #999; }
</style>