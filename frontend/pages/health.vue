<template>
  <div class="page-body">
    <!-- 顶部导航 -->
    <header class="header">
      <h1>健康中心</h1>
      <div class="tabs">
        <button @click="activeTab='cardio'" :class="{active:activeTab=='cardio'}">🫀 心肺</button>
        <button @click="activeTab='emotion'" :class="{active:activeTab=='emotion'}">🧠 情绪</button>
        <button @click="activeTab='sleep'" :class="{active:activeTab=='sleep'}">😴 睡眠</button>
      </div>
      <div class="action-buttons">
        <div class="action-btn call" @click="goToVideoCall">📞 视频通话</div>
        <div class="action-btn sos" @click="callNurseStation">🆘 紧急呼救</div>
      </div>
    </header>

    <!-- 心肺健康 -->
    <section v-show="activeTab=='cardio'" class="cardio-layout">
      <!-- 左侧面板 -->
      <div class="left-panel">
        <!-- 健康摘要 -->
        <div class="l-card summary-card">
          <h3>健康摘要</h3>
          <div class="metrics">
            <div class="metric">
              <div class="metric-value">{{ healthData.hr }}</div>
              <div class="metric-label">心率 (bpm)</div>
            </div>
            <div class="metric">
              <div class="metric-value">{{ healthData.br }}</div>
              <div class="metric-label">呼吸率 (/min)</div>
            </div>
          </div>
          <div class="status">
            <span class="status-dot" :class="signalStatus"></span>
            {{ signalStatusText }}
          </div>
        </div>

        <!-- 健康趋势 -->
        <div class="l-card">
          <h3>健康趋势</h3>
          <div class="period-tabs">
            <button @click="period='day'" :class="{active:period=='day'}">日</button>
            <button @click="period='week'" :class="{active:period=='week'}">周</button>
            <button @click="period='month'" :class="{active:period=='month'}">月</button>
          </div>
          <div class="trend-chart">
            <div class="chart-bars">
              <div 
                v-for="(item, index) in hrTrendData" 
                :key="index"
                class="chart-bar hr-bar"
                :style="{ height: (item / 100 * 100) + '%' }"
              >
                <div class="bar-value">{{ item }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 健康指南 -->
        <div class="l-card">
          <h3>健康指南</h3>
          <ul class="guide-list">
            <li>🏃 每周3-5次有氧运动</li>
            <li>💧 每天饮水1.5-2升</li>
            <li>😌 每日冥想10分钟</li>
            <li>💤 保证7-8小时睡眠</li>
          </ul>
        </div>
      </div>

      <!-- 右侧面板 -->
      <div class="right-panel">
        <!-- 顶部状态栏 -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ healthData.hr }}</div>
            <div class="stat-label">当前心率</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ healthData.br }}</div>
            <div class="stat-label">当前呼吸率</div>
          </div>
          <div class="stat-card purple">
            <div class="stat-value">{{ healthData.cr }}</div>
            <div class="stat-label">心肺频率比 (CR)</div>
          </div>
          <div class="stat-card teal">
            <div class="stat-value">{{ healthData.brel }}%</div>
            <div class="stat-label">呼吸急促度</div>
          </div>
        </div>

        <!-- 第一排：心率波形 + 呼吸波形 -->
        <div class="chart-row">
          <div class="chart-card">
            <h3>❤️ 心率波形</h3>
            <div class="wave-chart">
              <svg viewBox="0 0 400 120" preserveAspectRatio="none">
                <polyline :points="hrWavePoints" fill="none" stroke="#ef4444" stroke-width="2" />
              </svg>
            </div>
          </div>
          <div class="chart-card">
            <h3>💨 呼吸波形</h3>
            <div class="wave-chart">
              <svg viewBox="0 0 400 120" preserveAspectRatio="none">
                <polyline :points="brWavePoints" fill="none" stroke="#22c55e" stroke-width="2" />
              </svg>
            </div>
          </div>
        </div>

        <!-- 第二排：心肺频率比趋势 + 呼吸急促度趋势 -->
        <div class="chart-row">
          <div class="chart-card">
            <h3>🔄 CR趋势</h3>
            <div class="mini-chart">
              <div class="chart-bars-small">
                <div 
                  v-for="(item, index) in crTrendData" 
                  :key="index"
                  class="chart-bar-small cr-bar"
                  :style="{ height: ((item - 2) / 5 * 100) + '%' }"
                ></div>
              </div>
            </div>
          </div>
          <div class="chart-card">
            <h3>⏰ BREL趋势</h3>
            <div class="mini-chart">
              <div class="chart-bars-small">
                <div 
                  v-for="(item, index) in brelTrendData" 
                  :key="index"
                  class="chart-bar-small brel-bar"
                  :style="{ height: ((item + 30) / 60 * 100) + '%' }"
                ></div>
              </div>
            </div>
          </div>
          <div class="chart-card polar-card">
            <h3>🔵 相位差圆周</h3>
            <div class="polar-chart">
              <svg viewBox="0 0 150 150">
                <circle cx="75" cy="75" r="60" fill="none" stroke="#e2e8f0" stroke-width="2" />
                <circle cx="75" cy="75" r="40" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="75" cy="75" r="20" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="75" cy="75" r="55" fill="none" stroke="#ec4899" stroke-width="8" stroke-dasharray="30 300" :stroke-dashoffset="-healthData.phaseDiff" />
                <circle cx="75" cy="75" r="8" fill="#ec4899" />
              </svg>
            </div>
            <div class="polar-value">{{ healthData.phaseDiff }}°</div>
          </div>
        </div>

        <!-- 第三排：心肺相空间 + PLV -->
        <div class="chart-row">
          <div class="chart-card lissajous-card">
            <h3>🌀 心肺相空间 (Lissajous)</h3>
            <div class="lissajous-chart">
              <svg viewBox="0 0 200 200">
                <circle cx="100" cy="100" r="70" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="100" cy="100" r="50" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="100" cy="100" r="30" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <polyline :points="lissajousPoints" fill="none" stroke="#14b8a6" stroke-width="1.5" />
              </svg>
            </div>
          </div>
          <div class="chart-card plv-card">
            <h3>🔗 相位锁定值 (PLV)</h3>
            <div class="plv-display">
              <div class="plv-value">{{ healthData.plv }}</div>
              <div class="plv-label">{{ plvLevel }}</div>
            </div>
            <div class="mini-chart">
              <div class="chart-bars-small">
                <div 
                  v-for="(item, index) in plvTrendData" 
                  :key="index"
                  class="chart-bar-small plv-bar"
                  :style="{ height: (item * 100) + '%' }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 情绪健康 -->
    <section v-show="activeTab=='emotion'" class="emotion-layout">
      <div class="left-panel">
        <div class="l-card video-card">
          <h3>视频流</h3>
          <div class="video-box">📹 视频区域</div>
        </div>
        <div class="l-card snapshots-card">
          <h3>情绪快照</h3>
          <div class="snapshots">
            <div v-for="(s,i) in snapshots" :key="i" class="snapshot" :style="{background:s.color}">
              {{ s.emoji }}
            </div>
          </div>
        </div>
      </div>

      <div class="right-panel">
        <div class="emotion-cards">
          <div class="emotion-card">
            <h3>AU 通道</h3>
            <div class="emotion-display" :style="{color:emotion.au.color}">{{ emotion.au.emotion }}</div>
            <div class="prob-row"><span>中性</span><div class="prob-bar-container"><div class="prob-bar neutral" :style="{width:emotion.au.neutral+'%'}"></div></div><span>{{ emotion.au.neutral }}%</span></div>
            <div class="prob-row"><span>积极</span><div class="prob-bar-container"><div class="prob-bar positive" :style="{width:emotion.au.positive+'%'}"></div></div><span>{{ emotion.au.positive }}%</span></div>
            <div class="prob-row"><span>消极</span><div class="prob-bar-container"><div class="prob-bar negative" :style="{width:emotion.au.negative+'%'}"></div></div><span>{{ emotion.au.negative }}%</span></div>
          </div>
          <div class="emotion-card">
            <h3>FER+ 通道</h3>
            <div class="emotion-display" :style="{color:emotion.fer.color}">{{ emotion.fer.emotion }}</div>
            <div class="prob-row"><span>中性</span><div class="prob-bar-container"><div class="prob-bar neutral" :style="{width:emotion.fer.neutral+'%'}"></div></div><span>{{ emotion.fer.neutral }}%</span></div>
            <div class="prob-row"><span>积极</span><div class="prob-bar-container"><div class="prob-bar positive" :style="{width:emotion.fer.positive+'%'}"></div></div><span>{{ emotion.fer.positive }}%</span></div>
            <div class="prob-row"><span>消极</span><div class="prob-bar-container"><div class="prob-bar negative" :style="{width:emotion.fer.negative+'%'}"></div></div><span>{{ emotion.fer.negative }}%</span></div>
          </div>
          <div class="emotion-card fusion">
            <h3>融合结果</h3>
            <div class="emotion-display" :style="{color:emotion.fusion.color}">{{ emotion.fusion.emotion }}</div>
            <div class="prob-row"><span>中性</span><div class="prob-bar-container"><div class="prob-bar neutral" :style="{width:emotion.fusion.neutral+'%'}"></div></div><span>{{ emotion.fusion.neutral }}%</span></div>
            <div class="prob-row"><span>积极</span><div class="prob-bar-container"><div class="prob-bar positive" :style="{width:emotion.fusion.positive+'%'}"></div></div><span>{{ emotion.fusion.positive }}%</span></div>
            <div class="prob-row"><span>消极</span><div class="prob-bar-container"><div class="prob-bar negative" :style="{width:emotion.fusion.negative+'%'}"></div></div><span>{{ emotion.fusion.negative }}%</span></div>
          </div>
        </div>

        <div class="chart-card">
          <h3>情绪时序图</h3>
          <div class="wave-chart">
            <svg viewBox="0 0 600 150" preserveAspectRatio="none">
              <polyline :points="neutralPoints" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,5" />
              <polyline :points="positivePoints" fill="none" stroke="#22c55e" stroke-width="2" />
              <polyline :points="negativePoints" fill="none" stroke="#3b82f6" stroke-width="2" />
            </svg>
          </div>
        </div>

        <div class="chart-card">
          <h3>情绪趋势</h3>
          <div class="period-tabs">
            <button @click="emoPeriod='day'" :class="{active:emoPeriod=='day'}">日</button>
            <button @click="emoPeriod='week'" :class="{active:emoPeriod=='week'}">周</button>
            <button @click="emoPeriod='month'" :class="{active:emoPeriod=='month'}">月</button>
            <button @click="emoPeriod='year'" :class="{active:emoPeriod=='year'}">年</button>
          </div>
          <div class="stacked-bar-chart">
            <div class="stacked-bars">
              <div v-for="(day, index) in emotionWeeklyData" :key="index" class="stacked-bar-group">
                <div class="stacked-bar neutral" :style="{height:day.neutral+'%'}"></div>
                <div class="stacked-bar positive" :style="{height:day.positive+'%'}"></div>
                <div class="stacked-bar negative" :style="{height:day.negative+'%'}"></div>
              </div>
            </div>
            <div class="stacked-labels">
              <span v-for="day in ['周一','周二','周三','周四','周五','周六','周日']" :key="day">{{ day }}</span>
            </div>
          </div>
        </div>

        <div class="bottom-row">
          <div class="bottom-card stress-card">
            <h3>压力值</h3>
            <div class="stress-value" :class="stressClass">{{ emotion.stress }}%</div>
            <div class="stress-bar"><div class="stress-fill" :style="{width:emotion.stress+'%'}"></div></div>
          </div>
          <div class="bottom-card">
            <h3>情绪分析</h3>
            <div class="analysis-item"><span>主导情绪</span><span>{{ emotion.analysis.dominant }}</span></div>
            <div class="analysis-item"><span>情绪波动</span><span>{{ emotion.analysis.volatility }}</span></div>
            <div class="analysis-item"><span>持续时间</span><span>{{ emotion.analysis.duration }}</span></div>
          </div>
          <div class="bottom-card">
            <h3>建议</h3>
            <p>{{ emotion.suggestion }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 睡眠健康 -->
    <section v-show="activeTab=='sleep'" class="sleep-section">
      <div class="sleep-card large">
        <h3>睡眠时长趋势</h3>
        <div class="bar-chart">
          <div class="chart-bars">
            <div 
              v-for="(item, index) in sleepDurationData" 
              :key="index"
              class="chart-bar sleep-bar"
              :style="{ height: (item / 10 * 100) + '%' }"
            >
              <div class="bar-value">{{ item }}h</div>
            </div>
          </div>
          <div class="chart-labels">
            <div v-for="day in ['周一','周二','周三','周四','周五','周六','周日']" :key="day" class="chart-label">{{ day }}</div>
          </div>
        </div>
      </div>
      <div class="sleep-card">
        <h3>睡眠记录</h3>
        <div class="sleep-records">
          <div v-for="(r,i) in sleepRecords" :key="i" class="sleep-record">
            <span>{{ r.date }}</span>
            <span>{{ r.hours }}h{{ r.minutes }}m</span>
            <span :class="r.quality">{{ r.qualityText }}</span>
          </div>
        </div>
      </div>
      <div class="sleep-card">
        <h3>睡眠得分</h3>
        <div class="score-display">
          <div class="score-value">{{ sleepScore }}</div>
          <div class="score-stars">{{ '★'.repeat(sleepStars) }}{{ '☆'.repeat(5-sleepStars) }}</div>
          <div class="score-comment">{{ sleepComment }}</div>
        </div>
      </div>
      <div class="sleep-card">
        <h3>睡眠阶段分布</h3>
        <div class="pie-chart-container">
          <svg viewBox="0 0 200 200" class="pie-chart">
            <circle cx="100" cy="100" r="80" fill="none" stroke="#1e3a8a" :stroke-dasharray="circumference * sleepPhasesData.deep / 100 + ' ' + circumference" />
            <circle cx="100" cy="100" r="80" fill="none" stroke="#3b82f6" :stroke-dasharray="circumference * sleepPhasesData.light / 100 + ' ' + circumference" :stroke-dashoffset="-circumference * sleepPhasesData.deep / 100" />
            <circle cx="100" cy="100" r="80" fill="none" stroke="#8b5cf6" :stroke-dasharray="circumference * sleepPhasesData.rem / 100 + ' ' + circumference" :stroke-dashoffset="-circumference * (sleepPhasesData.deep + sleepPhasesData.light) / 100" />
            <circle cx="100" cy="100" r="80" fill="none" stroke="#94a3b8" :stroke-dasharray="circumference * sleepPhasesData.awake / 100 + ' ' + circumference" :stroke-dashoffset="-circumference * (sleepPhasesData.deep + sleepPhasesData.light + sleepPhasesData.rem) / 100" />
            <circle cx="100" cy="100" r="55" fill="white" />
          </svg>
        </div>
        <div class="phases-legend">
          <span><span class="legend-color deep"></span>深睡 {{ sleepPhasesData.deep }}%</span>
          <span><span class="legend-color light"></span>浅睡 {{ sleepPhasesData.light }}%</span>
          <span><span class="legend-color rem"></span>REM {{ sleepPhasesData.rem }}%</span>
          <span><span class="legend-color awake"></span>清醒 {{ sleepPhasesData.awake }}%</span>
        </div>
      </div>
      <div class="sleep-card">
        <h3>睡眠解读与建议</h3>
        <p>您的深睡眠时间占比{{ sleepPhasesData.deep }}%，处于正常范围。REM睡眠充足，睡眠质量良好。建议保持规律作息。</p>
        <ul>
          <li>🌡️ 保持卧室温度在18-22°C</li>
          <li>📵 睡前1小时避免使用电子设备</li>
          <li>🧘 建议进行10分钟冥想放松</li>
          <li>💧 睡前适量饮水</li>
        </ul>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const HLKK_PORT = 5020;
const activeTab = ref('cardio');
const period = ref('day');
const emoPeriod = ref('week');

const healthData = ref({ hr: 72, br: 16, cr: 4.5, brel: 15, signal: 'NORMAL', plv: 0.914, phaseDiff: 45 });

const emotion = ref({
  au: { emotion: '中性', color: '#8b949e', neutral: 60, positive: 25, negative: 15 },
  fer: { emotion: '积极', color: '#22c55e', neutral: 20, positive: 70, negative: 10 },
  fusion: { emotion: '积极', color: '#22c55e', neutral: 35, positive: 55, negative: 10 },
  stress: 45,
  analysis: { dominant: '积极', volatility: '中等', duration: '15分钟' },
  suggestion: '今日情绪状态良好，建议保持积极心态，适当进行户外活动。'
});

const snapshots = ref([
  { emoji: '😊', color: '#22c55e' },
  { emoji: '😐', color: '#eab308' },
  { emoji: '😔', color: '#ef4444' },
  { emoji: '😊', color: '#22c55e' },
  { emoji: '😐', color: '#eab308' }
]);

const sleepRecords = ref([
  { date: '昨天', hours: 7, minutes: 35, quality: 'good', qualityText: '良好' },
  { date: '前天', hours: 6, minutes: 45, quality: 'normal', qualityText: '一般' },
  { date: '周三', hours: 8, minutes: 10, quality: 'excellent', qualityText: '优秀' },
  { date: '周二', hours: 7, minutes: 0, quality: 'good', qualityText: '良好' },
  { date: '周一', hours: 6, minutes: 30, quality: 'normal', qualityText: '一般' }
]);

const sleepScore = ref(78);
const sleepStars = computed(() => Math.min(5, Math.ceil(sleepScore.value / 20)));
const sleepComment = computed(() => {
  if (sleepScore.value >= 90) return '睡眠质量非常好！';
  if (sleepScore.value >= 70) return '睡眠质量良好，继续保持';
  return '睡眠质量一般，建议改善';
});

const sleepPhasesData = ref({ deep: 25, light: 45, rem: 20, awake: 10 });
const circumference = 2 * Math.PI * 80;

const hrTrendData = ref(Array(6).fill(0).map(() => Math.round(65 + Math.random() * 25)));
const crTrendData = ref(Array(12).fill(0).map(() => Math.round((3 + Math.random() * 4) * 10) / 10));
const brelTrendData = ref(Array(12).fill(0).map(() => Math.round(-30 + Math.random() * 60)));
const plvTrendData = ref(Array(12).fill(0).map(() => 0.7 + Math.random() * 0.3));
const sleepDurationData = ref([6.5, 7, 8.2, 7.5, 6.8, 8.5, 7.8]);

const emotionWeeklyData = ref([
  { neutral: 45, positive: 35, negative: 20 },
  { neutral: 55, positive: 30, negative: 15 },
  { neutral: 40, positive: 45, negative: 15 },
  { neutral: 60, positive: 25, negative: 15 },
  { neutral: 50, positive: 35, negative: 15 },
  { neutral: 70, positive: 20, negative: 10 },
  { neutral: 65, positive: 25, negative: 10 }
]);

const signalStatus = computed(() => {
  const s = healthData.value.signal;
  if (s === 'NORMAL') return 'normal';
  if (s.includes('UNSTABLE')) return 'warning';
  return 'danger';
});

const signalStatusText = computed(() => {
  const map = {
    'NORMAL': '● 正常',
    'BR_UNSTABLE': '◐ 呼吸不稳',
    'HR_UNSTABLE': '◐ 心率不稳',
    'THAW': '↻ 恢复中',
    'BIG_MOVE': '✕ 大幅运动',
    'NO_TARGET': '○ 无目标',
    'INIT': '… 等待数据'
  };
  return map[healthData.value.signal] || healthData.value.signal;
});

const plvLevel = computed(() => {
  const p = healthData.value.plv;
  if (p < 0.3) return '清醒焦虑';
  if (p <= 0.9) return '日常活动';
  return '深度放松';
});

const stressClass = computed(() => {
  const s = emotion.value.stress;
  if (s >= 70) return 'high';
  if (s >= 40) return 'medium';
  return 'low';
});

const hrWavePoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 50; i++) {
    const x = (i / 50) * 400;
    const y = 60 + Math.sin(i * 0.5) * 30 + Math.sin(i * 0.1) * 15 + (Math.random() - 0.5) * 8;
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const brWavePoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 50; i++) {
    const x = (i / 50) * 400;
    const y = 60 + Math.sin(i * 0.15) * 35 + (Math.random() - 0.5) * 6;
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const lissajousPoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 64; i++) {
    const t = (i / 64) * 2 * Math.PI;
    const x = 100 + 50 * Math.cos(t);
    const y = 100 + 40 * Math.sin(t * 1.5);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const neutralPoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 60; i++) {
    const x = (i / 60) * 600;
    const y = 130 - (30 + Math.sin(i * 0.1) * 10 + Math.random() * 5);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const positivePoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 60; i++) {
    const x = (i / 60) * 600;
    const y = 130 - (35 + Math.sin(i * 0.12) * 15 + Math.random() * 5);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const negativePoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 60; i++) {
    const x = (i / 60) * 600;
    const y = 130 - (15 + Math.sin(i * 0.08) * 8 + Math.random() * 5);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

async function fetchData() {
  try {
    const res = await fetch(`http://localhost:${HLKK_PORT}/data`);
    if (res.ok) {
      const data = await res.json();
      healthData.value.hr = data.raw?.hr?.toFixed(0) || 72;
      healthData.value.br = data.raw?.br?.toFixed(0) || 16;
      healthData.value.signal = data.raw?.signal_state || 'NORMAL';
      if (data.physiology) {
        healthData.value.cr = data.physiology.cr_ratio || 4.5;
        healthData.value.brel = data.physiology.br_elevation || 15;
        healthData.value.plv = data.physiology.plv_r || 0.914;
        healthData.value.phaseDiff = data.physiology.mean_phase_diff ? ((data.physiology.mean_phase_diff * 180 / Math.PI) % 360).toFixed(0) : 45;
      }
    }
  } catch (e) {
    healthData.value.hr = Math.round(65 + Math.random() * 20);
    healthData.value.br = Math.round(14 + Math.random() * 6);
    healthData.value.cr = Math.round((3 + Math.random() * 4) * 10) / 10;
    healthData.value.brel = Math.round(-30 + Math.random() * 60);
    hrTrendData.value = Array(6).fill(0).map(() => Math.round(65 + Math.random() * 25));
    crTrendData.value = Array(12).fill(0).map(() => Math.round((3 + Math.random() * 4) * 10) / 10);
    brelTrendData.value = Array(12).fill(0).map(() => Math.round(-30 + Math.random() * 60));
    plvTrendData.value = Array(12).fill(0).map(() => 0.7 + Math.random() * 0.3);
  }
}

let intervalId = null;

const goToVideoCall = () => {
  router.push('/video');
};

const callNurseStation = () => {
  if (confirm('确定要呼叫护理站吗？')) {
    alert('正在连接护理站...\n\n📞 护理站已收到您的呼叫，工作人员将尽快与您联系。');
  }
};

onMounted(() => {
  fetchData();
  intervalId = setInterval(fetchData, 1000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
});
</script>

<style scoped>
.page-body { 
  padding: 0;
  margin: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #ffffff;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 40px;
  background: #f8fafc;
  border-bottom: 2px solid #e2e8f0;
}

.header h1 {
  font-size: 36px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.action-buttons {
  display: flex;
  gap: 15px;
}

.action-btn {
  padding: 14px 24px;
  font-size: 18px;
  font-weight: 600;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn.call {
  background: linear-gradient(135deg, #22c55e, #16a34a);
  color: white;
  box-shadow: 0 4px 15px rgba(34, 197, 94, 0.3);
}

.action-btn.call:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(34, 197, 94, 0.4);
}

.action-btn.sos {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: white;
  box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
}

.action-btn.sos:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4);
}

.tabs {
  display: flex;
  gap: 15px;
}

.tabs button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 28px;
  font-size: 18px;
  font-weight: 600;
  color: #64748b;
  background: white;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s;
}

.tabs button:hover {
  background: #f1f5f9;
}

.tabs button.active {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
  border-color: transparent;
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3);
}

