/**
 * 健康数据缓存 - 持久化波形数据和历史记录
 * 避免页面切换时重新加载
 */
import { ref, readonly } from 'vue'

// 最大保存的数据点数
const MAX_HISTORY = 200
const MAX_WAVE_POINTS = 100

// 缓存数据
const cachedData = ref({
  // 波形数据
  hrWave: Array(MAX_WAVE_POINTS).fill(0),
  brWave: Array(MAX_WAVE_POINTS).fill(0),
  
  // 历史数据（用于趋势图）
  hrHistory: [],
  brHistory: [],
  
  // 当前值
  heartRate: 72,
  breathRate: 16,
  
  // 信号状态
  signalState: 'INIT',
  
  // 最后更新时间
  lastUpdate: 0,
  
  // 是否已经初始化
  isInitialized: false
})

// 从 localStorage 加载缓存
const loadFromStorage = () => {
  try {
    const saved = localStorage.getItem('akon_health_cache')
    if (saved) {
      const data = JSON.parse(saved)
      // 只加载有效的数据，避免过期数据
      const now = Date.now()
      if (data.lastUpdate && (now - data.lastUpdate < 3600000)) { // 1小时内有效
        Object.assign(cachedData.value, data)
        console.log('[HealthCache] 从 localStorage 恢复健康数据')
      }
    }
  } catch (e) {
    console.warn('[HealthCache] 加载缓存失败:', e)
  }
}

// 保存到 localStorage
const saveToStorage = () => {
  try {
    localStorage.setItem('akon_health_cache', JSON.stringify({
      ...cachedData.value,
      lastUpdate: Date.now()
    }))
  } catch (e) {
    console.warn('[HealthCache] 保存缓存失败:', e)
  }
}

// 添加心率数据点
const addHeartRateData = (hr, hph) => {
  // 更新心率数值（如果有）
  if (hr && hr > 0) {
    cachedData.value.heartRate = hr
    
    // 记录历史数据（每分钟一个点）
    const now = Date.now()
    const lastHistory = cachedData.value.hrHistory[cachedData.value.hrHistory.length - 1]
    if (!lastHistory || now - lastHistory.timestamp > 60000) {
      cachedData.value.hrHistory.push({
        timestamp: now,
        value: hr
      })
      // 限制历史数据长度
      if (cachedData.value.hrHistory.length > MAX_HISTORY) {
        cachedData.value.hrHistory.shift()
      }
    }
  }
  
  // 更新波形数据（即使没有心率数值，只要有波形数据就更新）
  if (hph !== null && hph !== undefined) {
    cachedData.value.hrWave.push(hph)
    if (cachedData.value.hrWave.length > MAX_WAVE_POINTS) {
      cachedData.value.hrWave.shift()
    }
  }
  
  saveToStorage()
}

// 添加呼吸率数据点
const addBreathRateData = (br, bph) => {
  // 更新呼吸率数值（如果有）
  if (br && br > 0) {
    cachedData.value.breathRate = br
    
    // 记录历史数据（每分钟一个点）
    const now = Date.now()
    const lastHistory = cachedData.value.brHistory[cachedData.value.brHistory.length - 1]
    if (!lastHistory || now - lastHistory.timestamp > 60000) {
      cachedData.value.brHistory.push({
        timestamp: now,
        value: br
      })
      // 限制历史数据长度
      if (cachedData.value.brHistory.length > MAX_HISTORY) {
        cachedData.value.brHistory.shift()
      }
    }
  }
  
  // 更新波形数据（即使没有呼吸率数值，只要有波形数据就更新）
  if (bph !== null && bph !== undefined) {
    cachedData.value.brWave.push(bph)
    if (cachedData.value.brWave.length > MAX_WAVE_POINTS) {
      cachedData.value.brWave.shift()
    }
  }
  
  saveToStorage()
}

// 从系统状态更新数据
const updateFromSystemState = (systemState) => {
  const physiology = systemState?.perception?.physiology?.raw
  if (!physiology) return
  
  // 更新信号状态
  if (physiology.signal_state) {
    cachedData.value.signalState = physiology.signal_state
  }
  
  // 更新心率
  addHeartRateData(physiology.hr, physiology.hph)
  
  // 更新呼吸率
  addBreathRateData(physiology.br, physiology.bph)
  
  cachedData.value.isInitialized = true
}

// 初始化
const initCache = () => {
  if (!cachedData.value.isInitialized) {
    loadFromStorage()
    cachedData.value.isInitialized = true
  }
}

// 清除缓存
const clearCache = () => {
  cachedData.value.hrWave = Array(MAX_WAVE_POINTS).fill(0)
  cachedData.value.brWave = Array(MAX_WAVE_POINTS).fill(0)
  cachedData.value.hrHistory = []
  cachedData.value.brHistory = []
  cachedData.value.heartRate = 72
  cachedData.value.breathRate = 16
  cachedData.value.signalState = 'INIT'
  cachedData.value.lastUpdate = Date.now()
  localStorage.removeItem('akon_health_cache')
}

initCache()

export const useHealthCache = () => {
  return {
    data: readonly(cachedData),
    addHeartRateData,
    addBreathRateData,
    updateFromSystemState,
    clearCache
  }
}

export default {
  data: readonly(cachedData),
  init: initCache,
  update: updateFromSystemState,
  addHR: addHeartRateData,
  addBR: addBreathRateData,
  clear: clearCache
}
