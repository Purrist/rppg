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
    module: null,
    dwellTime: 2000,
  },
  gameRuntime: {
    score: 0,
    timer: 60,
    accuracy: 0,
    trialCount: 0,
    correctCount: 0,
  },
  perception: {
    personDetected: false,
    personCount: 0,
    faceCount: 0,
    bodyDetected: false,
    footPosition: { x: 0, y: 0, detected: false },
    emotion: 'neutral',
    attention: 0,
    fatigue: 0,
    heartRate: null,
    activity: 'unknown',
    speaking: false,
    idleMinutes: 0,
  },
  environment: {
    lightLevel: 'normal',
  },
  settings: {
    dwellTime: 2000,
    soundEnabled: true,
    projectionEnabled: true,
    voiceWakeup: true,
    voiceSpeaking: true,
  },
  timeInfo: {
    time: '',
    date: '',
    weekday: '',
  },
  timestamp: 0,
  // ⭐ 全局聊天记录（所有页面共享）
  chatMessages: [],
  // ⭐ 语音状态
  voice: {
    isListening: false,
    isSpeaking: false,
    isAwakened: false,
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
    if (data.environment !== undefined) Object.assign(state.value.environment, data.environment)
    if (data.settings !== undefined) Object.assign(state.value.settings, data.settings)
    if (data.timeInfo !== undefined) Object.assign(state.value.timeInfo, data.timeInfo)
    if (data.timestamp !== undefined) state.value.timestamp = data.timestamp
    
    listeners.forEach(cb => cb(state.value))
  })
  
  socket.on('perception_update', (data) => {
    if (data) {
      Object.assign(state.value.perception, data)
      listeners.forEach(cb => cb(state.value))
    }
  })
  
  // ⭐ 游戏运行时数据更新
  socket.on('game_runtime_update', (data) => {
    if (data.gameRuntime) Object.assign(state.value.gameRuntime, data.gameRuntime)
    if (data.gameStatus) Object.assign(state.value.game, data.gameStatus)
    if (data.gameDifficulty !== undefined) state.value.game.difficulty = data.gameDifficulty
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ 语音状态更新
  socket.on('voice_status', (data) => {
    if (data.status === 'listening') {
      state.value.voice.isListening = true
    } else {
      state.value.voice.isListening = false
    }
  })
  
  // ⭐ 语音播报状态更新
  socket.on('voice_speaking', (data) => {
    state.value.voice.isSpeaking = data.status === 'start'
  })
  
  // ⭐ 唤醒超时更新
  socket.on('voice_sleep', (data) => {
    state.value.voice.isAwakened = false
  })
  
  // ⭐ 唤醒成功
  socket.on('voice_wake_up', (data) => {
    state.value.voice.isAwakened = true
    // 添加系统消息
    state.value.chatMessages.push({ role: 'system', content: data.response })
    if (data.user_text) {
      state.value.chatMessages.push({ role: 'user', content: data.user_text })
    }
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ 用户说话
  socket.on('voice_user_speak', (data) => {
    state.value.chatMessages.push({ role: 'user', content: data.text })
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ AI回复（语音命令）
  socket.on('voice_ai_response', (data) => {
    // 避免重复添加用户消息
    const lastMsg = state.value.chatMessages[state.value.chatMessages.length - 1]
    if (!lastMsg || lastMsg.role !== 'user' || lastMsg.content !== data.user_text) {
      state.value.chatMessages.push({ role: 'user', content: data.user_text })
    }
    state.value.chatMessages.push({ role: 'assistant', content: data.ai_response })
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ 语音播报状态
  socket.on('voice_speaking', (data) => {
    state.value.voice.isSpeaking = data.status === 'start'
  })
  
  // ⭐ 唤醒超时
  socket.on('voice_sleep', (data) => {
    state.value.voice.isAwakened = false
  })
}

// ⭐ 添加消息到聊天记录
export function addChatMessage(message) {
  state.value.chatMessages.push(message)
  listeners.forEach(cb => cb(state.value))
}

// ⭐ 清空聊天记录
export function clearChatMessages() {
  state.value.chatMessages = []
  listeners.forEach(cb => cb(state.value))
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
export const setVoiceSetting = (type, enabled) => socket?.emit('set_voice_setting', { type, enabled })
export const gameControl = (action, data = {}) => socket?.emit('game_control', { action, ...data })
export const gameAction = (action, data = {}) => socket?.emit('game_action', { action, ...data })
export const requestSystemState = () => socket?.emit('get_system_state')

// 切换智伴模式
export const toggleCompanion = () => {
  const newMode = state.value.aiMode === 'companion' ? 'basic' : 'companion'
  setAIMode(newMode)
}

// 便捷方法
export const isBasicMode = () => state.value.aiMode === 'basic'
export const isCompanionMode = () => state.value.aiMode === 'companion'
export const isGameActive = () => ['READY', 'PLAYING', 'PAUSED', 'SETTLING'].includes(state.value.game?.status)

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
