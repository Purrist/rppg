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
              <span style="font-size:36px;font-weight:700;color:#0D9488">{{ jsonHealthData.hr }}</span>
              <span style="font-size:18px;color:#94A3B8">bpm</span>
            </div>
            <!-- 呼吸率卡片 -->
            <div class="mini-st" style="display:flex;align-items:center;justify-content:space-between;padding:16px;height:55px">
              <span style="font-size:18px;font-weight:600;color:#64748B">呼吸率</span>
              <span style="font-size:36px;font-weight:700;color:#F97316">{{ jsonHealthData.br }}</span>
              <span style="font-size:18px;color:#94A3B8">/min</span>
            </div>
            <!-- 心肺频率比指针 -->
            <div class="card" style="padding:12px;height:180px">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
                <h3 style="font-size:18px;font-weight:700;color:#1E293B">心肺频率比</h3>
                <span style="padding:0px 12px;border-radius:16px;font-size:14px;font-weight:600" :style="getCrStatusStyle()">
                  {{ jsonHealthData.cr_label || getCrStatus() }}
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
                <div class="m-val text-3xl mt-1" style="color:#0D9488">{{ jsonHealthData.cr > 0 ? jsonHealthData.cr.toFixed(1) : healthData.cr }}</div>
              </div>
            </div>
            <!-- 呼吸急促度指针 -->
            <div class="card" style="padding:12px;height:180px">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
                <h3 style="font-size:18px;font-weight:700;color:#1E293B">呼吸急促度</h3>
                <span style="padding:0px 12px;border-radius:16px;font-size:14px;font-weight:600" :style="getBrelStatusStyle()">
                  {{ jsonHealthData.brel_label || getBrelStatus() }}
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
                <div class="m-val text-3xl mt-1" :style="{color:brelColor}">{{ jsonHealthData.brel !== 0 ? jsonHealthData.brel.toFixed(0) : healthData.brel }}%</div>
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
            <div style="display:flex;align-items:center;gap:12px">
              <div style="font-size:17px;font-weight:700;color:#1E293B">健康趋势</div>
              <span style="font-size:14px;color:#64748B">心肺频率比</span>
            </div>
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
        <div class="card emotion-card" style="height:35;padding:16px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
            <span style="font-size:17px;font-weight:700;color:#1E293B">实时情绪</span>
            <div style="display:flex;align-items:center;gap:12px">
              <span :style="{color:personDetected?'#10B981':'#94A3B8',fontSize:'16px',fontWeight:'600'}">
                {{ personDetected ? '有人' : '无人' }}
              </span>
            </div>
          </div>
          <div class="emo-bar" style="height:12px;margin-bottom:16px">
            <div :style="{width:(fusionEmotionResult.scores.positive*100)+'%',background:'#10B981'}"></div>
            <div :style="{width:(fusionEmotionResult.scores.neutral*100)+'%',background:'#94A3B8'}"></div>
            <div :style="{width:(fusionEmotionResult.scores.negative*100)+'%',background:'#EF4444'}"></div>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-around">
            <span style="font-size:28px;font-weight:700" :style="{color:fusionEmotionResult.emotion === '积极' ? '#10B981' : fusionEmotionResult.emotion === '消极' ? '#EF4444' : '#94A3B8'}">{{ fusionEmotionResult.emotion }}</span>
            <span style="font-size:28px;color:#1E293B;font-weight:700">{{ fusionEmotionResult.confidence === '--' ? '--' : (fusionEmotionResult.confidence * 100).toFixed(0) + '%' }}</span>
          </div>
        </div>

        <!-- 压力值 -->
        <div class="card" style="padding:12px;height:180px;display:flex;flex-direction:column;align-items:center">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;align-self:stretch">
            <h3 style="font-size:18px;font-weight:700;color:#1E293B">压力值</h3>
            <span style="padding:4px 12px;border-radius:16px;font-size:14px;font-weight:600" :style="getStressStatusStyle()">
              {{ getStressStatus() }}
            </span>
          </div>
          <div class="gauge-container">
            <svg viewBox="0 0 160 88" width="140" height="77">
              <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#E2E8F0" stroke-width="10" stroke-linecap="round"/>
              <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" :stroke="pressureColor" stroke-width="10" stroke-linecap="round" :stroke-dasharray="stressProgress" :stroke-dashoffset="stressOffset"/>
              <line x1="80" y1="80" :x2="stressNeedleX" :y2="stressNeedleY" stroke="#1E293B" stroke-width="2" stroke-linecap="round"/>
              <circle cx="80" cy="80" r="3" fill="#1E293B"/>
            </svg>
          </div>
          <div class="m-val text-3xl mt-1" :style="{color:pressureColor}">{{ estimatedStress }}</div>
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
          <div style="display:flex;gap:12px;margin-bottom:16px">
            <div class="mini-st" style="height:15px;flex:1;padding:20px;display:flex;align-items:center;justify-content:space-between">
              <span style="font-size:14px;color:#64748B">主导</span>
              <span style="font-size:20px;font-weight:700;color:#0D9488">{{ emotion.analysis.dominant }}</span>
            </div>
            <div class="mini-st" style="height:15px;flex:1;padding:20px;display:flex;align-items:center;justify-content:space-between">
              <span style="font-size:14px;color:#64748B">稳定性</span>
              <span style="font-size:20px;font-weight:700;color:#10B981">{{ emotion.analysis.stability }}</span>
            </div>
            <div class="mini-st" style="height:15px;flex:1;padding:20px;display:flex;align-items:center;justify-content:space-between">
              <span style="font-size:14px;color:#64748B">波动</span>
              <span style="font-size:20px;font-weight:700;color:#F97316">{{ emotion.analysis.volatility }}</span>
            </div>
          </div>
          <div class="card" style="padding:12px;background:#F8FAFC">
            <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
              <span style="font-size:14px;font-weight:600;color:#1E293B">建议</span>
              <i class="fas fa-spa" style="font-size:16px;color:#0D9488"></i>
            </div>
            <div style="font-size:14px;color:#475569;line-height:1.7">
            进行5-10分钟的深呼吸练习，帮助维持情绪稳定<br/>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 睡眠健康 -->
    <section v-show="activeTab=='sleep'" class="split fade-up" style="margin-top:20px">
      <div class="left-col">
        <!-- 睡眠比例卡片 -->
        <div class="card" style="padding:16px">
          <h3 style="font-size:17px;font-weight:700;margin-bottom:12px;color:#1E293B">睡眠比例</h3>
          <div style="display:flex;justify-content:center;align-items:center">
            <svg viewBox="0 0 200 200" width="140" height="140">
              <!-- 背景圆环 -->
              <circle cx="100" cy="100" r="80" fill="none" stroke="#F1F5F9" stroke-width="30"/>
              
              <!-- 各阶段圆环 -->
              <circle cx="100" cy="100" r="80" fill="none" stroke="#0F766E" stroke-width="30"
                      :stroke-dasharray="`${sleepDeep/totalSleep*2*Math.PI*80} ${2*Math.PI*80}`"
                      stroke-linecap="round"/>
              <circle cx="100" cy="100" r="80" fill="none" stroke="#14B8A6" stroke-width="30"
                      :stroke-dasharray="`${sleepLight/totalSleep*2*Math.PI*80} ${2*Math.PI*80}`"
                      :stroke-dashoffset="`-${sleepDeep/totalSleep*2*Math.PI*80}`"
                      stroke-linecap="round"/>
              <circle cx="100" cy="100" r="80" fill="none" stroke="#F59E0B" stroke-width="30"
                      :stroke-dasharray="`${sleepRem/totalSleep*2*Math.PI*80} ${2*Math.PI*80}`"
                      :stroke-dashoffset="`-${(sleepDeep + sleepLight)/totalSleep*2*Math.PI*80}`"
                      stroke-linecap="round"/>
              <circle cx="100" cy="100" r="80" fill="none" stroke="#EF4444" stroke-width="30"
                      :stroke-dasharray="`${sleepAwake/totalSleep*2*Math.PI*80} ${2*Math.PI*80}`"
                      :stroke-dashoffset="`-${(sleepDeep + sleepLight + sleepRem)/totalSleep*2*Math.PI*80}`"
                      stroke-linecap="round"/>
              
              <!-- 中心文字 -->
              <text x="100" y="92" text-anchor="middle" font-size="26" font-weight="700" fill="#1E293B">{{(sleepDeep+sleepLight+sleepRem).toFixed(1)}}h</text>
              <text x="100" y="118" text-anchor="middle" font-size="14" font-weight="500" fill="#64748B">总睡眠</text>
            </svg>
          </div>
          
          <!-- 四行详情：上下结构 -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 16px;margin-top:18px">
            <div style="padding:8px 10px;background:#F0FDFA;border-radius:6px">
              <div style="display:flex;align-items:center;gap:6px">
                <span style="width:12px;height:12px;border-radius:3px;background:#0F766E"></span>
                <span style="font-size:12px;color:#64748B">深睡</span>
              </div>
              <div style="display:flex;gap:10px;font-size:14px;font-weight:600;color:#0F766E;margin-top:8px">
                <span>{{sleepDeep}}h</span>
                <span>{{(sleepDeep/totalSleep*100).toFixed(0)}}%</span>
              </div>
            </div>
            <div style="padding:8px 10px;background:#F0FDFA;border-radius:6px">
              <div style="display:flex;align-items:center;gap:6px">
                <span style="width:12px;height:12px;border-radius:3px;background:#14B8A6"></span>
                <span style="font-size:12px;color:#64748B">浅睡</span>
              </div>
              <div style="display:flex;gap:10px;font-size:14px;font-weight:600;color:#14B8A6;margin-top:8px">
                <span>{{sleepLight}}h</span>
                <span>{{(sleepLight/totalSleep*100).toFixed(0)}}%</span>
              </div>
            </div>
            <div style="padding:8px 10px;background:#F0FDFA;border-radius:6px">
              <div style="display:flex;align-items:center;gap:6px">
                <span style="width:12px;height:12px;border-radius:3px;background:#F59E0B"></span>
                <span style="font-size:12px;color:#64748B">REM</span>
              </div>
              <div style="display:flex;gap:10px;font-size:14px;font-weight:600;color:#F59E0B;margin-top:8px">
                <span>{{sleepRem}}h</span>
                <span>{{(sleepRem/totalSleep*100).toFixed(0)}}%</span>
              </div>
            </div>
            <div style="padding:8px 10px;background:#FEF2F2;border-radius:6px">
              <div style="display:flex;align-items:center;gap:6px">
                <span style="width:12px;height:12px;border-radius:3px;background:#EF4444"></span>
                <span style="font-size:12px;color:#64748B">清醒</span>
              </div>
              <div style="display:flex;gap:10px;font-size:14px;font-weight:600;color:#EF4444;margin-top:8px">
                <span>{{sleepAwake}}h</span>
                <span>{{(sleepAwake/totalSleep*100).toFixed(0)}}%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 睡眠记录近两天 -->
        <div class="card" style="padding:16px">
          <h3 style="font-size:17px;font-weight:700;margin-bottom:12px;color:#1E293B">睡眠记录</h3>
          <div style="display:flex;flex-direction:column;gap:10px">
            <div v-for="(r,i) in sleepRecords.slice(0,2)" :key="i"
                 style="display:flex;justify-content:space-between;align-items:center;padding:12px;background:#F8FAFC;border-radius:8px">
              <div>
                <div style="font-size:14px;font-weight:600;color:#1E293B">{{r.date}}</div>
                <div style="font-size:12px;color:#94A3B8">{{r.start}} - {{r.end}}</div>
              </div>
              <div style="text-align:right">
                <div style="font-size:20px;font-weight:700" :style="{color:r.score>=80?'#0D9488':r.score>=60?'#F97316':'#EF4444'}">{{r.score}}</div>
                <div style="font-size:12px;color:#94A3B8">{{r.duration}}h</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="right-col">
        <!-- 睡眠趋势 -->
        <div class="card" style="padding:16px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div style="font-size:17px;font-weight:700;color:#1E293B">睡眠趋势</div>
            <div style="display:flex;gap:16px;flex-wrap:wrap" v-if="sleepPeriod==='day'">
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#0F766E;border-radius:2px"></span><span style="font-size:11px;color:#64748B">深睡</span></div>
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#14B8A6;border-radius:2px"></span><span style="font-size:11px;color:#64748B">浅睡</span></div>
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#F59E0B;border-radius:2px"></span><span style="font-size:11px;color:#64748B">REM</span></div>
            </div>
            <div style="display:flex;gap:12px" v-if="sleepPeriod==='week'">
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#0F766E;border-radius:2px"></span><span style="font-size:11px;color:#64748B">深睡</span></div>
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#14B8A6;border-radius:2px"></span><span style="font-size:11px;color:#64748B">浅睡</span></div>
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#F59E0B;border-radius:2px"></span><span style="font-size:11px;color:#64748B">REM</span></div>
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#EF4444;border-radius:2px"></span><span style="font-size:11px;color:#64748B">清醒</span></div>
            </div>
            <div style="display:flex;gap:12px" v-if="sleepPeriod==='year'">
              <div style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:10px;background:#0D9488;border-radius:2px"></span><span style="font-size:11px;color:#64748B">睡眠时长</span></div>
            </div>
            <div style="display:flex;gap:6px">
              <button class="tab-btn2" :class="{active:sleepPeriod==='day'}" @click="sleepPeriod='day'">日</button>
              <button class="tab-btn2" :class="{active:sleepPeriod==='week'}" @click="sleepPeriod='week'">周</button>
              <button class="tab-btn2" :class="{active:sleepPeriod==='year'}" @click="sleepPeriod='year'">年</button>
            </div>
          </div>
          <div style="height:200px;position:relative">
            <canvas ref="sleepChartCanvas"></canvas>
          </div>
        </div>

        <!-- 解读与建议 -->
        <div class="card" style="padding:16px">
          <h3 style="font-size:17px;font-weight:700;margin-bottom:12px;color:#1E293B">解读与建议</h3>
          
          <!-- 睡眠解读 -->
          <div style="background:#F0FDFA;border-radius:8px;padding:12px;border:1px solid #CCFBF1;margin-bottom:12px">
            <div style="font-size:14px;font-weight:600;color:#0F766E;margin-bottom:6px">睡眠解读</div>
            <p style="font-size:13px;color:#0F766E;line-height:1.6">
              深睡占比{{(sleepDeep/totalSleep*100).toFixed(0)}}%，接近推荐水平。REM充足，心肺耦合强(PLV={{sleepPlv}})，自主神经调节良好。
            </p>
          </div>
          
          <!-- 建议列表 -->
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;align-items:flex-start;gap:10px;padding:10px;background:#F8FAFC;border-radius:8px">
              <div style="width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;background:#F0FDFA">
                <i class="fas fa-clock" style="font-size:14px;color:#0D9488"></i>
              </div>
              <div style="flex:1">
                <div style="font-size:14px;font-weight:600;color:#1E293B">固定作息</div>
                <div style="font-size:12px;color:#64748B">同一时间入睡起床</div>
              </div>
            </div>
            
            <div style="display:flex;align-items:flex-start;gap:10px;padding:10px;background:#F8FAFC;border-radius:8px">
              <div style="width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;background:#FFF7ED">
                <i class="fas fa-book-open" style="font-size:14px;color:#F97316"></i>
              </div>
              <div style="flex:1">
                <div style="font-size:14px;font-weight:600;color:#1E293B">睡前放松</div>
                <div style="font-size:12px;color:#64748B">避免蓝光刺激</div>
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

