<script lang="ts">
  import { app } from '../lib/stores.svelte';

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
  function batColor(r: number): string {
    if (r < 0) return '#555';
    if (r < 20) return '#f44336';
    if (r < 40) return '#ff9800';
    return '#4caf50';
  }
  function pfColor(ok: boolean): string { return ok ? '#2e7d32' : '#333'; }

  let d = $derived(app.drone);
  let ahiPitch = $derived(Math.max(-40, Math.min(40, d.pitch * 0.8)));
  let gpsOk = $derived(d.gps_fix === '3D' || d.gps_fix === 'RTK固定' || d.gps_fix === 'RTK浮动' || d.gps_fix === '差分');
  let satsOk = $derived(d.gps_sats >= 10);
  let batOk = $derived(d.remaining > 20 || d.remaining < 0);
  let homeOk = $derived(d.home_lat !== 0);
</script>

<div class="panel telem">
  <div class="header-row">
    <span class="mode-name">{d.mode}</span>
    <span class="armed-badge" class:armed={d.armed}>{d.armed ? '已解锁' : '已锁定'}</span>
    <span class="gps">{d.gps_fix} {d.gps_sats}星</span>
    {#if d.flight_time > 0}<span class="timer">{fmtTime(d.flight_time)}</span>{/if}
    {#if d.bat_time > 0}<span class="bat-time">剩余{d.bat_time}s</span>{/if}
  </div>

  <div class="grid">
    <div class="card">
      <div class="label">姿态</div>
      <div style="display:flex;align-items:center;gap:8px">
        <svg viewBox="-50 -50 100 100" width="70" height="70" style="border-radius:50%;border:1px solid #444;flex-shrink:0">
          <defs><clipPath id="ahClip"><circle r="45"/></clipPath></defs>
          <g transform="rotate({-d.roll})" clip-path="url(#ahClip)">
            <rect x="-60" y={-60 + ahiPitch} width="120" height="60" fill="#1565c0"/>
            <rect x="-60" y={ahiPitch} width="120" height="60" fill="#795548"/>
            <line x1="-60" y1={ahiPitch} x2="60" y2={ahiPitch} stroke="white" stroke-width="0.5"/>
          </g>
          <line x1="-18" y1="0" x2="-6" y2="0" stroke="#ffa726" stroke-width="2.5"/>
          <line x1="6" y1="0" x2="18" y2="0" stroke="#ffa726" stroke-width="2.5"/>
          <circle r="2.5" fill="none" stroke="#ffa726" stroke-width="1.5"/>
        </svg>
        <div>
          <div class="value" style="font-size:14px">{d.roll.toFixed(1)} / {d.pitch.toFixed(1)} / {d.yaw.toFixed(0)}</div>
          <div class="unit">横滚 / 俯仰 / 偏航</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="label">位置</div>
      <div class="value" style="font-size:15px">{d.lat.toFixed(6)}, {d.lon.toFixed(6)}</div>
      <div class="unit">距起飞点 {d.dist_home.toFixed(0)}m</div>
    </div>
    <div class="card">
      <div class="label">高度</div>
      <div class="value">{d.alt_rel.toFixed(1)} m</div>
      <div class="unit">海拔 {d.alt_msl.toFixed(0)}m</div>
    </div>
    <div class="card">
      <div class="label">速度</div>
      <div style="display:flex;align-items:center;gap:6px">
        <svg viewBox="-30 -30 60 60" width="34" height="34" style="flex-shrink:0">
          <circle r="25" fill="none" stroke="#555" stroke-width="1"/>
          <g transform="rotate({-d.hdg})">
            <text y="-16" text-anchor="middle" fill="#f44336" font-size="9" font-weight="bold">N</text>
            <text y="22" text-anchor="middle" fill="#666" font-size="7">S</text>
          </g>
          <polygon points="0,-22 -3,-17 3,-17" fill="#ff9800"/>
        </svg>
        <div>
          <div class="value" style="font-size:16px">{d.gs.toFixed(1)} m/s</div>
          <div class="unit">垂直 {d.vz.toFixed(1)}m/s | {d.hdg.toFixed(0)}&deg;</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="label">电池</div>
      <div class="value">{d.voltage.toFixed(1)} V</div>
      <div class="unit">{d.current.toFixed(1)} A | {d.remaining >= 0 ? d.remaining + '%' : '---'}</div>
      <div class="bat-bar"><div class="bat-fill" style="width:{Math.max(0,d.remaining)}%;background:{batColor(d.remaining)}"></div></div>
    </div>
    <div class="card">
      <div class="label">航点</div>
      <div class="value">#{d.wp}</div>
      <div class="unit">机型: {d.vtype || '---'}</div>
    </div>
  </div>

  <div class="preflight">
    <span class="pf" style="background:{pfColor(gpsOk)}">GPS</span>
    <span class="pf" style="background:{pfColor(satsOk)}">卫星</span>
    <span class="pf" style="background:{pfColor(batOk)}">电量</span>
    <span class="pf" style="background:{pfColor(homeOk)}">起飞点</span>
    {#if gpsOk && satsOk && batOk && homeOk}
      <span class="pf ready">就绪</span>
    {/if}
  </div>
</div>

<style>
  .panel { background:var(--bg-panel); border-radius:8px; padding:15px; flex:1; min-width:0; }
  .header-row { display:flex; align-items:center; gap:12px; margin-bottom:10px; flex-wrap:wrap; }
  .mode-name { font-size:22px; font-weight:bold; }
  .armed-badge { padding:3px 12px; border-radius:12px; font-size:13px; font-weight:bold; background:#2e7d32; color:white; }
  .armed-badge.armed { background:#d32f2f; }
  .gps { font-size:14px; color:var(--text-dim); }
  .timer { font-size:14px; color:#ffa726; }
  .bat-time { font-size:12px; color:#ff9800; }
  .grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; }
  .card { background:var(--bg-card); border-radius:6px; padding:10px; }
  .label { font-size:11px; color:var(--text-dim); text-transform:uppercase; }
  .value { font-size:18px; font-weight:bold; margin-top:3px; }
  .unit { font-size:12px; color:var(--text-dim); }
  .bat-bar { margin-top:4px; background:#333; border-radius:3px; height:6px; overflow:hidden; }
  .bat-fill { height:100%; border-radius:3px; transition:width 0.5s; }
  .preflight { display:flex; gap:6px; margin-top:8px; font-size:11px; flex-wrap:wrap; }
  .pf { padding:2px 6px; border-radius:3px; color:white; }
  .pf.ready { background:#2e7d32; font-weight:bold; }
  @media(max-width:800px) { .grid { grid-template-columns:1fr 1fr; } }
</style>
