<template>
  <div class="page-body">
    <h2>娱乐中心</h2>
    
    <!-- 阿康推荐区域 -->
    <div v-if="recommendations.length > 0" class="akon-recommend">
      <div class="recommend-header">
        <span class="akon-icon">🤖</span>
        <span>阿康为您推荐</span>
      </div>
      <div class="recommend-items">
        <div 
          v-for="(item, idx) in recommendations" 
          :key="idx" 
          class="recommend-item"
          @click="playMedia(item)"
        >
          <span class="item-icon">{{ recommendType === 'movie' ? '🎬' : '🎵' }}</span>
          <span class="item-name">{{ item }}</span>
        </div>
      </div>
    </div>
    
    <!-- 常规媒体列表 -->
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

// 推荐内容
const recommendations = ref([])
const recommendType = ref('movie')

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
    
    // 接收阿康推荐
    socket.on('akon_recommend', (data) => {
      console.log('[娱乐] 收到阿康推荐:', data)
      recommendType.value = data.type || 'movie'
      recommendations.value = data.items || []
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

/* 阿康推荐区域 */
.akon-recommend {
  background: linear-gradient(135deg, #FFF9F6 0%, #FFF 100%);
  border: 2px solid #FFD6B3;
  border-radius: 24px;
  padding: 24px;
  margin-bottom: 30px;
}

.recommend-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  font-size: 22px;
  font-weight: bold;
  color: #FF7222;
}

.akon-icon {
  font-size: 28px;
}

.recommend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.recommend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #FFF;
  border: 2px solid #FF7222;
  border-radius: 16px;
  padding: 16px 24px;
  font-size: 20px;
  cursor: pointer;
  transition: all 0.2s;
}

.recommend-item:hover {
  background: #FF7222;
  color: #FFF;
  transform: translateY(-2px);
}

.item-icon {
  font-size: 24px;
}

/* 常规媒体列表 */
.media-list { 
  display: flex; 
  flex-direction: column; 
  gap: 20px; 
}

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
