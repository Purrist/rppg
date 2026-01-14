<template>
  <div style="text-align: center; padding: 20px;">
    <h1>rPPG 监控终端</h1>
    <div v-if="backendUrl">
      <img :src="`${backendUrl}/video_feed`" alt="实时心率监控画面" style="max-width: 90%; border-radius: 10px; border: 2px solid #333;" />
    </div>
    <div v-else>正在寻找后端服务...</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const backendUrl = ref('')

onMounted(() => {
  // 动态获取当前局域网 IP
  const host = window.location.hostname
  backendUrl.value = `http://${host}:8080`
})
</script>