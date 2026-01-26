<template>
  <div class="training-page">
    <div class="header-info">
      <h1>益智训练：打地鼠</h1>
      <p class="status-tag" :class="{ 'is-playing': game.playing }">
        {{ game.playing ? '● 游戏正在进行' : '○ 待机中（请挡住投影白圈开始）' }}
      </p>
    </div>

    <div class="stats-panel">
      <div class="data-card">倒计时：<span class="val">{{ game.timer }}s</span></div>
      <div class="data-card">当前得分：<span class="val">{{ game.score }}</span></div>
      <div class="data-card">实时心率：<span class="val">{{ health.bpm }}</span></div>
      <div class="data-card">当前情绪：<span class="val">{{ health.emotion }}</span></div>
    </div>

    <div class="control-btns">
      <button v-if="game.playing" @click="pauseGame" class="pause">暂停游戏</button>
      <button @click="$router.back()" class="exit">退出并返回</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

const game = ref({ playing: false, timer: 0, score: 0 })
const health = ref({ bpm: '--', emotion: 'neutral' })

let socket = null

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)
  
  socket.on('game_update', (data) => {
    game.value = data
  })

  socket.on('tablet_stream', (res) => {
    if (res.state) {
      health.value = res.state
    }
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

const pauseGame = () => {
  socket.emit('game_event', { action: 'pause' })
}
</script>

<style scoped>
.training-page { padding: 60px 40px; display: flex; flex-direction: column; gap: 40px; }
.status-tag { font-size: 20px; color: #999; margin-top: 10px; }
.status-tag.is-playing { color: #4CAF50; font-weight: bold; }

.stats-panel { display: grid; grid-template-columns: repeat(2, 1fr); gap: 25px; }
.data-card { background: #F8F9FA; padding: 40px; border-radius: 30px; text-align: center; border: 1px solid #EEE; }
.val { display: block; font-size: 56px; font-weight: bold; color: #FF7222; margin-top: 15px; }

.control-btns { margin-top: 40px; display: flex; gap: 20px; }
.control-btns button { flex: 1; padding: 30px; border-radius: 20px; font-size: 26px; font-weight: bold; border: none; cursor: pointer; }
.pause { background: #FFD111; color: #333; }
.exit { background: #EEE; color: #666; }
</style>