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
import { useRouter } from 'vue-router'

const router = useRouter()

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

.setting-item .value {
  font-size: 22px;
  color: #888;
}

.setting-item .arrow {
  font-size: 24px;
  color: #CCC;
}
</style>
