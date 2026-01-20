<template>
  <div class="monitor-page">
    <header class="top-bar">
      <div class="brand">
        <span class="dot"></span> 智慧情绪守护
      </div>
      <div class="status-badge" :style="{ backgroundColor: getEmotionColor(streamData.emotion) }">
        {{ getEmotionText(streamData.emotion) }}
      </div>
    </header>

    <div class="main-stage">
      <div class="video-container">
        <img v-if="streamData.image" 
             :src="'data:image/jpeg;base64,' + streamData.image" 
             class="live-stream" />
        <div v-else class="loading-state">
          <div class="spinner"></div>
          <p>正在连接视觉AI系统...</p>
        </div>
      </div>
    </div>

    <footer class="bottom-info">
      <div class="info-card primary">
        <span class="label">当前状态</span>
        <span class="value">{{ getEmotionText(streamData.emotion) }}</span>
      </div>
      <div class="info-card">
        <span class="label">置信度</span>
        <span class="value">{{ streamData.confidence }}%</span>
      </div>
      <div class="info-card accent">
        <span class="label">AI 引擎</span>
        <span class="value">高精度模式</span>
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

// 情绪翻译与配色映射
const getEmotionText = (emo) => {
  const dict = {
    'happy': '开心', 'sad': '忧伤', 'angry': '愤怒', 
    'neutral': '平静', 'fear': '恐惧', 'surprise': '惊讶', 'detecting': '识别中'
  }
  return dict[emo] || emo
}

const getEmotionColor = (emo) => {
  if (emo === 'happy') return '#33B555' // 提示色：绿
  if (emo === 'sad' || emo === 'angry') return '#FB4422' // 提示色：红
  return '#FF7222' // 主题色：橙
}

onMounted(() => {
  // 关键修复：动态获取 IP 地址，确保平板能连上后端
  const backendUrl = `http://${window.location.hostname}:8081`
  const socket = io(backendUrl)

  socket.on('video_frame', (data) => {
    streamData.value = data
  })
})
</script>

<style scoped>
/* 全局样式：白底、温暖、灵动 */
.monitor-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #FFFFFF;
  color: #333;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  overflow: hidden;
}

/* 顶部：灵动感 */
.top-bar {
  padding: 2vh 4vw;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.brand {
  font-size: 28px;
  font-weight: 800;
  color: #FF7222;
  display: flex;
  align-items: center;
  gap: 10px;
}
.dot {
  width: 12px; height: 12px;
  background: #1DD1BB; /* 点缀色 */
  border-radius: 50%;
}
.status-badge {
  padding: 8px 24px;
  border-radius: 50px;
  color: white;
  font-weight: bold;
  font-size: 20px;
  transition: all 0.3s ease;
}

/* 视频区域：解决溢出问题的核心 */
.main-stage {
  flex: 1;
  min-height: 0; /* 关键：允许 flex 项目缩小 */
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0 4vw;
}
.video-container {
  width: 100%;
  height: 100%;
  max-width: 1200px;
  background: #F5F5F7;
  border-radius: 24px;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  border: 4px solid #FFD111; /* 辅助色：黄 */
}
.live-stream {
  width: 100%;
  height: 100%;
  object-fit: contain; /* 保证画面不被裁剪且完整显示 */
}

/* 底部：适老化、大色块、温暖 */
.bottom-info {
  height: 18vh;
  display: flex;
  gap: 20px;
  padding: 2vh 4vw;
  background: #FFF9F5; /* 淡淡的暖色底 */
}
.info-card {
  flex: 1;
  background: white;
  border-radius: 16px;
  padding: 15px 20px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  box-shadow: 0 4px 15px rgba(255, 114, 34, 0.1);
  border-bottom: 5px solid #2AAADD; /* 辅助色：蓝 */
}
.info-card.primary { border-bottom-color: #FF7222; }
.info-card.accent { border-bottom-color: #7555FF; }

.label { font-size: 16px; color: #888; margin-bottom: 5px; }
.value { font-size: 32px; font-weight: 900; color: #333; }

/* 正在加载动画 */
.spinner {
  width: 50px; height: 50px;
  border: 5px solid #f3f3f3;
  border-top: 5px solid #FF7222;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>