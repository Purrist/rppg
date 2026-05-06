# dashboard_preview.py
# 运行: python dashboard_preview.py
# 会在当前目录生成 dashboard_preview.png
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

# ===== 颜色 =====
BG='#050a12'; BG2='#0a1220'; BG3='#0b1322'; BD='#13203a'
C={'red':'#ff4757','cyan':'#00e5ff','teal':'#14b8a6','purple':'#a855f7',
   'pink':'#ec4899','blue':'#3b82f6','orange':'#f97316','yellow':'#facc15',
   'green':'#00e676','dim':'#2a4060','mid':'#4a6a8a','txt':'#c8d6e5'}

def sa(ax, title='', xy=True):
    ax.set_facecolor(BG2)
    for s in ax.spines.values(): s.set_color(BD); s.set_linewidth(0.5)
    if title:
        ax.set_title(title, fontsize=7, color=C['mid'], fontweight='600',
                     loc='left', pad=3, fontfamily='monospace')
    ax.tick_params(colors=C['dim'], labelsize=5, length=0)
    ax.grid(True, color='#0f1a2d', linewidth=0.3, linestyle='--')
    if not xy: ax.set_xticks([]); ax.set_yticks([])

# ===== 虚拟数据 =====
np.random.seed(42)
N = 300; t = np.linspace(0, 30, N)

inst_hr = np.clip(72 + 4*np.sin(2*np.pi*t/4.5) + np.random.normal(0,1.5,N), 55, 95)
inst_br = np.clip(16 + np.random.normal(0,0.8,N), 12, 22)
hp = np.cumsum(inst_hr/60*0.1)*2*np.pi
bp = np.cumsum(inst_br/60*0.1)*2*np.pi
rsa_t = np.clip(5 - 2*np.exp(-((t-12)**2)/20) + np.random.normal(0,0.3,N), 1, 8)
plv_t = np.clip(0.65 - 0.2*np.exp(-((t-10)**2)/30) + np.random.normal(0,0.02,N), 0.1, 0.9)
pd_t = np.clip(0.8 + 0.3*np.sin(2*np.pi*t/8) + np.random.normal(0,0.15,N), -np.pi, np.pi)
brv_t = np.clip(8 + 3*np.sin(2*np.pi*t/15) + np.random.normal(0,1,N), 2, 20)
hrr_t = np.clip(10 + 8*np.sin(2*np.pi*t/20) + np.random.normal(0,1,N), 0, 40)
hri_t = np.clip(3.5 - 1*np.exp(-((t-12)**2)/25) + np.random.normal(0,0.3,N), 0.5, 6)
sl_t = np.random.normal(0, 0.3, N)
cr_t = np.clip(4.5 + 0.3*np.sin(2*np.pi*t/12) + np.random.normal(0,0.1,N), 3, 6)
el_t = np.random.normal(0, 3, N)
rhr = 72 + np.random.normal(0,2,N); rbr = 16 + np.random.normal(0,0.5,N)
rc = [5.2,4.8,5.1,4.3,3.8,3.2,2.8,3.5,4.0,4.5,4.8,5.0,4.9,5.1,5.3]
hh = np.random.normal(72,5,500); bh = np.random.normal(16,1.2,500)

# ===== 画布 =====
fig = plt.figure(figsize=(22.2, 12.5), facecolor=BG, dpi=100)
gs = GridSpec(8, 12, figure=fig, hspace=0.45, wspace=0.35,
              left=0.025, right=0.975, top=0.97, bottom=0.01,
              height_ratios=[0.5, 0.28, 0.62, 1, 1, 1, 1, 1])

# ===== Header =====
a = fig.add_subplot(gs[0,:])
a.set_facecolor('#0a1120'); a.set_xlim(0,1); a.set_ylim(0,1)
a.set_xticks([]); a.set_yticks([])
for s in a.spines.values(): s.set_visible(False)
a.text(0.01, 0.5, 'HLK-LD6002', fontsize=14, color=C['cyan'],
        fontweight='700', fontfamily='monospace', va='center')
a.text(0.125, 0.5, 'PhysioEngine V4.0 / Phase Dynamics', fontsize=8,
        color=C['mid'], fontfamily='monospace', va='center')
a.text(0.70, 0.55, 'HR', fontsize=8, color=C['dim'], fontfamily='monospace',
        va='center', fontweight='600')
a.text(0.735, 0.55, '72', fontsize=20, color=C['red'], fontfamily='monospace',
        va='center', fontweight='700')
a.text(0.79, 0.55, 'bpm', fontsize=7, color=C['dim'], fontfamily='monospace', va='center')
a.text(0.84, 0.55, 'BR', fontsize=8, color=C['dim'], fontfamily='monospace',
        va='center', fontweight='600')
