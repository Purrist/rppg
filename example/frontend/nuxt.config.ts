export default defineNuxtConfig({
  css: [],
  devtools: { enabled: false },
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