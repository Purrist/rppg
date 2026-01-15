<template>
  <div>
    <nav class="navbar">
      <div class="nav-brand">认知训练伴随监测系统</div>
      <div class="nav-links">
        <NuxtLink to="/" class="nav-link">🏠 首页</NuxtLink>
        <NuxtLink to="/tablet" class="nav-link">📱 平板控制</NuxtLink>
        <NuxtLink to="/training" class="nav-link">🎮 投影训练</NuxtLink>
      </div>
    </nav>
    <NuxtPage />
  </div>
</template>

<style scoped>
.navbar {
  background: #161b22;
  border-bottom: 1px solid #30363d;
  padding: 12px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.nav-brand {
  font-size: 16px;
  font-weight: 600;
  color: #e1e1e1;
}

.nav-links {
  display: flex;
  gap: 16px;
}

.nav-link {
  color: #8b949e;
  text-decoration: none;
  font-size: 14px;
  padding: 6px 12px;
  border-radius: 4px;
  transition: all 0.2s;
}

.nav-link:hover {
  color: #e1e1e1;
  background: #21262d;
}

.nav-link.active {
  color: #58a6ff;
  background: #0d1117;
  border: 1px solid #30363d;
}
</style>