a.text(0.87, 0.55, '16', fontsize=20, color=C['cyan'], fontfamily='monospace',
        va='center', fontweight='700')
a.text(0.925, 0.55, '/min', fontsize=7, color=C['dim'], fontfamily='monospace',
        va='center')
a.add_patch(plt.Circle((0.975, 0.55), 0.015, transform=a.transAxes,
                         color=C['green'], zorder=10))
a.text(0.965, 0.55, 'LIVE', fontsize=7, color=C['mid'], fontfamily='monospace',
        va='center', ha='right')

# ===== Profile =====
a = fig.add_subplot(gs[1,:])
a.set_facecolor('#080e1a'); a.set_xlim(0,1); a.set_ylim(0,1)
a.set_xticks([]); a.set_yticks([])
for s in a.spines.values(): s.set_visible(False)
for i, tx in enumerate(['HRrest 63.0 bpm','BRrest 14.3 /min',
                         'HRmax 166.0 bpm','RSAbase 11.0 bpm','PLVbase 0.480']):
    a.text(0.01+i*0.2, 0.5, tx, fontsize=7, color=C['mid'],
           fontfamily='monospace', va='center')

# ===== Cards =====
a = fig.add_subplot(gs[2,:])
a.set_facecolor(BG); a.set_xlim(0,1); a.set_ylim(0,1)
a.set_xticks([]); a.set_yticks([])
for s in a.spines.values(): s.set_visible(False)
cd = [('RSA','4.28','teal','base 11','S'), ('PLV','0.542','purple','0~1','S'),
      ('PhaseD','0.83','pink','rad','S'), ('BRV','8.5%','cyan','CV%','A'),
      ('HRR','12.3%','red','%','A'), ('HRI','2.85','blue','SDbpm','A'),
      ('CR','4.50','orange','HR/BR','A'), ('Slope','0.12','yellow','bpm/s','A'),
      ('Elev','-2.1%','pink','%','A'), ('Samples','847','mid','total','N')]
cw = 0.097
for i, (nm, vl, cl, sb, bg) in enumerate(cd):
    x0 = 0.005 + i*(cw+0.003)
    r = FancyBboxPatch((x0,0.08), cw, 0.84, boxstyle="round,pad=0.008",
                        facecolor=BG3, edgecolor=BD, linewidth=0.5,
                        transform=a.transAxes)
    a.add_patch(r)
    bc = C['cyan'] if bg in ('S','N') else C['red']
    a.text(x0+cw-0.008, 0.85, bg, fontsize=6, color=bc, fontweight='700',
           ha='right', transform=a.transAxes, fontfamily='monospace')
    a.text(x0+0.006, 0.85, nm, fontsize=7, color=C['dim'], fontweight='600',
           transform=a.transAxes, fontfamily='monospace')
    a.text(x0+0.006, 0.42, vl, fontsize=14, color=C[cl], fontweight='700',
           transform=a.transAxes, fontfamily='monospace')
    a.text(x0+0.006, 0.15, sb, fontsize=6, color=C['dim'],
           transform=a.transAxes, fontfamily='monospace')

# ===== ROW A (gs[3]): 4 panels =====
# 1. Instant HR/BR
ax = fig.add_subplot(gs[3,0:3]); sa(ax,'Instant HR/BR')
ax.plot(t, inst_hr, color=C['red'], lw=0.8)
ax.fill_between(t, inst_hr, alpha=0.08, color=C['red'])
ax2 = ax.twinx()
ax2.plot(t, inst_br, color=C['cyan'], lw=0.8)
ax2.fill_between(t, inst_br, alpha=0.06, color=C['cyan'])
ax2.tick_params(colors=C['dim'], labelsize=5, length=0)
for s in ax2.spines.values(): s.set_color(BD)

# 2. Lissajous (spans 2 rows)
ax = fig.add_subplot(gs[3:5,3:6]); sa(ax,'Lissajous Phase Space')
ax.scatter((bp%(2*np.pi))-np.pi, (hp%(2*np.pi))-np.pi,
           c=np.linspace(0.1,0.95,N), cmap='Purples', s=1, alpha=0.8, edgecolors='none')

# 3. Raw Phase
ax = fig.add_subplot(gs[3,6:9]); sa(ax,'Raw Phase Waveform')
ax.plot(t, hp[:N], color=C['red'], lw=0.5, alpha=0.7)
ax.plot(t, bp[:N], color=C['cyan'], lw=0.5, alpha=0.7)

