<template>
  <div class="page-root">
    <!-- 顶部导航 -->
    <header class="page-header">
      <div class="flex items-center gap-2">
        <span style="font-size:24px;font-weight:800;color:#1E293B">健康中心</span>
      </div>
      <div class="flex items-center">
        <button class="tab-btn" :class="{active:activeTab==='cardio'}" @click="switchTab('cardio')" style="margin-right: 32px;"><i class="fas fa-lungs" style="font-size:24px; margin-right: 12px;"></i>心肺健康</button>
        <button class="tab-btn" :class="{active:activeTab==='emotion'}" @click="switchTab('emotion')" style="margin-right: 32px;"><i class="fas fa-brain" style="font-size:24px; margin-right: 12px;"></i>情绪健康</button>
        <button class="tab-btn" :class="{active:activeTab==='sleep'}" @click="switchTab('sleep')"><i class="fas fa-moon" style="font-size:24px; margin-right: 12px;"></i>睡眠健康</button>
      </div>
      <div class="flex items-center gap-2">
        <span style="font-size:16px;font-weight:700;color:#64748B">{{currentTime}}</span>
      </div>
    </header>

    <!-- 心肺健康 -->
    <section v-show="activeTab=='cardio'" class="split fade-up">
      <!-- 左侧面板 -->
      <div class="left-col" style="margin-top:20px">
        <!-- 实时数据 -->
        <div class="card" style="padding:16px">
          <h3 style="font-size:18px;font-weight:700;margin-bottom:16px;color:#1E293B">实时数据</h3>
          <div style="display:flex;flex-direction:column;gap:12px">
            <!-- 心率卡片 -->
            <div class="mini-st" style="display:flex;align-items:center;justify-content:space-between;padding:16px;height:55px">
              <span style="font-size:18px;font-weight:600;color:#64748B">心率</span>
              <span style="font-size:36px;font-weight:700;color:#0D9488">{{ healthData.hr }}</span>
              <span style="font-size:18px;color:#94A3B8">bpm</span>
            </div>
            <!-- 呼吸率卡片 -->
            <div class="mini-st" style="display:flex;align-items:center;justify-content:space-between;padding:16px;height:55px">
              <span style="font-size:18px;font-weight:600;color:#64748B">呼吸率</span>
              <span style="font-size:36px;font-weight:700;color:#F97316">{{ healthData.br }}</span>
              <span style="font-size:18px;color:#94A3B8">/min</span>
            </div>
            <!-- 心肺频率比指针 -->
            <div class="card" style="padding:12px;height:180px">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
                <h3 style="font-size:18px;font-weight:700;color:#1E293B">心肺频率比</h3>
                <span style="padding:0px 12px;border-radius:16px;font-size:14px;font-weight:600" :style="getCrStatusStyle()">
                  {{ getCrStatus() }}
                </span>
              </div>
              <div style="display:flex;flex-direction:column;align-items:center">
                <div class="gauge-container">
                  <svg viewBox="0 0 160 88" width="160" height="88">
                    <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#E2E8F0" stroke-width="10" stroke-linecap="round"/>
                    <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" :stroke="crColor" stroke-width="10" stroke-linecap="round" :stroke-dasharray="crProgress" :stroke-dashoffset="crOffset"/>
                    <line x1="80" y1="80" :x2="crNeedleX" :y2="crNeedleY" stroke="#1E293B" stroke-width="2" stroke-linecap="round"/>
                    <circle cx="80" cy="80" r="3" fill="#1E293B"/>
                  </svg>
                </div>
                <div class="m-val text-3xl mt-1" style="color:#0D9488">{{ healthData.cr }}</div>
              </div>
            </div>
            <!-- 呼吸急促度指针 -->
            <div class="card" style="padding:12px;height:180px">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
                <h3 style="font-size:18px;font-weight:700;color:#1E293B">呼吸急促度</h3>
                <span style="padding:0px 12px;border-radius:16px;font-size:14px;font-weight:600" :style="getBrelStatusStyle()">
                  {{ getBrelStatus() }}
                </span>
              </div>
              <div style="display:flex;flex-direction:column;align-items:center">
                <div class="gauge-container">
                  <svg viewBox="0 0 160 88" width="160" height="88">
                    <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#E2E8F0" stroke-width="10" stroke-linecap="round"/>
                    <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" :stroke="brelColor" stroke-width="10" stroke-linecap="round" :stroke-dasharray="brelProgress" :stroke-dashoffset="brelOffset"/>
                    <line x1="80" y1="80" :x2="brelNeedleX" :y2="brelNeedleY" stroke="#1E293B" stroke-width="2" stroke-linecap="round"/>
                    <circle cx="80" cy="80" r="3" fill="#1E293B"/>
                  </svg>
                </div>
                <div class="m-val text-3xl mt-1" :style="{color:brelColor}">{{ healthData.brel }}%</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧面板 -->
      <div class="right-col" style="margin-top:20px">
        <!-- 健康趋势 -->
        <div class="card" style="padding:20px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div style="font-size:17px;font-weight:700;color:#1E293B">健康趋势</div>
            <div style="display:flex;gap:6px">
              <button class="tab-btn2" :class="{active:period==='day'}" @click="period='day'">日</button>
              <button class="tab-btn2" :class="{active:period==='week'}" @click="period='week'">周</button>
              <button class="tab-btn2" :class="{active:period==='year'}" @click="period='year'">年</button>
            </div>
          </div>
          <div style="height:215px;position:relative">
            <canvas ref="chartCanvas"></canvas>
          </div>
          <div id="stats" style="display:flex;gap:12px;margin-top:12px"></div>
        </div>

        <!-- 健康指南 -->
        <div class="card" style="padding:15px">
          <h3 style="font-size:18px;font-weight:700;margin-bottom:10px;color:#1E293B">健康指南</h3>
          <div style="display:flex;gap:16px">
            <div class="card" style="flex:1;padding:16px;display:flex;flex-direction:column;align-items:center">
              <div style="width:70px;height:70px;margin-bottom:10px">
                <svg viewBox="0 0 80 80">
                  <circle cx="40" cy="40" r="35" fill="none" stroke="#E2E8F0" stroke-width="6"/>
                  <circle cx="40" cy="40" r="35" fill="none" stroke="#0D9488" stroke-width="6" stroke-linecap="round" :stroke-dasharray="220" :stroke-dashoffset="220*(1-0.75)"/>
                  <text x="40" y="46" text-anchor="middle" font-size="18" font-weight="700" fill="#1E293B">75%</text>
                </svg>
              </div>
              <div style="font-size:15px;font-weight:600;color:#1E293B;margin-bottom:4px">有氧运动</div>
              <div style="font-size:11px;color:#64748B;text-align:center">每日30分钟中等强度</div>
            </div>
            <div class="card" style="flex:1;padding:16px;display:flex;flex-direction:column;align-items:center">
              <div style="width:70px;height:70px;margin-bottom:10px">
                <svg viewBox="0 0 80 80">
                  <circle cx="40" cy="40" r="35" fill="none" stroke="#E2E8F0" stroke-width="6"/>
                  <circle cx="40" cy="40" r="35" fill="none" stroke="#F97316" stroke-width="6" stroke-linecap="round" :stroke-dasharray="220" :stroke-dashoffset="220*(1-0.6)"/>
                  <text x="40" y="46" text-anchor="middle" font-size="18" font-weight="700" fill="#1E293B">60%</text>
                </svg>
              </div>
              <div style="font-size:15px;font-weight:600;color:#1E293B;margin-bottom:4px">深呼吸</div>
              <div style="font-size:11px;color:#64748B;text-align:center">腹式呼吸每天5分钟</div>
            </div>
            <div class="card" style="flex:1;padding:16px;display:flex;flex-direction:column;align-items:center">
              <div style="width:70px;height:70px;margin-bottom:10px">
                <svg viewBox="0 0 80 80">
                  <circle cx="40" cy="40" r="35" fill="none" stroke="#E2E8F0" stroke-width="6"/>
                  <circle cx="40" cy="40" r="35" fill="none" stroke="#3B82F6" stroke-width="6" stroke-linecap="round" :stroke-dasharray="220" :stroke-dashoffset="220*(1-0.85)"/>
                  <text x="40" y="46" text-anchor="middle" font-size="18" font-weight="700" fill="#1E293B">85%</text>
                </svg>
              </div>
              <div style="font-size:15px;font-weight:600;color:#1E293B;margin-bottom:4px">充足睡眠</div>
              <div style="font-size:11px;color:#64748B;text-align:center">7-9小时优质睡眠</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 情绪健康 -->
    <section v-show="activeTab=='emotion'" class="split fade-up" style="margin-top:20px">
      <div class="left-col">
        <!-- 实时情绪 -->
        <div class="card emotion-card" style="padding:16px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <span style="font-size:16px;font-weight:600;color:#1E293B">实时情绪</span>
            <div style="display:flex;align-items:center;gap:12px">
              <span :style="{color:personDetected?'#10B981':'#94A3B8',fontSize:'16px',fontWeight:'600'}">
                {{ personDetected ? '有人' : '无人' }}
              </span>
            </div>
          </div>
          <div class="emo-bar" style="height:12px;margin-bottom:12px">
            <div :style="{width:(fusionEmotion.positive||emotion.fusion.positive)+'%',background:'#10B981'}"></div>
            <div :style="{width:(fusionEmotion.neutral||emotion.fusion.neutral)+'%',background:'#94A3B8'}"></div>
            <div :style="{width:(fusionEmotion.negative||emotion.fusion.negative)+'%',background:'#EF4444'}"></div>
          </div>
          <div style="display:flex;align-items:center;justify-content:center">
            <span style="font-size:14px;color:#64748B;margin-right:4px">积极:</span>
            <span style="font-size:28px;color:#10B981;font-weight:700">{{ personDetected ? ((fusionEmotion.positive||emotion.fusion.positive)).toFixed(0) + '%' : '--' }}</span>
          </div>
        </div>

        <!-- 压力值 -->
        <div class="card" style="padding:12px;height:200px;display:flex;flex-direction:column;align-items:center">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;align-self:stretch">
            <h3 style="font-size:18px;font-weight:700;color:#1E293B">压力值</h3>
            <span style="padding:4px 12px;border-radius:16px;font-size:14px;font-weight:600" :style="getStressStatusStyle()">
              {{ getStressStatus() }}
            </span>
          </div>
          <div class="gauge-container">
            <svg viewBox="0 0 160 88" width="160" height="88">
              <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#E2E8F0" stroke-width="10" stroke-linecap="round"/>
              <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" :stroke="pressureColor" stroke-width="10" stroke-linecap="round" :stroke-dasharray="stressProgress" :stroke-dashoffset="stressOffset"/>
              <line x1="80" y1="80" :x2="stressNeedleX" :y2="stressNeedleY" stroke="#1E293B" stroke-width="2" stroke-linecap="round"/>
              <circle cx="80" cy="80" r="3" fill="#1E293B"/>
            </svg>
          </div>
          <div class="m-val text-3xl mt-1" :style="{color:pressureColor}">{{ emotion.stress }}</div>
        </div>

        <!-- 视频流 -->
        <div class="card" style="padding:10px">
          <h3 style="font-size:18px;font-weight:700;margin-bottom:12px;color:#1E293B">视频流</h3>
          <div style="height:170px;background:#F1F5F9;display:flex;align-items:center;justify-content:center;border-radius:8px;overflow:hidden">
            <img src="http://192.168.137.25:8080/video" style="width:100%;height:100%;object-fit:cover" @error="e=>{e.target.style.display='none';e.target.nextElementSibling.style.display='flex'}" onerror="this.style.display='none'">
            <div style="display:none;flex-direction:column;align-items:center;justify-content:center;color:#94A3B8">
              <i class="fas fa-video text-2xl mb-2"></i>
              <span style="font-size:14px">未连接</span>
            </div>
          </div>
        </div>
      </div>

      <div class="right-col">
        <!-- 情绪趋势 - 只有日、周、年 -->
        <div class="card" style="padding:20px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div style="font-size:17px;font-weight:700;color:#1E293B">情绪趋势</div>
            <div style="display:flex;align-items:center;gap:16px">
              <div style="display:flex;align-items:center;gap:8px">
                <div style="display:flex;align-items:center;gap:4px">
                  <span style="display:inline-block;width:20px;height:2px;background:#10B981"></span>
                  <span style="font-size:12px;color:#64748B">积极</span>
                </div>
                <div style="display:flex;align-items:center;gap:4px">
                  <span style="display:inline-block;width:20px;height:2px;background:#94A3B8;border-style:dashed;border-width:2px;border-bottom:none"></span>
                  <span style="font-size:12px;color:#64748B">压力</span>
                </div>
              </div>
              <div style="display:flex;gap:6px">
                <button class="tab-btn2" :class="{active:emoPeriod==='day'}" @click="emoPeriod='day'">日</button>
                <button class="tab-btn2" :class="{active:emoPeriod==='week'}" @click="emoPeriod='week'">周</button>
                <button class="tab-btn2" :class="{active:emoPeriod==='year'}" @click="emoPeriod='year'">年</button>
              </div>
            </div>
          </div>
          <div style="height:200px;position:relative">
            <canvas ref="emotionChartCanvas"></canvas>
          </div>
          <div id="emotionStats" style="display:flex;gap:12px;margin-top:12px"></div>
        </div>

        <!-- 情绪分析 -->
        <div class="card" style="padding:20px">
          <h3 style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:16px">情绪分析</h3>
          <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:16px">
            <div class="mini-st" style="padding:12px;display:flex;align-items:center;justify-content:space-between">
              <span style="font-size:14px;color:#64748B">主导</span>
              <span style="font-size:20px;font-weight:700;color:#0D9488">{{ emotion.analysis.dominant }}</span>
            </div>
            <div class="mini-st" style="padding:12px;display:flex;align-items:center;justify-content:space-between">
              <span style="font-size:14px;color:#64748B">稳定性</span>
              <span style="font-size:20px;font-weight:700;color:#10B981">{{ emotion.analysis.stability }}</span>
            </div>
            <div class="mini-st" style="padding:12px;display:flex;align-items:center;justify-content:space-between">
              <span style="font-size:14px;color:#64748B">波动</span>
              <span style="font-size:20px;font-weight:700;color:#F97316">{{ emotion.analysis.volatility }}</span>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:16px;padding:10px 12px;background:#f8f8f8;border-radius:10px">
            <span style="font-size:14px;font-weight:600;color:#1E293B">建议</span>
            <div class="adv-item" style="padding:0"><i class="fas fa-spa text-teal-500" style="font-size:16px"></i><span style="font-size:14px;color:#475569">深呼吸练习维持情绪稳定</span></div>
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
import { ref, computed, onMounted, onUnmounted, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { watch } from 'vue'
import systemStore from '../core/systemStore.js';

const router = useRouter();
const HLKK_PORT = 5020;
const activeTab = ref('cardio');
const period = ref('day');
const emoPeriod = ref('day');
const currentTime = ref('');

// SystemStore 数据
const systemState = ref({});
let unsubscribeStore = null;

// 从 SystemStore 获取的感知数据
const perception = computed(() => systemState.value.perception || {});
const personDetected = computed(() => perception.value.personDetected || false);
const faceData = computed(() => perception.value.face || {});
const fusionEmotion = computed(() => faceData.value.fusion || {});

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

// 心肺频率比状态和样式
const getCrStatus = () => {
  if (healthData.value.cr < 4) return '偏低';
  if (healthData.value.cr <= 6) return '正常';
  return '偏高';
};

const getCrStatusStyle = () => {
  if (healthData.value.cr < 4) return { backgroundColor: '#F0FDFA', color: '#0D9488' };
  if (healthData.value.cr <= 6) return { backgroundColor: '#F0FDFA', color: '#0D9488' };
  return { backgroundColor: '#FFF7ED', color: '#F97316' };
};

// 呼吸急促度状态和样式
const getBrelStatus = () => {
  if (healthData.value.brel < 30) return '平稳';
  if (healthData.value.brel < 60) return '轻度';
  return '急促';
};

const getBrelStatusStyle = () => {
  if (healthData.value.brel < 30) return { backgroundColor: '#F0FDFA', color: '#0D9488' };
  if (healthData.value.brel < 60) return { backgroundColor: '#FFF7ED', color: '#F97316' };
  return { backgroundColor: '#FEF2F2', color: '#EF4444' };
};

// 趋势数据
const chartCanvas = ref(null);
let chart = null;
let ChartLoaded = ref(null);

const trendData = {
  day: {
    labels: Array.from({length:24},(_,i)=>`${String(i).padStart(2,'0')}:00`),
    values: [1.05,1.02,0.98,0.95,0.92,0.88,0.96,1.10,1.22,1.18,1.30,1.28,1.15,1.32,1.45,1.62,1.55,1.40,1.28,1.18,1.35,1.48,1.25,1.10],
    stats: [{val:'1.18',lab:'平均值'},{val:'1.62',lab:'最高值'},{val:'2.5h',lab:'异常时长'}]
  },
  week: {
    labels: ['周一','周二','周三','周四','周五','周六','周日'],
    normal: [18,20,16,22,19,14,21],
    abnormal: [3,2,5,1,3,6,2],
    stats: [{val:'130',lab:'正常总次数'},{val:'22',lab:'异常总次数'},{val:'周六',lab:'异常最多'}]
  },
  year: {
    labels: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
    normal: [520,480,510,540,560,530,500,490,550,570,540,530],
    abnormal: [45,52,38,30,25,35,48,55,28,22,32,38],
    stats: [{val:'6,320',lab:'年度正常'},{val:'448',lab:'年度异常'},{val:'10月',lab:'最健康月份'}]
  }
};

const MIN = 0.8, MAX = 1.5;

async function loadChart() {
  if (typeof window !== 'undefined' && !ChartLoaded.value) {
    return new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = '/js/chart.min.js';
      script.onload = () => {
        ChartLoaded.value = true;
        resolve(window.Chart);
      };
      document.head.appendChild(script);
    });
  }
  return window.Chart;
}

