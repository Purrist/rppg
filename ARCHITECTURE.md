# ARCHITECTURE.md - 系统架构文档

> 本文档清晰描述整个系统的架构、页面流转逻辑、前后端通信、硬件联系，以及代码文件的方法参数解析。

---

## 一、系统概述

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│     "让AI成为老人的智能陪伴，让健康监测和认知训练变得自然、有趣"            │
│                                                                             │
│     硬件组成：                                                              │
│     • 安卓平板 (2560×1600, 16:10) - 前置摄像头用于状态感知                 │
│     • 投影仪 + 外置摄像头 - 地面投影交互                                    │
│     • 电脑 - 运行后端服务                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、硬件架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         电脑（系统主机）                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Python 后端                           │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │   │
│  │  │ tablet_     │ │ screen_     │ │  games.py   │        │   │
│  │  │ processor   │ │ processor   │ │ (游戏逻辑)   │        │   │
│  │  │ (平板处理)   │ │ (投影处理)   │ └─────────────┘        │   │
│  │  └─────────────┘ └─────────────┘                        │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │   │
│  │  │   app.py    │ │ akon_tools  │ │ akon_agent  │        │   │
│  │  │ (主程序)     │ │ (工具箱)     │ │ (AI助手)    │        │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘        │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 Nuxt.js + Vue.js 前端                    │   │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐              │   │
│  │  │ 平板端UI  │ │ 投影端UI  │ │ 开发者后台 │              │   │
│  │  │ (16:10)   │ │ (全屏)    │ │ (监控调试) │              │   │
│  │  └───────────┘ └───────────┘ └───────────┘              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌───────────┐       ┌───────────┐       ┌───────────┐
   │ 安卓平板  │       │  投影仪   │       │外置摄像头 │
   │(IP Webcam)│       │ (地面)    │       │ (USB)     │
   └───────────┘       └───────────┘       └───────────┘
```

---

## 三、状态流转 ⭐

### 3.1 四个状态

| 状态 | 平板 | 投影 | 触发条件 |
|------|------|------|----------|
| **IDLE（待机）** | 游戏列表 | 粒子效果 | 初始状态/退出游戏 |
| **READY（预备）** | "请在投影区域开始游戏" | 粒子+灰圈 | 点击游戏/结算结束 |
| **PLAYING（游戏中）** | 游戏信息+控制按钮 | 地鼠洞 | 站在圆圈内3秒 |
| **SETTLING（结算）** | "游戏结束"+成绩 | "游戏结束"+成绩 | 60秒结束/结束游戏 |

### 3.2 状态流转图

```
                    点击游戏
    ┌─────────┐ ───────────────→ ┌─────────┐
    │  待机   │                   │  预备   │
    │  IDLE   │ ←─────────────── │  READY  │
    └─────────┘   退出游戏        └─────────┘
         ↑              ▲              │
         │              │              │ 站在圆圈内3秒
         │              │              ↓
         │              │        ┌─────────┐
         │              │        │ 游戏中  │
         │              │        │PLAYING  │
         │              │        └─────────┘
         │              │              │
         │              │              │ 60秒结束/结束游戏
         │              │              ↓
         │              │        ┌─────────┐
         │              └────────│  结算   │
         │           5秒后回到预备│SETTLING │
         │                       └─────────┘
         │                             │
         │                             │ 5秒后
         │                             ↓
         │                       ┌─────────┐
         │                       │  预备   │
         └───────────────────────│  READY  │
              （只有退出游戏才回到IDLE）
