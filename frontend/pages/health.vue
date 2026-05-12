<template>
  <div class="page-root">
    <!-- 顶部导航 -->
    <header class="page-header">
      <div class="flex items-center gap-2">
        <span class="font-bold text-xl tracking-tight">健康中心</span>
      </div>
      <div class="flex items-center gap-1.5 bg-slate-50 p-0.5 rounded-lg">
        <button class="tab-btn" :class="{active:activeTab==='cardio'}" @click="switchTab('cardio')"><i class="fas fa-lungs mr-1" style="font-size:16px"></i>心肺</button>
        <button class="tab-btn" :class="{active:activeTab==='emotion'}" @click="switchTab('emotion')"><i class="fas fa-brain mr-1" style="font-size:16px"></i>情绪</button>
        <button class="tab-btn" :class="{active:activeTab==='sleep'}" @click="switchTab('sleep')"><i class="fas fa-moon mr-1" style="font-size:16px"></i>睡眠</button>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[11px] text-slate-400">{{currentTime}}</span>
      </div>
    </header>

    <!-- 心肺健康 -->
    <section v-show="activeTab=='cardio'" class="split fade-up">
      <!-- 左侧面板 -->
      <div class="left-col">
        <!-- 健康摘要 -->
        <div class="card" style="padding:12px">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-teal-50 flex items-center justify-center"><i class="fas fa-heart-pulse text-teal-600" style="font-size:8px"></i></div><h3 class="font-bold text-xs">健康摘要</h3></div>
            <span class="text-[9px] text-teal-600 font-semibold bg-teal-50 px-1.5 py-0.5 rounded">实时</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
            <div class="mini-st">
              <div class="m-label">心率</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val text-lg" style="color:#0D9488">{{ healthData.hr }}</span><span class="m-unit">bpm</span></div>
              <div class="flex items-center gap-0.5 mt-0.5"><i class="fas fa-check text-green-500" style="font-size:8px"></i><span class="text-[9px] text-green-600">正常</span></div>
            </div>
            <div class="mini-st">
              <div class="m-label">呼吸率</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val text-lg" style="color:#F97316">{{ healthData.br }}</span><span class="m-unit">/min</span></div>
              <div class="flex items-center gap-0.5 mt-0.5"><i class="fas fa-check text-green-500" style="font-size:8px"></i><span class="text-[9px] text-green-600">正常</span></div>
            </div>
            <div class="mini-st">
              <div class="m-label">心率储备</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val">{{ healthData.hrr }}</span><span class="m-unit">%</span></div>
              <div class="prog-bar mt-1"><div class="prog-fill" :style="{width:healthData.hrr+'%',background:healthData.hrr<60?'#0D9488':'#F97316'}"></div></div>
            </div>
            <div class="mini-st">
              <div class="m-label">心肺频率比</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val">{{ healthData.cr }}</span></div>
              <span class="text-[9px] text-slate-400 mt-0.5 block">理想 4-6</span>
            </div>
            <div class="mini-st">
              <div class="m-label">呼吸变异性</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val">{{ healthData.brv }}</span><span class="m-unit">%</span></div>
            </div>
            <div class="mini-st">
              <div class="m-label">呼吸急促度</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val">{{ healthData.brel }}</span><span class="m-unit">%</span></div>
            </div>
            <div class="mini-st">
              <div class="m-label">心率斜率</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val">{{ healthData.hrSlope }}</span></div>
            </div>
            <div class="mini-st">
              <div class="m-label">相位锁定值</div>
              <div class="flex items-baseline gap-0.5 mt-0.5"><span class="m-val">{{ healthData.plv }}</span></div>
            </div>
          </div>
        </div>

        <!-- 健康指南 -->
        <div class="card" style="padding:12px">
          <div class="flex items-center gap-1.5 mb-2"><div class="w-4 h-4 rounded bg-emerald-50 flex items-center justify-center"><i class="fas fa-book-medical text-emerald-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">健康指南</h3></div>
          <div class="flex flex-col gap-1.5">
            <div class="adv-item" v-for="(a,i) in cardioAdvices" :key="i">
              <div class="w-6 h-6 rounded flex items-center justify-center shrink-0" :style="{background:a.bg}"><i :class="a.icon" style="font-size:9px" :style="{color:a.color}"></i></div>
              <div><div class="text-[11px] font-semibold text-slate-700">{{a.title}}</div><div class="text-[9px] text-slate-400">{{a.desc}}</div></div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧面板 -->
      <div class="right-col">
        <!-- 健康趋势 -->
        <div class="card" style="padding:12px">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-indigo-50 flex items-center justify-center"><i class="fas fa-chart-line text-indigo-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">健康趋势</h3></div>
            <div class="flex gap-0.5">
              <button class="per-btn" :class="{active:period==='day'}" @click="period='day'">日</button>
              <button class="per-btn" :class="{active:period==='week'}" @click="period='week'">周</button>
              <button class="per-btn" :class="{active:period==='month'}" @click="period='month'">月</button>
            </div>
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

        <!-- 波形图 一排 -->
        <div class="right-2col">
          <div class="card" style="padding:12px">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-1"><div class="w-1.5 h-1.5 rounded-full bg-teal-500 pulse-d"></div><span class="font-bold text-[11px]">心率波形</span></div>
              <span class="m-val text-base" style="color:#0D9488">{{ healthData.hr }}</span>
            </div>
            <div class="wave-chart">
              <svg viewBox="0 0 400 120" preserveAspectRatio="none">
                <polyline :points="hrWavePoints" fill="none" stroke="#0D9488" stroke-width="2" />
              </svg>
            </div>
          </div>
          <div class="card" style="padding:12px">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-1"><div class="w-1.5 h-1.5 rounded-full bg-orange-500 pulse-d"></div><span class="font-bold text-[11px]">呼吸波形</span></div>
              <span class="m-val text-base" style="color:#F97316">{{ healthData.br }}</span>
            </div>
            <div class="wave-chart">
              <svg viewBox="0 0 400 120" preserveAspectRatio="none">
                <polyline :points="brWavePoints" fill="none" stroke="#F97316" stroke-width="2" />
              </svg>
            </div>
          </div>
        </div>

        <!-- 仪表盘 一排 -->
        <div class="right-2col">
          <div class="card" style="padding:12px;display:flex;flex-direction:column;align-items:center">
            <h3 class="font-bold text-[11px] mb-2 self-start">心肺频率比</h3>
            <div class="gauge-container">
              <svg viewBox="0 0 160 88" width="160" height="88">
                <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#E2E8F0" stroke-width="10" stroke-linecap="round"/>
                <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" :stroke="crColor" stroke-width="10" stroke-linecap="round" :stroke-dasharray="crProgress" :stroke-dashoffset="crOffset"/>
                <line x1="80" y1="80" :x2="crNeedleX" :y2="crNeedleY" stroke="#1E293B" stroke-width="2" stroke-linecap="round"/>
                <circle cx="80" cy="80" r="3" fill="#1E293B"/>
              </svg>
            </div>
            <div class="m-val text-2xl mt-1" style="color:#0D9488">{{ healthData.cr }}</div>
            <div class="text-[9px] text-slate-400 mt-0.5">理想范围 4.0 - 6.0</div>
            <div class="flex gap-3 mt-1.5 text-[9px]">
              <span class="flex items-center gap-0.5"><span class="w-1.5 h-1.5 rounded-full" style="background:#10B981"></span>偏低</span>
              <span class="flex items-center gap-0.5"><span class="w-1.5 h-1.5 rounded-full" style="background:#0D9488"></span>正常</span>
              <span class="flex items-center gap-0.5"><span class="w-1.5 h-1.5 rounded-full" style="background:#F97316"></span>偏高</span>
            </div>
          </div>
          <div class="card" style="padding:12px;display:flex;flex-direction:column;align-items:center">
            <h3 class="font-bold text-[11px] mb-2 self-start">呼吸急促度</h3>
            <div class="gauge-container">
              <svg viewBox="0 0 160 88" width="160" height="88">
                <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#E2E8F0" stroke-width="10" stroke-linecap="round"/>
                <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" :stroke="brelColor" stroke-width="10" stroke-linecap="round" :stroke-dasharray="brelProgress" :stroke-dashoffset="brelOffset"/>
                <line x1="80" y1="80" :x2="brelNeedleX" :y2="brelNeedleY" stroke="#1E293B" stroke-width="2" stroke-linecap="round"/>
                <circle cx="80" cy="80" r="3" fill="#1E293B"/>
              </svg>
            </div>
            <div class="m-val text-2xl mt-1" :style="{color:brelColor}">{{ healthData.brel }}%</div>
            <div class="text-[9px] text-slate-400 mt-0.5">正常 &lt; 30%</div>
            <div class="flex gap-3 mt-1.5 text-[9px]">
              <span class="flex items-center gap-0.5"><span class="w-1.5 h-1.5 rounded-full" style="background:#10B981"></span>平稳</span>
              <span class="flex items-center gap-0.5"><span class="w-1.5 h-1.5 rounded-full" style="background:#F97316"></span>轻度</span>
              <span class="flex items-center gap-0.5"><span class="w-1.5 h-1.5 rounded-full" style="background:#EF4444"></span>急促</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 情绪健康 -->
    <section v-show="activeTab=='emotion'" class="split fade-up">
      <div class="left-col">
        <!-- 视频流 -->
        <div class="card" style="padding:10px">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-slate-100 flex items-center justify-center"><i class="fas fa-video text-slate-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">视频流</h3></div>
            <span class="live-tag"><span class="w-1 h-1 rounded-full bg-red-500 pulse-d"></span>LIVE</span>
          </div>
          <div class="vid-box" style="height:170px">
            <div class="scan-ln"></div>
            <div class="absolute inset-0 flex flex-col items-center justify-center text-white/50">
              <i class="fas fa-video text-xl mb-1"></i>
              <span class="text-[10px]">摄像头未连接</span>
            </div>
            <div style="position:absolute;top:18%;left:26%;width:48%;height:58%;border:1.5px solid rgba(13,148,136,.45);border-radius:50%"></div>
          </div>
          <div class="flex gap-1.5 mt-2">
            <button class="flex-1 py-1.5 rounded-lg text-[10px] font-semibold bg-teal-50 text-teal-700 hover:bg-teal-100 transition border border-teal-100"><i class="fas fa-camera mr-0.5"></i>本地</button>
            <button class="flex-1 py-1.5 rounded-lg text-[10px] font-semibold bg-slate-50 text-slate-600 hover:bg-slate-100 transition border border-slate-200"><i class="fas fa-globe mr-0.5"></i>IP</button>
          </div>
        </div>

        <!-- 情绪通道 -->
        <div class="card" style="padding:12px">
          <div class="flex items-center gap-1.5 mb-2"><div class="w-4 h-4 rounded bg-indigo-50 flex items-center justify-center"><i class="fas fa-layer-group text-indigo-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">情绪通道</h3></div>
          <!-- AU -->
          <div class="mb-2.5">
            <div class="flex items-center justify-between mb-1"><span class="text-[11px] font-semibold text-slate-600">AU 通道</span><span class="m-val text-sm" style="color:#0D9488">{{ emotion.auScore.toFixed(2) }}</span></div>
            <div class="emo-bar"><div :style="{width:emotion.au.positive+'%',background:'#10B981'}"></div><div :style="{width:emotion.au.neutral+'%',background:'#94A3B8'}"></div><div :style="{width:emotion.au.negative+'%',background:'#EF4444'}"></div></div>
            <div class="flex justify-between mt-0.5 text-[9px] text-slate-400"><span>积极{{ emotion.au.positive }}%</span><span>中性{{ emotion.au.neutral }}%</span><span>消极{{ emotion.au.negative }}%</span></div>
          </div>
          <!-- FER+ -->
          <div class="mb-2.5">
            <div class="flex items-center justify-between mb-1"><span class="text-[11px] font-semibold text-slate-600">FER+ 通道</span><span class="m-val text-sm" style="color:#F97316">{{ emotion.ferScore.toFixed(2) }}</span></div>
            <div class="emo-bar"><div :style="{width:emotion.fer.positive+'%',background:'#10B981'}"></div><div :style="{width:emotion.fer.neutral+'%',background:'#94A3B8'}"></div><div :style="{width:emotion.fer.negative+'%',background:'#EF4444'}"></div></div>
            <div class="flex justify-between mt-0.5 text-[9px] text-slate-400"><span>积极{{ emotion.fer.positive }}%</span><span>中性{{ emotion.fer.neutral }}%</span><span>消极{{ emotion.fer.negative }}%</span></div>
          </div>
          <!-- 融合 -->
          <div class="pt-2 border-t border-slate-100">
            <div class="flex items-center justify-between mb-1"><span class="text-[11px] font-bold text-slate-700">融合结果</span><span class="m-val text-base" style="color:#0F766E">{{ emotion.fusionScore.toFixed(2) }}</span></div>
            <div class="emo-bar" style="height:8px"><div :style="{width:emotion.fusion.positive+'%',background:'#10B981'}"></div><div :style="{width:emotion.fusion.neutral+'%',background:'#94A3B8'}"></div><div :style="{width:emotion.fusion.negative+'%',background:'#EF4444'}"></div></div>
            <div class="flex justify-between mt-0.5 text-[9px] text-slate-400"><span>积极{{ emotion.fusion.positive }}%</span><span>中性{{ emotion.fusion.neutral }}%</span><span>消极{{ emotion.fusion.negative }}%</span></div>
          </div>
        </div>

        <!-- 压力值 -->
        <div class="card" style="padding:12px;display:flex;flex-direction:column;align-items:center">
          <h3 class="font-bold text-xs mb-2 self-start">压力值</h3>
          <div class="relative" style="width:100px;height:100px">
            <svg viewBox="0 0 100 100" class="prog-ring" width="100" height="100">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#F1F5F9" stroke-width="7"/>
              <circle cx="50" cy="50" r="42" fill="none" :stroke="pressureColor" stroke-width="7" stroke-linecap="round" :stroke-dasharray="2*Math.PI*42" :stroke-dashoffset="2*Math.PI*42*(1-emotion.stress/100)"/>
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center" style="transform:rotate(90deg)">
              <span class="m-val text-xl" :style="{color:pressureColor}">{{ emotion.stress }}</span>
              <span class="text-[8px] text-slate-400">/100</span>
            </div>
          </div>
          <div class="text-[11px] font-semibold mt-1.5" :style="{color:pressureColor}">{{ pressureLabel }}</div>
        </div>
      </div>

      <div class="right-col">
        <!-- 情绪时序图 -->
        <div class="card" style="padding:12px">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-rose-50 flex items-center justify-center"><i class="fas fa-wave-square text-rose-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">情绪时序图</h3><span class="live-tag"><span class="w-1 h-1 rounded-full bg-red-500 pulse-d"></span>LIVE</span></div>
            <div class="flex gap-0.5">
              <button class="per-btn" :class="{active:emoPeriod==='day'}" @click="emoPeriod='day'">日</button>
              <button class="per-btn" :class="{active:emoPeriod==='week'}" @click="emoPeriod='week'">周</button>
              <button class="per-btn" :class="{active:emoPeriod==='month'}" @click="emoPeriod='month'">月</button>
              <button class="per-btn" :class="{active:emoPeriod==='year'}" @click="emoPeriod='year'">年</button>
            </div>
          </div>
          <div class="wave-chart">
            <svg viewBox="0 0 600 150" preserveAspectRatio="none">
              <polyline :points="neutralPoints" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,5" />
              <polyline :points="positivePoints" fill="none" stroke="#10B981" stroke-width="2" />
              <polyline :points="negativePoints" fill="none" stroke="#EF4444" stroke-width="2" />
            </svg>
          </div>
        </div>

        <!-- 情绪趋势 + 情绪分析 -->
        <div class="right-2col">
          <div class="card" style="padding:12px">
            <div class="flex items-center gap-1.5 mb-2"><div class="w-4 h-4 rounded bg-teal-50 flex items-center justify-center"><i class="fas fa-chart-bar text-teal-600" style="font-size:8px"></i></div><h3 class="font-bold text-xs">情绪趋势</h3></div>
            <div class="stacked-bar-chart">
              <div class="stacked-bars">
                <div v-for="(day, index) in emotionWeeklyData" :key="index" class="stacked-bar-group">
                  <div class="stacked-bar neutral" :style="{height:day.neutral+'%'}"></div>
                  <div class="stacked-bar positive" :style="{height:day.positive+'%'}"></div>
                  <div class="stacked-bar negative" :style="{height:day.negative+'%'}"></div>
                </div>
              </div>
            </div>
          </div>
          <div class="card" style="padding:12px">
            <div class="flex items-center gap-1.5 mb-2"><div class="w-4 h-4 rounded bg-amber-50 flex items-center justify-center"><i class="fas fa-magnifying-glass-chart text-amber-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">情绪分析</h3></div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:8px">
              <div class="mini-st text-center"><div class="m-label">主导</div><div class="m-val text-xs mt-0.5" style="color:#0D9488">{{ emotion.analysis.dominant }}</div></div>
              <div class="mini-st text-center"><div class="m-label">稳定性</div><div class="m-val text-xs mt-0.5" style="color:#10B981">{{ emotion.analysis.stability }}</div></div>
              <div class="mini-st text-center"><div class="m-label">波动</div><div class="m-val text-xs mt-0.5" style="color:#F97316">{{ emotion.analysis.volatility }}</div></div>
            </div>
            <div class="bg-teal-50/50 rounded-lg p-2.5 border border-teal-100 mb-2">
              <div class="text-[10px] font-semibold text-teal-800 mb-0.5">摘要</div>
              <p class="text-[9px] text-teal-700 leading-relaxed">积极情绪占比{{ emotion.fusion.positive }}%，消极情绪维持较低水平。压力指数{{ emotion.stress }}，处于健康范围。</p>
            </div>
            <div class="text-[10px] font-semibold text-slate-700 mb-1">建议</div>
            <div class="flex flex-col gap-1">
              <div class="adv-item" style="padding:6px 8px"><i class="fas fa-spa text-teal-500" style="font-size:9px"></i><span class="text-[9px] text-slate-600">深呼吸练习维持情绪稳定</span></div>
              <div class="adv-item" style="padding:6px 8px"><i class="fas fa-music text-orange-500" style="font-size:9px"></i><span class="text-[9px] text-slate-600">轻音乐增强积极体验</span></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 睡眠健康 -->
    <section v-show="activeTab=='sleep'" class="split fade-up">
      <div class="left-col">
        <!-- 睡眠得分 -->
        <div class="card" style="padding:12px;display:flex;flex-direction:column;align-items:center">
          <h3 class="font-bold text-xs mb-2 self-start">睡眠得分</h3>
          <div class="relative" style="width:110px;height:110px">
            <svg viewBox="0 0 110 110" class="prog-ring" width="110" height="110">
              <circle cx="55" cy="55" r="46" fill="none" stroke="#F1F5F9" stroke-width="8"/>
              <circle cx="55" cy="55" r="46" fill="none" stroke="#0D9488" stroke-width="8" stroke-linecap="round" :stroke-dasharray="2*Math.PI*46" :stroke-dashoffset="2*Math.PI*46*(1-sleepScore/100)"/>
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center" style="transform:rotate(90deg)">
              <span class="m-val text-2xl" style="color:#0D9488">{{ sleepScore }}</span>
              <span class="text-[9px] text-slate-400">/100</span>
            </div>
          </div>
          <div class="text-[11px] font-semibold mt-2" style="color:#0D9488">{{ sleepScoreLabel }}</div>
        </div>

        <!-- 睡眠比例 -->
        <div class="card" style="padding:12px">
          <div class="flex items-center gap-1.5 mb-2"><div class="w-4 h-4 rounded bg-teal-50 flex items-center justify-center"><i class="fas fa-chart-pie text-teal-600" style="font-size:8px"></i></div><h3 class="font-bold text-xs">睡眠比例</h3></div>
          <div class="sleep-bar mb-2">
            <div :style="{width:sleepDeep/totalSleep*100+'%',background:'#0F766E'}"></div>
            <div :style="{width:sleepLight/totalSleep*100+'%',background:'#14B8A6'}"></div>
            <div :style="{width:sleepRem/totalSleep*100+'%',background:'#F59E0B'}"></div>
            <div :style="{width:sleepAwake/totalSleep*100+'%',background:'#EF4444'}"></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 8px">
            <div class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded" style="background:#0F766E"></span><span class="text-[9px] text-slate-500">深睡</span><span class="text-[11px] font-bold ml-auto">{{ sleepDeep }}h</span></div>
            <div class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded" style="background:#14B8A6"></span><span class="text-[9px] text-slate-500">浅睡</span><span class="text-[11px] font-bold ml-auto">{{ sleepLight }}h</span></div>
            <div class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded" style="background:#F59E0B"></span><span class="text-[9px] text-slate-500">REM</span><span class="text-[11px] font-bold ml-auto">{{ sleepRem }}h</span></div>
            <div class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded" style="background:#EF4444"></span><span class="text-[9px] text-slate-500">清醒</span><span class="text-[11px] font-bold ml-auto">{{ sleepAwake }}h</span></div>
          </div>
          <div class="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
            <span class="text-[9px] text-slate-400">总睡眠</span>
            <span class="m-val text-sm">{{(sleepDeep+sleepLight+sleepRem).toFixed(1)}}h</span>
          </div>
        </div>

        <!-- 睡眠记录 -->
        <div class="card" style="padding:12px;flex:1;min-height:0;display:flex;flex-direction:column">
          <div class="flex items-center gap-1.5 mb-2"><div class="w-4 h-4 rounded bg-blue-50 flex items-center justify-center"><i class="fas fa-clock-rotate-left text-blue-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">睡眠记录</h3></div>
          <div class="flex flex-col overflow-y-auto flex-1 min-h-0" style="margin:0 -4px;padding:0 4px">
            <div class="rec-row" v-for="(r,i) in sleepRecords" :key="i">
              <div class="flex-1 min-w-0">
                <div class="text-[11px] font-medium text-slate-700">{{r.date}}</div>
                <div class="text-[9px] text-slate-400">{{r.start}} - {{r.end}}</div>
              </div>
              <div class="text-right">
                <div class="m-val text-sm" :style="{color:r.score>=80?'#0D9488':r.score>=60?'#F97316':'#EF4444'}">{{r.score}}</div>
                <div class="text-[9px] text-slate-400">{{r.duration}}h</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="right-col">
        <!-- 睡眠时长趋势 -->
        <div class="card" style="padding:12px">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-violet-50 flex items-center justify-center"><i class="fas fa-chart-area text-violet-500" style="font-size:8px"></i></div><h3 class="font-bold text-xs">睡眠时长趋势</h3></div>
            <div class="flex gap-2 text-[9px]">
              <span class="flex items-center gap-0.5"><span class="w-2 h-2 rounded" style="background:#0F766E"></span>深睡</span>
              <span class="flex items-center gap-0.5"><span class="w-2 h-2 rounded" style="background:#14B8A6"></span>浅睡</span>
              <span class="flex items-center gap-0.5"><span class="w-2 h-2 rounded" style="background:#F59E0B"></span>REM</span>
              <span class="flex items-center gap-0.5"><span class="w-2 h-2 rounded" style="background:#EF4444"></span>清醒</span>
            </div>
          </div>
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
          </div>
        </div>

        <!-- Lissajous + 相位差 -->
        <div class="right-2col">
          <div class="card" style="padding:12px">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-1"><div class="w-4 h-4 rounded bg-indigo-50 flex items-center justify-center"><i class="fas fa-bezier-curve text-indigo-500" style="font-size:8px"></i></div><span class="font-bold text-[11px]">心肺相空间</span></div>
              <span class="text-[9px] text-slate-400">HR vs BR</span>
            </div>
            <div class="lissajous-chart">
              <svg viewBox="0 0 200 200">
                <circle cx="100" cy="100" r="70" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="100" cy="100" r="50" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="100" cy="100" r="30" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <polyline :points="lissajousPoints" fill="none" stroke="#6366F1" stroke-width="1.5" />
              </svg>
            </div>
          </div>
          <div class="card" style="padding:12px">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-1"><div class="w-4 h-4 rounded bg-violet-50 flex items-center justify-center"><i class="fas fa-circle-notch text-violet-500" style="font-size:8px"></i></div><span class="font-bold text-[11px]">相位差圆周</span></div>
              <span class="m-val text-sm" style="color:#6366F1">{{ healthData.phaseDiff }}°</span>
            </div>
            <div class="polar-chart">
              <svg viewBox="0 0 150 150">
                <circle cx="75" cy="75" r="60" fill="none" stroke="#e2e8f0" stroke-width="2" />
                <circle cx="75" cy="75" r="40" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="75" cy="75" r="20" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <circle cx="75" cy="75" r="55" fill="none" stroke="#6366F1" stroke-width="8" :stroke-dasharray="phaseDashArray" :stroke-dashoffset="-healthData.phaseDiff * 1.8" />
                <circle cx="75" cy="75" r="8" fill="#6366F1" />
              </svg>
            </div>
          </div>
        </div>

        <!-- PLV + 解读 -->
        <div class="right-2col">
          <div class="card" style="padding:12px;display:flex;flex-direction:column;align-items:center;justify-content:center">
            <h3 class="font-bold text-[11px] mb-2 self-start">相位锁定值</h3>
            <div class="relative" style="width:110px;height:110px">
              <svg viewBox="0 0 110 110" class="prog-ring" width="110" height="110">
                <circle cx="55" cy="55" r="44" fill="none" stroke="#F1F5F9" stroke-width="8"/>
                <circle cx="55" cy="55" r="44" fill="none" stroke="#6366F1" stroke-width="8" stroke-linecap="round" :stroke-dasharray="2*Math.PI*44" :stroke-dashoffset="2*Math.PI*44*(1-sleepPlv)"/>
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center" style="transform:rotate(90deg)">
                <span class="m-val text-xl" style="color:#6366F1">{{ sleepPlv }}</span>
              </div>
            </div>
            <div class="text-[9px] text-slate-400 mt-2">心肺耦合强度</div>
            <div class="text-[10px] font-semibold" style="color:#6366F1">强耦合</div>
          </div>
          <div class="card" style="padding:12px">
            <div class="flex items-center gap-1.5 mb-2"><div class="w-4 h-4 rounded bg-teal-50 flex items-center justify-center"><i class="fas fa-file-medical text-teal-600" style="font-size:8px"></i></div><h3 class="font-bold text-xs">解读与建议</h3></div>
            <div class="bg-teal-50/50 rounded-lg p-2.5 border border-teal-100 mb-2">
              <div class="text-[10px] font-semibold text-teal-800 mb-0.5">睡眠解读</div>
              <p class="text-[9px] text-teal-700 leading-relaxed">深睡占比{{(sleepDeep/totalSleep*100).toFixed(0)}}%，接近推荐水平。REM充足，心肺耦合强(PLV={{sleepPlv}})，自主神经调节良好。</p>
            </div>
            <div class="flex flex-col gap-1.5">
              <div class="adv-item" v-for="(a,i) in sleepAdvices" :key="i">
                <div class="w-5 h-5 rounded flex items-center justify-center shrink-0" :style="{background:a.bg}"><i :class="a.icon" style="font-size:8px" :style="{color:a.color}"></i></div>
                <div><div class="text-[10px] font-semibold text-slate-700">{{a.title}}</div><div class="text-[9px] text-slate-400">{{a.desc}}</div></div>
              </div>
            </div>
          </div>
        </div>
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
const currentTime = ref('');