async function renderChart(tab) {
  if (chart) chart.destroy();
  const ctx = chartCanvas.value?.getContext('2d');
  if (!ctx) return;
  
  const Chart = await loadChart();
  if (!Chart) return;
  
  const d = trendData[tab];
  
  if (tab === 'day') {
    const points = d.values.map(v => (v < MIN || v > MAX) ? 4 : 0);
    const pColor = d.values.map(v => (v < MIN || v > MAX) ? '#f0654a' : '#0D9488');
    const grad = ctx.createLinearGradient(0,0,0,200);
    grad.addColorStop(0,'rgba(13,148,136,0.15)');
    grad.addColorStop(1,'rgba(13,148,136,0)');

    chart = new Chart(ctx, {
      type:'line',
      data:{
        labels: d.labels,
        datasets:[{
          data: d.values, borderColor:'#0D9488', borderWidth:2,
          backgroundColor: grad, fill:true, tension:0.4,
          pointRadius: points, pointBackgroundColor: pColor,
          pointBorderColor: pColor, pointHoverRadius:5
        }]
      },
      options: lineOpts(),
      plugins:[rangePlugin]
    });
  } else {
    chart = new Chart(ctx, {
      type:'bar',
      data:{
        labels: d.labels,
        datasets:[
          {label:'正常',data:d.normal,backgroundColor:'rgba(13,148,136,0.7)',borderRadius:4,barPercentage:0.6},
          {label:'异常',data:d.abnormal,backgroundColor:'rgba(240,101,74,0.7)',borderRadius:4,barPercentage:0.6}
        ]
      },
      options:{
        responsive:true,maintainAspectRatio:false,
        animation:{duration:500},
        plugins:{
          legend:{position:'top',align:'end',labels:{font:{size:11},boxWidth:10,padding:10}},
          tooltip:{backgroundColor:'#fff',titleColor:'#333',bodyColor:'#333',borderColor:'#eee',borderWidth:1,cornerRadius:6,padding:8}
        },
        scales:{
          x:{stacked:true,grid:{display:false},ticks:{color:'#aaa',font:{size:10}},border:{display:false}},
          y:{stacked:true,beginAtZero:true,grid:{color:'rgba(0,0,0,0.04)'},ticks:{color:'#aaa',font:{size:10}},border:{display:false}}
        }
      }
    });
  }
  
  renderStats(tab);
}

