# 实时数据文件结构说明

## 概述

本目录包含两个实时更新的 JSON 文件：
- `emotion.json` - 情绪分析数据（由 emotion.py 生成）
- `health.json` - 生理健康数据（由 hlkk.py 生成）

---

## emotion.json - 情绪分析数据结构

### 文件路径
`frontend/core/emotion.json`

### 更新频率
约 30fps（每秒更新 30 次）

### 数据结构

```json
{
  "timestamp": "20260513_003151",
  "elapsed": 0.0,
  "au": {
    "emotion": "neutral",
    "confidence": 0.0,
    "scores": {
      "neutral": 0,
      "positive": 0,
      "negative": 0
    },
    "pose": "front",
    "pitch": -5.2,
    "yaw": -16.0,
    "au_features": {}
  },
  "fer": {
    "label": "neutral",
    "conf": 0.0,
    "probs_3": {
      "neutral": 0,
      "positive": 0,
      "negative": 0
    }
  },
  "fusion": {
    "emotion": "no_face",
    "confidence": 0.0,
    "scores": {
      "neutral": 0,
      "positive": 0,
      "negative": 0
    }
  }
}
```

### 字段说明

#### 顶层字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | string | 时间戳，格式为 `YYYYMMDD_HHMMSS` |
| `elapsed` | float | 程序启动后经过的秒数 |

#### au 字段（动作单元分析）
| 字段 | 类型 | 说明 |
|------|------|------|
| `emotion` | string | 基于面部动作单元的情绪判断，可能值：`neutral`（中性）、`positive`（积极）、`negative`（消极）、`no_face`（无脸）、`out_of_range`（超出范围）、`speaking`（说话中）、`uncalibrated`（未校准） |
| `confidence` | float | 情绪判断的置信度，范围 [0, 1] |
| `scores` | object | 三种情绪的得分，键：`neutral`、`positive`、`negative`，值范围 [0, 1] |
| `pose` | string | 面部朝向，可能值：`front`（正脸）、`up`（抬头）、`down`（低头）、`side_left`（左侧脸）、`side_right`（右侧脸） |
| `pitch` | float | 俯仰角（度数），负值表示低头，正值表示抬头 |
| `yaw` | float | 偏航角（度数），负值表示向左，正值表示向右 |
| `au_features` | object | 动作单元特征值，键为 AU 名称（如 `AU12`、`AU6`），值为该 AU 的激活强度 |

#### fer 字段（面部表情识别）
| 字段 | 类型 | 说明 |
|------|------|------|
| `label` | string | 表情标签，可能值：`neutral`、`positive`、`negative` |
| `conf` | float | 表情识别的置信度，范围 [0, 1] |
| `probs_3` | object | 三类情绪的概率分布，键：`neutral`、`positive`、`negative`，值范围 [0, 1] |

#### fusion 字段（融合结果）
| 字段 | 类型 | 说明 |
|------|------|------|
| `emotion` | string | 融合后的最终情绪判断，值同 au.emotion |
| `confidence` | float | 融合结果的置信度，范围 [0, 1] |
| `scores` | object | 融合后的三种情绪得分，值同 au.scores |

---

## health.json - 生理健康数据结构

### 文件路径
`frontend/core/health.json`

### 更新频率
由 Web 客户端请求频率决定，通常约 1-10fps

### 数据结构

```json
{
  "time": 1778604125.574545,
  "hr": 99.0,
  "br": 15.0,
  "hph": 0.5109634399414062,
  "bph": 0.11682373285293579,
  "is_human": 1,
  "distance": 34.439998626708984,
  "distance_valid": 1,
  "signal_state": "NORMAL",
  "hr_valid": true,
  "br_valid": true,
  "phase_valid": true,
  "hrr": 42.0,
  "hrr_label": "中强度",
  "slope": 3.45,
  "slope_label": "快速上升",
  "brv": 1.94,
  "brv_label": "规律",
  "brel": -9.1,
  "brel_label": "放松",
  "cr": 8.31,
  "cr_label": "偏高",
  "plv": 0.991,
  "plv_label": "深度放松"
}
```

