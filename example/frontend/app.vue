<template>
  <div class="app-root">
    <div class="tablet">
      <NuxtPage />
    </div>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #__nuxt {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #f2f4f7;
}

.app-root {
  width: 100vw;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 16:10，铺满高度，左右留白 */
.tablet {
  height: 100vh;
  aspect-ratio: 16 / 10;
  background: #ffffff;
}
</style>
