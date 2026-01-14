export default defineNuxtConfig({
  devServer: {
    host: '0.0.0.0', // 关键：允许外部访问
    port: 3000
  },
  ssr: false // 禁用 SSR 以适配客户端 API 调用
})