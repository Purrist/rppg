<template>
  <div class="main">
    <div class="header">远程生理信号监测终端</div>
    
    <div class="monitor-grid">
      <div class="card">
        <div class="card-title">追踪源视频</div>
        <img :src="`http://${host}:8080/stream/raw`" />
      </div>

      <div class="card">
        <div class="card-title">波形分析流 (滤波)</div>
        <img :src="`http://${host}:8080/stream/wave`" />
      </div>
    </div>

    <div class="stats">
      <div class="bpm-display">
        <span class="value">{{ bpm }}</span>
        <span class="unit">BPM</span>
      </div>
      <div class="info">状态: {{ bpm === '--' ? '正在校准...' : '监测中' }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const host = ref('')
const bpm = ref('--')

onMounted(() => {
  host.value = window.location.hostname
  setInterval(async () => {
    try {
      const res = await fetch(`http://${host.value}:8080/bpm`)
      const data = await res.json()
      bpm.value = data.bpm
    } catch (e) {}
  }, 800)
})
</script>

<style scoped>
.main { background: #050505; min-height: 100vh; color: #00ff41; font-family: 'Courier New', Courier, monospace; padding: 20px; }
.header { border-bottom: 1px solid #00ff41; padding: 10px; font-size: 24px; text-align: center; margin-bottom: 30px; }
.monitor-grid { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }
.card { background: #111; border: 1px solid #333; padding: 10px; border-radius: 4px; }
.card-title { font-size: 12px; color: #888; margin-bottom: 10px; text-transform: uppercase; }
img { width: 480px; height: 320px; background: #000; display: block; object-fit: contain; }
.stats { margin-top: 40px; text-align: center; background: #111; padding: 30px; border-radius: 8px; border: 1px solid #333; }
.bpm-display .value { font-size: 100px; font-weight: bold; }
.bpm-display .unit { font-size: 20px; margin-left: 10px; color: #555; }
.info { color: #555; margin-top: 10px; }
</style>