const router = useRouter();
const HLKK_PORT = 5020;
const BACKEND_PORT = 5000;

// 动态获取后端地址
const getBackendHost = () => {
  if (typeof window === 'undefined') return 'localhost'
  const host = window.location.hostname
  return host || 'localhost'
}

const backendHost = getBackendHost()
const backendUrl = `http://${backendHost}:${BACKEND_PORT}`
const hlkkUrl = `http://${backendHost}:${HLKK_PORT}`

console.log('[Health] 后端地址:', backendUrl)
console.log('[Health] HLKK地址:', hlkkUrl)

const activeTab = ref('cardio');
const period = ref('day');
const emoPeriod = ref('day');
const sleepPeriod = ref('day');
const currentTime = ref('');

// 从 JSON 文件获取的数据
const jsonEmotionData = ref({
  timestamp: '',
  elapsed: 0,
  au: { emotion: 'no_face', confidence: 0, scores: { neutral: 0, positive: 0, negative: 0 }, pose: 'front', pitch: 0, yaw: 0, au_features: {} },
  fer: { label: 'neutral', conf: 0, probs_3: { neutral: 0, positive: 0, negative: 0 } },
  fusion: { emotion: 'no_face', confidence: 0, scores: { neutral: 0, positive: 0, negative: 0 } }
});