```

### 3.3 按钮功能区分

| 按钮 | 所在状态 | 目标状态 | 说明 |
|------|----------|----------|------|
| 退出游戏 | READY | IDLE | 回到游戏列表 |
| 结束游戏 | PLAYING | SETTLING | 进入结算，5秒后→READY |
| 重新开始 | PLAYING/PAUSED | READY | 回到预备状态 |

---

## 四、前后端通信

### 4.1 Socket.IO 事件

| 事件名 | 方向 | 数据 | 说明 |
|--------|------|------|------|
| `game_control` | 前端→后端 | `{action, game}` | 游戏控制 |
| `game_update` | 后端→前端 | `{status, score, timer, ...}` | 游戏状态更新 |
| `system_state` | 后端→前端 | `{state: {...}}` | 系统状态 |
| `navigate_to` | 后端→前端 | `{page}` | 导航命令 |
| `game_hit` | 前端→后端 | `{hole, hit}` | 击中判定 |
| `get_state` | 前端→后端 | `{client, first_connect}` | 获取状态 |

### 4.2 game_control action

| action | 说明 | 状态变化 |
|--------|------|----------|
| `ready` | 进入预备状态 | → READY |
| `start` | 开始游戏 | READY → PLAYING |
| `pause` | 暂停/继续 | PLAYING ↔ PAUSED |
| `stop` | 结束游戏 | → IDLE |
| `restart` | 重新开始 | → READY（原子操作） |

### 4.3 HTTP API

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 获取脚部位置状态 |
| `/api/config` | GET/POST | 获取/保存配置 |
| `/api/system/state` | GET | 获取系统状态 |
| `/video_feed` | GET | 原始视频流 |
| `/corrected_feed` | GET | 校正后视频流 |

---

## 五、文件结构

```
rppg/
├── backend/
│   ├── app.py                 # 主程序入口
│   ├── games.py               # 游戏逻辑
│   ├── screen_processor.py    # 投影端处理器
│   ├── tablet_processor.py    # 平板端处理器
│   ├── akon_agent.py          # 阿康AI代理
│   ├── akon_tools.py          # 阿康工具箱
│   ├── state_manager.py       # 状态管理
│   ├── camera_calibrate.py    # 摄像头校准
│   ├── projection_config.json # 投影配置
│   ├── calibration_config.json# 校准配置
│   ├── training_history.json  # 训练历史
│   └── backend/memory/
│       ├── conversation_history.json
│       └── user_memory.json
│
├── frontend/
│   ├── app.vue                # 根组件
│   ├── nuxt.config.ts         # Nuxt配置
│   ├── package.json           # 依赖
│   └── pages/
│       ├── index.vue          # 首页
│       ├── health.vue         # 健康页
│       ├── entertainment.vue  # 娱乐页
│       ├── learning.vue       # 益智页
│       ├── training.vue       # 训练页
│       ├── projection.vue     # 投影页
│       ├── developer.vue      # 开发者后台
│       └── settings.vue       # 设置页
│
├── REMEMBER.md                # 必读文档
├── INSTRUCTION.md             # 毕设规划
├── DEVELOP.md                 # 开发文档
├── ARCHITECTURE.md            # 系统架构（本文件）
└── ENV.md                     # 环境配置
```

---

## 六、后端代码解析

### 6.1 app.py - 主程序入口

**全局状态**：
```python
system_state = {
    "mode": "normal",      # normal/game
    "current_page": "/",   # 当前页面
    "game": {
        "active": False,   # 游戏是否活跃
        "name": None,      # 游戏名称
        "status": "IDLE",  # 游戏状态
        "score": 0,        # 得分
        "timer": 60        # 剩余时间
    }
}
```

**核心函数**：

| 函数名 | 参数 | 说明 |
|--------|------|------|
| `handle_game_control(data)` | `{action, game}` | 处理游戏控制事件 |
| `handle_get_state(data)` | `{client, first_connect}` | 获取当前状态 |
| `handle_game_hit(data)` | `{hole, hit}` | 处理击中判定 |
| `handle_navigate(data)` | `{page, source}` | 处理导航请求 |
| `main_worker()` | None | 后台任务循环 |

**关键逻辑**：

```python
# restart action - 原子操作
elif action == 'restart':
    # 1. 设置状态为 IDLE（不发送）
    system_state["game"]["status"] = "IDLE"
    # 2. 调用 set_ready()，发送 READY
    whack_a_mole.set_ready()
    # 3. 不发送 system_state，避免触发导航
    return