function lineOpts() {
  return {
    responsive:true, maintainAspectRatio:false,
    animation:{duration:500},
    plugins:{legend:{display:false},tooltip:{
      backgroundColor:'#fff', titleColor:'#333', bodyColor:'#333',
      borderColor:'#eee', borderWidth:1, cornerRadius:6, padding:8
    }},
    scales:{
      x:{grid:{color:'rgba(0,0,0,0.04)'},ticks:{color:'#aaa',font:{size:10},maxTicksLimit:8},border:{display:false}},
      y:{min:0.5,max:2.0,grid:{color:'rgba(0,0,0,0.04)'},ticks:{color:'#aaa',font:{size:10}},border:{display:false}}
    }
  };
}

const rangePlugin = {
  beforeDraw(c) {
    const {ctx:c2,chartArea:{left,right},scales:{y}} = c;
    const yT = y.getPixelForValue(MAX), yB = y.getPixelForValue(MIN);
    c2.save();
    c2.fillStyle = 'rgba(13,148,136,0.04)';
    c2.fillRect(left, yT, right-left, yB-yT);
    c2.setLineDash([5,3]);
    c2.strokeStyle = 'rgba(200,170,50,0.3)';
    c2.lineWidth = 1;
    [yT,yB].forEach(yy => { c2.beginPath(); c2.moveTo(left,yy); c2.lineTo(right,yy); c2.stroke(); });
    c2.restore();
  }
};

