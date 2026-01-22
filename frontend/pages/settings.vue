<template>
  <div class="settings-view">
    <h1 class="title">系统设置</h1>
    <div class="card">
      <div class="item"><span>声音提示</span> <input type="checkbox" checked /></div>
      <div class="item"><span>高对比度模式</span> <input type="checkbox" /></div>
      <div class="item"><span>Akon 语音唤醒</span> <input type="checkbox" checked /></div>
    </div>
    <div class="card">
      <div class="item"><span>当前版本</span> <span>v1.6.0</span></div>
      <div class="item"><span>设备序列号</span> <span>RPPG-7788-2026</span></div>
    </div>
  </div>
</template>

<style scoped>
.settings-view { padding-top: 80px; }
.title { font-size: 40px; margin-bottom: 40px; }
.card { background: #F9F9F9; border-radius: 30px; padding: 10px 40px; margin-bottom: 30px; }
.item { display: flex; justify-content: space-between; padding: 30px 0; border-bottom: 1px solid #EEE; font-size: 24px; font-weight: bold; }
.item:last-child { border: none; }
</style>