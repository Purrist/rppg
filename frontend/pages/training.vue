<template>
  <div class="training-page">
    <div class="stats-panel">
      <div class="data-card">倒计时：<span class="val">{{ timer }}s</span></div>
      <div class="data-card">心率：<span class="val">{{ health.bpm }}</span></div>
      <div class="data-card">情绪：<span class="val">{{ health.emotion }}</span></div>
      <div class="data-card">难度：<span class="val">Lv.{{ difficulty }}</span></div>
    </div>

    <div class="center-metrics">
      <div class="metric">平均反应：{{ avgSpeed }}ms</div>
      <div class="metric">正确率：{{ accuracy }}%</div>
    </div>

    <div class="control-btns">
      <button @click="startGame" class="start">开始训练</button>
      <button @click="pauseGame">暂停</button>
      <button @click="resetGame">重新开始</button>
    </div>
  </div>
</template>

<script setup>
import { io } from 'socket.io-client'
const socket = io(`http://${window.location.hostname}:8080`)
const health = ref({ bpm: '--', emotion: 'neutral' })
const timer = ref(120)
const difficulty = ref(3)

// 监听平板监测数据（来自原有的 TabletProcessor）
socket.on('tablet_video_frame', (res) => {
  health.value = res.data
})

const startGame = () => socket.emit('start_game', {})
const resetGame = () => socket.emit('game_event', { action: 'reset' })
</script>

<style scoped>
.training-page { padding: 40px; background: #fff; height: 100%; display: flex; flex-direction: column; }
.stats-panel { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
.data-card { background: #f8f9fa; padding: 30px; border-radius: 20px; text-align: center; font-size: 24px; }
.val { display: block; font-size: 40px; font-weight: bold; color: #FF7222; }
.center-metrics { flex: 1; display: flex; justify-content: space-around; align-items: center; font-size: 32px; font-weight: bold; }
.control-btns { display: flex; gap: 20px; padding-bottom: 40px; }
button { flex: 1; padding: 30px; border-radius: 20px; font-size: 24px; border: none; background: #eee; cursor: pointer; }
button.start { background: #FF7222; color: #fff; }
</style>