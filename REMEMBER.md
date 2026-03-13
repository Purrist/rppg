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
| 平板摄像头 | IP Webcam | perception_manager | 情绪/心率/环境/身体/眼部/综合状态 |
| 投影摄像头 | USB | screen_processor | 脚部位置(x,y)/检测状态 |

---

## 三、UI规范

### 平板端（16:10）
- **锁定比例**：2560×1600，无滚动无缩放无边框
- **页面分类**：
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
| 暂停黄 | #FFD111 |

---

## 四、游戏状态流转

```
IDLE(待机) → READY(预备) → PLAYING(游戏中) → SETTLING(结算)
     ↑                                              │
     └──────────── 退出游戏 ────────────────────────┘
```

**关键**：结算5秒后 → READY（不是IDLE！）

| 按钮 | 功能 |
|------|------|
| 退出游戏 | → IDLE |
| 结束游戏 | → SETTLING → READY |
| 重新开始 | → READY |

---

## 五、绿点要求 ⭐

- 丝滑流畅，必须跟脚
- 不能抖动、卡顿、破裂、消失
- 准确识别人，不能误识别

**当前参数**：
- detection_confidence: 0.55
- tracking_confidence: 0.55
- visibility_threshold: 0.4
- smooth_alpha: 0.5

---

## 六、安全词

| 禁止 | 替换 |
|------|------|
| 监控 | 状态感知 |
| 老人 | 受众 |
| 医疗 | 健康 |
| 监视 | 观察 |

---

## 七、修改原则

1. **没让我重写就只修改**，不重写整个文件
2. **联动修改**：状态相关代码需同时检查前后端
3. **更新文档**：改代码→DEVELOP.md，确认无误→ARCHITECTURE.md

---

## 八、文件结构

```
download/
├── backend/
│   ├── perception/           # 感知模块
│   │   ├── __init__.py
│   │   ├── perception_manager.py
│   │   ├── emotion_detector.py
│   │   ├── heart_rate_detector.py
│   │   ├── environment_detector.py
│   │   ├── body_state_detector.py
│   │   ├── eye_tracker.py
│   │   └── utils.py
│   ├── app.py                # 主程序 + Agent循环
│   ├── akon_agent.py         # Agent核心
│   ├── akon_tools.py         # 行动执行器
│   ├── state_manager.py      # 世界模型
│   ├── games.py              # 游戏逻辑
│   ├── screen_processor.py   # 投影摄像头处理
│   ├── rppg_processor.py     # 心率检测
│   ├── tablet_processor.py   # 平板处理
│   └── camera_calibrate.py   # 摄像头校准
│
├── frontend/
│   ├── pages/
│   │   ├── index.vue         # 首页
│   │   ├── health.vue        # 健康
│   │   ├── entertainment.vue # 娱乐
│   │   ├── learning.vue      # 益智
│   │   ├── training.vue      # 训练
│   │   ├── projection.vue    # 投影
│   │   ├── developer.vue     # 开发后台
│   │   └── settings.vue      # 设置
│   └── app.vue               # 根组件
│
├── ARCHITECTURE.md           # 系统架构
├── DEVELOP.md                # 开发文档
├── INSTRUCTION.md            # 毕设规划
├── REMEMBER.md               # 本文件
└── ENV.md                    # 环境配置
```

---

*最后更新：2024-03-11*