const healthData = ref({ hr: 72, br: 16, cr: 4.5, brel: 15, signal: 'NORMAL', plv: 0.914, phaseDiff: 45, hrr: 38, brv: 12, hrSlope: 0.15 });

const emotion = ref({
  au: { emotion: '中性', color: '#8b949e', neutral: 60, positive: 25, negative: 15 },
  fer: { emotion: '积极', color: '#22c55e', neutral: 20, positive: 70, negative: 10 },
  fusion: { emotion: '积极', color: '#22c55e', neutral: 35, positive: 55, negative: 10 },
  stress: 45,
  analysis: { dominant: '平静', stability: '良好', volatility: '低' },
  suggestion: '今日情绪状态良好，建议保持积极心态，适当进行户外活动。',
  auScore: 0.65,
  ferScore: 0.58,
  fusionScore: 0.62
});

const snapshots = ref([
  { emoji: '😊', color: '#22c55e' },
  { emoji: '😐', color: '#eab308' },
  { emoji: '😔', color: '#ef4444' },
  { emoji: '😊', color: '#22c55e' },
  { emoji: '😐', color: '#eab308' }
]);

const sleepRecords = ref([
  { date: '今天', start: '23:15', end: '06:45', score: 82, duration: '7.5' },
  { date: '昨天', start: '22:50', end: '06:30', score: 78, duration: '7.7' },
  { date: '前天', start: '23:30', end: '07:00', score: 85, duration: '7.5' },
  { date: '3天前', start: '00:10', end: '07:15', score: 65, duration: '7.1' },
  { date: '4天前', start: '23:00', end: '06:50', score: 88, duration: '7.8' },
]);

