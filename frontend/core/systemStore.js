/**
 * System Store - 前端状态订阅器
 * 
 * 原则：后端是唯一的数据中心，前端只负责：
 * 1. 订阅后端状态更新
 * 2. 发送用户操作到后端
 * 3. 显示数据
 * 
 * 不存储任何状态，所有数据来自后端！
 */

import { ref, readonly } from 'vue'

// 当前状态（从后端同步）
const state = ref({
  aiMode: 'basic',
  currentPage: '/',
  gameState: {
    status: 'IDLE',
    currentGame: null,
    difficulty: 3,
    score: 0,
    timer: 60,
    module: null,
    dwellTime: 2000
  },
  perception: {
    personDetected: false,
    faceCount: 0,
    footPosition: { x: 0, y: 0, detected: false },
    emotion: 'neutral',
    attention: 0,
    fatigue: 0
  },
  userState: {
    heartRate: null,
    overallState: 'normal'
  },
  settings: {
    dwellTime: 2000
  }
})

// Socket实例
let socket = null

// 监听器
const listeners = new Set()

/**
 * 初始化 - 传入Socket实例
 */
export function initStore(socketInstance) {
  socket = socketInstance
  
  // 监听后端状态更新
  socket.on('system_state', (data) => {
    updateState(data)
  })
  
  // 监听游戏状态更新
  socket.on('game_update', (data) => {
    if (data) {
      state.value.gameState = { ...state.value.gameState, ...data }
      notifyListeners('game', data)
    }
  })
  
  // 监听感知数据
  socket.on('perception_update', (data) => {
    if (data) {
      state.value.perception = { ...state.value.perception, ...data }
      notifyListeners('perception', data)
    }
  })
  
  console.log('[SystemStore] 已初始化')
}

/**
 * 更新状态
 */
function updateState(data) {
  if (data.aiMode !== undefined) state.value.aiMode = data.aiMode
  if (data.currentPage !== undefined) state.value.currentPage = data.currentPage
  if (data.gameState !== undefined) state.value.gameState = { ...state.value.gameState, ...data.gameState }
  if (data.perception !== undefined) state.value.perception = { ...state.value.perception, ...data.perception }
  if (data.userState !== undefined) state.value.userState = { ...state.value.userState, ...data.userState }
  if (data.settings !== undefined) state.value.settings = { ...state.value.settings, ...data.settings }
  
  notifyListeners('state', state.value)
}

/**
 * 通知监听器
 */
function notifyListeners(key, value) {
  listeners.forEach(cb => cb(key, value, state.value))
}

/**
 * 订阅状态变化
 */
export function subscribe(callback) {
  listeners.add(callback)
  callback('init', null, state.value)
  return () => listeners.delete(callback)
}

/**
 * 获取当前状态（只读）
 */
export function getState() {
  return readonly(state)
}

// ==================== 发送操作到后端 ====================

/**
 * 设置AI模式
 */
export function setAIMode(mode) {
  if (socket) socket.emit('set_ai_mode', { mode })
}

/**
 * 设置当前页面
 */
export function setCurrentPage(page) {
  if (socket) socket.emit('set_page', { page })
}

/**
 * 设置确认时间
 */
export function setDwellTime(ms) {
  if (socket) socket.emit('set_dwell_time', { dwellTime: ms })
}

/**
 * 游戏控制
 */
export function gameControl(action, data = {}) {
  if (socket) socket.emit('game_control', { action, ...data })
}

/**
 * 游戏动作
 */
export function gameAction(action, data = {}) {
  if (socket) socket.emit('game_action', { action, ...data })
}

// ==================== 导出 ====================
export default {
  state: readonly(state),
  init: initStore,
  subscribe,
  getState,
  setAIMode,
  setCurrentPage,
  setDwellTime,
  gameControl,
  gameAction
}