```

---

### 6.2 games.py - 游戏逻辑

**WhackAMole类属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `status` | str | 游戏状态：IDLE/READY/PLAYING/PAUSED/SETTLING |
| `score` | int | 得分 |
| `timer` | int | 剩余时间（秒） |
| `current_mole` | int | 当前地鼠位置（0-2，-1表示无） |
| `mole_stay` | float | 地鼠停留时间（5秒） |
| `mole_interval` | float | 地鼠出现间隔（1.5秒） |
| `SETTLING_DURATION` | float | 结算时间（5秒） |

**核心方法**：

| 方法名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `set_ready()` | None | None | 设置准备状态，发送game_update |
| `start_game()` | None | None | 开始游戏 |
| `toggle_pause()` | None | None | 暂停/继续 |
| `stop()` | None | None | 停止游戏，发送game_update |
| `start_settling()` | None | None | 进入结算状态 |
| `handle_hit(hole_index, hit)` | 洞索引, 是否击中 | None | 处理击中判定 |
| `update(health_state)` | 健康状态 | None | 更新游戏状态（每50ms调用） |
| `_emit_state()` | None | None | 发送game_update事件 |

**update()方法流程**：

```python
def update(self, health_state=None):
    # 1. 结算状态处理
    if self.status == "SETTLING":
        elapsed = time.time() - self.settling_start_time
        if elapsed >= self.SETTLING_DURATION:
            self.set_ready()  # 5秒后回到预备状态
        return
    
    # 2. 游戏中状态处理
    if self.status == "PLAYING":
        # 更新计时器
        self.timer = max(0, int(60 - elapsed))
        
        # 时间结束 → 进入结算
        if self.timer <= 0:
            self.start_settling()
            return
        
        # 地鼠逻辑
        if self.current_mole == -1:
            # 出现新地鼠
            if now - self.last_mole_time > self.mole_interval:
                self.current_mole = random.randint(0, 2)
        else:
            # 地鼠逃走
            if now - self.mole_appear_time > self.mole_stay:
                self.score = max(0, self.score - 5)
                self.current_mole = -1
