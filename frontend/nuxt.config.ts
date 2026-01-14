export default defineNuxtConfig({
  devServer: {
    host: '0.0.0.0', // 监听所有网卡
    port: 3000
  },
  ssr: false // 纯客户端渲染，方便操作摄像头相关逻辑
})