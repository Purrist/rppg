<template>
  <div class="proj-canvas" :class="{ 'is-playing': game.status === 'PLAYING' }">
    <div v-if="game.status === 'SLEEP'" class="black-out"></div>

    <div v-else-if="game.status === 'READY'" class="ready-screen">
      <div class="trigger-zone">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="46" class="track" />
          <circle cx="50" cy="50" r="46" class="bar" 
            :style="{ strokeDashoffset: 289 - (289 * progress[1] / 100) }" />
        </svg>
        <div class="ready-text">请将手放入</div>
      </div>
    </div>

    <div v-else-if="game.status === 'PLAYING'" class="game-screen">
      <div class="top-info">得分: {{ game.score }} | 剩余时间: {{ game.timer }}s</div>
      <div class="holes-row">
        <div v-for="i in 3" :key="i" class="hole">
          <svg viewBox="0 0 100 100" class="mini-progress">
            <circle cx="50" cy="50" r="48" :class="['ring', progress[i-1]>0 ? (game.current_mole===(i-1)?'correct':'wrong'):'']" 
              :style="{ strokeDashoffset: 301 - (301 * progress[i-1] / 100) }" />
          </svg>
          <div v-if="game.current_mole === (i-1)" class="mole-icon">🐹</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { io } from 'socket.io-client'

const game = ref({ status: 'SLEEP', score: 0, timer: 60, current_mole: -1 })
const progress = ref([0, 0, 0])

onMounted(() => {
  const socket = io(`http://${window.location.hostname}:8080`)
  socket.on('game_update', d => game.value = d)
  socket.on('screen_stream', d => { if(d.interact) progress.value = d.interact.progress })
})
</script>

<style scoped>
.proj-canvas { width: 100vw; height: 100vh; background: #000; overflow: hidden; }
.is-playing { background: #FFF !important; }

/* 待机白圈 */
.ready-screen { height: 100%; display: flex; align-items: center; justify-content: center; }
.trigger-zone { position: relative; width: 400px; height: 400px; }
.trigger-zone svg { transform: rotate(-90deg); }
.track { fill: none; stroke: #333; stroke-width: 4; }
.bar { fill: none; stroke: #FFF; stroke-width: 6; stroke-dasharray: 289; transition: stroke-dashoffset 0.1s; }
.ready-text { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #FFF; font-size: 40px; }

/* 游戏白底 */
.game-screen { height: 100%; display: flex; flex-direction: column; background: #FFF; }
.top-info { padding: 40px; font-size: 60px; font-weight: 900; color: #333; text-align: center; }
.holes-row { flex: 1; display: flex; justify-content: space-around; align-items: center; }
.hole { width: 300px; height: 300px; position: relative; }
.mini-progress .ring { fill: none; stroke: #EEE; stroke-width: 4; stroke-dasharray: 301; transform: rotate(-90deg); transform-origin: center; transition: stroke-dashoffset 0.1s; }
.ring.correct { stroke: #4CAF50; }
.ring.wrong { stroke: #FF3B30; }
.mole-icon { position: absolute; inset: 0; font-size: 160px; text-align: center; line-height: 300px; }
</style>