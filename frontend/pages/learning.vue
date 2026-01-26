<template>
  <div class="page-body">
    <h2>🧩 益智训练中心</h2>
    <div class="learning-grid">
      <div class="l-card mole" @click="$router.push('/training')">
        <div class="l-icon">🐹</div>
        <div class="l-text">
          <h3>趣味打地鼠</h3>
          <p>锻炼手眼协调与反应速度</p>
        </div>
      </div>
      <div class="l-card stroop" @click="handleTodo">
        <div class="l-icon">🎨</div>
        <div class="l-text">
          <h3>色词挑战</h3>
          <p>提升认知抑制与注意力</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const handleTodo = () => {
  window.alert('该功能正在开发中，敬请期待！')
}
</script>

<style scoped>
.page-body { padding: 40px; }
.learning-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 40px; }
.l-card { 
  background: #FFF; border: 2px solid #EEE; border-radius: 30px; 
  padding: 30px; display: flex; align-items: center; gap: 20px; cursor: pointer;
  transition: transform 0.2s;
}
.l-card:active { transform: scale(0.98); }
.l-icon { font-size: 60px; }
.l-text h3 { font-size: 28px; margin-bottom: 5px; color: #333; }
.l-text p { color: #888; font-size: 18px; }
</style>