<template>
  <div class="app-root">
    <div class="tablet-canvas">
      <NuxtPage />
    </div>
  </div>
</template>

<style>
/* 1. 彻底锁定全局，杜绝滚动条 */
* { 
  margin: 0; 
  padding: 0; 
  box-sizing: border-box; 
  -webkit-font-smoothing: antialiased;
}

html, body, #__nuxt {
  width: 100vw;
  height: 100vh;
  overflow: hidden; /* 核心：禁止任何方向滚动 */
  /* 背景改为明亮的浅灰渐变，不再是黑色 */
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ed 100%);
}

/* 2. 定义 16:10 比例容器 */
.app-root {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tablet-canvas {
  /* 强制锁定 2560*1600 的比例 */
  aspect-ratio: 16 / 10;
  width: 100%;
  max-height: 100%;
  position: relative;
  overflow: hidden; /* 内部也不允许滚动 */
  
  /* 这里的样式会应用到全局，不再需要 main.css */
  --primary-blue: #4a90e2;
  --glass: rgba(255, 255, 255, 0.7);
}

/* 定义全局精致组件样式（供 tabcam.vue 使用） */
.glass-panel {
  background: var(--glass);
  -webkit-backdrop-filter: blur(15px);
  backdrop-filter: blur(15px);
  border: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
  border-radius: 20px;
}
</style>