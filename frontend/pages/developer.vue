<template>
  <div class="dev-container">
    <div class="header">
      <h1>🛠 开发者诊断后台</h1>
      <button @click="$router.back()" class="back-btn">返回主页</button>
    </div>

    <div class="main-layout">
      <div class="card video-card">
        <h3>实时画面 (TabletProcessor)</h3>
        <div class="monitor">
          <img v-if="stream.image" :src="'data:image/jpeg;base64,' + stream.image" />
          <div v-else class="loading-box">等待视频流接入...</div>
        </div>
      </div>

      <div class="card data-card">
        <h3>引擎内部状态 (state)</h3>
        <div class="state-item">
          <span class="label">当前情绪:</span>
          <span class="value">{{ stream.data.emotion || '--' }}</span>
        </div>
        <div class="state-item">
          <span class="label">BPM/信号值:</span>
          <span class="value">{{ stream.data.bpm || '--' }}</span>
        </div>
        <hr />
        <pre class="raw-json">{{ stream.data }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { io } from 'socket.io-client'

const stream = ref({
  image: '',
  data: {}
})

onMounted(() => {
  const socket = io(`http://${window.location.hostname}:8080`)
  
  socket.on('tablet_video_frame', (res) => {
    stream.value = res
  })

  onUnmounted(() => {
    socket.disconnect()
  })
})
</script>

<style scoped>
/* 严格要求：白底主题 */
.dev-container {
  min-height: 100vh;
  background: #FFFFFF;
  padding: 40px;
  color: #333;
  font-family: 'PingFang SC', sans-serif;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}

.back-btn {
  padding: 10px 25px;
  border-radius: 12px;
  border: 1px solid #ddd;
  background: #fff;
  cursor: pointer;
  font-weight: bold;
}

.main-layout {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 30px;
}

.card {
  background: #F8F9FA;
  border: 2px solid #F0F0F0;
  border-radius: 25px;
  padding: 25px;
}

.monitor {
  width: 100%;
  aspect-ratio: 16/10;
  background: #000;
  border-radius: 15px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.monitor img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.loading-box { color: #666; }

.state-item {
  margin: 15px 0;
  font-size: 20px;
}

.state-item .label { color: #888; margin-right: 10px; }
.state-item .value { font-weight: bold; color: #FF7222; }

.raw-json {
  background: #eee;
  padding: 15px;
  border-radius: 10px;
  font-size: 14px;
  margin-top: 20px;
  white-space: pre-wrap;
}
</style>