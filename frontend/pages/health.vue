<template>
  <div class="page-body">
    <h2>健康看板</h2>
    <div class="health-grid">
      <div class="h-card"><h3>实时信号强度</h3><div class="chart-box">信号解析中...</div></div>
      <div class="h-card"><h3>历史状态趋势</h3><div class="chart-box">数据加载中...</div></div>
      <div class="h-card"><h3>活动时长统计</h3><div class="chart-box">120 分钟</div></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

let socket = null
const FLASK_PORT = 5000

onMounted(() => {
  try {
    socket = io(`http://localhost:${FLASK_PORT}`, {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionAttempts: 3,
      timeout: 5000
    })
    
    socket.on('connect', () => {
      // 记录用户访问
      socket.emit('user_interaction', {
        type: 'view',
        data: { page: 'health' }
      })
    })
  } catch (e) {
    console.error('Socket初始化失败', e)
  }
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})
</script>

<style scoped>
.page-body { padding: 40px; }
h2 { font-size: 36px; margin-bottom: 30px; }
.health-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }
.h-card { background: #F9F9F9; border-radius: 20px; padding: 20px; }
.h-card h3 { font-size: 18px; color: #888; margin-bottom: 10px; }
.chart-box { height: 150px; display: flex; align-items: center; justify-content: center; font-size: 24px; color: #333; }
</style>
