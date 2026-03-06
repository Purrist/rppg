<template>
  <div class="page-body">
    <h2>娱乐中心</h2>
    <div class="media-list">
      <div class="m-item" @click="playMedia('经典戏剧')">经典戏剧</div>
      <div class="m-item" @click="playMedia('昨日新闻回放')">昨日新闻回放</div>
      <div class="m-item" @click="playMedia('我的回忆录')">我的回忆录</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

let socket = null
const backendConnected = ref(false)
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
      backendConnected.value = true
    })
    
    socket.on('disconnect', () => {
      backendConnected.value = false
    })
    
    socket.on('connect_error', () => {
      backendConnected.value = false
    })
  } catch (e) {
    console.error('Socket初始化失败', e)
  }
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

const playMedia = (name) => {
  // 记录用户交互
  if (backendConnected.value && socket) {
    socket.emit('user_interaction', {
      type: 'click',
      data: { target: 'media', name }
    })
  }
  
  alert(`即将播放：${name}`)
}
</script>

<style scoped>
.page-body { padding: 40px; }
h2 { font-size: 36px; margin-bottom: 30px; }
.media-list { display: flex; flex-direction: column; gap: 20px; }
.m-item { 
  background: #FFF; 
  border: 2px solid #EEE; 
  border-radius: 20px; 
  padding: 30px; 
  font-size: 24px; 
  cursor: pointer;
  transition: all 0.2s;
}
.m-item:hover { border-color: #FF7222; background: #FFF9F6; }
</style>
