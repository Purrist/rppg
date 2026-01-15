<template>
  <div class="home-container">
    <div class="header">
      <h1 class="title">认知训练系统</h1>
      <p class="subtitle">选择一个游戏开始训练</p>
    </div>

    <div class="games-grid">
      <div class="game-card" @click="selectGame('color-word')">
        <div class="game-icon">🎨</div>
        <h3 class="game-title">色词游戏</h3>
        <p class="game-description">反应力挑战！选择文字呈现的颜色，而不是文字的内容</p>
        <div class="game-stats">
          <span class="stat">⏱️ 2秒/题</span>
          <span class="stat">🎯 准确率</span>
        </div>
      </div>

      <div class="game-card disabled">
        <div class="game-icon">🧠</div>
        <h3 class="game-title">记忆游戏</h3>
        <p class="game-description">记忆卡片位置，找到所有配对的卡片</p>
        <div class="game-stats">
          <span class="stat">🎴 6对卡片</span>
          <span class="stat">⏱️ 限时挑战</span>
        </div>
      </div>

      <div class="game-card disabled">
        <div class="game-icon">⚡</div>
        <h3 class="game-title">反应测试</h3>
        <p class="game-description">快速点击出现的红色圆圈，测试反应速度</p>
        <div class="game-stats">
          <span class="stat">⚡ 反应速度</span>
          <span class="stat">🎯 精准度</span>
        </div>
      </div>

      <div class="game-card disabled">
        <div class="game-icon">🔢</div>
        <h3 class="game-title">认知训练</h3>
        <p class="game-description">数字记忆和计算训练，提升认知能力</p>
        <div class="game-stats">
          <span class="stat">🔢 数字记忆</span>
          <span class="stat">🧮 计算能力</span>
        </div>
      </div>
    </div>

    <div class="footer">
      <p>💡 提示：点击游戏卡片开始训练</p>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const selectGame = (gameType) => {
  router.push('/training')
}
</script>

<style scoped>
.home-container {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  color: #ffffff;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.header {
  text-align: center;
  margin-bottom: 3rem;
}

.title {
  font-size: 3rem;
  font-weight: 700;
  margin-bottom: 1rem;
  text-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}

.subtitle {
  font-size: 1.5rem;
  opacity: 0.9;
}

.games-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
  max-width: 1200px;
  width: 100%;
  margin-bottom: 3rem;
}

.game-card {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 2rem;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 2px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.game-card:hover:not(.disabled) {
  transform: translateY(-8px);
  background: rgba(255, 255, 255, 0.2);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
}

.game-card.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.game-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  text-align: center;
}

.game-title {
  font-size: 1.8rem;
  font-weight: 600;
  margin-bottom: 0.8rem;
  text-align: center;
}

.game-description {
  font-size: 1rem;
  opacity: 0.9;
  margin-bottom: 1.5rem;
  text-align: center;
  line-height: 1.6;
}

.game-stats {
  display: flex;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.stat {
  background: rgba(255, 255, 255, 0.2);
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 500;
}

.footer {
  text-align: center;
  font-size: 1.2rem;
  opacity: 0.8;
}
</style>