const sleepScore = ref(82);
const sleepScoreLabel = computed(() => {
  if (sleepScore.value >= 85) return '优秀';
  if (sleepScore.value >= 70) return '良好';
  if (sleepScore.value >= 50) return '一般';
  return '较差';
});

const sleepDeep = ref(1.5);
const sleepLight = ref(3.2);
const sleepRem = ref(1.8);
const sleepAwake = ref(0.5);
const sleepPlv = ref(0.914);
const totalSleep = computed(() => sleepDeep.value + sleepLight.value + sleepRem.value + sleepAwake.value);

const cardioAdvices = ref([
  { title: '有氧运动', desc: '每日30分钟中等强度', icon: 'fas fa-running', bg: '#F0FDFA', color: '#0D9488' },
  { title: '深呼吸', desc: '腹式呼吸每天5分钟', icon: 'fas fa-wind', bg: '#FFF7ED', color: '#F97316' },
  { title: '充足睡眠', desc: '7-9小时优质睡眠', icon: 'fas fa-bed', bg: '#EFF6FF', color: '#3B82F6' },
]);

const sleepAdvices = ref([
  { title: '固定作息', desc: '同一时间入睡起床', icon: 'fas fa-clock', bg: '#F0FDFA', color: '#0D9488' },
  { title: '睡前放松', desc: '避免蓝光刺激', icon: 'fas fa-book-open', bg: '#FFF7ED', color: '#F97316' },
]);

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

