/**
 * 高性能波形绘制器
 * 使用双缓冲 + 增量绘制
 */

// 存储 canvas 上下文和双缓冲
const canvasCache = new Map()

export class WaveformRenderer {
  constructor(canvas, options = {}) {
    this.canvas = canvas
    this.ctx = canvas.getContext('2d')
    this.options = {
      color: '#0D9488',
      backgroundColor: 'rgba(13, 148, 136, 0.15)',
      lineWidth: 2,
      smoothing: 0.4,
      ...options
    }
    
    // 双缓冲
    this.offscreenCanvas = document.createElement('canvas')
    this.offscreenCtx = this.offscreenCanvas.getContext('2d')
    
    // 上一帧的数据，用于比较是否需要重绘
    this.lastDataHash = ''
    this.lastWidth = 0
    this.lastHeight = 0
    
    // 动画帧 ID
    this.animationFrameId = null
    
    // 是否需要重绘
    this.needsRedraw = true
  }
  
  // 计算数据哈希，用于判断是否需要重绘
  static computeDataHash(data) {
    return data.join(',')
  }
  
  // 设置尺寸
  setSize(width, height) {
    if (this.lastWidth !== width || this.lastHeight !== height) {
      this.canvas.width = width
      this.canvas.height = height
      this.offscreenCanvas.width = width
      this.offscreenCanvas.height = height
      this.lastWidth = width
      this.lastHeight = height
      this.needsRedraw = true
    }
  }
  
  // 绘制波形（双缓冲）
  draw(data) {
    if (!this.canvas || !this.ctx) return
    
    const width = this.canvas.width
    const height = this.canvas.height
    
    if (width === 0 || height === 0) return
    
    const dataHash = WaveformRenderer.computeDataHash(data)
    
    // 数据没变，不需要重绘
    if (dataHash === this.lastDataHash && !this.needsRedraw) {
      return
    }
    
    this.lastDataHash = dataHash
    this.needsRedraw = false
    
    const ctx = this.offscreenCtx
    
    // 1. 清除背景
    ctx.clearRect(0, 0, width, height)
    
    // 2. 绘制背景
    ctx.fillStyle = this.options.backgroundColor
    ctx.fillRect(0, 0, width, height)
    
    // 3. 绘制网格
    this.drawGrid(ctx, width, height)
    
    // 4. 绘制波形线
    this.drawWaveLine(ctx, data, width, height)
    
    // 5. 把结果绘制到主 canvas
    this.ctx.drawImage(this.offscreenCanvas, 0, 0)
  }
  
  // 绘制网格
  drawGrid(ctx, width, height) {
    ctx.strokeStyle = 'rgba(200, 200, 200, 0.3)'
    ctx.lineWidth = 1
    
    // 水平网格
    const gridStep = height / 4
    for (let i = 1; i < 4; i++) {
      ctx.beginPath()
      ctx.moveTo(0, i * gridStep)
      ctx.lineTo(width, i * gridStep)
      ctx.stroke()
    }
    
    // 垂直网格
    const gridStepV = width / 5
    for (let i = 1; i < 5; i++) {
      ctx.beginPath()
      ctx.moveTo(i * gridStepV, 0)
      ctx.lineTo(i * gridStepV, height)
      ctx.stroke()
    }
  }
  
  // 绘制波形线（使用贝塞尔曲线平滑）
  drawWaveLine(ctx, data, width, height) {
    if (!data || data.length === 0) return
    
    const padding = 5
    const availableWidth = width - padding * 2
    const availableHeight = height - padding * 2
    
    // 计算归一化数据
    const normalizedData = this.normalizeData(data)
    
    ctx.strokeStyle = this.options.color
    ctx.lineWidth = this.options.lineWidth
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    
    ctx.beginPath()
    
    // 从第一个点开始
    let x = padding
    let y = padding + normalizedData[0] * availableHeight
    ctx.moveTo(x, y)
    
    // 使用贝塞尔曲线平滑连接
    for (let i = 1; i < normalizedData.length; i++) {
      const nextX = padding + (i / (normalizedData.length - 1)) * availableWidth
      const nextY = padding + normalizedData[i] * availableHeight
      
      // 控制点
      const cpX = (x + nextX) / 2
      
      ctx.quadraticCurveTo(cpX, (y + nextY) / 2, nextX, nextY)
      
      x = nextX
      y = nextY
    }
    
    ctx.stroke()
  }
  
  // 归一化数据到 0-1 范围
  normalizeData(data) {
    if (!data || data.length === 0) return []
    
    // 找到最大最小值
    let min = Infinity
    let max = -Infinity
    for (const val of data) {
      if (val < min) min = val
      if (val > max) max = val
    }
    
    // 如果所有值都相同，返回中间值
    if (max === min) {
      return data.map(() => 0.5)
    }
    
    const range = max - min
    
    // 归一化
    return data.map(val => (val - min) / range)
  }
  
  // 强制重绘
  forceRedraw() {
    this.needsRedraw = true
    this.lastDataHash = ''
  }
  
  // 销毁
  destroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId)
    }
  }
}

export default WaveformRenderer