const jsonHealthData = ref({
  time: 0,
  hr: 72,
  br: 16,
  hph: 0,
  bph: 0,
  is_human: 0,
  distance: 0,
  distance_valid: 0,
  signal_state: 'INIT',
  hr_valid: false,
  br_valid: false,
  phase_valid: false,
  hrr: 0,
  hrr_label: '',
  slope: 0,
  slope_label: '',
  brv: 0,
  brv_label: '',
  brel: 0,
  brel_label: '',
  cr: 0,
  cr_label: '',
  plv: 0.9,
  plv_label: ''
});

// 有人/无人判断（优先使用 emotion.json 的融合情绪）
const personDetected = computed(() => {
  return jsonEmotionData.value.fusion.emotion !== 'no_face';
});

// 融合情绪结果
const fusionEmotionResult = computed(() => {
  const fusion = jsonEmotionData.value.fusion;
  if (!personDetected.value) {
    return { emotion: '--', confidence: '--', scores: { neutral: 0, positive: 0, negative: 0 } };
  }
  return {
    emotion: fusion.emotion === 'positive' ? '积极' : fusion.emotion === 'negative' ? '消极' : '中性',
    confidence: fusion.confidence,
    scores: fusion.scores
  };
});

// 从 PLV 值估算压力值 (PLV越高，压力越低)
const estimatedStress = computed(() => {
  const plv = jsonHealthData.value.plv;
  // PLV范围 0-1，转换为压力值 100-0
  return Math.max(0, Math.min(100, Math.round((1 - plv) * 100)));
});

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
  const ctx = chartCanvas.value?.getContext('2d');
  if (!ctx) return;
  
  const Chart = await loadChart();
  if (!Chart) return;
  
  const d = trendData[tab];
  
  // 如果图表已存在，只更新数据
  if (chart) {
    chart.data.labels = d.labels;
    
    if (tab === 'day') {
      const points = d.values.map(v => (v < MIN || v > MAX) ? 4 : 0);
      const pColor = d.values.map(v => (v < MIN || v > MAX) ? '#f0654a' : '#0D9488');
      
      chart.config.type = 'line';
      chart.data.datasets = [{
        data: d.values, borderColor:'#0D9488', borderWidth:2,
        backgroundColor: ctx.createLinearGradient(0,0,0,200),
        fill:true, tension:0.4,
        pointRadius: points, pointBackgroundColor: pColor,
        pointBorderColor: pColor, pointHoverRadius:5
      }];
      const grad = chart.data.datasets[0].backgroundColor;
      grad.addColorStop(0,'rgba(13,148,136,0.15)');
      grad.addColorStop(1,'rgba(13,148,136,0)');
      
      chart.options = lineOpts();
      chart.plugins = [rangePlugin];
    } else {
      chart.config.type = 'bar';
      chart.data.datasets = [
        {label:'正常',data:d.normal,backgroundColor:'rgba(13,148,136,0.7)',borderRadius:4,barPercentage:0.6},
        {label:'异常',data:d.abnormal,backgroundColor:'rgba(240,101,74,0.7)',borderRadius:4,barPercentage:0.6}
      ];
      chart.options = {
        responsive:true,maintainAspectRatio:false,
        animation:{duration:300},
        plugins:{
          legend:{position:'top',align:'end',labels:{font:{size:11},boxWidth:10,padding:10}},
          tooltip:{backgroundColor:'#fff',titleColor:'#333',bodyColor:'#333',borderColor:'#eee',borderWidth:1,cornerRadius:6,padding:8}
        },
        scales:{
          x:{stacked:true,grid:{display:false},ticks:{color:'#aaa',font:{size:10}},border:{display:false}},
          y:{stacked:true,beginAtZero:true,grid:{color:'rgba(0,0,0,0.04)'},ticks:{color:'#aaa',font:{size:10}},border:{display:false}}
        }
      };
    }
    
    chart.update();
    renderStats(tab);
    return;
  }
  
  // 如果图表不存在，创建新图表
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
        animation:{duration:300},
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
  const s = estimatedStress.value;
  if (s < 30) return '#10B981';
  if (s < 60) return '#F97316';
  return '#EF4444';
});

