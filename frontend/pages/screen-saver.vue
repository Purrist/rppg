<template>
  <div class="screen-saver" @click="handleScreenSaverClick">
    <div class="face" :style="faceStyle">
      <div class="eyes-wrapper">
        <div class="eye left">
          <div class="lower"><div class="lid"></div></div>
          <div class="upper"><div class="lid"></div></div>
        </div>
        <div class="eye right">
          <div class="lower"><div class="lid"></div></div>
          <div class="upper"><div class="lid"></div></div>
        </div>
      </div>
      <div class="mouth"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { subscribe } from '../core/systemStore.js'
import { useRouter } from 'vue-router'

const router = useRouter()

const states = {
  neutral: {
    face: { rotationX:0, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:0,position:0}, upper:{rotation:0,position:0} },
    right: { lower:{rotation:0,position:0}, upper:{rotation:0,position:0} },
    mouth: { width:'10vmin', height:'4vmin', radius:'999px', rotation:'0deg' }
  },
  happy: {
    face: { rotationX:0, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:5,position:30}, upper:{rotation:0,position:0} },
    right: { lower:{rotation:-5,position:30}, upper:{rotation:0,position:0} },
    mouth: { width:'18vmin', height:'6vmin', radius:'40vmin 40vmin 999px 999px', rotation:'0deg' }
  },
  sad: {
    face: { rotationX:0, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:0,position:0}, upper:{rotation:-20,position:40} },
    right: { lower:{rotation:0,position:0}, upper:{rotation:20,position:40} },
    mouth: { width:'16vmin', height:'6vmin', radius:'999px 999px 40vmin 40vmin', rotation:'0deg' }
  },
  close: {
    face: { rotationX:-20, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:0,position:45}, upper:{rotation:0,position:45} },
    right: { lower:{rotation:0,position:45}, upper:{rotation:0,position:45} },
    mouth: { width:'8vmin', height:'3vmin', radius:'999px', rotation:'0deg' }
  },
  angry: {
    face: { rotationX:-10, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:0,position:0}, upper:{rotation:20,position:40} },
    right: { lower:{rotation:0,position:0}, upper:{rotation:-20,position:40} },
    mouth: { width:'16vmin', height:'5vmin', radius:'999px 999px 40vmin 40vmin', rotation:'0deg' }
  },
  confused: {
    face: { rotationX:0, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:0,position:0}, upper:{rotation:0,position:40} },
    right: { lower:{rotation:0,position:0}, upper:{rotation:0,position:0} },
    mouth: { width:'10vmin', height:'4vmin', radius:'999px', rotation:'25deg' }
  },
  suspicious: {
    face: { rotationX:0, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:-4,position:20}, upper:{rotation:4,position:20} },
    right: { lower:{rotation:4,position:20}, upper:{rotation:-4,position:20} },
    mouth: { width:'12vmin', height:'2vmin', radius:'999px', rotation:'-5deg' }
  },
  pain: {
    face: { rotationX:0, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:10,position:20}, upper:{rotation:-10,position:20} },
    right: { lower:{rotation:-10,position:20}, upper:{rotation:10,position:20} },
    mouth: { width:'8vmin', height:'10vmin', radius:'999px', rotation:'0deg' }
  },
  unamused: {
    face: { rotationX:0, rotationY:0, rotationZ:0 },
    left: { lower:{rotation:0,position:0}, upper:{rotation:0,position:40} },
    right: { lower:{rotation:0,position:0}, upper:{rotation:0,position:40} },
    mouth: { width:'14vmin', height:'2.5vmin', radius:'999px', rotation:'0deg' }
  },
  unsure: {
    face: { rotationX:0, rotationY:0, rotationZ:7 },
    left: { lower:{rotation:10,position:20}, upper:{rotation:-10,position:20} },
    right: { lower:{rotation:0,position:0}, upper:{rotation:0,position:0} },
    mouth: { width:'10vmin', height:'3.5vmin', radius:'999px', rotation:'20deg' }
  }
}

const emotionList = Object.keys(states).filter(e => e !== 'sad' && e !== 'angry')
const currentState = ref('happy')
const previousStates = ref(['happy'])
let emotionTimer = null
let unsubscribe = null
let isPageLoaded = false

