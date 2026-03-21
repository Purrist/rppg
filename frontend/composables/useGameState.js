/**
 * 游戏状态管理 - 统一存储和传递游戏状态
 * 
 * 存储格式（JSON）：
 * {
 *   currentGame: string | null,      // 当前游戏ID: 'whack_a_mole' | 'processing_speed' | null
 *   gameStatus: string,              // 游戏状态: 'IDLE' | 'READY' | 'PLAYING' | 'PAUSED' | 'SETTLING'
 *   dwellTime: number,               // 确认时间（毫秒）
 *   score: number,                   // 当前得分
 *   timer: number,                   // 剩余时间（秒）
 *   difficulty: number | string,     // 难度等级
 *   timestamp: number,               // 状态更新时间戳
 *   config: {                        // 游戏配置
 *     duration: number,              // 游戏时长（秒）
 *     module: string | null,         // 当前模块（处理速度训练）
 *     // 其他配置...
 *   }
 * }
 */

import { ref, computed, watch } from 'vue'

// 默认游戏状态
const DEFAULT_STATE = {
  currentGame: null,
  gameStatus: 'IDLE',
  dwellTime: 2000,  // 默认2秒
  score: 0,
  timer: 60,
  difficulty: 3,
  timestamp: 0,
  config: {
    duration: 60,
    module: null,
  }
}

// 创建响应式状态
const gameState = ref({ ...DEFAULT_STATE })

// localStorage key
const STORAGE_KEY = 'game_state'

/**
 * 从 localStorage 加载状态
 */
function loadFromStorage() {
  if (typeof window === 'undefined') return DEFAULT_STATE
  
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      return { ...DEFAULT_STATE, ...parsed }
    }
  } catch (e) {
    console.error('[GameState] 加载状态失败:', e)
  }
  return DEFAULT_STATE
}

/**
 * 保存状态到 localStorage
 */
function saveToStorage(state) {
  if (typeof window === 'undefined') return
  
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...state,
      timestamp: Date.now()
    }))
  } catch (e) {
    console.error('[GameState] 保存状态失败:', e)
  }
}

/**
 * 初始化状态
 */
export function initGameState() {
  const saved = loadFromStorage()
  gameState.value = saved
  
  // 监听状态变化并自动保存
  watch(gameState, (newState) => {
    saveToStorage(newState)
  }, { deep: true })
  
  return gameState
}

/**
 * 获取当前游戏状态
 */
export function getGameState() {
  return gameState.value
}

/**
 * 更新游戏状态（部分更新）
 */
export function updateGameState(updates) {
  gameState.value = {
    ...gameState.value,
    ...updates,
    timestamp: Date.now()
  }
}

/**
 * 设置当前游戏
 */
export function setCurrentGame(gameId) {
  gameState.value.currentGame = gameId
  gameState.value.timestamp = Date.now()
}

/**
 * 设置游戏状态
 */
export function setGameStatus(status) {
  gameState.value.gameStatus = status
  gameState.value.timestamp = Date.now()
}

/**
 * 设置确认时间
 */
export function setDwellTime(ms) {
  gameState.value.dwellTime = ms
  gameState.value.timestamp = Date.now()
  
  // 同时保存到独立的 localStorage key（兼容旧代码）
  if (typeof window !== 'undefined') {
    localStorage.setItem('dwellTime', ms.toString())
  }
}

/**
 * 获取确认时间
 */
export function getDwellTime() {
  // 优先从独立存储读取（兼容旧代码）
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem('dwellTime')
    if (saved) {
      const ms = parseInt(saved)
      if (!isNaN(ms)) {
        // 同步到统一状态
        if (gameState.value.dwellTime !== ms) {
          gameState.value.dwellTime = ms
        }
        return ms
      }
    }
  }
  return gameState.value.dwellTime
}

/**
 * 更新游戏数据（得分、时间等）
 */
export function updateGameData(data) {
  gameState.value = {
    ...gameState.value,
    score: data.score ?? gameState.value.score,
    timer: data.timer ?? gameState.value.timer,
    difficulty: data.difficulty ?? data.difficulty_level ?? gameState.value.difficulty,
    timestamp: Date.now()
  }
}

/**
 * 重置游戏状态
 */
export function resetGameState() {
  gameState.value = {
    ...DEFAULT_STATE,
    dwellTime: getDwellTime(), // 保留确认时间设置
    timestamp: Date.now()
  }
}

/**
 * 检查是否在游戏中
 */
export function isInGame() {
  return gameState.value.gameStatus === 'PLAYING' || 
         gameState.value.gameStatus === 'PAUSED' ||
         gameState.value.gameStatus === 'READY' ||
         gameState.value.gameStatus === 'SETTLING'
}

/**
 * 检查当前是否是某个游戏
 */
export function isCurrentGame(gameId) {
  return gameState.value.currentGame === gameId
}

/**
 * 导出状态为 JSON 字符串
 */
export function exportState() {
  return JSON.stringify(gameState.value)
}

/**
 * 从 JSON 字符串导入状态
 */
export function importState(jsonString) {
  try {
    const parsed = JSON.parse(jsonString)
    gameState.value = {
      ...DEFAULT_STATE,
      ...parsed,
      timestamp: Date.now()
    }
    return true
  } catch (e) {
    console.error('[GameState] 导入状态失败:', e)
    return false
  }
}

// 计算属性
export const currentGame = computed(() => gameState.value.currentGame)
export const gameStatus = computed(() => gameState.value.gameStatus)
export const dwellTime = computed(() => gameState.value.dwellTime)
export const currentScore = computed(() => gameState.value.score)
export const currentTimer = computed(() => gameState.value.timer)

// 默认导出
export default {
  state: gameState,
  currentGame,
  gameStatus,
  dwellTime,
  currentScore,
  currentTimer,
  init: initGameState,
  get: getGameState,
  update: updateGameState,
  setGame: setCurrentGame,
  setStatus: setGameStatus,
  setDwellTime,
  getDwellTime,
  updateData: updateGameData,
  reset: resetGameState,
  isInGame,
  isCurrentGame,
  export: exportState,
  import: importState
}