const pressureLabel = computed(() => {
  const s = estimatedStress.value;
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
  const stress = Math.min(Math.max(estimatedStress.value, 0), 100);
  const circumference = Math.PI * 120;
  return `${stress / 100 * circumference} ${circumference}`;
});

const stressOffset = computed(() => 0);

const stressNeedleAngle = computed(() => {
  const stress = Math.min(Math.max(estimatedStress.value, 0), 100);
  return Math.PI + stress / 100 * Math.PI;
});

const stressNeedleX = computed(() => 80 + Math.cos(stressNeedleAngle.value) * 42);
const stressNeedleY = computed(() => 80 + Math.sin(stressNeedleAngle.value) * 42);

// 主导情绪
const dominantEmotion = computed(() => {
  if (!personDetected.value) return '--';
  return fusionEmotionResult.value.emotion;
});

const dominantEmotionColor = computed(() => {
  const e = dominantEmotion.value;
  if (e === '积极') return '#10B981';
  if (e === '中性') return '#94A3B8';
  if (e === '消极') return '#EF4444';
  return '#94A3B8';
});

// 压力状态
const getStressStatus = () => {
  const stress = estimatedStress.value;
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
  const ctx = emotionChartCanvas.value?.getContext('2d');
  if (!ctx) return;
  
  const Chart = await loadChart();
  if (!Chart) return;
  
  const d = emotionTrendData[period];
  
  // 如果图表已存在，只更新数据
  if (emotionChart) {
    emotionChart.data.labels = d.labels;
    emotionChart.data.datasets[0].data = d.positive;
    emotionChart.data.datasets[1].data = d.stress;
    emotionChart.update();
    renderEmotionStats(period);
    return;
  }
  
  // 如果图表不存在，创建新图表
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
      animation:{duration:300},
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

// 睡眠趋势图表
const sleepChartCanvas = ref(null);
let sleepChart = null;

const sleepTrendData = {
  day: {
    labels: ['22:00','23:00','00:00','01:00','02:00','03:00','04:00','05:00','06:00'],
    // 每个时间段的睡眠阶段：0=清醒, 1=REM, 2=浅睡, 3=深睡
    stages: [2, 2, 3, 2, 1, 2, 2, 2, 0]
  },
  week: {
    labels: ['周一','周二','周三','周四','周五','周六','周日'],
    deep: [1.2, 1.5, 1.3, 1.4, 1.6, 1.8, 1.5],
    light: [3.2, 3.5, 3.0, 3.4, 3.6, 3.8, 3.3],
    rem: [1.5, 1.8, 1.6, 1.7, 1.9, 2.0, 1.7],
    awake: [0.4, 0.3, 0.5, 0.3, 0.2, 0.3, 0.4]
  },
  year: {
    labels: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
    duration: [6.8, 7.0, 6.5, 7.2, 7.5, 7.0, 7.3, 6.8, 7.2, 7.6, 7.1, 7.0]
  }
};

const renderSleepChart = async (period) => {
  const ctx = sleepChartCanvas.value?.getContext('2d');
  if (!ctx) return;

  const Chart = await loadChart();
  if (!Chart) return;

  const d = sleepTrendData[period];

  // 销毁旧图表并重新创建（因为图表类型不同）
  if (sleepChart) {
    sleepChart.destroy();
    sleepChart = null;
  }

  if (period === 'day') {
    // 日视图：睡眠阶段条形图
    sleepChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: d.labels,
        datasets: [{
          data: d.stages,
          backgroundColor: d.stages.map(s => {
            if (s === 0) return '#EF4444';  // 清醒-红色
            if (s === 1) return '#F59E0B';  // REM-橙色
            if (s === 2) return '#14B8A6';  // 浅睡-青色
            if (s === 3) return '#0F766E';  // 深睡-深绿
            return '#94A3B8';  // 默认灰色
          }),
          borderRadius: 4,
          barPercentage: 0.8
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        indexAxis: 'x',
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: '#64748B', font: { size: 11 } }, border: { display: false } },
          y: { 
            display: false,
            min: -0.5,
            max: 3.5
          }
        }
      }
    });
  } else if (period === 'week') {
    // 周视图：堆叠柱状图
    sleepChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: d.labels,
        datasets: [
          { label: '深睡', data: d.deep, backgroundColor: '#0F766E', borderRadius: 4, barPercentage: 0.7 },
          { label: '浅睡', data: d.light, backgroundColor: '#14B8A6', borderRadius: 4, barPercentage: 0.7 },
          { label: 'REM', data: d.rem, backgroundColor: '#F59E0B', borderRadius: 4, barPercentage: 0.7 },
          { label: '清醒', data: d.awake, backgroundColor: '#EF4444', borderRadius: 4, barPercentage: 0.7 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        plugins: { legend: { display: false } },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: '#64748B', font: { size: 11 } }, border: { display: false } },
          y: { stacked: true, beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { color: '#64748B', font: { size: 11 } }, border: { display: false } }
        }
      }
    });
  } else {
    // 年视图：睡眠时长柱状图
    sleepChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: d.labels,
        datasets: [{
          label: '睡眠时长',
          data: d.duration,
          backgroundColor: '#0D9488',
          borderRadius: 4,
          barPercentage: 0.7
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: '#64748B', font: { size: 10 } }, border: { display: false } },
          y: { beginAtZero: true, max: 10, grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { color: '#64748B', font: { size: 11 } }, border: { display: false } }
        }
      }
    });
  }
};

