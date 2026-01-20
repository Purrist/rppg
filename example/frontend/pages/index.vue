<template>
  <div class="app-container">
    <header class="header">
      <div class="logo">守护助手 <span class="engine-tag">AI 视觉引擎</span></div>
      <div class="timer">训练时长：12:45</div>
    </header>

    <div class="main-layout">
      <section class="video-section">
        <div class="stream-wrapper">
          <img :src="'data:image/jpeg;base64,' + stream.image" class="stream-img" v-if="stream.image"/>
          <div class="overlay-info" :style="{ borderColor: statusColor }">
            <span class="status-text">{{ currentEmotionName }}</span>
          </div>
        </div>
      </section>

      <section class="data-section">
        <div class="difficulty-indicator">
          <p class="label">当前训练状态</p>
          <div class="level-box" :style="{ background: statusColor }">
             {{ difficultyAdvice }}
          </div>
        </div>

        <div class="chart-container">
          <div class="chart-label">情绪波动追踪 (过去30秒)</div>
          <div class="simple-trend">
            <div v-for="(v, i) in historyStack" :key="i" 
                 class="bar" 
                 :style="{ height: (v.val * 30 + 20) + '%', background: v.color }">
            </div>
          </div>
          <div class="chart-axis">
            <span>难</span><span>准</span><span>易</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { io } from 'socket.io-client'

const stream = ref({ image: '', data: { emotion: 'neutral', status_level: 1 } })
const historyStack = ref([])

const difficultyAdvice = computed(() => {
  const levels = ["难度偏高，建议降级", "状态极佳，保持训练", "难度较低，建议挑战"]
  return levels[stream.value.data.status_level] || "正在分析..."
})

const statusColor = computed(() => {
  const colors = ["#FB4422", "#33B555", "#2AAADD"] // 你的提示色 & 辅助色
  return colors[stream.value.data.status_level] || "#FF7222"
})

const currentEmotionName = computed(() => {
  const dict = { 'happy': '愉悦', 'sad': '沮丧', 'angry': '愤怒', 'neutral': '平静', 'fear': '紧张', 'surprise': '惊讶' }
  return dict[stream.value.data.emotion] || '识别中'
})

onMounted(() => {
  const socket = io(`http://${window.location.hostname}:8081`)
  socket.on('video_frame', (res) => {
    stream.value = res
    // 更新可视化简图数据
    if (historyStack.value.length > 20) historyStack.value.shift()
    historyStack.value.push({
      val: res.data.status_level,
      color: statusColor.value
    })
  })
})
</script>

<style scoped>
.app-container {
  height: 100vh; display: flex; flex-direction: column;
  background: #FFFFFF; font-family: 'PingFang SC';
}
.header {
  padding: 20px 40px; display: flex; justify-content: space-between; align-items: center;
  border-bottom: 2px solid #f0f0f0;
}
.logo { font-size: 32px; font-weight: 800; color: #FF7222; } /* 主题色 */
.main-layout { flex: 1; display: grid; grid-template-columns: 1.2fr 0.8fr; padding: 20px; gap: 20px; }

.stream-wrapper {
  width: 100%; height: 100%; position: relative;
  border-radius: 40px; overflow: hidden; border: 12px solid #FFD111; /* 辅助色：黄 */
}
.stream-img { width: 100%; height: 100%; object-fit: cover; }

.overlay-info {
  position: absolute; top: 30px; left: 30px;
  padding: 10px 30px; border-radius: 50px; background: rgba(255,255,255,0.9);
  border-left: 10px solid #FF7222; font-size: 24px; font-weight: bold;
}

.data-section { display: flex; flex-direction: column; gap: 20px; }
.difficulty-indicator {
  padding: 30px; border-radius: 30px; background: #FFF9F5; text-align: center;
}
.level-box {
  margin-top: 15px; padding: 20px; border-radius: 20px; color: white; font-size: 28px; font-weight: 900;
}

.simple-trend {
  height: 150px; display: flex; align-items: flex-end; gap: 4px; padding: 10px;
  background: #F8F8F8; border-radius: 15px;
}
.bar { flex: 1; border-radius: 4px; transition: all 0.3s ease; }
.chart-axis { display: flex; justify-content: space-between; padding: 5px 10px; color: #999; }
</style>