# 4. Phase Diff Polar (spans 2 rows)
ax = fig.add_subplot(gs[3:5,9:12], projection='polar', facecolor=BG2)
ax.set_theta_zero_location('N'); ax.set_theta_direction(-1)
ax.tick_params(colors=C['dim'], labelsize=4, pad=1)
ax.grid(True, color='#0f1a2d', lw=0.3, ls='--')
ax.spines['polar'].set_color(BD); ax.spines['polar'].set_linewidth(0.5)
ax.set_rlim(-1, 1)
dd = (hp-bp)%(2*np.pi) - np.pi + np.random.normal(0,0.3,len(hp))
ang = np.arctan2(np.sin(dd[-150:]), np.cos(dd[-150:]))
rd = np.clip(np.abs(dd[-150:]), 0, 1)
ax.scatter(ang, rd, c=C['pink'], s=4, alpha=0.3)
ax.scatter(ang[-1:], rd[-1:], c=C['pink'], s=30, zorder=10,
           edgecolors='white', lw=0.5)
fig.text(0.835, 0.895, 'Phase Diff Polar', fontsize=7, color=C['mid'],
         fontweight='600', fontfamily='monospace')

# ===== ROW B (gs[4]): right side =====
# 5. RSA Trend
ax = fig.add_subplot(gs[4,0:2]); sa(ax,'RSA Trend')
ax.plot(t, rsa_t, color=C['teal'], lw=0.8)
ax.fill_between(t, rsa_t, alpha=0.1, color=C['teal'])
ax.axhline(11, color=C['mid'], lw=0.5, ls='--', alpha=0.5)
ax.text(28, 11.3, 'base', fontsize=5, color=C['mid'], ha='right')

# 6. RSA Polar
ax = fig.add_subplot(gs[4,2:4], projection='polar', facecolor=BG2)
ax.tick_params(colors=C['dim'], labelsize=4, pad=1)
ax.grid(True, color='#0f1a2d', lw=0.3, ls='--')
ax.spines['polar'].set_color(BD); ax.spines['polar'].set_linewidth(0.5)
ax.scatter(bp[:150]%(2*np.pi), inst_hr[:150], c=C['teal'], s=3, alpha=0.4)
fig.text(0.22, 0.665, 'RSA Polar Wrap', fontsize=7, color=C['mid'],
         fontweight='600', fontfamily='monospace')

# 7. RSA Per-Cycle
ax = fig.add_subplot(gs[4,4:6]); sa(ax,'RSA Per-Cycle')
cb2 = [C['green'] if v>=11 else C['yellow'] if v>=6.6 else C['red'] for v in rc]
ax.bar(range(len(rc)), rc, color=cb2, width=0.7, lw=0)
ax.axhline(11, color=C['mid'], lw=0.5, ls='--', alpha=0.5)

# 8. HR Distribution
ax = fig.add_subplot(gs[4,6:8]); sa(ax,'HR Distribution')
ax.hist(hh, bins=30, color=C['blue'], alpha=0.7, edgecolor='none')
ax.set_xlim(50, 95)

# 9. PLV Color Trend
ax = fig.add_subplot(gs[4,8:10]); sa(ax,'PLV Trend (Color)')
for i in range(len(t)-1):
    v = plv_t[i]
    ax.plot(t[i:i+2], plv_t[i:i+2],
            color=C['red'] if v<0.2 else C['yellow'] if v<0.4 else C['purple'], lw=0.8)
ax.fill_between(t, plv_t, alpha=0.08, color=C['purple'])
ax.axhline(0.4, color=C['red'], lw=0.4, ls='--', alpha=0.4)
ax.set_ylim(0, 1)
ax.text(28, 0.42, '0.4', fontsize=5, color=C['red'], ha='right')

# 10. Phase Diff Series
ax = fig.add_subplot(gs[4,10:12]); sa(ax,'Phase Diff Series')
ax.plot(t, pd_t, color=C['pink'], lw=0.8)
ax.fill_between(t, pd_t, alpha=0.08, color=C['pink'])
ax.axhline(0, color=C['mid'], lw=0.4, ls='--', alpha=0.4)

# ===== ROW C (gs[5]): 6 charts =====
row_c = [
    (gs[5,0:2], brv_t, C['cyan'], 'BRV Trend', None),
    (gs[5,2:4], hrr_t, C['red'], 'HRR %', [20,45]),
    (gs[5,4:6], hri_t, C['blue'], 'HRI (HR Oscillation)', None),
    (gs[5,6:8], sl_t, C['yellow'], 'HR Slope', None),
    (gs[5,8:10], cr_t, C['orange'], 'CR Ratio (HR/BR)', [3.5,5.5]),
    (gs[5,10:12], el_t, C['pink'], 'BR Elevation %', None),
]
for pos, data, cl, ttl, extra in row_c:
    ax = fig.add_subplot(pos); sa(ax, ttl)
    ax.plot(t, data, color=cl, lw=0.8)
    ax.fill_between(t, data, alpha=0.1, color=cl)
    if extra:
        ax.axhline(extra[0], color=cl, lw=0.3, ls='--', alpha=0.4)
        ax.axhline(extra[1], color=cl, lw=0.3, ls='--', alpha=0.4)

