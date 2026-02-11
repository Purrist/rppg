<template>
  <div class="dev-page">
    <div class="top-nav">
      <h2>🛠 视觉引擎控制台</h2>
      <button @click="$router.push('/')">退出后台</button>
    </div>

    <div class="video-grid">
      <div class="monitor-card">
        <h3>平板端摄像头 (生理/情绪)</h3>
        <img v-if="tabletImg" :src="'data:image/jpeg;base64,' + tabletImg" />
        <div v-else class="placeholder">等待平板视频流...</div>
      </div>

      <div class="monitor-card">
        <h3>外接摄像头 (投影区域识别)</h3>
        <img v-if="screenImg" :src="'data:image/jpeg;base64,' + screenImg" />
        <div v-else class="placeholder">等待投影视频流...</div>
      </div>
    </div>
    
    <div class="debug-logs">
      <h3>系统日志</h3>
      <pre>{{ logs }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

// --- 核心修复：显式声明响应式变量 ---
const tabletImg = ref('')
const screenImg = ref('')
const logs = ref('系统初始化...\n')

let socket = null

onMounted(() => {
  socket = io(`http://${window.location.hostname}:8080`)

  socket.on('connect', () => {
    logs.value += '[Socket] 已连接到后端服务器\n'
  })

  socket.on('tablet_stream', (data) => {
    tabletImg.value = data.image
  })

  socket.on('screen_stream', (data) => {
    screenImg.value = data.image
  })

  socket.on('game_update', (data) => {
    // 不再向 logs 字符串追加内容，防止内存溢出导致卡顿
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})
</script>

<style scoped>
.dev-page { 
  background: #fff; height: 100vh; width: 100vw; 
  padding: 40px; color: #000; overflow-y: auto; 
}
.top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.video-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.monitor-card { background: #f4f4f4; padding: 15px; border-radius: 12px; }
.monitor-card img { width: 100%; border-radius: 8px; background: #000; min-height: 300px; }
.placeholder { height: 300px; display: flex; align-items: center; justify-content: center; color: #999; }
.debug-logs { margin-top: 30px; background: #222; color: #0f0; padding: 20px; border-radius: 10px; }
.debug-logs pre { white-space: pre-wrap; font-family: monospace; height: 200px; overflow-y: auto; }
</style>