const pressureColor = computed(() => {
  const s = emotion.value.stress;
  if (s < 30) return '#10B981';
  if (s < 60) return '#F97316';
  return '#EF4444';
});

const pressureLabel = computed(() => {
  const s = emotion.value.stress;
  if (s < 30) return '放松';
  if (s < 50) return '轻度压力';
  if (s < 70) return '中度压力';
  return '高度压力';
});

const crColor = computed(() => {
  const cr = healthData.value.cr;
  if (cr < 4) return '#10B981';
  if (cr <= 6) return '#0D9488';
  return '#F97316';
});

const crProgress = computed(() => {
  const cr = Math.min(Math.max(healthData.value.cr, 2), 8);
  const percentage = (cr - 2) / 6 * 100;
  const circumference = Math.PI * 120;
  return `${percentage / 100 * circumference} ${circumference}`;
});

const crOffset = computed(() => 0);

const crNeedleAngle = computed(() => {
  const cr = Math.min(Math.max(healthData.value.cr, 2), 8);
  return Math.PI + (cr - 2) / 6 * Math.PI;
});

const crNeedleX = computed(() => 80 + Math.cos(crNeedleAngle.value) * 42);
const crNeedleY = computed(() => 80 + Math.sin(crNeedleAngle.value) * 42);

