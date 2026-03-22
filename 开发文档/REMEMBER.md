# REMEMBER.md - 必读文档

> **每次对话前必读！**

---

## 一、项目核心

**毕设题目**：结合健康监测与认知训练的老年陪伴机器人交互体验设计研究

**核心目标**：开发 EAOS（具身智能操作系统）原型

**硬件组成**：
- 安卓平板（16:10, 2560×1600）+ 前置摄像头
- 投影仪 + 外置USB摄像头
- 电脑运行后端

**技术栈**：
- 后端：Python + Flask + MediaPipe + Ollama
- 前端：Nuxt.js + Vue 3 + Socket.IO

---

## 二、两个摄像头

| 摄像头 | 来源 | 处理模块 | 输出 |
|--------|------|----------|------|
| 平板摄像头 | IP Webcam | perception_manager | 情绪/心率/环境/身体/眼部 |
| 投影摄像头 | USB | perception_screen_processor | 脚部位置(x,y) |

---

## 三、UI规范

### 平板端（16:10）
- 锁定比例：2560×1600，无滚动无缩放无边框
- 有侧边栏：index/health/learning/training/settings
- 全屏沉浸：projection/developer

### 投影端（16:9）
- 1920×1080，无侧边栏无悬浮球

### 色彩
| 用途 | 颜色 |
|------|------|
| 主题色 | #FF7222 |
| 安全绿 | #33B555 |
| 警戒红 | #FB4422 |

---

## 四、游戏状态流转（2024-03-19 更新）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌──────────┐    点击游戏     ┌──────────┐    站入圆圈3秒    ┌──────────┐ │
│   │  待机    │ ──────────────▶ │  预备    │ ────────────────▶ │  游戏中  │ │
│   │  IDLE    │                 │  READY   │                   │ PLAYING  │ │
│   └──────────┘                 └──────────┘                   └──────────┘ │
│        ▲                            ▲ ▲                            │       │
│        │                            │ │                            │       │
│        │                            │ │ 5秒后自动返回               │       │
│        │                            │ └────────────────────────────┘       │
│        │                            │                              │ 时间结束│
│        │                            │                              ▼       │
│        │                            │                        ┌──────────┐ │
│        │                            └────────────────────────│  结算    │ │
│        │                                     再来一次         │ SETTLING │ │
│        └─────────────────────────────────────────────────────└──────────┘ │
│                          点结束游戏/返回列表                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 关键规则

1. **游戏结束自动返回READY**：时间结束 → SETTLING → 5秒后 → READY
2. **点结束游戏直接返回游戏列表**：结束游戏 → IDLE → 前端跳转到learning.vue
3. **点重新开始返回预备状态**：重新开始 → READY

### 按钮行为

| 按钮 | 所在状态 | 目标状态 | 说明 |
|------|----------|----------|------|
| 退出游戏 | READY | IDLE | 返回游戏列表 |
| 结束游戏 | PLAYING | IDLE | 返回游戏列表 |
| 重新开始 | PLAYING/PAUSED/SETTLING | READY | 回到预备状态 |
| 再来一次 | SETTLING | READY | 重新开始 |
| 返回列表 | SETTLING | IDLE | 返回游戏列表 |

---

## 五、文件结构

```
download/
├── backend/
│   ├── core/                          # 核心模块
│   │   ├── __init__.py
│   │   ├── core_agent.py              # Agent核心
│   │   ├── core_state_manager.py      # 世界模型
│   │   └── core_tools.py              # 行动执行器
│   │
│   ├── games/                         # 游戏系统（可扩展）
│   │   ├── __init__.py
│   │   ├── games_base.py              # 游戏基类
│   │   ├── games_manager.py           # 游戏管理器
│   │   ├── game_whack_a_mole.py       # 打地鼠游戏
│   │   └── processing_speed_game.py   # 处理速度训练
│   │
│   ├── perception/                    # 感知模块
│   │   ├── __init__.py
│   │   ├── perception_manager.py      # 感知管理器
│   │   ├── perception_screen_processor.py  # 投影摄像头
│   │   └── utils.py                   # 工具函数
│   │
│   └── app.py                         # 主程序入口
│
├── frontend/
│   ├── components/                    # 组件
│   │   ├── GameFrame.vue              # 通用游戏框架
│   │   └── WhackAMole.vue             # 打地鼠游戏
│   │
│   ├── pages/                         # 页面
│   │   ├── index.vue                  # 首页
│   │   ├── health.vue                 # 健康页
│   │   ├── entertainment.vue          # 娱乐页
│   │   ├── learning.vue               # 益智页
│   │   ├── training.vue               # 训练页
│   │   ├── projection.vue             # 投影页
│   │   ├── developer.vue              # 开发后台
│   │   └── settings.vue               # 设置页
│   │
│   └── app.vue                        # 根组件
│
├── ARCHITECTURE.md                    # 系统架构文档
├── DEVELOP.md                         # 开发文档
├── ENV.md                             # 环境配置
├── INSTRUCTION.md                     # 毕设规划
├── 处理速度训练.md                     # 处理速度训练设计文档
├── 理论.md                            # 理论基础文档
└── REMEMBER.md                        # 本文件
```

---

## 六、添加新游戏

### 后端
1. 在 `games/` 下创建 `game_xxx.py`
2. 继承 `GameBase`，实现抽象方法
3. 在 `games/__init__.py` 注册

```python
# games/game_xxx.py
from .games_base import GameBase, GameConfig

class XxxGame(GameBase):
    def _on_ready(self): pass
    def _on_start(self): pass
    def _on_update(self, data): pass
    def _on_action(self, action, data): pass

# games/__init__.py
GAME_REGISTRY = {
    "whack_a_mole": WhackAMoleGame,
    "processing_speed": ProcessingSpeedGame,
    "xxx": XxxGame,
}
```

### 前端
1. 在 `components/` 下创建 `XxxGame.vue`
2. 使用 `GameFrame` 组件

```vue
<template>
  <GameFrame ref="gameFrameRef" :game-config="gameConfig">
    <template #game-content="{ state, footPosition }">
      <!-- 游戏特定内容 -->
    </template>
  </GameFrame>
</template>
```

---

## 七、安全词

| 禁止 | 替换 |
|------|------|
| 监控 | 状态感知 |
| 老人 | 受众 |
| 医疗 | 健康 |

---

## 八、修改原则

1. **没让我重写就只修改**
2. **改代码→DEVELOP.md，确认无误→ARCHITECTURE.md**

---

## 九、已恢复的文件

- `/home/z/my-project/download/处理速度训练.md` - 处理速度训练设计文档（依据ACTIVE研究）
- `/home/z/my-project/download/理论.md` - 理论基础文档

---

*最后更新：2024-03-19*
