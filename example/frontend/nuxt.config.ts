export default defineNuxtConfig({
  css: [],
  devtools: { enabled: false },
  app: {
    head: {
      title: 'AI Vision Monitor',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no' }
      ]
    }
  },
  devServer: {
    host: '0.0.0.0', // 监听所有网卡，允许局域网访问
    port: 3000       // 确认端口号，通常默认是 3000
  },
  // 针对开发环境的 HMR 设置
  vite: {
    server: {
      hmr: {
        overlay: false
      }
    }
  }
})