const brelColor = computed(() => {
  const brel = healthData.value.brel;
  if (brel < 30) return '#10B981';
  if (brel < 60) return '#F97316';
  return '#EF4444';
});

const brelProgress = computed(() => {
  const brel = Math.min(Math.max(healthData.value.brel, 0), 100);
  const circumference = Math.PI * 120;
  return `${brel / 100 * circumference} ${circumference}`;
});

const brelOffset = computed(() => 0);

const brelNeedleAngle = computed(() => {
  const brel = Math.min(Math.max(healthData.value.brel, 0), 100);
  return Math.PI + brel / 100 * Math.PI;
});

const brelNeedleX = computed(() => 80 + Math.cos(brelNeedleAngle.value) * 42);
const brelNeedleY = computed(() => 80 + Math.sin(brelNeedleAngle.value) * 42);

const phaseDashArray = computed(() => {
  const phase = healthData.value.phaseDiff;
  const circumference = Math.PI * 110;
  const arcLength = (phase / 360) * circumference;
  return `${arcLength} ${circumference}`;
});

const switchTab = (tab) => {
  activeTab.value = tab;
};

const updateTime = () => {
  currentTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

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
  updateTime();
  intervalId = setInterval(fetchData, 1000);
  setInterval(updateTime, 1000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
});
</script>