# ===== ROW D (gs[6]): 4 charts =====
# 17. Raw HR/BR
ax = fig.add_subplot(gs[6,0:3]); sa(ax,'Raw HR/BR Trend')
ax.plot(t, rhr, color=C['red'], lw=1.0)
ax2 = ax.twinx()
ax2.plot(t, rbr, color=C['cyan'], lw=1.0)
ax2.tick_params(colors=C['dim'], labelsize=5, length=0)
for s in ax2.spines.values(): s.set_color(BD)

# 18. BR Distribution
ax = fig.add_subplot(gs[6,3:5]); sa(ax,'BR Distribution')
ax.hist(bh, bins=20, color=C['cyan'], alpha=0.7, edgecolor='none')
ax.set_xlim(10, 25)

# 19. RSA vs PLV
ax = fig.add_subplot(gs[6,5:7]); sa(ax,'RSA vs PLV Correlation')
ax.scatter(plv_t[::3], rsa_t[::3], c=C['teal'], s=4, alpha=0.4, edgecolors='none')
ax.scatter(plv_t[-1], rsa_t[-1], c=C['teal'], s=40,
           edgecolors='white', lw=0.5, zorder=10)
ax.set_xlim(0, 1)

# 20. Composite
ax = fig.add_subplot(gs[6,7:12]); sa(ax,'Composite: HRR / CR / BRV')
ax.plot(t, hrr_t, color=C['red'], lw=0.8, label='HRR%')
ax.plot(t, cr_t, color=C['orange'], lw=0.8, label='CR')
ax.bar(t, brv_t, width=0.08, color=C['cyan'], alpha=0.3, label='BRV%')
ax.legend(fontsize=6, loc='upper right', facecolor=BG2, edgecolor=BD,
          labelcolor=C['mid'])

# ===== ROW E (gs[7]): 4 detail panels =====
hd = np.unwrap(np.diff(np.concatenate([[hp[0]], hp[:200]])))
ax = fig.add_subplot(gs[7,0:3]); sa(ax,'HR Phase Differential')
ax.plot(t[:200], hd, color=C['red'], lw=0.5, alpha=0.8)
ax.fill_between(t[:200], hd, alpha=0.06, color=C['red'])

bd2 = np.unwrap(np.diff(np.concatenate([[bp[0]], bp[:200]])))
ax = fig.add_subplot(gs[7,3:6]); sa(ax,'BR Phase Modulation')
ax.plot(t[:200], bd2, color=C['cyan'], lw=0.5, alpha=0.8)
ax.fill_between(t[:200], bd2, alpha=0.06, color=C['cyan'])

ax = fig.add_subplot(gs[7,6:9]); sa(ax,'HRR vs HRI Correlation')
ax.scatter(hrr_t[::3], hri_t[::3], c=C['blue'], s=4, alpha=0.4, edgecolors='none')
ax.scatter(hrr_t[-1], hri_t[-1], c=C['blue'], s=40,
           edgecolors='white', lw=0.5, zorder=10)

# 24. System Gauges
ax = fig.add_subplot(gs[7,9:12]); sa(ax,'System Status Gauges', xy=False)
ax.set_xlim(0, 4); ax.set_ylim(0, 4)
for i, (nm, vl, bs, cl) in enumerate([('RSA',4.28,11.0,'teal'),
                                        ('PLV',0.542,0.65,'purple'),
                                        ('BRV',8.5,8.0,'cyan'),
                                        ('HRR',12.3,100.0,'red')]):
    y = 3.5 - i*1.0
    rt = min(vl/bs, 1.5) if bs > 0 else 0
    ax.text(0.2, y, nm, fontsize=8, color=C[cl], fontweight='700',
            fontfamily='monospace', va='center')
    ax.barh(y, rt*2.5, height=0.5, left=1.2, color=C[cl], alpha=0.3,
            edgecolor=C[cl], linewidth=0.5)
    ax.text(1.2+rt*2.5+0.1, y, str(vl), fontsize=7, color=C['txt'],
            va='center', fontfamily='monospace')
    ax.text(3.9, y, '/'+str(bs), fontsize=6, color=C['dim'],
            va='center', fontfamily='monospace', ha='right')

# ===== Save =====
plt.savefig('dashboard_preview.png', facecolor=BG, dpi=120,
            bbox_inches='tight', pad_inches=0.1)
plt.close()
print('OK -> dashboard_preview.png (22.2x12.5 inches, 120dpi)')
