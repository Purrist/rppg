<template>
  <div class="test-container">
    <div class="header">
      <h1>USB 摄像头测试页面</h1>
      <p>状态：<span :class="{ online: isConnected }">{{ isConnected ? '已连接' : '断开' }}</span></p>
      <button @click="$router.back()">返回</button>
    </div>

    <div class="video-box">
      <img v-if="imgData" :src="'data:image/jpeg;base64,' + imgData" />
      <div v-else class="loader">等待视频流，请检查 Python 是否启动...</div>
    </div>
    
    <div class="hint">
      * 如果画面黑屏，请尝试修改 test_cam.py 中的 camera_index 为 1 或 2
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

const imgData = ref('')
const isConnected = ref(false)
let socket = null

onMounted(() => {
  // 连接测试专用的 8888 端口
  socket = io(`http://${window.location.hostname}:8888`)
  
  socket.on('connect', () => { isConnected.value = true })
  socket.on('test_stream', (data) => { imgData.value = data.image })
  socket.on('disconnect', () => { isConnected.value = false })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})
</script>

<style scoped>
.test-container {
  width: 100vw; height: 100vh; background: #1a1a1a; color: white;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.header { text-align: center; margin-bottom: 20px; }
.online { color: #4CAF50; font-weight: bold; }
.video-box {
  width: 800px; height: 600px; border: 4px solid #333;
  background: #000; display: flex; align-items: center; justify-content: center;
}
.video-box img { width: 100%; height: 100%; object-fit: contain; }
.loader { font-size: 20px; color: #666; }
.hint { margin-top: 20px; color: #888; }
button { padding: 10px 20px; margin-top: 10px; cursor: pointer; }
</style>