<style scoped>
.page-root {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #ffffff;
}

.split {
  background: #ffffff;
}

.page-header {
  flex-shrink: 0;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
}

.page-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px 12px;
  min-height: 0;
}

.tab-btn {
  padding: 8px 18px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 16px;
  cursor: pointer;
  border: none;
  background: transparent;
  color: #64748B;
  transition: all .2s;
  font-family: 'Space Grotesk', sans-serif;
}

.tab-btn:hover {
  color: #0F766E;
  background: #F0FDFA;
}

.tab-btn.active {
  background: #0D9488;
  color: #fff;
  box-shadow: 0 2px 6px rgba(13, 148, 136, .25);
}

.live-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .4px;
  background: #FEF2F2;
  color: #EF4444;
}

.pulse-d {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .5; transform: scale(1.2); }
}

.split {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 12px;
  height: 100%;
}

.left-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  padding-right: 2px;
}

.right-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  padding-right: 2px;
}

.right-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #E8ECF0;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .03);
  transition: box-shadow .25s, transform .25s;
}

.card:hover {
  box-shadow: 0 4px 14px rgba(0, 0, 0, .05);
  transform: translateY(-1px);
}

.m-label {
  font-size: 10px;
  color: #94A3B8;
  font-weight: 500;
  letter-spacing: .2px;
}

