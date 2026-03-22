<template>
  <div class="page-body">
    <h2>🧩 益智训练中心</h2>
    <div class="learning-grid">
      <div class="l-card" @click="showGameInfo('whack_a_mole')">
        <div class="l-icon">🐹</div>
        <div class="l-text">
          <h3>趣味打地鼠</h3>
          <p>锻炼手眼协调与反应速度</p>
        </div>
      </div>
      
      <div class="l-card" @click="showGameInfo('processing_speed')">
        <div class="l-icon">⚡</div>
        <div class="l-text">
          <h3>处理速度训练</h3>
          <p>科学提升认知处理速度</p>
        </div>
      </div>
      
      <div class="l-card" @click="handleTodo">
        <div class="l-icon">🎨</div>
        <div class="l-text">
          <h3>色词挑战</h3>
          <p>提升认知抑制与注意力</p>
        </div>
      </div>
      
      <div class="l-card" @click="handleTodo">
        <div class="l-icon">🧠</div>
        <div class="l-text">
          <h3>记忆配对</h3>
          <p>提升图像记忆能力</p>
        </div>
      </div>
    </div>
    
    <!-- 游戏信息弹窗 -->
    <div v-if="selectedGame" class="game-modal" @click.self="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="modal-icon">{{ gameInfo[selectedGame].icon }}</span>
          <h3>{{ gameInfo[selectedGame].title }}</h3>
          <button class="close-btn" @click="closeModal">×</button>
        </div>
        
        <div class="modal-body">
          <p class="game-desc">{{ gameInfo[selectedGame].description }}</p>
          
          <div class="rules-section">
            <h4>📋 游戏规则</h4>
            <ul>
              <li v-for="(rule, index) in gameInfo[selectedGame].rules" :key="index">
                {{ rule }}
              </li>
            </ul>
          </div>
          
          <div class="tips-section">
            <h4>💡 游戏提示</h4>
            <p>{{ gameInfo[selectedGame].tips }}</p>
          </div>
        </div>
        
        <div class="modal-footer">
          <button class="start-btn" @click="confirmStartGame">
            开始游戏
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { initStore, subscribe, gameControl } from '../core/systemStore.js'

const router = useRouter()
let socket = null
let unsubscribe = null

const selectedGame = ref(null)

const gameInfo = {
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

const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  return window.location.hostname || 'localhost'
}

const FLASK_PORT = 5000
const backendUrl = `http://${getBackendHost()}:${FLASK_PORT}`

onMounted(() => {
  socket = io(backendUrl, {
    transports: ['polling', 'websocket'],
    reconnection: true
  })
  
  // ⭐ 关键修复：初始化systemStore
  initStore(socket)
  
  socket.on('connect', () => {
    console.log('[益智] 后端已连接')
  })
  
  socket.on('navigate_to', (data) => {
    router.push(data.page)
  })
  
  // 监听游戏状态变化
  socket.on('game_update', (data) => {
    // 更新统一游戏状态
    if (data.game_id) {
      setCurrentGame(data.game_id)
    }
    if (data.status) {
      setGameStatus(data.status)
    }
    
    // 如果状态变为READY，跳转到training页面
    if (data.status === 'READY') {
      router.push('/training')
    }
  })
  
  socket.on('system_state', (data) => {
    if (data.state?.game) {
      if (data.state.game.active === false && data.state.game.status === 'IDLE') {
        // 已经在 learning 页面，不需要跳转
      }
    }
  })
})

onUnmounted(() => {
  if (socket) socket.disconnect()
})

const showGameInfo = (gameName) => {
  selectedGame.value = gameName
}

const closeModal = () => {
  selectedGame.value = null
}

const confirmStartGame = () => {
  if (selectedGame.value && socket && socket.connected) {
    const gameId = selectedGame.value
    console.log('[learning] 开始游戏:', gameId)
    
    // 发送到后端，后端是唯一的真相来源
    gameControl('ready', { game: gameId })
    selectedGame.value = null
  } else {
    alert('后端未连接，请稍后重试')
  }
}

