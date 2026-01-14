<template>
  <div class="monitor-container">
    <div class="nav-header">RPPG 多区域光谱扫描监控系统</div>
    
    <div class="main-layout">
      <div class="video-box">
        <div class="status-tag">REAL-TIME OVERLAY</div>
        <img :src="videoUrl" class="stream-img" />
      </div>

      <div class="sidebar">
        <div class="metric-card">
          <div class="label">当前频率估算</div>
          <div class="bpm-value">{{ bpm }} <small>BPM</small></div>
        </div>

        <div class="info-list">
          <div class="info-item">信号源: 3-ROI Fusion</div>
          <div class="info-item">光照归一化: 开启</div>
          <div class="info-item">采样状态: {{ bpm === '--' ? '校准中' : '锁定中' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const host = ref('')
const videoUrl = ref('')
const bpm = ref('--')
let timer = null

onMounted(() => {
  host.value = window.location.hostname
  videoUrl.value = `http://${host.value}:8080/video_feed`
  
  timer = setInterval(async () => {
    try {
      const r = await fetch(`http://${host.value}:8080/bpm_data`)
      const d = await r.json()
      bpm.value = d.bpm
    } catch (e) {}
  }, 1000)
})

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.monitor-container { background: #000; min-height: 100vh; color: #0f0; font-family: monospace; padding: 20px; }
.nav-header { border-bottom: 1px solid #040; padding-bottom: 15px; margin-bottom: 30px; font-size: 1.2rem; }
.main-layout { display: flex; gap: 20px; flex-wrap: wrap; }
.video-box { flex: 2; min-width: 500px; border: 1px solid #040; background: #050505; position: relative; }
.stream-img { width: 100%; display: block; height: auto; }
.status-tag { position: absolute; top: 10px; left: 10px; background: rgba(0, 255, 0, 0.2); padding: 4px 10px; font-size: 0.7rem; }
.sidebar { flex: 1; min-width: 280px; display: flex; flex-direction: column; gap: 20px; }
.metric-card { background: #0a0a0a; border: 1px solid #040; padding: 40px 20px; text-align: center; }
.bpm-value { font-size: 4rem; font-weight: bold; margin-top: 10px; }
.bpm-value small { font-size: 1rem; color: #060; }
.label { color: #888; font-size: 0.8rem; }
.info-list { background: #0a0a0a; border: 1px solid #040; padding: 15px; font-size: 0.8rem; line-height: 2; color: #080; }
</style>