const faceStyle = computed(() => {
  const state = states[currentState.value]
  if (!state) return {}
  return {
    '--left-lower-rotation': `${state.left.lower.rotation}deg`,
    '--left-lower-position': `${state.left.lower.position}%`,
    '--left-upper-rotation': `${state.left.upper.rotation}deg`,
    '--left-upper-position': `${state.left.upper.position}%`,
    '--right-lower-rotation': `${state.right.lower.rotation}deg`,
    '--right-lower-position': `${state.right.lower.position}%`,
    '--right-upper-rotation': `${state.right.upper.rotation}deg`,
    '--right-upper-position': `${state.right.upper.position}%`,
    '--face-rotation-x': `${state.face.rotationX}deg`,
    '--face-rotation-y': `${state.face.rotationY}deg`,
    '--face-rotation-z': `${state.face.rotationZ}deg`,
    '--mouth-width': state.mouth.width,
    '--mouth-height': state.mouth.height,
    '--mouth-radius': state.mouth.radius,
    '--mouth-rotation': state.mouth.rotation
  }
})

function setEmotion(emotion) {
  if (states[emotion] !== undefined) {
    currentState.value = emotion
  }
}

function nextEmotion() {
  let ind = Math.floor(Math.random() * emotionList.length)
  if (previousStates.value.indexOf(ind) !== -1) return nextEmotion()
  previousStates.value.push(ind)
  previousStates.value = previousStates.value.slice(-4)
  return emotionList[ind]
}

function exitScreenSaver() {
  window.dispatchEvent(new CustomEvent('exit-screen-saver'))
  router.push('/')
}

function handleScreenSaverClick() {
  if (isPageLoaded) {
    exitScreenSaver()
  }
}

onMounted(() => {
  setEmotion('happy')
  
  emotionTimer = setInterval(() => {
    setEmotion(nextEmotion())
  }, 10000)

  unsubscribe = subscribe((state) => {
    const distance = state.perception?.physiology?.raw?.distance
    const faceDetected = state.perception?.face?.au?.face_detected
    
    if (isPageLoaded && distance < 50 && faceDetected) {
      exitScreenSaver()
    }
  })

  setTimeout(() => {
    isPageLoaded = true
  }, 500)
})

onUnmounted(() => {
  if (emotionTimer) clearInterval(emotionTimer)
  if (unsubscribe) unsubscribe()
})
</script>

<style>
.screen-saver {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: #000;
  overflow: hidden;
  perspective: 25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  cursor: pointer;
}

:root {
  --eye-size: 34vmin;
  --eye-gap: 34vmin;
}

.face {
  --left-lower-rotation: 0deg;
  --left-lower-position: 0%;
  --left-upper-rotation: 0deg;
  --left-upper-position: 0%;
  --right-lower-rotation: 0deg;
  --right-lower-position: 0%;
  --right-upper-rotation: 0deg;
  --right-upper-position: 0%;
  --face-rotation-x: 0deg;
  --face-rotation-y: 0deg;
  --face-rotation-z: 0deg;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5vmin;
  transform: translateZ(8vmin) rotateX(var(--face-rotation-x)) rotateY(var(--face-rotation-y)) rotateZ(var(--face-rotation-z));
  transition: .75s cubic-bezier(.25, .5, .5, 1);
}

.eyes-wrapper {
  display: grid;
  grid-template-columns: var(--eye-size) var(--eye-gap) var(--eye-size);
  grid-template-rows: var(--eye-size);
  grid-template-areas: "left . right";
  filter: blur(1vmin) contrast(8);
  mix-blend-mode: lighten;
}

.face .eye {
  position: relative;
  background: white;
  border-radius: 100%;
  overflow: hidden;
  box-shadow: 0 0 0 2vmin black;
}

.face .eye,
.face .eye * {
  transition: .5s cubic-bezier(0.75, 0.25, 0.25, 0.75);
}

.face .eye > div {
  --rotation: 0deg;
  --position: 0%;
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  transform: rotate(var(--rotation));
}

.face .eye > div .lid {
  position: absolute;
  width: 100%;
  height: 100%;
  background: black;
}

.face .eye > div.lower .lid {
  top: calc(100% - var(--position));
}

.face .eye > div.upper .lid {
  bottom: calc(100% - var(--position));
}

.face .eye.left {
  grid-area: left;
}

.face .eye.left .lower {
  --rotation: var(--left-lower-rotation);
  --position: var(--left-lower-position);
}

.face .eye.left .upper {
  --rotation: var(--left-upper-rotation);
  --position: var(--left-upper-position);
}

.face .eye.right {
  grid-area: right;
}

.face .eye.right .lower {
  --rotation: var(--right-lower-rotation);
  --position: var(--right-lower-position);
}

.face .eye.right .upper {
  --rotation: var(--right-upper-rotation);
  --position: var(--right-upper-position);
}

.mouth {
  width: var(--mouth-width, 10vmin);
  height: var(--mouth-height, 4vmin);
  background: white;
  border-radius: var(--mouth-radius, 999px);
  transform: rotate(var(--mouth-rotation, 0deg));
  transition: .5s cubic-bezier(0.75, 0.25, 0.25, 0.75);
}
</style>