function renderStats(tab) {
  document.getElementById('stats').innerHTML = trendData[tab].stats.map(s =>
    `<div style="flex:1;background:#f8f8f8;border-radius:10px;padding:10px 16px;display:flex;align-items:center;justify-content:space-between">
      <div style="font-size:14px;color:#999">${s.lab}</div>
      <div style="font-size:20px;font-weight:700;color:#1E293B">${s.val}</div>
    </div>`
  ).join('');
}

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

// 压力值仪表盘
const stressProgress = computed(() => {
  const stress = Math.min(Math.max(emotion.value.stress, 0), 100);
  const circumference = Math.PI * 120;
  return `${stress / 100 * circumference} ${circumference}`;
});

const stressOffset = computed(() => 0);

const stressNeedleAngle = computed(() => {
  const stress = Math.min(Math.max(emotion.value.stress, 0), 100);
  return Math.PI + stress / 100 * Math.PI;
});

const stressNeedleX = computed(() => 80 + Math.cos(stressNeedleAngle.value) * 42);
const stressNeedleY = computed(() => 80 + Math.sin(stressNeedleAngle.value) * 42);

// 主导情绪
const dominantEmotion = computed(() => {
  const p = emotion.value.fusion;
  if (p.positive >= p.neutral && p.positive >= p.negative) return '积极';
  if (p.neutral >= p.positive && p.neutral >= p.negative) return '中性';
  return '消极';
});

