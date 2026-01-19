<template>
  <div class="page-container">
    <header class="header glass-panel">
      <div class="logo">AI VISION <span class="highlight">LAB</span></div>
      <div class="sys-info">SYSTEM ACTIVE | 2560x1600 MODE</div>
    </header>

    <div class="layout">
      <main class="video-box glass-panel">
        <div class="stream-container">
          <img src="http://192.168.137.1:8080/video_feed" class="stream-img" />
          
          <div class="corner tl"></div><div class="corner tr"></div>
          <div class="corner bl"></div><div class="corner br"></div>
        </div>
      </main>

      <aside class="side-bar">
        <div class="data-card glass-panel">
          <label>CURRENT TASK</label>
          <p>Real-time Emotion & Mesh</p>
          <div class="divider"></div>
          <label>ENGINE STATUS</label>
          <p class="status-ok">DeepFace Optimized</p>
        </div>

        <button class="btn-refresh" @click="reload">RESTART STREAM</button>
      </aside>
    </div>
  </div>
</template>

<script setup>
const reload = () => window.location.reload();
</script>

<style scoped>
.page-container {
  width: 100%;
  height: 100%;
  padding: 40px;
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.header {
  height: 90px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 50px;
}

.logo { font-size: 22px; letter-spacing: 6px; font-weight: 300; }
.highlight { font-weight: 800; color: #4a90e2; }
.sys-info { font-size: 12px; color: #999; letter-spacing: 1px; }

.layout {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 30px;
  flex: 1;
}

.video-box {
  padding: 15px;
  background: #ffffff;
  display: flex;
}

.stream-container {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
}

.stream-img {
  width: 100%;
  height: 100%;
  object-fit: contain; /* 关键：保持视频比例不拉伸 */
}

.side-bar { display: flex; flex-direction: column; gap: 20px; }

.data-card { padding: 40px; }
.divider { height: 1px; background: rgba(0,0,0,0.05); margin: 30px 0; }

label { font-size: 11px; color: #aaa; letter-spacing: 2px; display: block; margin-bottom: 10px; }
p { font-size: 18px; font-weight: 600; color: #333; }
.status-ok { color: #27ae60; }

.btn-refresh {
  height: 70px;
  border: none;
  background: #2c3e50;
  color: white;
  border-radius: 20px;
  font-weight: 700;
  letter-spacing: 1px;
  cursor: pointer;
  box-shadow: 0 10px 20px rgba(0,0,0,0.1);
}

/* 装饰角 */
.corner { position: absolute; width: 25px; height: 25px; border: 4px solid #4a90e2; }
.tl { top: 20px; left: 20px; border-right: none; border-bottom: none; }
.tr { top: 20px; right: 20px; border-left: none; border-bottom: none; }
.bl { bottom: 20px; left: 20px; border-right: none; border-top: none; }
.br { bottom: 20px; right: 20px; border-left: none; border-top: none; }
</style>