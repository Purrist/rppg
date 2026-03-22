# DEVELOP.md - 开发日志

## v2.2 - 2024-03-19

### 重要修复

#### 1. developer.vue 人检测数据显示
- **修复**: 确保正确显示perception_manager的真实数据
- **改进**: 200ms更新频率，显示三维指标（身体负荷、认知负荷、参与意愿）
- **状态**: 显示person_detected、face_count、body_detected等真实数据

#### 2. 处理速度训练游戏
- **修复**: 正确区分游戏类型（processing_speed vs whack_a_mole）
- **实现**: 基于文献的经典认知训练游戏
  - Go/No-Go模块：反应控制训练
  - 选择反应模块：决策速度训练
  - 序列反应模块：序列学习训练

#### 3. 难度分级系统
- **实现**: 8级难度，基于文献参数
- **动态调整**: 每5个试次评估，正确率<60%降难度，>90%且反应快升难度

### 文献依据

#### ACTIVE研究 (Ball et al., 2002)
- 样本: N=2,832，年龄65-94岁
- 处理速度训练效果: +87%即时效果
- 难度调整: 正确率60-90%为最佳训练区间

#### Go/No-Go (Nielson et al., 2002)
- Go比例: 50-80%为最佳训练范围
- 测量指标: Go反应时、No-Go抑制率

#### 选择反应 (Hick, 1952; Jensen, 2006)
- Hick定律: RT = a + b × log₂(n+1)
- CRT与智力相关: r=0.45

#### 序列反应 (Nissen & Bullemer, 1987)
- SRTT经典范式
- 序列长度: 3-8步

### 文件清单

#### 后端
- `games/processing_speed_game.py` - 处理速度训练游戏（基于文献）
- `games/__init__.py` - 游戏注册
- `perception/perception_manager.py` - 感知管理器（三维指标）

#### 前端
- `pages/developer.vue` - 开发者页面（显示真实数据）
- `pages/projection.vue` - 投影页面（支持两种游戏）

---

## v2.1 - 2024-03-19

### 问题修复

#### 1. developer.vue 人检测数据显示问题
- **问题**: 显示的数据是假的/不动的
- **原因**: perception_manager需要视频流才能更新数据
- **修复**: 
  - 添加视频流状态检测
  - 显示真实的perception_manager数据
  - 添加"无人检测"状态提示

#### 2. 处理速度训练显示打地鼠问题
- **问题**: 点击处理速度训练显示的是打地鼠界面
- **原因**: 前端没有正确区分游戏类型
- **修复**:
  - 修复training.vue游戏类型判断
  - 修复projection.vue游戏类型判断
  - 确保后端正确传递游戏类型

### 架构说明

#### 核心交互逻辑
```
地面交互核心：站在区域内3秒 = 选中/确认
- READY状态：站在中心圆3秒开始游戏
- PLAYING状态：站在目标区域3秒确认选择
```

#### 人检测逻辑
```
外接摄像头：检测全身（骨骼、运动、姿态）
平板摄像头：检测人脸、情绪
任一检测到人 = person_detected = true
```

#### 状态评估体系（三维指标）
```
1. 身体负荷 (Physical Load)
   - 心率因子 (参考: Karvonen公式)
   - 运动强度
   - 姿态稳定性
   - 疲劳迹象

2. 认知负荷 (Cognitive Load)
   - 反应时间
   - 错误率
   - 犹豫次数
   - 注意力稳定性

3. 参与意愿 (Engagement)
   - 正面情绪
   - 主动性
   - 坚持性
```

#### 难度分级（基于文献）
```
Go/No-Go难度分级（参考: Ball et al. 2002, Nielson et al. 2002）:
| 等级 | Go比例 | 呈现时间 | 停留时间 | 区域数 |
|------|--------|----------|----------|--------|
| 1    | 90%    | 8秒      | 3秒      | 1      |
| 2    | 80%    | 7秒      | 3秒      | 1      |
| 3    | 70%    | 6秒      | 2.5秒    | 2      |
| 4    | 60%    | 5秒      | 2.5秒    | 2      |
| 5    | 50%    | 4.5秒    | 2秒      | 3      |
| 6    | 50%    | 4秒      | 2秒      | 3      |
| 7    | 40%    | 3.5秒    | 1.5秒    | 4      |
| 8    | 40%    | 3秒      | 1.5秒    | 4      |
```

### 文件清单

#### 后端
- `games/processing_speed_game.py` - 处理速度训练游戏逻辑
- `games/__init__.py` - 游戏注册
- `perception/perception_manager.py` - 感知管理器（三维指标）

#### 前端
- `pages/developer.vue` - 开发者页面（显示真实数据）
- `pages/learning.vue` - 游戏列表入口
- `pages/training.vue` - 通用游戏页面
- `pages/projection.vue` - 通用投影页面

---

## v2.0 - 2024-03-18

### 初始架构
- 游戏基类 (games_base.py)
- 游戏管理器 (games_manager.py)
- 感知管理器 (perception_manager.py)
- 打地鼠游戏 (game_whack_a_mole.py)
