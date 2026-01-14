<template>
  <div class="research-container">
    <div class="header">
      <span>认知训练伴随监测原型 (Cognitive-RPPG v1.6)</span>
      <span class="mode-tag">学术研究模式</span>
    </div>

    <div class="main-view">
      <div class="viewport">
        <img :src="`http://${host}:8080/video_feed`" />
        <div class="overlay-info">
          ROI 状态: 3-Point Tracking [Locked]
        </div>
      </div>

      <div class="control-panel">
        <div class="stat-box">
          <div class="label">实时频率 (BPM)</div>
          <div class="value">{{ bpm }}</div>
        </div>
        
        <div class="analysis-box">
          <p>场景: 养老机构室内</p>
          <p>算法: Spatial-Temporal Fusion</p>
          <p>补偿: Global Normalization ON</p>
        </div>
      </div>
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
      const r = await fetch(`http://${host.value}:8080/get_metrics`)
      const d = await r.json()
      bpm.value = d.bpm
    } catch (e) {}
  }, 1000)
})
</script>

<style scoped>
.research-container { background: #0a0c10; min-height: 100vh; color: #e1e1e1; font-family: 'Inter', sans-serif; padding: 20px; }
.header { display: flex; justify-content: space-between; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin-bottom: 20px; font-weight: 600; }
.mode-tag { color: #f8e45c; font-size: 0.8rem; border: 1px solid #f8e45c; padding: 2px 8px; border-radius: 4px; }
.main-view { display: grid; grid-template-columns: 1fr 320px; gap: 20px; }
.viewport { position: relative; border: 1px solid #30363d; background: #000; border-radius: 8px; overflow: hidden; }
.viewport img { width: 100%; display: block; }
.overlay-info { position: absolute; bottom: 10px; left: 10px; font-size: 12px; color: #00ff00; background: rgba(0,0,0,0.5); padding: 4px 8px; }
.control-panel { display: flex; flex-direction: column; gap: 20px; }
.stat-box { background: #161b22; border: 1px solid #30363d; padding: 30px; border-radius: 8px; text-align: center; }
.value { font-size: 64px; font-weight: 800; color: #58a6ff; }
.analysis-box { background: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 8px; font-size: 13px; color: #8b949e; line-height: 1.8; }
</style>