const dominantEmotionColor = computed(() => {
  const e = dominantEmotion.value;
  if (e === '积极') return '#10B981';
  if (e === '中性') return '#94A3B8';
  return '#EF4444';
});

// 压力状态
const getStressStatus = () => {
  const stress = emotion.value.stress;
  if (stress < 30) return '偏低';
  if (stress < 60) return '正常';
  return '偏高';
};

const getStressStatusStyle = () => {
  const status = getStressStatus();
  let bg, color;
  if (status === '偏低') { bg = '#ECFDF5'; color = '#10B981'; }
  else if (status === '正常') { bg = '#F0FDF9'; color = '#0D9488'; }
  else { bg = '#FEF3F2'; color = '#EF4444'; }
  return { backgroundColor: bg, color };
};

// 情绪趋势图表
const emotionChartCanvas = ref(null);
let emotionChart = null;

const emotionTrendData = {
  day: {
    labels: ['0:00','03:00','06:00','09:00','12:00','15:00','18:00','21:00','24:00'],
    positive: [45,52,48,55,62,58,50,48,46],
    stress: [42,38,45,52,48,55,40,35,38],
    stats: [{val:'良好',lab:'整体状态'},{val:'52%',lab:'平均积极'},{val:'15:00',lab:'最佳时段'}]
  },
  week: {
    labels: ['周一','周二','周三','周四','周五','周六','周日'],
    positive: [45,52,48,55,62,58,50],
    stress: [42,38,45,52,48,55,40],
    stats: [{val:'130',lab:'样本数'},{val:'51%',lab:'平均积极'},{val:'周五',lab:'最佳日'}]
  },
  year: {
    labels: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
    positive: [42,48,52,58,62,65,68,65,58,52,48,45],
    stress: [48,42,38,35,32,30,28,32,38,42,45,48],
    stats: [{val:'6,320',lab:'年度样本'},{val:'54%',lab:'平均积极'},{val:'7月',lab:'最佳月'}]
  }
};