```

---

### 6.3 screen_processor.py - 投影端处理器

**ScreenProcessor类属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `cap` | cv2.VideoCapture | 摄像头对象 |
| `pose` | mp.solutions.pose.Pose | MediaPipe Pose实例 |
| `raw_frame` | np.ndarray | 原始帧 |
| `corrected_frame` | np.ndarray | 校正后帧 |
| `position_smoother` | PositionSmoother | 位置平滑器 |

**核心方法**：

| 方法名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `get_raw_jpeg()` | None | bytes | 获取原始JPEG图像 |
| `get_corrected_jpeg()` | None | bytes | 获取校正后JPEG图像 |
| `update_matrix()` | None | None | 更新透视变换矩阵 |
| `get_status()` | None | dict | 获取脚部位置状态 |

**_loop()方法流程**：

```python
def _loop(self):
    while self.running:
        # 1. 读取帧
        ret, frame = self.cap.read()
        
        # 2. 翻转（镜像）
        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)
        
        # 3. 骨骼检测
        results = self.pose.process(rgb)
        
        # 4. 提取脚部位置
        if results.pose_landmarks:
            left_ankle = lm[27]
            right_ankle = lm[28]
            if left_ankle.visibility > 0.4 and right_ankle.visibility > 0.4:
                # 计算中心点
                center = ((l_pt[0] + r_pt[0]) // 2, (l_pt[1] + r_pt[1]) // 2)
                # 透视变换
                dst_pt = cv2.perspectiveTransform(src_pt, self.matrix)
        
        # 5. 平滑处理
        smooth_x, smooth_y, smooth_detected = self.position_smoother.update(x, y, detected)
        
        # 6. 更新全局状态
        state["feet_x"] = smooth_x
        state["feet_y"] = smooth_y
        state["feet_detected"] = smooth_detected
```

**SmoothFilter类**：

```python
class SmoothFilter:
    def __init__(self, alpha=0.5, threshold=20):
        self.alpha = alpha          # 平滑系数
        self.threshold = threshold  # 阈值
    
    def update(self, new_value):
        diff = abs(new_value - self.value)
        # 大变化时快速响应，小变化时平滑
        alpha = 0.85 if diff > self.threshold else self.alpha
        self.value = alpha * new_value + (1 - alpha) * self.value
        return self.value
```

---

## 七、前端代码解析

### 7.1 app.vue - 根组件

**核心变量**：

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `backendConnected` | ref(boolean) | 后端连接状态 |
| `gameActive` | ref(boolean) | 游戏是否活跃 |
| `hasInitialized` | ref(boolean) | 是否已初始化 |
| `isRestarting` | ref(boolean) | 是否正在重新开始 |

**关键逻辑**：

```javascript
// 监听系统状态
socket.on('system_state', (data) => {
  if (data.state && data.state.game) {
    gameActive.value = data.state.game.active
    
    // READY状态重置重新开始标记
    if (data.state.game.status === 'READY') {
      isRestarting.value = false
    }
    
    // IDLE状态导航到首页（除非正在重新开始）
    if (data.state.game.status === 'IDLE' && 
        data.state.game.active === false && 
        !isRestarting.value) {
      router.push('/learning')
    }
  }
})
```

---

### 7.2 training.vue - 训练页

**核心变量**：

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `game` | ref(object) | 游戏状态对象 |
| `isExiting` | ref(boolean) | 是否正在退出 |
| `isRestarting` | ref(boolean) | 是否正在重新开始 |

**状态监听**：

```javascript
watch(() => game.value.status, (newStatus) => {
  // IDLE状态返回游戏列表（除非正在重新开始）
  if (newStatus === 'IDLE' && !isRestarting.value) {
    router.push('/learning')
  }
  
  // READY状态重置标记
  if (newStatus === 'READY') {
    isRestarting.value = false
  }
})
```

**按钮处理**：

```javascript
// 退出游戏（准备状态）
const exitGame = () => {
  socket.emit('game_control', { action: 'stop' })
  router.push('/learning')
}

// 结束游戏（游戏中）→ 进入结算
const endGame = () => {
  socket.emit('game_control', { action: 'stop' })
}

// 重新开始 → 回到预备
const restartGame = () => {
  isRestarting.value = true
  socket.emit('game_control', { action: 'restart' })
}
```

---

### 7.3 projection.vue - 投影页

**核心变量**：

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `gameState` | ref(string) | 游戏状态 |
| `game` | ref(object) | 游戏数据 |
| `footPosition` | reactive(object) | 脚部位置 |
| `readyProgress` | ref(number) | 准备进度 |
| `holeProgress` | ref(array) | 洞的进度 |

**状态对应显示**：

| gameState | 显示内容 |
|-----------|----------|
| IDLE | 粒子效果 |
| READY | 粒子 + 灰圈 + "请进入圆圈内" |
| PLAYING | 地鼠洞 + 游戏内容 |
| SETTLING | "游戏结束" + 成绩 |

**准备状态逻辑**：

```javascript
function updateReadyState() {
  const centerX = 320, centerY = 180, radius = 80
  const dx = footPosition.x - centerX
  const dy = footPosition.y - centerY
  const inZone = footPosition.detected && (dx*dx + dy*dy <= radius*radius)
  
  if (inZone) {
    if (readyStartTime.value === 0) {
      readyStartTime.value = Date.now()
    }
    readyProgress.value = ((Date.now() - readyStartTime.value) / 3000) * 100
    
    if (readyProgress.value >= 100) {
      socket.emit('game_control', { action: 'start' })
    }
  } else {
    readyStartTime.value = 0
    readyProgress.value = 0
  }
}
```

---

## 八、关键连接

### 8.1 状态同步链路

```
用户操作 → 前端发送事件 → 后端处理 → 发送game_update/system_state → 前端更新UI
```

### 8.2 游戏控制链路

```
training.vue                    app.py                     games.py
    │                              │                           │
    ├─ game_control {action} ───→ │                           │
    │                              ├─ 更新system_state ──────→│
    │                              │                           ├─ 更新游戏状态
    │                              │                           ├─ _emit_state()
    │  ←── game_update ────────────┼───────────────────────────┤
    │  ←── system_state ───────────┤                           │
    │                              │                           │
```

### 8.3 脚部检测链路

```
外置摄像头 → screen_processor.py → state全局变量 → HTTP API → projection.vue
                                                      │
                                                      └─→ 位置判断 → 游戏交互
```

---

## 九、大模型接入规划

### 9.1 当前方案

```
Ollama (本地LLM) + qwen2.5:3b
```

### 9.2 活系统架构

```
[感知模块] → [Qwen3.5 本地运行] → [工具集] → [记忆库]
                │
                ├─ 理解内容
                ├─ 思考决策
                └─ 调用工具
```

---

*最后更新：2024-03-08*