.m-val {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  color: #1E293B;
}

.m-unit {
  font-size: 10px;
  color: #94A3B8;
  font-weight: 400;
  margin-left: 1px;
}

.mini-st {
  background: #F8FAFB;
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid #F1F5F9;
  transition: all .2s;
}

.mini-st:hover {
  background: #F0FDFA;
  border-color: #CCFBF1;
}

.prog-bar {
  height: 5px;
  border-radius: 3px;
  background: #E2E8F0;
  overflow: hidden;
}

.prog-fill {
  height: 100%;
  border-radius: 3px;
  transition: width .8s ease;
}

.emo-bar {
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  display: flex;
  background: #F1F5F9;
}

.per-btn {
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid #E8ECF0;
  background: #fff;
  color: #64748B;
  transition: all .2s;
}

.per-btn:hover {
  border-color: #0D9488;
  color: #0D9488;
}

.per-btn.active {
  background: #0D9488;
  color: #fff;
  border-color: #0D9488;
}

.vid-box {
  background: linear-gradient(135deg, #1E293B, #334155, #1E293B);
  border-radius: 10px;
  position: relative;
  overflow: hidden;
}

.vid-box::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 40%, rgba(13, 148, 136, .12) 0%, transparent 70%);
}

.scan-ln {
  position: absolute;
  left: 0;
  right: 0;
  height: 1.5px;
  background: linear-gradient(90deg, transparent, rgba(13, 148, 136, .35), transparent);
  animation: scanline 3s linear infinite;
}

