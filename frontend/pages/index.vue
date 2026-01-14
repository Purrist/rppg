<template>
  <div style="text-align: center; font-family: sans-serif; padding: 20px;">
    <h1>rPPG 远程心率监测</h1>
    <div style="margin: 20px auto; max-width: 640px; background: #000; border-radius: 12px; overflow: hidden;">
      <img :src="videoUrl" alt="Video Stream" style="width: 100%; display: block;" />
    </div>
    <div style="font-size: 24px; color: #e74c3c; font-weight: bold;">
      实时心率: -- BPM
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
const videoUrl = ref('')

onMounted(() => {
  // 动态获取当前访问的 IP，自动适配局域网
  const host = window.location.hostname
  videoUrl.value = `http://${host}:8080/video_feed`
})
</script>