const handleTodo = () => {
  alert('该功能正在开发中，敬请期待！')
}
</script>

<style scoped>
.page-body { 
  padding: 40px; 
}

.learning-grid { 
  display: grid; 
  grid-template-columns: 1fr 1fr; 
  gap: 30px; 
  margin-top: 40px; 
}

.l-card { 
  background: #FFF; 
  border: 2px solid #EEE; 
  border-radius: 30px; 
  padding: 30px; 
  display: flex; 
  align-items: center; 
  gap: 20px; 
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.l-card:hover {
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}

.l-card:active { 
  transform: scale(0.98); 
}

.l-icon { 
  font-size: 60px; 
}

.l-text h3 { 
  font-size: 28px; 
  margin-bottom: 5px; 
  color: #333; 
}

.l-text p { 
  color: #888; 
  font-size: 18px; 
}

/* 弹窗样式 - 增大尺寸 */
.game-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 40px;
}

.modal-content {
  background: #FFF;
  border-radius: 40px;
  width: 90%;
  max-width: 900px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px 30px;  /* 减小padding */
  background: linear-gradient(135deg, #FF7222 0%, #FF9A5C 100%);
  color: #FFF;
  flex-shrink: 0;
}

.modal-icon {
  font-size: 40px;  /* 减小图标 */
}

.modal-header h3 {
  flex: 1;
  font-size: 28px;  /* 减小标题 */
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  color: #FFF;
  font-size: 36px;  /* 减小关闭按钮 */
  cursor: pointer;
  padding: 0 10px;
  transition: transform 0.2s;
}

.close-btn:hover {
  transform: scale(1.1);
}

/* ⭐ 可滚动内容区域 - 增大空间 */
.modal-body {
  padding: 30px 40px;
  overflow-y: auto;
  flex: 1;
  max-height: calc(85vh - 160px);  /* 减小减去的值，增大内容区域 */
  scrollbar-width: thin;
  scrollbar-color: #FF7222 #f0f0f0;
}

/* 自定义滚动条样式 */
.modal-body::-webkit-scrollbar {
  width: 10px;
}

.modal-body::-webkit-scrollbar-track {
  background: #f0f0f0;
  border-radius: 5px;
}

.modal-body::-webkit-scrollbar-thumb {
  background: #FF7222;
  border-radius: 5px;
}

.modal-body::-webkit-scrollbar-thumb:hover {
  background: #e66000;
}

.game-desc {
  font-size: 24px;
  color: #666;
  margin-bottom: 30px;
  line-height: 1.6;
}

.rules-section, .tips-section {
  margin-bottom: 30px;
}

.rules-section h4, .tips-section h4 {
  font-size: 28px;
  color: #333;
  margin-bottom: 20px;
}

.rules-section ul {
  list-style: none;
  padding: 0;
}

.rules-section li {
  font-size: 22px;
  color: #555;
  padding: 15px 0;
  padding-left: 40px;
  position: relative;
  line-height: 1.6;
}

.rules-section li::before {
  content: '•';
  position: absolute;
  left: 15px;
  color: #FF7222;
  font-weight: bold;
  font-size: 28px;
}

.tips-section p {
  font-size: 22px;
  color: #FF7222;
  background: #FFF5F0;
  padding: 25px;
  border-radius: 20px;
  line-height: 1.6;
}

.modal-footer {
  padding: 20px 30px 25px;  /* 减小padding */
  display: flex;
  justify-content: center;
  flex-shrink: 0;
  border-top: 2px solid #f0f0f0;
}

.start-btn {
  background: #FF7222;
  color: #FFF;
  border: none;
  padding: 18px 60px;  /* 减小按钮 */
  border-radius: 40px;
  font-size: 24px;  /* 减小字体 */
  font-weight: bold;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.start-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 6px 30px rgba(255, 114, 34, 0.5);
}

.start-btn:active {
  transform: scale(0.98);
}
</style>
