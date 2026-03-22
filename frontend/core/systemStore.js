/**
 * System Store - 前端状态订阅器
 * 
 * 原则：
 * - SystemCore是唯一的真相来源
 * - 前端只订阅和显示，不存储权威状态
 */

import { ref, readonly } from 'vue'

// 状态（从后端SystemCore同步）
const state = ref({
  aiMode: 'basic',
  currentPage: '/',
  game: {
    status: 'IDLE',
    currentGame: null,
    difficulty: 3,
    dwellTime: 2000,
  },
  gameRuntime: {
    score: 0,
    timer: 60,
    accuracy: 0,
  },
  perception: {
    personDetected: false,
    emotion: 'neutral',
    attention: 0,
    fatigue: 0,
    footPosition: { x: 0, y: 0, detected: false },
  },
  settings: {
    dwellTime: 2000,
  },
})

let socket = null
const listeners = new Set()

// 初始化
export function initStore(socketInstance) {
  socket = socketInstance
  
  socket.on('system_state', (data) => {
    if (!data) return
    
    if (data.aiMode !== undefined) state.value.aiMode = data.aiMode
    if (data.currentPage !== undefined) state.value.currentPage = data.currentPage
    if (data.game !== undefined) Object.assign(state.value.game, data.game)
    if (data.gameRuntime !== undefined) Object.assign(state.value.gameRuntime, data.gameRuntime)
    if (data.perception !== undefined) Object.assign(state.value.perception, data.perception)
    if (data.settings !== undefined) Object.assign(state.value.settings, data.settings)
    
    listeners.forEach(cb => cb(state.value))
  })
  
  socket.on('perception_update', (data) => {
    if (data) Object.assign(state.value.perception, data)
  })
}

// 订阅
export function subscribe(callback) {
  listeners.add(callback)
  callback(state.value)
  return () => listeners.delete(callback)
}

// 获取状态
export function getState() {
  return readonly(state)
}

// 发送操作到后端
export const setAIMode = (mode) => socket?.emit('set_ai_mode', { mode })
export const setCurrentPage = (page) => socket?.emit('set_page', { page })
export const setDwellTime = (ms) => socket?.emit('set_dwell_time', { dwellTime: ms })
export const gameControl = (action, data = {}) => socket?.emit('game_control', { action, ...data })
export const requestSystemState = () => socket?.emit('get_system_state')

// 便捷方法
export const isBasicMode = () => state.value.aiMode === 'basic'
export const isCompanionMode = () => state.value.aiMode === 'companion'
export const isGameActive = () => ['READY', 'PLAYING', 'PAUSED', 'SETTLING'].includes(state.value.game.status)

export default {
  state: readonly(state),
  init: initStore,
  subscribe,
  getState,
  setAIMode,
  setCurrentPage,
  setDwellTime,
  gameControl,
  requestSystemState,
  isBasicMode,
  isCompanionMode,
  isGameActive,
}
