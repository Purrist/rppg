<template>
  <div class="app-viewport">
    <div class="tablet-frame">
      <aside class="side-nav">
        <div class="nav-links">
          <NuxtLink to="/" class="nav-item">🏠<br>首页</NuxtLink>
          <NuxtLink to="/health" class="nav-item">❤️<br>健康</NuxtLink>
          <NuxtLink to="/entertainment" class="nav-item">🎵<br>娱乐</NuxtLink>
          <NuxtLink to="/learning" class="nav-item">🧠<br>学习</NuxtLink>
        </div>
        
        <div class="user-zone" @click.stop="ui.menu = !ui.menu">
          <div class="avatar">👴</div>
          <div class="name">张爷爷</div>
          <div v-if="ui.menu" class="pop-menu">
            <div @click="$router.push('/developer')">🛠 开发者后台</div>
            <div @click="$router.push('/settings')">⚙️ 系统设置</div>
            <div class="logout">退出登录</div>
          </div>
        </div>
      </aside>

      <main class="main-content">
        <NuxtPage />
      </main>

      <div 
        class="akon-ball"
        :style="{ left: ball.x + 'px', top: ball.y + 'px' }"
        @mousedown="handleDragStart"
        @touchstart="handleDragStart"
      >
        Akon
      </div>

      <div v-if="ui.akon" class="akon-modal" @click="ui.akon = false">
        <div class="akon-panel" @click.stop>
          <h2>阿康助手</h2>
          <p>爷爷，该喝水了，或者我们要开始一组色词训练吗？</p>
          <button @click="ui.akon = false">知道啦</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const ui = reactive({ menu: false, akon: false })
const ball = reactive({ x: 1000, y: 700 })
let dragging = false

const handleDragStart = (e) => {
  dragging = false
  const startX = e.touches ? e.touches[0].clientX : e.clientX
  const startY = e.touches ? e.touches[0].clientY : e.clientY
  const initX = ball.x
  const initY = ball.y

  const onMove = (ev) => {
    dragging = true
    const curX = ev.touches ? ev.touches[0].clientX : ev.clientX
    const curY = ev.touches ? ev.touches[0].clientY : ev.clientY
    ball.x = initX + (curX - startX)
    ball.y = initY + (curY - startY)
  }

  const onEnd = () => {
    window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onEnd)
    window.removeEventListener('touchmove', onMove); window.removeEventListener('touchend', onEnd)
    if (!dragging) ui.akon = true // 点击而非拖拽时打开面板
  }
  window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onEnd)
  window.addEventListener('touchmove', onMove); window.addEventListener('touchend', onEnd)
}
</script>

<style>
/* 基础锁死：禁止一切滚动和白边 */
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { 
  width: 100vw; height: 100vh; overflow: hidden; 
  background: #000; /* 背景黑，突出 16:10 区域 */
}

.app-viewport { 
  width: 100vw; height: 100vh; 
  display: flex; justify-content: center; align-items: center; 
}

/* 16:10 容器 */
.tablet-frame {
  height: 100vh; aspect-ratio: 16/10;
  background: #FFFFFF; display: flex; position: relative; overflow: hidden;
}

/* 侧边栏：大字号 */
.side-nav {
  width: 140px; background: #F8F9FA; display: flex; flex-direction: column;
  padding: 40px 0; border-right: 1px solid #EEE;
}
.nav-links { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 30px; }
.nav-item { 
  text-decoration: none; color: #333; font-size: 22px; font-weight: bold; 
  text-align: center; width: 100px; padding: 15px 0; border-radius: 20px;
}
.router-link-active { background: #FF7222; color: #FFF; }

.user-zone { text-align: center; position: relative; cursor: pointer; }
.avatar { font-size: 50px; }
.name { font-size: 20px; font-weight: bold; margin-top: 5px; }

/* 菜单弹出 */
.pop-menu {
  position: absolute; left: 150px; bottom: 0; width: 200px; 
  background: white; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); z-index: 100;
}
.pop-menu div { padding: 20px; font-size: 20px; border-bottom: 1px solid #F5F5F5; text-align: left; }

/* 主内容：静默滚动 */
.main-content { 
  flex: 1; height: 100%; overflow-y: auto; 
  padding: 40px; scrollbar-width: none; 
}
.main-content::-webkit-scrollbar { display: none; }

/* 悬浮球 */
.akon-ball {
  position: fixed; width: 90px; height: 90px; background: #FF7222; 
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  color: #FFF; font-weight: bold; cursor: grab; z-index: 500;
  box-shadow: 0 8px 20px rgba(255,114,34,0.4);
}

/* 阿康面板 */
.akon-modal { position: absolute; inset: 0; background: rgba(0,0,0,0.4); z-index: 600; display: flex; align-items: flex-end; }
.akon-panel { 
  width: 100%; background: #FFF; border-radius: 30px 30px 0 0; 
  padding: 50px; animation: slideUp 0.3s; 
}
@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
.akon-panel h2 { font-size: 32px; margin-bottom: 20px; }
.akon-panel p { font-size: 24px; color: #666; }
</style>