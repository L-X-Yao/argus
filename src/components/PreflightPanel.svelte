<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { t } from '../lib/i18n.svelte';
  import { Check, X as XIcon } from '@lucide/svelte';

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
      { name: '导航滤波', ok: !(d.ekf_flags & 0x480) && Math.max(d.ekf_vel, d.ekf_pos_h, d.ekf_pos_v, d.ekf_compass) < 1.0,
        detail: (d.ekf_flags & 0x480) ? '异常' : Math.max(d.ekf_vel, d.ekf_pos_h, d.ekf_pos_v, d.ekf_compass) < 0.5 ? '正常' : '警告', critical: true },
      { name: '振动水平', ok: Math.max(d.vibe[0], d.vibe[1], d.vibe[2]) < 30,
        detail: `${Math.max(d.vibe[0], d.vibe[1], d.vibe[2]).toFixed(0)} m/s² (限<30)`, critical: true },
      { name: '遥控信号', ok: d.rc_rssi > 0 || d.rc[0] > 0,
        detail: d.rc_rssi > 0 ? `RSSI ${d.rc_rssi}` : d.rc[0] > 0 ? '有信号' : '无信号', critical: false },
      { name: '任务航线', ok: app.waypoints.length > 0,
        detail: app.waypoints.length > 0 ? `${app.waypoints.length} 航点` : '未加载', critical: false },
      { name: '机型识别', ok: d.vtype !== '', detail: d.vtype || '未识别', critical: false },
      { name: '未解锁', ok: !d.armed, detail: d.armed ? '已解锁 — 注意安全' : '已锁定', critical: false },
    ];
  });

  let allCriticalOk = $derived(checks.filter(c => c.critical).every(c => c.ok));
  let passCount = $derived(checks.filter(c => c.ok).length);
</script>

<div class="p-3">
  <div class="flex items-center justify-between mb-2">
    <h2 class="text-xs font-semibold text-primary uppercase tracking-wider">{t('preflight.title')}</h2>
    <span class="text-[11px] font-medium {allCriticalOk ? 'text-success' : 'text-muted-foreground'}">
      {passCount}/{checks.length} {allCriticalOk ? t('preflight.ready') : t('preflight.notReady')}
    </span>
  </div>
  <div class="grid grid-cols-2 gap-x-3 gap-y-1 max-sm:grid-cols-1">
    {#each checks as c}
      <div class="flex items-center gap-1.5 py-0.5">
        <span class="w-4.5 h-4.5 rounded-full flex items-center justify-center shrink-0
          {c.ok ? 'bg-green-700 text-white' : c.critical ? 'bg-destructive text-white' : 'bg-muted text-muted-foreground'}">
          {#if c.ok}<Check size={11} strokeWidth={3} />{:else}<XIcon size={11} strokeWidth={3} />{/if}
        </span>
        <span class="text-xs font-semibold whitespace-nowrap">{c.name}</span>
        <span class="text-[11px] text-muted-foreground truncate">{c.detail}</span>
      </div>
    {/each}
  </div>
  {#if allCriticalOk}
    <div class="mt-2 py-1.5 bg-green-900/40 text-success text-center rounded-lg text-xs font-bold border border-green-700/30">
      {t('preflight.allPass')}
    </div>
  {/if}
</div>
