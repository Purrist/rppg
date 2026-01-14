<template>
  <div style="text-align: center; font-family: sans-serif; padding: 20px;">
    <h2>rPPG 心率监测终端</h2>
    
    <div style="display: inline-block; background: #000; border-radius: 8px; overflow: hidden; border: 4px solid #333;">
      <img :src="videoUrl" alt="正在加载视频流..." style="max-width: 100%; display: block;" />
    </div>

    <div style="margin-top: 20px;">
      <p style="font-size: 1.2rem;">当前状态: <span style="color: green;">已连接</span></p>
      <div style="font-size: 2rem; color: #e74c3c; font-weight: bold;">
        BPM: --
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const videoUrl = ref('')

onMounted(() => {
  // 自动获取当前访问的局域网 IP
  const host = window.location.hostname
  videoUrl.value = `http://${host}:8080/video_feed`
})
</script>