const renderEmotionChart = async (period) => {
  if (emotionChart) emotionChart.destroy();
  const ctx = emotionChartCanvas.value?.getContext('2d');
  if (!ctx) return;
  
  const Chart = await loadChart();
  if (!Chart) return;
  
  const d = emotionTrendData[period];
  
  emotionChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.labels,
      datasets: [
        { 
          label: '积极', 
          data: d.positive, 
          borderColor: '#10B981', 
          backgroundColor: 'rgba(16,185,129,0.1)', 
          tension: 0.4, 
          fill: true, 
          pointRadius: 0,
          borderWidth: 2
        },
        { 
          label: '压力', 
          data: d.stress, 
          borderColor: '#94A3B8', 
          backgroundColor: 'transparent', 
          tension: 0.4, 
          fill: false, 
          pointRadius: 0,
          borderWidth: 2,
          borderDash: [5, 5]
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { 
        x: { grid: { display: false }, ticks: { color: '#aaa', font: { size: 10 } }, border: { display: false } }, 
        y: { beginAtZero: true, max: 100, grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { color: '#aaa', font: { size: 10 } }, border: { display: false } } 
      }
    }
  });
  
  renderEmotionStats(period);
};

const renderEmotionStats = (period) => {
  const el = document.getElementById('emotionStats');
  if (!el) return;
  el.innerHTML = emotionTrendData[period].stats.map(s => `
    <div style="flex:1;background:#f8f8f8;border-radius:10px;padding:10px 16px;display:flex;align-items:center;justify-content:space-between">
      <div style="font-size:14px;color:#999">${s.lab}</div>
      <div style="font-size:20px;font-weight:700;color:#1E293B">${s.val}</div>
    </div>
  `).join('');
};

watch(emoPeriod, (newVal) => {
  renderEmotionChart(newVal);
});

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

watch(period, (newVal) => {
  renderChart(newVal);
});

onMounted(async () => {
  fetchData();
  updateTime();
  intervalId = setInterval(fetchData, 1000);
  setInterval(updateTime, 1000);
  
  // 订阅 SystemStore
  unsubscribeStore = systemStore.subscribe((state) => {
    systemState.value = state;
  });
  
  setTimeout(() => {
    renderChart('day');
    renderEmotionChart('day');
  }, 300);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
  if (unsubscribeStore) unsubscribeStore();
  if (chart) chart.destroy();
  if (emotionChart) emotionChart.destroy();
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
  padding: 4px 20px;
  margin: 0;
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

.tab-btn2 {
  padding: 6px 18px;
  border: none;
  background: #f0f0f0;
  color: #888;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all .2s;
}
.tab-btn2.active {
  background: #0D9488;
  color: #fff;
}

.tab-btn {
  padding: 12px 24px;
  border-radius: 10px;
  font-weight: 600;
  font-size: 20px;
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

.emotion-card {
  min-height: 140px;
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