/* 左右分栏布局 - 完全参照 learning.vue */
.cardio-layout, .emotion-layout {
  display: flex;
  gap: 20px;
  margin: 0;
  flex: 1;
  align-items: flex-start;
  padding: 20px;
}

.left-panel {
  width: 25%;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

/* 左侧卡片 */
.l-card {
  background: #FFF;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.l-card h3 {
  font-size: 20px;
  color: #333;
  margin-bottom: 15px;
}

.summary-card .metrics {
  display: flex;
  gap: 15px;
}

.metric {
  flex: 1;
  text-align: center;
  padding: 15px;
  background: #f8fafc;
  border-radius: 12px;
}

.metric-value {
  font-size: 36px;
  font-weight: 700;
  color: #1e293b;
}

.metric-label {
  font-size: 14px;
  color: #64748b;
  margin-top: 5px;
}

.status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #e2e8f0;
  font-size: 14px;
  color: #64748b;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #cbd5e1;
}

.status-dot.normal { background: #22c55e; }
.status-dot.warning { background: #eab308; }
.status-dot.danger { background: #ef4444; }

.period-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 15px;
}

.period-tabs button {
  padding: 6px 14px;
  font-size: 13px;
  color: #64748b;
  background: #f1f5f9;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.period-tabs button.active {
  background: #3b82f6;
  color: white;
}

.guide-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.guide-list li {
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  margin-bottom: 10px;
  font-size: 15px;
  color: #475569;
}

.video-card .video-box {
  height: 200px;
  background: #1e293b;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 24px;
}

.snapshots {
  display: flex;
  gap: 10px;
}

.snapshot {
  flex: 1;
  height: 60px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 15px;
}

.stat-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 20px;
  padding: 20px;
  text-align: center;
  color: white;
}

.stat-card.purple { background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); }
.stat-card.teal { background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%); }