watch(sleepPeriod, (newVal) => {
  renderSleepChart(newVal);
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

let waveFrame = 0;

const hrWavePoints = computed(() => {
  waveFrame++;
  const points = [];
  for (let i = 0; i <= 30; i++) {
    const x = (i / 30) * 400;
    const y = 60 + Math.sin(i * 0.5 + waveFrame * 0.02) * 25 + Math.sin(i * 0.1) * 10;
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const brWavePoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 30; i++) {
    const x = (i / 30) * 400;
    const y = 60 + Math.sin(i * 0.15 + waveFrame * 0.01) * 30;
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const lissajousPoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 32; i++) {
    const t = (i / 32) * 2 * Math.PI + waveFrame * 0.005;
    const x = 100 + 50 * Math.cos(t);
    const y = 100 + 40 * Math.sin(t * 1.5);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const neutralPoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 30; i++) {
    const x = (i / 30) * 600;
    const y = 130 - (30 + Math.sin(i * 0.1 + waveFrame * 0.01) * 8);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const positivePoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 30; i++) {
    const x = (i / 30) * 600;
    const y = 130 - (35 + Math.sin(i * 0.12 + waveFrame * 0.01) * 12);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

const negativePoints = computed(() => {
  const points = [];
  for (let i = 0; i <= 30; i++) {
    const x = (i / 30) * 600;
    const y = 130 - (15 + Math.sin(i * 0.08 + waveFrame * 0.008) * 6);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
});

async function fetchData() {
  try {
    // 从 JSON 文件获取数据
    await fetchEmotionData();
    await fetchHealthData();
    
    // 从 HLKK 服务获取数据（作为备用）
    const res = await fetch(`${hlkkUrl}/data`);
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

async function fetchEmotionData() {
  try {
    const res = await fetch(`${backendUrl}/core/emotion.json?` + Date.now());
    if (res.ok) {
      const data = await res.json();
      jsonEmotionData.value = data;
    }
  } catch (e) {
    console.warn('[Health] 无法读取 emotion.json:', e);
  }
}

async function fetchHealthData() {
  try {
    const res = await fetch(`${backendUrl}/core/health.json?` + Date.now());
    if (res.ok) {
      const data = await res.json();
      jsonHealthData.value = data;
    }
  } catch (e) {
    console.warn('[Health] 无法读取 health.json:', e);
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
  intervalId = setInterval(fetchData, 2000);
  setInterval(updateTime, 1000);
  
  setTimeout(() => {
    renderChart('day');
    renderEmotionChart('day');
    renderSleepChart('day');
  }, 300);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
  if (chart) chart.destroy();
  if (emotionChart) emotionChart.destroy();
  if (sleepChart) sleepChart.destroy();
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