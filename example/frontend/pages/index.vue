<template>
  <div class="root">
    <img :src="videoUrl" />
    <pre>{{ status }}</pre>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const videoUrl = 'http://192.168.130.206:8080/video'
const status = ref({})

onMounted(() => {
  setInterval(async () => {
    const res = await fetch('http://192.168.130.206:8080/status')
    status.value = await res.json()
  }, 1000)
})
</script>

<style>
html, body, #__nuxt {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
}

.root {
  width: 100%;
  height: 100%;
}

img {
  width: 100%;
  height: auto;
}
</style>