.stat-value {
  font-size: 32px;
  font-weight: bold;
  margin-bottom: 5px;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
}

/* 图表行 */
.chart-row {
  display: flex;
  gap: 15px;
}

.chart-card {
  flex: 1;
  background: #FFF;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.chart-card h3 {
  font-size: 18px;
  color: #333;
  margin-bottom: 15px;
}

.polar-card {
  flex: 0 0 200px;
  text-align: center;
}

.polar-chart {
  margin-top: 10px;
}

.polar-value {
  font-size: 24px;
  font-weight: bold;
  color: #ec4899;
  margin-top: 10px;
}

.lissajous-card {
  flex: 1.5;
}

.lissajous-chart {
  height: 180px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.plv-card {
  flex: 1;
}

.plv-display {
  text-align: center;
  margin-bottom: 15px;
}

.plv-value {
  font-size: 48px;
  font-weight: bold;
  color: #a855f7;
}

.plv-label {
  font-size: 14px;
  color: #64748b;
}

/* 波形图 */
.wave-chart {
  height: 120px;
  background: #f8fafc;
  border-radius: 10px;
}

.wave-chart svg {
  width: 100%;
  height: 100%;
}

/* 迷你图表 */
.mini-chart {
  height: 100px;
}

.chart-bars-small {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 100%;
}

.chart-bar-small {
  flex: 1;
  border-radius: 4px 4px 0 0;
  min-height: 5px;
}

.chart-bar-small.cr-bar { background: linear-gradient(to top, #f97316, #fb923c); }
.chart-bar-small.brel-bar { background: linear-gradient(to top, #14b8a6, #2dd4bf); }
.chart-bar-small.plv-bar { background: linear-gradient(to top, #a855f7, #c084fc); }

/* 情绪卡片 */
.emotion-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 15px;
}

.emotion-card {
  background: #FFF;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.emotion-card.fusion {
  border: 2px solid #3b82f6;
}

.emotion-card h3 {
  font-size: 16px;
  color: #64748b;
  margin-bottom: 12px;
}

.emotion-display {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 15px;
}

.prob-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #64748b;
  margin-bottom: 8px;
}

.prob-bar-container {
  flex: 1;
  height: 8px;
  background: #f1f5f9;
  border-radius: 4px;
  overflow: hidden;
}

.prob-bar {
  height: 100%;
}

.prob-bar.neutral { background: #94a3b8; }
.prob-bar.positive { background: #22c55e; }
.prob-bar.negative { background: #3b82f6; }

/* 堆叠柱状图 */
.stacked-bar-chart {
  margin-top: 10px;
}

.stacked-bars {
  display: flex;
  gap: 10px;
  height: 180px;
  align-items: flex-end;
}

.stacked-bar-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 6px 6px 0 0;
  overflow: hidden;
}

.stacked-bar {
  width: 100%;
}

.stacked-bar.neutral { background: #94a3b8; }
.stacked-bar.positive { background: #22c55e; }
.stacked-bar.negative { background: #3b82f6; }

.stacked-labels {
  display: flex;
  justify-content: space-around;
  margin-top: 10px;
  font-size: 13px;
  color: #64748b;
}

/* 底部行 */
.bottom-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 15px;
}

.bottom-card {
  background: #FFF;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.bottom-card h3 {
  font-size: 16px;
  color: #64748b;
  margin-bottom: 15px;
}

.stress-card {
  text-align: center;
}

.stress-value {
  font-size: 48px;
  font-weight: 700;
}

.stress-value.low { color: #22c55e; }
.stress-value.medium { color: #eab308; }
.stress-value.high { color: #ef4444; }

.stress-bar {
  height: 10px;
  background: #f1f5f9;
  border-radius: 5px;
  margin-top: 10px;
  overflow: hidden;
}

.stress-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #eab308, #ef4444);
}

.analysis-item {
  display: flex;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 15px;
}

.analysis-item span:first-child { color: #64748b; }
.analysis-item span:last-child { color: #1e293b; font-weight: 600; }

.bottom-card p {
  font-size: 15px;
  color: #475569;
  line-height: 1.6;
  margin: 0;
}

/* 睡眠布局 */
.sleep-section {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  padding: 20px 40px;
}

.sleep-card {
  background: #FFF;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

.sleep-card.large {
  grid-column: span 2;
}

.sleep-card h3 {
  font-size: 18px;
  color: #333;
  margin-bottom: 15px;
}

/* 柱状图 */
.bar-chart {
  margin-top: 10px;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 15px;
  height: 200px;
  padding: 20px 0;
  width: 100%;
  justify-content: space-around;
}

.chart-bar {
  width: 60px;
  border-radius: 8px 8px 0 0;
  position: relative;
  min-height: 10px;
}

.chart-bar.hr-bar { background: linear-gradient(to top, #ef4444, #f87171); }
.chart-bar.sleep-bar { background: linear-gradient(to top, #3b82f6, #60a5fa); }

.bar-value {
  position: absolute;
  top: -25px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 14px;
  font-weight: bold;
  color: #333;
}

.chart-labels {
  display: flex;
  justify-content: space-around;
  width: 100%;
  padding-top: 10px;
  border-top: 1px solid #EEE;
}

.chart-label {
  font-size: 14px;
  color: #666;
  text-align: center;
  width: 60px;
}

/* 睡眠记录 */
.sleep-records {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sleep-record {
  display: flex;
  justify-content: space-between;
  padding: 12px;
  background: #f8fafc;
  border-radius: 10px;
  font-size: 15px;
}

.sleep-record span:nth-child(2) {
  color: #1e293b;
  font-weight: 600;
}

.sleep-record span:nth-child(3) {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.sleep-record span.excellent { background: rgba(34,197,94,0.1); color: #22c55e; }
.sleep-record span.good { background: rgba(59,130,246,0.1); color: #3b82f6; }
.sleep-record span.normal { background: rgba(234,179,8,0.1); color: #eab308; }

/* 得分显示 */
.score-display {
  text-align: center;
}

.score-value {
  font-size: 56px;
  font-weight: 700;
  color: #3b82f6;
}

.score-stars {
  font-size: 28px;
  color: #e2e8f0;
  margin: 10px 0;
}

.score-comment {
  font-size: 15px;
  color: #64748b;
}

/* 饼图 */
.pie-chart-container {
  display: flex;
  justify-content: center;
  margin-top: 10px;
}

.pie-chart {
  width: 180px;
  height: 180px;
  transform: rotate(-90deg);
}

.pie-chart circle {
  stroke-width: 25;
}

.phases-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
  margin-top: 15px;
  font-size: 13px;
  color: #64748b;
}

.legend-color {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  margin-right: 5px;
}

.legend-color.deep { background: #1e3a8a; }
.legend-color.light { background: #3b82f6; }
.legend-color.rem { background: #8b5cf6; }
.legend-color.awake { background: #94a3b8; }

.sleep-card ul {
  margin: 10px 0 0;
  padding-left: 20px;
}

.sleep-card li {
  font-size: 14px;
  color: #475569;
  margin-bottom: 8px;
}

@media (max-width: 1200px) {
  .cardio-layout, .emotion-layout {
    flex-direction: column;
  }
  .left-panel {
    width: 100%;
    min-width: auto;
  }
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .chart-row {
    flex-direction: column;
  }
  .emotion-cards {
    grid-template-columns: 1fr;
  }
  .bottom-row {
    grid-template-columns: 1fr;
  }
  .sleep-section {
    grid-template-columns: 1fr;
  }
  .sleep-card.large {
    grid-column: span 1;
  }
}

@media (max-width: 768px) {
  .header {
    flex-direction: column;
    gap: 15px;
    padding: 15px;
  }
  .header h1 {
    font-size: 28px;
  }
  .tabs button {
    padding: 10px 20px;
    font-size: 16px;
  }
}
</style>