@keyframes scanline {
  0% { top: -10%; }
  100% { top: 110%; }
}

.sleep-bar {
  display: flex;
  border-radius: 6px;
  overflow: hidden;
  height: 24px;
}

.sleep-bar>div {
  transition: width .6s ease;
}

.rec-row {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-radius: 8px;
  transition: all .15s;
  border-bottom: 1px solid #F8FAFC;
}

.rec-row:last-child {
  border-bottom: none;
}

.rec-row:hover {
  background: #F8FAFB;
}

.adv-item {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #F8FAFB;
  border: 1px solid #F1F5F9;
  transition: all .2s;
}

.adv-item:hover {
  background: #F0FDFA;
  border-color: #CCFBF1;
}

.prog-ring {
  transform: rotate(-90deg);
}

.fade-up {
  animation: fadeUp .35s ease forwards;
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.gauge-container {
  margin: 10px 0;
}

.wave-chart {
  height: 120px;
  background: #f8fafc;
  border-radius: 10px;
}

.wave-chart svg {
  width: 100%;
  height: 100%;
}

.lissajous-chart {
  height: 180px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.polar-chart {
  margin-top: 10px;
}

.trend-chart {
  height: 130px;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 15px;
  height: 100%;
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

.chart-bar.hr-bar {
  background: linear-gradient(to top, #0D9488, #2DD4BF);
}

.chart-bar.sleep-bar {
  background: linear-gradient(to top, #0F766E, #14B8A6);
}

.bar-value {
  position: absolute;
  top: -25px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 14px;
  font-weight: bold;
  color: #333;
}

.stacked-bars {
  display: flex;
  gap: 10px;
  height: 140px;
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

.stacked-bar.neutral {
  background: #94A3B8;
}

.stacked-bar.positive {
  background: #10B981;
}

.stacked-bar.negative {
  background: #EF4444;
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