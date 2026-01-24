<template>
  <div class="projection-view" :class="{ 'bg-black': !playing }">
    <div v-if="playing" class="game-stage">
      <div v-for="(p, i) in progress" :key="i" class="hole">
        <div class="progress-ring">
          <svg viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="45" class="bg" />
            <circle cx="50" cy="50" r="45" class="bar" 
              :style="{ strokeDashoffset: 283 - (283 * p / 100) }" />
          </svg>
          <div class="mole-icon" :class="{ 'active': currentMole === i }">🐹</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { io } from 'socket.io-client'
const socket = io(`http://${window.location.hostname}:8080`)
const playing = ref(false)
const progress = ref([0, 0, 0])
const currentMole = ref(-1)

socket.on('game_command', (cmd) => {
  if (cmd.action === 'start') playing.value = true
  if (cmd.action === 'reset') { playing.value = false; currentMole.value = -1 }
})

socket.on('interaction_update', (data) => {
  progress.value = data.progress
})

// 地鼠跳出逻辑（后端控制更佳，此处前端简易模拟）
setInterval(() => {
  if (playing.value) currentMole.value = Math.floor(Math.random() * 3)
}, 2000)
</script>

<style scoped>
.projection-view { width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; transition: 0.5s; }
.bg-black { background: #000; }
.game-stage { display: flex; gap: 100px; }
.hole { width: 250px; height: 250px; position: relative; }
.progress-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.progress-ring .bg { fill: none; stroke: #333; stroke-width: 8; }
.progress-ring .bar { fill: none; stroke: #4CAF50; stroke-width: 10; stroke-dasharray: 283; transition: 0.1s; }
.mole-icon { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 80px; opacity: 0; transition: 0.3s; }
.mole-icon.active { opacity: 1; transform: translate(-50%, -80%); }
</style>