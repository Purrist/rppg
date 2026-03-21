<!--
  GameRules.vue - 游戏规则组件
  显示当前游戏的规则和提示
-->

<template>
  <div class="game-rules">
    <div class="rules-header">
      <span class="rules-icon">{{ rules.icon }}</span>
      <h3>{{ rules.title }}</h3>
    </div>
    
    <div class="rules-content">
      <p class="rules-desc">{{ rules.description }}</p>
      
      <div class="rules-list">
        <h4>📋 游戏规则</h4>
        <ul>
          <li v-for="(rule, index) in rules.rules" :key="index">
            {{ rule }}
          </li>
        </ul>
      </div>
      
      <div class="rules-tips">
        <h4>💡 游戏提示</h4>
        <p>{{ rules.tips }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  gameType: {
    type: String,
    required: true
  }
})

const gameRulesData = {
  'whack_a_mole': {
    icon: '🐹',
    title: '趣味打地鼠',
    description: '锻炼手眼协调与反应速度的经典游戏',
    rules: [
      '游戏开始后，地鼠会随机从三个洞中出现',
      '当🐹出现时，站在对应地鼠洞上停留2秒即可击中',
      '击中地鼠得10分，错过扣5分',
      '游戏时长60秒，尽可能获得高分！'
    ],
    tips: '请站在投影区域的圆圈内，当地鼠出现时快速移动到对应位置并停留确认。'
  },
  'processing_speed': {
    icon: '⚡',
    title: '处理速度训练',
    description: '基于ACTIVE研究的科学认知训练，包含三个模块',
    rules: [
      '【反应控制】绿色区域出现时要快速踩踏，红色区域出现时要忍住不踩',
      '【选择反应】根据提示踩踏对应颜色的区域',
      '【序列学习】按顺序踩踏亮起的区域，完成整个序列',
      '每个模块60秒，站在目标区域停留3秒确认选择',
      '反应越快得分越高，系统会根据表现自动调整难度'
    ],
    tips: '游戏共有8个圆形区域，请根据屏幕提示踩踏正确位置，停留3秒完成确认。'
  }
}

const rules = computed(() => {
  return gameRulesData[props.gameType] || {
    icon: '🎮',
    title: '游戏',
    description: '请开始游戏',
    rules: ['游戏规则加载中...'],
    tips: '请等待游戏开始'
  }
})
</script>

<style scoped>
.game-rules {
  background: #FFF;
  border-radius: 30px;
  padding: 30px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.rules-header {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 2px solid #EEE;
}

.rules-icon {
  font-size: 48px;
}

.rules-header h3 {
  font-size: 32px;
  color: #333;
  margin: 0;
}

.rules-content {
  flex: 1;
  overflow-y: auto;
}

.rules-desc {
  font-size: 20px;
  color: #666;
  margin-bottom: 25px;
  line-height: 1.5;
}

.rules-list, .rules-tips {
  margin-bottom: 25px;
}

.rules-list h4, .rules-tips h4 {
  font-size: 22px;
  color: #333;
  margin-bottom: 15px;
}

.rules-list ul {
  list-style: none;
  padding: 0;
}

.rules-list li {
  font-size: 18px;
  color: #555;
  padding: 10px 0;
  padding-left: 30px;
  position: relative;
  line-height: 1.5;
}

.rules-list li::before {
  content: '•';
  position: absolute;
  left: 10px;
  color: #FF7222;
  font-weight: bold;
  font-size: 24px;
}

.rules-tips p {
  font-size: 18px;
  color: #FF7222;
  background: #FFF5F0;
  padding: 20px;
  border-radius: 15px;
  line-height: 1.5;
}
</style>
