<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);

  interface Check {
    name: string;
    ok: boolean;
    detail: string;
    critical: boolean;
  }

  let checks = $derived.by((): Check[] => {
    const gpsOk = d.gps_fix === '3D' || d.gps_fix === 'RTK固定' || d.gps_fix === 'RTK浮动' || d.gps_fix === '差分';
    return [
      { name: 'GPS 定位', ok: gpsOk, detail: `${d.gps_fix}`, critical: true },
      { name: '卫星数量', ok: d.gps_sats >= 10, detail: `${d.gps_sats} 颗 (需≥10)`, critical: true },
      { name: '电池电压', ok: d.voltage > 22, detail: `${d.voltage.toFixed(1)}V`, critical: true },
      { name: '电池电量', ok: d.remaining > 30 || d.remaining < 0, detail: d.remaining >= 0 ? `${d.remaining}%` : '---', critical: true },
      { name: '起飞点', ok: d.home_lat !== 0, detail: d.home_lat !== 0 ? `${d.home_lat.toFixed(5)}, ${d.home_lon.toFixed(5)}` : '未设置', critical: true },
      { name: '链路状态', ok: d.connected && d.link_age >= 0 && d.link_age < 2, detail: d.connected ? `延迟 ${d.link_age.toFixed(1)}s` : '未连接', critical: true },
      { name: '机型识别', ok: d.vtype !== '', detail: d.vtype || '未识别', critical: false },
      { name: '未解锁', ok: !d.armed, detail: d.armed ? '已解锁 — 注意安全' : '已锁定', critical: false },
    ];
  });

  let allCriticalOk = $derived(checks.filter(c => c.critical).every(c => c.ok));
  let passCount = $derived(checks.filter(c => c.ok).length);
</script>

<div class="panel preflight">
  <h2>
    预飞检查
    <span class="summary" class:ready={allCriticalOk}>
      {passCount}/{checks.length} {allCriticalOk ? '就绪' : '未就绪'}
    </span>
  </h2>
  <div class="checks">
    {#each checks as c}
      <div class="check-row">
        <span class="indicator" class:ok={c.ok} class:fail={!c.ok} class:crit={c.critical && !c.ok}>
          {c.ok ? '✓' : '✕'}
        </span>
        <span class="check-name">{c.name}</span>
        <span class="check-detail">{c.detail}</span>
      </div>
    {/each}
  </div>
  {#if allCriticalOk}
    <div class="ready-banner">所有关键项通过 — 可以飞行</div>
  {/if}
</div>

<style>
  .panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 8px; text-transform:uppercase; letter-spacing:1px; display:flex; align-items:center; justify-content:space-between; }
  .summary { font-size:12px; font-weight:normal; color:var(--text-dim); }
  .summary.ready { color:#69f0ae; }
  .checks { display:grid; grid-template-columns:1fr 1fr; gap:3px 12px; }
  .check-row { display:flex; align-items:center; gap:6px; padding:3px 0; }
  .indicator { width:18px; height:18px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:bold; flex-shrink:0; }
  .indicator.ok { background:#2e7d32; color:white; }
  .indicator.fail { background:#37474f; color:#888; }
  .indicator.crit { background:#d32f2f; color:white; }
  .check-name { font-size:12px; font-weight:bold; white-space:nowrap; }
  .check-detail { font-size:11px; color:var(--text-dim); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ready-banner { margin-top:8px; padding:6px; background:#1b5e20; color:#69f0ae; text-align:center; border-radius:4px; font-size:13px; font-weight:bold; }
  @media(max-width:600px) { .checks { grid-template-columns:1fr; } }
</style>
