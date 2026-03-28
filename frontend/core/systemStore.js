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
    state: 'STANDBY',  // STANDBY / RESPONDING / LISTENING / PROCESSING
    isListening: false,
    isSpeaking: false,
    isRecording: false,
    isPlaying: false,
    isAwakened: false,
    isLoading: false,  // AI思考中
    message: '等待唤醒...',
    lastWakeTime: 0,
  },
})

let socket = null
const listeners = new Set()
let isInitialized = false  // ⭐ 标记是否已经初始化

// 从localStorage加载聊天记录
const loadChatMessagesFromStorage = () => {
  try {
    const saved = localStorage.getItem('akon_chat_messages')
    if (saved) {
      return JSON.parse(saved)
    }
  } catch (e) {
    console.error('[SystemStore] 加载聊天记录失败:', e)
  }
  return []
}

// 保存聊天记录到localStorage
const saveChatMessagesToStorage = (messages) => {
  try {
    localStorage.setItem('akon_chat_messages', JSON.stringify(messages))
  } catch (e) {
    console.error('[SystemStore] 保存聊天记录失败:', e)
  }
}

// 初始化
export function initStore(socketInstance) {
  // ⭐ 防止重复初始化
  if (isInitialized) {
    console.log('[SystemStore] 已经初始化，跳过')
    socket = socketInstance  // 更新socket引用
    return
  }
  
  socket = socketInstance
  isInitialized = true
  
  // ⭐ 从localStorage加载聊天记录
  state.value.chatMessages = loadChatMessagesFromStorage()
  
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
    // ⭐ 语音状态
    if (data.voice !== undefined) Object.assign(state.value.voice, data.voice)
    
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
  
  // ⭐ 语音状态变更
  socket.on('voice_state_change', (data) => {
    if (data.state) state.value.voice.state = data.state
    if (data.isRecording !== undefined) state.value.voice.isRecording = data.isRecording
    if (data.isPlaying !== undefined) state.value.voice.isPlaying = data.isPlaying
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ 唤醒成功 - 弹出阿康对话框
  socket.on('voice_wake_up', (data) => {
    state.value.voice.isAwakened = true
    state.value.voice.state = data.state || 'RESPONDING'
    // 不添加系统回应到聊天记录，只显示用户的实际输入
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ 用户说话 - 显示在对话中
  socket.on('voice_user_speak', (data) => {
    state.value.voice.state = data.state || 'PROCESSING'
    state.value.voice.isLoading = true  // 设置思考中状态
    // 添加用户消息
    state.value.chatMessages.push({ 
      role: 'user', 
      content: data.text,
      type: 'voice_input',
      timestamp: Date.now()
    })
    // ⭐ 保存到localStorage
    saveChatMessagesToStorage(state.value.chatMessages)
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ LLM回复 - 不直接添加，由app.vue处理（实现打字机效果）
  socket.on('voice_llm_response', (data) => {
    state.value.voice.isLoading = false  // 关闭思考中状态
    // 移除[ACTION:]标记
    let text = data.text.replace(/\[ACTION:\]/g, '').trim()
    // 触发自定义事件，让app.vue处理打字机效果
    window.dispatchEvent(new CustomEvent('ai_response', { 
      detail: { text, source: 'voice' } 
    }))
  })
  
  // ⭐ 语音播报状态
  socket.on('voice_speaking', (data) => {
    state.value.voice.isSpeaking = data.status === 'start'
    state.value.voice.isPlaying = data.status === 'start'
    listeners.forEach(cb => cb(state.value))
  })
  
  // ⭐ 语音状态（兼容旧版）
  socket.on('voice_status', (data) => {
    if (data.state) state.value.voice.state = data.state
    if (data.status === 'listening') {
      state.value.voice.isListening = true
    } else if (data.status === 'standby') {
      state.value.voice.isListening = false
      state.value.voice.isAwakened = false
      state.value.voice.state = 'STANDBY'
    }
    if (data.message) state.value.voice.message = data.message
    listeners.forEach(cb => cb(state.value))
  })
}

// ⭐ 添加消息到聊天记录
export function addChatMessage(message) {
  state.value.chatMessages.push(message)
  // ⭐ 保存到localStorage
  saveChatMessagesToStorage(state.value.chatMessages)
  listeners.forEach(cb => cb(state.value))
}

// ⭐ 清空聊天记录
export function clearChatMessages() {
  state.value.chatMessages = []
  listeners.forEach(cb => cb(state.value))
}

// ⭐ 设置AI思考中状态
export function setVoiceLoading(loading) {
  state.value.voice.isLoading = loading
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
