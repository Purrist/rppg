    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>生理监测</title>
    <script src="/static/chart.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
            background: #0a0e17;
            color: #a0aec0;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            padding: 6px 8px;
        }

        .top-bar {
            display: flex;
            gap: 6px;
            height: 52px;
            flex-shrink: 0;
            margin-bottom: 6px;
        }

        .num-box {
            flex: 1;
            background: #111827;
            border-radius: 6px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            border-left: 2px solid;
            position: relative;
            overflow: hidden;
        }

        .num-box.hr { border-color: #ef4444; }
        .num-box.br { border-color: #3b82f6; }
        .num-box.sdnn { border-color: #10b981; }
        .num-box.cpli { border-color: #f59e0b; }
        .num-box.cli { border-color: #8b5cf6; }
        .num-box.fsi { border-color: #ec4899; }

        .num-label { font-size: 9px; color: #4b5563; letter-spacing: 1px; }
        .num-value { font-size: 22px; font-weight: 700; line-height: 1; margin-top: 2px; }
        .num-unit { font-size: 8px; color: #374151; margin-top: 1px; }

        .num-box.hr .num-value { color: #ef4444; }
        .num-box.br .num-value { color: #3b82f6; }
        .num-box.sdnn .num-value { color: #10b981; }
        .num-box.cpli .num-value { color: #f59e0b; }
        .num-box.cli .num-value { color: #8b5cf6; }
        .num-box.fsi .num-value { color: #ec4899; }

        .main-area { display: flex; gap: 6px; flex: 1; min-height: 0; }

        .left-panel { width: 220px; flex-shrink: 0; display: flex; flex-direction: column; gap: 6px; }

        .gauge-box {
            background: #111827;
            border-radius: 6px;
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: relative;
            border: 1px solid #1f2937;
        }

        .gauge-title { position: absolute; top: 6px; left: 8px; font-size: 10px; color: #4b5563; font-weight: 500; }
        .gauge-svg { width: 140px; height: 80px; }
        .gauge-num { font-size: 18px; font-weight: 700; margin-top: -8px; }

        .gauge-num.phys { color: #f59e0b; }
        .gauge-num.cog { color: #8b5cf6; }
        .gauge-num.flow { color: #ec4899; }
        .gauge-num.emo { color: #06b6d4; }

        .right-panel { flex: 1; display: grid; grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(2, 1fr); gap: 6px; min-height: 0; }

        .chart-cell {
            background: #111827;
            border-radius: 6px;
            border: 1px solid #1f2937;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .chart-header { display: flex; align-items: center; gap: 6px; padding: 4px 8px; flex-shrink: 0; }
        .chart-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
        .chart-title-text { font-size: 10px; color: #6b7280; font-weight: 500; }

        .chart-body { flex: 1; min-height: 0; position: relative; }
        .chart-body canvas { position: absolute; top: 0; left: 0; width: 100% !important; height: 100% !important; }

        .bottom-bar {
            height: 24px;
            flex-shrink: 0;
            margin-top: 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 10px;
            background: #111827;
            border-radius: 4px;
            font-size: 10px;
        }

        .live-dot {
            width: 6px; height: 6px;
            background: #10b981;
            border-radius: 50%;
            display: inline-block;
            margin-right: 4px;
            animation: pulse 1.2s infinite;
        }

        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

        .emotion-pill {
            padding: 2px 10px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            color: #fff;
            background: linear-gradient(90deg, #4f46e5, #7c3aed);
        }

        .time-stamp { color: #374151; }
    </style>
</head>
<body>
    <div class="top-bar">
        <div class="num-box hr">
            <div class="num-label">心率</div>
            <div class="num-value" id="v-hr">--</div>
            <div class="num-unit">bpm</div>
        </div>
        <div class="num-box br">
            <div class="num-label">呼吸率</div>
            <div class="num-value" id="v-br">--</div>
            <div class="num-unit">次/分</div>
        </div>
        <div class="num-box sdnn">
            <div class="num-label">SDNN</div>
            <div class="num-value" id="v-sdnn">--</div>
            <div class="num-unit">ms</div>
        </div>
        <div class="num-box cpli">
            <div class="num-label">生理负荷</div>
            <div class="num-value" id="v-cpli">--</div>
            <div class="num-unit">CPLI</div>
        </div>
        <div class="num-box cli">
            <div class="num-label">认知负荷</div>
            <div class="num-value" id="v-cli">--</div>
            <div class="num-unit">CLI</div>
        </div>
        <div class="num-box fsi">
            <div class="num-label">心流</div>
            <div class="num-value" id="v-fsi">--</div>
            <div class="num-unit">FSI</div>
        </div>
    </div>

    <div class="main-area">
        <div class="left-panel">
            <div class="gauge-box">
                <div class="gauge-title">生理负荷</div>
                <svg class="gauge-svg" viewBox="0 0 140 80">
                    <defs>
                        <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stop-color="#10b981"/>
                            <stop offset="50%" stop-color="#f59e0b"/>
                            <stop offset="100%" stop-color="#ef4444"/>
                        </linearGradient>
                    </defs>
                    <path d="M 10 75 A 60 60 0 0 1 130 75" fill="none" stroke="url(#g1)" stroke-width="14" stroke-linecap="round"/>
                    <line id="n-phys" x1="70" y1="75" x2="70" y2="20" stroke="#fff" stroke-width="2.5" stroke-linecap="round" transform="rotate(-90 70 75)"/>
                    <circle cx="70" cy="75" r="4" fill="#fff"/>
                </svg>
                <div class="gauge-num phys" id="g-phys">0.00</div>
            </div>
            <div class="gauge-box">
                <div class="gauge-title">认知负荷</div>
                <svg class="gauge-svg" viewBox="0 0 140 80">
                    <path d="M 10 75 A 60 60 0 0 1 130 75" fill="none" stroke="url(#g1)" stroke-width="14" stroke-linecap="round"/>
                    <line id="n-cog" x1="70" y1="75" x2="70" y2="20" stroke="#fff" stroke-width="2.5" stroke-linecap="round" transform="rotate(-90 70 75)"/>
                    <circle cx="70" cy="75" r="4" fill="#fff"/>
                </svg>
                <div class="gauge-num cog" id="g-cog">0.00</div>
            </div>
            <div class="gauge-box">
                <div class="gauge-title">心流</div>
                <svg class="gauge-svg" viewBox="0 0 140 80">
                    <path d="M 10 75 A 60 60 0 0 1 130 75" fill="none" stroke="url(#g1)" stroke-width="14" stroke-linecap="round"/>
                    <line id="n-flow" x1="70" y1="75" x2="70" y2="20" stroke="#fff" stroke-width="2.5" stroke-linecap="round" transform="rotate(-90 70 75)"/>
                    <circle cx="70" cy="75" r="4" fill="#fff"/>
                </svg>
                <div class="gauge-num flow" id="g-flow">0.00</div>
            </div>
            <div class="gauge-box">
                <div class="gauge-title">效价</div>
                <svg class="gauge-svg" viewBox="0 0 140 80">
                    <path d="M 10 75 A 60 60 0 0 1 130 75" fill="none" stroke="url(#g1)" stroke-width="14" stroke-linecap="round"/>
                    <line id="n-emo" x1="70" y1="75" x2="70" y2="20" stroke="#fff" stroke-width="2.5" stroke-linecap="round" transform="rotate(-90 70 75)"/>
                    <circle cx="70" cy="75" r="4" fill="#fff"/>
                </svg>
                <div class="gauge-num emo" id="g-emo">0.00</div>
            </div>
        </div>

        <div class="right-panel">
            <div class="chart-cell">
                <div class="chart-header">
                    <div class="chart-dot" style="background:#ef4444"></div>
                    <div class="chart-dot" style="background:#3b82f6"></div>
                    <div class="chart-title-text">心跳/呼吸 相位</div>
                </div>
                <div class="chart-body"><canvas id="c-phase"></canvas></div>
            </div>
            <div class="chart-cell">
                <div class="chart-header">
                    <div class="chart-dot" style="background:#f59e0b"></div>
                    <div class="chart-dot" style="background:#10b981"></div>
                    <div class="chart-title-text">心率/呼吸率</div>
                </div>
                <div class="chart-body"><canvas id="c-rate"></canvas></div>
            </div>
            <div class="chart-cell">
                <div class="chart-header">
                    <div class="chart-dot" style="background:#10b981"></div>
                    <div class="chart-dot" style="background:#3b82f6"></div>
                    <div class="chart-title-text">HRV 时域</div>
                </div>
                <div class="chart-body"><canvas id="c-hrv"></canvas></div>
            </div>
            <div class="chart-cell">
                <div class="chart-header">
                    <div class="chart-dot" style="background:#ef4444"></div>
                    <div class="chart-dot" style="background:#f59e0b"></div>
                    <div class="chart-dot" style="background:#ec4899"></div>
                    <div class="chart-title-text">复合指数</div>
                </div>
                <div class="chart-body"><canvas id="c-index"></canvas></div>
            </div>
            <div class="chart-cell">
                <div class="chart-header">
                    <div class="chart-dot" style="background:#f59e0b"></div>
                    <div class="chart-title-text">情绪空间</div>
                </div>
                <div class="chart-body"><canvas id="c-emotion"></canvas></div>
            </div>
            <div class="chart-cell">
                <div class="chart-header">
                    <div class="chart-dot" style="background:#ec4899"></div>
                    <div class="chart-title-text">心流维度</div>
                </div>
                <div class="chart-body"><canvas id="c-radar"></canvas></div>
            </div>
        </div>
    </div>

    <div class="bottom-bar">
        <span><span class="live-dot"></span>实时</span>
        <span class="emotion-pill" id="e-pill">等待数据</span>
        <span class="time-stamp" id="e-time">--:--:--</span>
    </div>

    <script>
        const MAX = 100;
        const emptyLabels = Array(MAX).fill('');
        let charts = {};

        function initCharts() {
            const phaseData = Array(MAX).fill(0);
            const rateHData = Array(MAX).fill(72);
            const rateBData = Array(MAX).fill(16);
            const sdnnData = Array(MAX).fill(0);
            const rmssdData = Array(MAX).fill(0);
            const cpliData = Array(MAX).fill(0);
            const cliData = Array(MAX).fill(0);
            const fsiData = Array(MAX).fill(0);

            charts.phase = new Chart(document.getElementById('c-phase'), {
                type: 'line',
                data: {
                    labels: emptyLabels,
                    datasets: [
                        {
                            label: '心跳相位',
                            data: [...phaseData],
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239,68,68,0.08)',
                            borderWidth: 1,
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        },
                        {
                            label: '呼吸相位',
                            data: [...phaseData],
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59,130,246,0.08)',
                            borderWidth: 1,
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    parsing: false,
                    animation: { duration: 0 },
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false, grid: { display: false } },
                        y: { grid: { color: 'rgba(75,85,99,0.15)' }, ticks: { color: '#4b5563', font: { size: 8 }, padding: 2 } }
                    }
                }
            });

            charts.rate = new Chart(document.getElementById('c-rate'), {
                type: 'line',
                data: {
                    labels: emptyLabels,
                    datasets: [
                        {
                            label: '心率',
                            data: [...rateHData],
                            borderColor: '#f59e0b',
                            backgroundColor: 'rgba(245,158,11,0.08)',
                            borderWidth: 1.5,
                            fill: true,
                            tension: 0.3,
                            pointRadius: 0,
                            pointHoverRadius: 0,
                            yAxisID: 'y'
                        },
                        {
                            label: '呼吸率',
                            data: [...rateBData],
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16,185,129,0.08)',
                            borderWidth: 1.5,
                            fill: true,
                            tension: 0.3,
                            pointRadius: 0,
                            pointHoverRadius: 0,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    parsing: false,
                    animation: { duration: 0 },
                    plugins: { legend: { display: true, labels: { color: '#4b5563', font: { size: 8 }, boxWidth: 8 } } },
                    scales: {
                        x: { display: false, grid: { display: false } },
                        y: {
                            type: 'linear',
                            position: 'left',
                            grid: { color: 'rgba(75,85,99,0.1)' },
                            ticks: { color: '#f59e0b', font: { size: 8 } },
                            title: { display: false }
                        },
                        y1: {
                            type: 'linear',
                            position: 'right',
                            grid: { display: false },
                            ticks: { color: '#10b981', font: { size: 8 } },
                            title: { display: false }
                        }
                    }
                }
            });

            charts.hrv = new Chart(document.getElementById('c-hrv'), {
                type: 'line',
                data: {
                    labels: emptyLabels,
                    datasets: [
                        {
                            label: 'SDNN',
                            data: [...sdnnData],
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16,185,129,0.08)',
                            borderWidth: 1.5,
                            fill: true,
                            tension: 0.3,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        },
                        {
                            label: 'RMSSD',
                            data: [...rmssdData],
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59,130,246,0.08)',
                            borderWidth: 1.5,
                            fill: true,
                            tension: 0.3,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    parsing: false,
                    animation: { duration: 0 },
                    plugins: { legend: { display: true, labels: { color: '#4b5563', font: { size: 8 }, boxWidth: 8 } } },
                    scales: {
                        x: { display: false, grid: { display: false } },
                        y: { grid: { color: 'rgba(75,85,99,0.15)' }, ticks: { color: '#4b5563', font: { size: 8 }, padding: 2 } }
                    }
                }
            });

            charts.index = new Chart(document.getElementById('c-index'), {
                type: 'line',
                data: {
                    labels: emptyLabels,
                    datasets: [
                        {
                            label: 'CPLI',
                            data: [...cpliData],
                            borderColor: '#ef4444',
                            borderWidth: 1.2,
                            fill: false,
                            tension: 0.3,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        },
                        {
                            label: 'CLI',
                            data: [...cliData],
                            borderColor: '#f59e0b',
                            borderWidth: 1.2,
                            fill: false,
                            tension: 0.3,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        },
                        {
                            label: 'FSI',
                            data: [...fsiData],
                            borderColor: '#ec4899',
                            borderWidth: 1.2,
                            fill: false,
                            tension: 0.3,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    parsing: false,
                    animation: { duration: 0 },
                    plugins: { legend: { display: true, labels: { color: '#4b5563', font: { size: 8 }, boxWidth: 8 } } },
                    scales: {
                        x: { display: false, grid: { display: false } },
                        y: { min: 0, max: 1.1, grid: { color: 'rgba(75,85,99,0.1)' }, ticks: { color: '#4b5563', font: { size: 8 } } }
                    }
                }
            });

            charts.emotion = new Chart(document.getElementById('c-emotion'), {
                type: 'scatter',
                data: {
                    datasets: [
                        {
                            label: '当前',
                            data: [{x: 0.5, y: 0.5}],
                            backgroundColor: '#f59e0b',
                            borderColor: '#fff',
                            borderWidth: 2,
                            pointRadius: 7,
                            pointHoverRadius: 9
                        },
                        {
                            label: '轨迹',
                            data: [],
                            backgroundColor: 'rgba(245,158,11,0.25)',
                            borderColor: 'transparent',
                            pointRadius: 2,
                            pointHoverRadius: 4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 0 },
                    plugins: { legend: { display: true, labels: { color: '#4b5563', font: { size: 8 }, boxWidth: 8 } } },
                    scales: {
                        x: { min: 0, max: 1, title: { display: true, text: '效价', color: '#4b5563', font: { size: 9 } }, grid: { color: 'rgba(75,85,99,0.1)' }, ticks: { color: '#4b5563', font: { size: 8 } } },
                        y: { min: 0, max: 1, title: { display: true, text: '唤醒', color: '#4b5563', font: { size: 9 } }, grid: { color: 'rgba(75,85,99,0.1)' }, ticks: { color: '#4b5563', font: { size: 8 } } }
                    }
                }
            });

            charts.radar = new Chart(document.getElementById('c-radar'), {
                type: 'radar',
                data: {
                    labels: ['HRV最优', '心率稳定', 'ANS协调', '呼吸同步'],
                    datasets: [{
                        data: [0.5, 0.5, 0.5, 0.5],
                        borderColor: '#ec4899',
                        backgroundColor: 'rgba(236,72,153,0.15)',
                        borderWidth: 1.5,
                        pointBackgroundColor: '#ec4899',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 1,
                        pointRadius: 3,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 0 },
                    plugins: { legend: { display: false } },
                    scales: {
                        r: {
                            min: 0,
                            max: 1,
                            ticks: { display: false, stepSize: 0.2 },
                            grid: { color: 'rgba(75,85,99,0.15)' },
                            angleLines: { color: 'rgba(75,85,99,0.1)' },
                            pointLabels: { color: '#6b7280', font: { size: 9 } }
                        }
                    }
                }
            });
        }

        function setNeedle(id, v) {
            const el = document.getElementById(id);
            if (el) el.setAttribute('transform', `rotate(${-90 + v * 180} 70 75)`);
        }

        function normalizeData(arr, defaultVal = 0) {
            const result = arr.slice(-MAX);
            while (result.length < MAX) {
                result.unshift(defaultVal);
            }
            return result;
        }

        const sdnnBuf = Array(MAX).fill(0);
        const rmssdBuf = Array(MAX).fill(0);
        const cpliBuf = Array(MAX).fill(0);
        const cliBuf = Array(MAX).fill(0);
        const fsiBuf = Array(MAX).fill(0);
        const eValBuf = Array(MAX).fill(0.5);
        const eArBuf = Array(MAX).fill(0.5);

        async function tick() {
            try {
                const d = await (await fetch('/data')).json();
                const hr = d.heart_rate || 72;
                const br = d.breath_rate || 16;
                const rt = d.rt || {};
                const m = d.metrics || {};

                document.getElementById('v-hr').textContent = Math.round(hr);
                document.getElementById('v-br').textContent = br.toFixed(1);

                if (m.hrv) {
                    document.getElementById('v-sdnn').textContent = m.hrv.sdnn ? m.hrv.sdnn.toFixed(1) : '--';
                }
                if (m.physiological) {
                    document.getElementById('v-cpli').textContent = m.physiological.cpli ? m.physiological.cpli.toFixed(2) : '--';
                    setNeedle('n-phys', m.physiological.cpli || 0);
                    document.getElementById('g-phys').textContent = (m.physiological.cpli || 0).toFixed(2);
                }
                if (m.cognitive) {
                    document.getElementById('v-cli').textContent = m.cognitive.cli ? m.cognitive.cli.toFixed(2) : '--';
                    setNeedle('n-cog', m.cognitive.cli || 0);
                    document.getElementById('g-cog').textContent = (m.cognitive.cli || 0).toFixed(2);
                }
                if (m.flow) {
                    document.getElementById('v-fsi').textContent = m.flow.fsi ? m.flow.fsi.toFixed(2) : '--';
                    setNeedle('n-flow', m.flow.fsi || 0);
                    document.getElementById('g-flow').textContent = (m.flow.fsi || 0).toFixed(2);
                }
                if (m.emotion) {
                    setNeedle('n-emo', m.emotion.valence || 0.5);
                    document.getElementById('g-emo').textContent = (m.emotion.valence || 0.5).toFixed(2);
                }

                const pill = document.getElementById('e-pill');
                if (m.emotion && m.emotion.quadrant) {
                    const q = m.emotion.quadrant;
                    pill.textContent = q.replace('High Arousal Positive', '兴奋').replace('Low Arousal Positive', '平静')
                                       .replace('High Arousal Negative', '焦虑').replace('Low Arousal Negative', '低落');
                    pill.style.background = q.includes('Positive')
                        ? 'linear-gradient(90deg, #059669, #10b981)'
                        : 'linear-gradient(90deg, #dc2626, #ef4444)';
                }

                if (rt.heart_phase && rt.breath_phase) {
                    const hp = normalizeData(rt.heart_phase, 0);
                    const bp = normalizeData(rt.breath_phase, 0);
                    charts.phase.data.datasets[0].data = hp;
                    charts.phase.data.datasets[1].data = bp;
                    charts.phase.update('none');
                }

                if (rt.heart_rate && rt.breath_rate) {
                    const hrData = normalizeData(rt.heart_rate, 72);
                    const brData = normalizeData(rt.breath_rate, 16);
                    charts.rate.data.datasets[0].data = hrData;
                    charts.rate.data.datasets[1].data = brData;
                    charts.rate.update('none');
                }

                if (m.hrv) {
                    sdnnBuf.push(m.hrv.sdnn || 0);
                    sdnnBuf.shift();
                    rmssdBuf.push(m.hrv.rmssd || 0);
                    rmssdBuf.shift();
                    charts.hrv.data.datasets[0].data = [...sdnnBuf];
                    charts.hrv.data.datasets[1].data = [...rmssdBuf];
                    charts.hrv.update('none');
                }

                if (m.physiological && m.cognitive && m.flow) {
                    cpliBuf.push(m.physiological.cpli || 0);
                    cpliBuf.shift();
                    cliBuf.push(m.cognitive.cli || 0);
                    cliBuf.shift();
                    fsiBuf.push(m.flow.fsi || 0);
                    fsiBuf.shift();

                    charts.index.data.datasets[0].data = [...cpliBuf];
                    charts.index.data.datasets[1].data = [...cliBuf];
                    charts.index.data.datasets[2].data = [...fsiBuf];
                    charts.index.update('none');
                }

                if (m.emotion) {
                    eValBuf.push(m.emotion.valence || 0.5);
                    eValBuf.shift();
                    eArBuf.push(m.emotion.arousal || 0.5);
                    eArBuf.shift();

                    charts.emotion.data.datasets[0].data = [{x: m.emotion.valence, y: m.emotion.arousal}];

                    const trajLen = Math.min(15, eValBuf.length);
                    const traj = [];
                    for (let i = 0; i < trajLen; i++) {
                        traj.push({ x: eValBuf[eValBuf.length - trajLen + i], y: eArBuf[eArBuf.length - trajLen + i] });
                    }
                    charts.emotion.data.datasets[1].data = traj;
                    charts.emotion.update('none');
                }

                if (m.flow) {
                    charts.radar.data.datasets[0].data = [
                        m.flow.hrv_optimal || 0,
                        m.flow.hr_stability || 0,
                        m.flow.ans_coordination || 0,
                        m.flow.br_hr_sync || 0
                    ];
                    charts.radar.update('none');
                }

                document.getElementById('e-time').textContent = new Date().toLocaleTimeString('zh-CN', {hour12: false});
            } catch (e) {
                console.error('Data fetch error:', e);
            }
            setTimeout(tick, 200);
        }

        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            tick();
        });
    </script>