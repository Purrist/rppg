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
        <div class="ready-text">请进入</div>
      </div>
    </div>

    <div v-else-if="game.status === 'PLAYING'" class="game-screen">
      <div class="top-info">得分: {{ game.score }} | 剩余: {{ game.timer }}s</div>
      <div class="holes-row">
        <div v-for="i in 3" :key="i" class="hole-container">
          <svg viewBox="0 0 100 100" class="mini-progress">
            <circle cx="50" cy="50" r="48" 
              :class="['ring', getRingColor(i-1)]"
              :style="{ strokeDashoffset: 301 - (301 * progress[i-1] / 100) }" />
          </svg>
          <div class="mole-space">
            <transition name="pop"><div v-if="game.current_mole === i-1" class="mole">🐹</div></transition>
          </div>
          <div class="base"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { io } from 'socket.io-client'

const progress = ref([0, 0, 0])
const game = ref({ status: 'SLEEP', score: 0, timer: 60, current_mole: -1 })
let socket = null

const getRingColor = (idx) => {
  if (progress.value[idx] <= 0) return 'off'
  if (progress.value[idx] < 100) return 'loading' // 加载中：灰蓝色
  return game.value.current_mole === idx ? 'hit' : 'miss' // 100%判定
}

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)
  socket.on('game_update', d => game.value = d)
  socket.on('screen_stream', d => { if(d.interact) progress.value = d.interact.progress })
})
</script>

<style scoped>
.proj-canvas { width: 100vw; height: 100vh; background: #000; overflow: hidden; }
.is-playing { background: #FFF !important; }
.ready-screen { height: 100%; display: flex; align-items: center; justify-content: center; }
.trigger-zone { position: relative; width: 400px; height: 400px; }
.trigger-zone svg { transform: rotate(-90deg); width: 100%; height: 100%; }
.track { fill: none; stroke: #333; stroke-width: 4; }
.bar { fill: none; stroke: #FFF; stroke-width: 6; stroke-dasharray: 289; transition: stroke-dashoffset 0.05s linear; }
.ready-text { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #FFF; font-size: 50px; }

.game-screen { height: 100%; display: flex; flex-direction: column; }
.top-info { font-size: 60px; font-weight: 900; color: #333; text-align: center; padding: 40px; }
.holes-row { display: flex; justify-content: space-around; align-items: flex-end; flex: 1; padding-bottom: 100px; }
.hole-container { position: relative; width: 300px; display: flex; flex-direction: column; align-items: center; }

.mini-progress { position: absolute; top: -50px; width: 350px; height: 350px; transform: rotate(-90deg); }
.ring { fill: none; stroke-width: 8; stroke-dasharray: 301; transition: stroke-dashoffset 0.05s linear; }
.off { opacity: 0; }
.loading { stroke: #6496C8; opacity: 1; }
.hit { stroke: #33B555; opacity: 1; stroke-width: 12; }
.miss { stroke: #FB4422; opacity: 1; stroke-width: 12; }

.mole-space { height: 200px; }
.mole { font-size: 150px; }
.base { width: 250px; height: 50px; background: #333; border-radius: 50%; }

.pop-enter-active { transition: transform 0.1s; }
.pop-enter-from { transform: translateY(100px); }
</style>