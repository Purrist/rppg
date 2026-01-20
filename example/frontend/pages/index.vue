<template>
  <div class="monitor-page">
    <header class="top-bar">
      <div class="brand">EMOTION SENSOR</div>
      <div class="status-badge" :class="streamData.emotion">
        {{ streamData.emotion?.toUpperCase() || 'LOADING' }}
      </div>
    </header>

    <div class="main-stage">
      <img v-if="streamData.image" 
           :src="'data:image/jpeg;base64,' + streamData.image" 
           class="live-stream" />
      <div v-else class="loading-state">
        <div class="spinner"></div>
        <p>CONNECTING TO VISION AI...</p>
      </div>
    </div>

    <footer class="bottom-info">
      <div class="info-group">
        <span class="label">CONFIDENCE</span>
        <span class="value">{{ streamData.confidence }}%</span>
      </div>
      <div class="info-group">
        <span class="label">LATENCY</span>
        <span class="value">LOW</span>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { io } from 'socket.io-client'

const streamData = ref({
  image: '',
  emotion: 'detecting',
  confidence: 0
})

onMounted(() => {
  // 这里的 IP 换成你电脑的局域网 IP
  const socket = io('http://localhost:8081')

  socket.on('video_frame', (data) => {
    streamData.value = data
  })
})
</script>

<style scoped>
.monitor-page {
  height: 100%; display: flex; flex-direction: column;
  background: #0a0a0b; color: #fff; font-family: sans-serif;
}
.top-bar {
  padding: 20px 30px; display: flex; justify-content: space-between; align-items: center;
}
.brand { font-weight: 900; letter-spacing: 2px; color: #00ff7f; }
.status-badge {
  padding: 4px 12px; border-radius: 4px; border: 1px solid #333; font-size: 12px;
}
.main-stage {
  flex: 1; display: flex; justify-content: center; align-items: center; padding: 0 20px;
}
.live-stream {
  width: 100%; max-width: 1200px; border-radius: 12px;
  box-shadow: 0 0 50px rgba(0, 255, 127, 0.1);
}
.bottom-info {
  padding: 30px; display: flex; gap: 40px; border-top: 1px solid #1a1a1b;
}
.info-group { display: flex; flex-direction: column; }
.label { font-size: 10px; color: #666; margin-bottom: 5px; }
.value { font-size: 20px; font-weight: 700; color: #eee; }

/* 动画转圈 */
.spinner {
  width: 40px; height: 40px; border: 3px solid #333; border-top-color: #00ff7f;
  border-radius: 50%; animation: rot 1s infinite linear; margin-bottom: 10px;
}
@keyframes rot { to { transform: rotate(360deg); } }
</style>