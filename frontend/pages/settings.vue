<template>
  <div class="settings-page">
    <h1>⚙️ 系统设置</h1>
    
    <div class="settings-section">
      <h2>个人信息</h2>
      <div class="setting-item">
        <span class="label">姓名</span>
        <span class="value">张爷爷</span>
      </div>
      <div class="setting-item">
        <span class="label">年龄</span>
        <span class="value">72岁</span>
      </div>
    </div>
    
    <div class="settings-section">
      <h2>投影交互设置</h2>
      <div class="setting-item">
        <span class="label">
          <div class="label-main">确认时间（灵敏度）</div>
          <div class="label-sub">站在识别区域后，进度圈从0%到100%所需的时间</div>
        </span>
        <div class="value-control">
          <button class="adjust-btn" @click="decreaseDwellTime" :disabled="dwellTime <= 1500">−</button>
          <span class="value">{{ (dwellTime / 1000).toFixed(1) }}秒</span>
          <button class="adjust-btn" @click="increaseDwellTime" :disabled="dwellTime >= 4000">+</button>
        </div>
      </div>
      <div class="setting-hint">
        <p>💡 <strong>提示</strong>：确认时间越短，交互越灵敏，但可能误触；确认时间越长，交互越稳定，但需要等待更久。</p>
        <p>推荐设置：<strong>2.0秒</strong>（适合大多数用户）</p>
      </div>
    </div>
    
    <div class="settings-section">
      <h2>系统管理</h2>
      <div class="setting-item clickable" @click="goToDeveloper">
        <span class="label">🛠 开发者后台</span>
        <span class="arrow">→</span>
      </div>
      <div class="setting-item clickable" @click="goToProjection">
        <span class="label">📽 投影页面</span>
        <span class="arrow">→</span>
      </div>
    </div>
    
    <div class="settings-section">
      <h2>关于</h2>
      <div class="setting-item">
        <span class="label">系统版本</span>
        <span class="value">v1.0.0</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { initGameState, setDwellTime, getDwellTime } from '../composables/useGameState.js'

const router = useRouter()

// 确认时间（毫秒），范围1500-4000ms，默认2000ms
const dwellTime = ref(2000)

// 初始化游戏状态管理
initGameState()

// 从统一状态管理读取保存的设置
onMounted(() => {
  dwellTime.value = getDwellTime()
})

// 减少确认时间
const decreaseDwellTime = () => {
  if (dwellTime.value > 1500) {
    dwellTime.value -= 500
    saveDwellTime()
  }
}

// 增加确认时间
const increaseDwellTime = () => {
  if (dwellTime.value < 4000) {
    dwellTime.value += 500
    saveDwellTime()
  }
}

// 保存设置（使用统一状态管理）
const saveDwellTime = () => {
  setDwellTime(dwellTime.value)
}

const goToDeveloper = () => {
  router.push('/developer')
}

const goToProjection = () => {
  router.push('/projection')
}
</script>

<style scoped>
.settings-page {
  padding: 40px;
}

.settings-page h1 {
  font-size: 36px;
  font-weight: 900;
  color: #333;
  margin-bottom: 40px;
}

.settings-section {
  margin-bottom: 40px;
}

.settings-section h2 {
  font-size: 24px;
  color: #888;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #EEE;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #FFF;
  border-radius: 15px;
  margin-bottom: 15px;
}

.setting-item.clickable {
  cursor: pointer;
  transition: background 0.2s;
}

.setting-item.clickable:hover {
  background: #F5F5F5;
}

.setting-item .label {
  font-size: 22px;
  color: #333;
}

.label-main {
  font-size: 22px;
  font-weight: 600;
  color: #333;
  margin-bottom: 5px;
}

.label-sub {
  font-size: 16px;
  color: #888;
  max-width: 400px;
  line-height: 1.4;
}

.value-control {
  display: flex;
  align-items: center;
  gap: 15px;
}

.value-control .value {
  font-size: 24px;
  font-weight: 700;
  color: #FF7222;
  min-width: 80px;
  text-align: center;
}

.adjust-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid #FF7222;
  background: #FFF;
  color: #FF7222;
  font-size: 24px;
  font-weight: bold;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.adjust-btn:hover:not(:disabled) {
  background: #FF7222;
  color: #FFF;
}

.adjust-btn:disabled {
  border-color: #CCC;
  color: #CCC;
  cursor: not-allowed;
}

.setting-hint {
  background: #FFF5F0;
  padding: 20px;
  border-radius: 15px;
  margin-top: 10px;
}

.setting-hint p {
  font-size: 18px;
  color: #666;
  line-height: 1.6;
  margin-bottom: 10px;
}

.setting-hint p:last-child {
  margin-bottom: 0;
}

.setting-hint strong {
  color: #FF7222;
}

.setting-item .value {
  font-size: 22px;
  color: #888;
}

.setting-item .arrow {
  font-size: 24px;
  color: #CCC;
}
</style>