### 字段说明

#### 基础数据字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `time` | float | Unix 时间戳（秒） |
| `hr` | float | 心率（Heart Rate），单位：次/分钟 |
| `br` | float | 呼吸率（Breath Rate），单位：次/分钟 |
| `hph` | float | 心率相位（Heart Phase），范围 [0, 2π) |
| `bph` | float | 呼吸相位（Breath Phase），范围 [0, 2π) |
| `is_human` | int | 是否检测到人体，`0`=否，`1`=是（此值不太准确） |
| `distance` | float | 传感器距离，单位：厘米 |
| `distance_valid` | int | 距离值是否有效，`0`=无效，`1`=有效 |
| `signal_state` | string | 信号状态，可能值：`INIT`（初始化）、`NORMAL`（正常）、`WEAK`（弱信号）等 |
| `hr_valid` | boolean | 心率数据是否有效 |
| `br_valid` | boolean | 呼吸率数据是否有效 |
| `phase_valid` | boolean | 相位数据是否有效 |

#### 心率相关分析字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `hrr` | float | 心率储备百分比（Heart Rate Reserve），范围 [0, 100] |
| `hrr_label` | string | 心率储备标签：`低强度`（<40）、`中强度`（40-60）、`高强度`（>60） |
| `slope` | float | 心率变化斜率 |
| `slope_label` | string | 心率变化标签：`快速下降`（< -0.5）、`平稳`（-0.5~0.5）、`缓慢上升`（0.5~2）、`快速上升`（>2） |

#### 呼吸相关分析字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `brv` | float | 呼吸变异性（Breath Rate Variability），变异系数（CV）|
| `brv_label` | string | 呼吸变异性标签：`规律`（<5）、`正常`（5~15）、`不规律`（>15） |
| `brel` | float | 呼吸提升度（Breath Elevation） |
| `brel_label` | string | 呼吸状态标签：描述当前呼吸的放松程度 |

#### 综合分析字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `cr` | float | 心-呼吸耦合比（Cardio-Respiratory Ratio） |
| `cr_label` | string | 耦合比标签：`偏低`（<3.5）、`正常`（3.5~5.5）、`偏高`（>5.5） |
| `plv` | float | 相位锁定值（Phase Locking Value），心-呼吸同步程度，范围 [0, 1] |
| `plv_label` | string | PLV 标签：`清醒焦虑`（<0.3）、`日常活动`（0.3~0.9）、`深度放松`（>0.9） |

---

## 注意事项

1. **文件覆盖**：两个 JSON 文件会被实时覆盖，请不要手动修改
2. **数据有效性**：使用数据前请检查 `*_valid` 字段，确保数据有效
3. **性能影响**：高频文件写入可能影响性能，仅在需要时访问
4. **原子性**：文件写入可能不是原子的，建议读取时处理异常
5. **初始化**：程序刚启动时可能没有有效数据，注意处理 `null` 和默认值

---

## 使用示例

### JavaScript/TypeScript

```javascript
// 读取 emotion.json
async function getEmotionData() {
  try {
    const response = await fetch('/core/emotion.json');
    const data = await response.json();
    return data;
  } catch (e) {
    console.error('读取情绪数据失败:', e);
    return null;
  }
}

// 读取 health.json
async function getHealthData() {
  try {
    const response = await fetch('/core/health.json');
    const data = await response.json();
    return data;
  } catch (e) {
    console.error('读取健康数据失败:', e);
    return null;
  }
}
```

### Python

```python
import json
import os

FRONTEND_CORE = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'core')

def get_emotion_data():
    try:
        with open(os.path.join(FRONTEND_CORE, 'emotion.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'读取情绪数据失败: {e}')
        return None

def get_health_data():
    try:
        with open(os.path.join(FRONTEND_CORE, 'health.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'读取健康数据失败: {e}')
        return None
```
