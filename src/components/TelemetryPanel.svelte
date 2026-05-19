<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
  function batColor(r: number): string {
    if (r < 0) return 'text-muted-foreground';
    if (r < 20) return 'text-destructive';
    if (r < 40) return 'text-warning';
    return 'text-success';
  }

  let d = $derived(app.drone);
  let ahiPitch = $derived(Math.max(-40, Math.min(40, d.pitch * 0.8)));
  let gpsOk = $derived(d.gps_fix === '3D' || d.gps_fix === 'RTK固定' || d.gps_fix === 'RTK浮动' || d.gps_fix === '差分');
  let satsOk = $derived(d.gps_sats >= 10);
  let batOk = $derived(d.remaining > 20 || d.remaining < 0);
  let homeOk = $derived(d.home_lat !== 0);
</script>

<div class="bg-card border border-border rounded-xl p-4 flex-1 min-w-0">
  <div class="flex items-center gap-3 mb-3 flex-wrap">
    <span class="text-xl font-bold">{d.mode}</span>
    <Badge variant={d.armed ? 'destructive' : 'default'} class="text-xs font-bold">
      {d.armed ? '已解锁' : '已锁定'}
    </Badge>
    <span class="text-sm text-muted-foreground">{d.gps_fix} {d.gps_sats}星</span>
    {#if d.flight_time > 0}<span class="text-sm text-warning font-mono">{fmtTime(d.flight_time)}</span>{/if}
    {#if d.bat_time > 0}<span class="text-xs text-warning">剩余{d.bat_time}s</span>{/if}
  </div>

  <div class="grid grid-cols-3 gap-2 max-md:grid-cols-2">
    <div class="bg-background rounded-lg p-3">
      <div class="text-[11px] text-muted-foreground uppercase">姿态</div>
      <div class="flex items-center gap-2 mt-1">
        <svg viewBox="-50 -50 100 100" width="56" height="56" class="rounded-full border border-border shrink-0">
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
          <div class="text-sm font-bold tabular-nums">{d.roll.toFixed(1)} / {d.pitch.toFixed(1)} / {d.yaw.toFixed(0)}</div>
          <div class="text-[11px] text-muted-foreground">横滚 / 俯仰 / 偏航</div>
        </div>
      </div>
    </div>
    <div class="bg-background rounded-lg p-3">
      <div class="text-[11px] text-muted-foreground uppercase">位置</div>
      <div class="text-sm font-bold mt-1 tabular-nums">{d.lat.toFixed(6)}, {d.lon.toFixed(6)}</div>
      <div class="text-[11px] text-muted-foreground">距起飞点 {d.dist_home.toFixed(0)}m</div>
    </div>
    <div class="bg-background rounded-lg p-3">
      <div class="text-[11px] text-muted-foreground uppercase">高度</div>
      <div class="text-lg font-bold mt-1 tabular-nums">{d.alt_rel.toFixed(1)} m</div>
      <div class="text-[11px] text-muted-foreground">海拔 {d.alt_msl.toFixed(0)}m</div>
    </div>
    <div class="bg-background rounded-lg p-3">
      <div class="text-[11px] text-muted-foreground uppercase">速度</div>
      <div class="flex items-center gap-2 mt-1">
        <svg viewBox="-30 -30 60 60" width="30" height="30" class="shrink-0">
          <circle r="25" fill="none" stroke="hsl(var(--border))" stroke-width="1"/>
          <g transform="rotate({-d.hdg})">
            <text y="-16" text-anchor="middle" fill="#f44336" font-size="9" font-weight="bold">N</text>
            <text y="22" text-anchor="middle" fill="#666" font-size="7">S</text>
          </g>
          <polygon points="0,-22 -3,-17 3,-17" fill="#ff9800"/>
        </svg>
        <div>
          <div class="text-base font-bold tabular-nums">{d.gs.toFixed(1)} m/s</div>
          <div class="text-[11px] text-muted-foreground">垂直 {d.vz.toFixed(1)}m/s | {d.hdg.toFixed(0)}&deg;</div>
        </div>
      </div>
    </div>
    <div class="bg-background rounded-lg p-3">
      <div class="text-[11px] text-muted-foreground uppercase">电池</div>
      <div class="text-lg font-bold mt-1 {batColor(d.remaining)} tabular-nums">{d.voltage.toFixed(1)} V</div>
      <div class="text-[11px] text-muted-foreground">{d.current.toFixed(1)} A | {d.remaining >= 0 ? d.remaining + '%' : '---'}</div>
      <div class="mt-1 h-1.5 bg-muted rounded-full overflow-hidden">
        <div class="h-full rounded-full transition-all duration-500
          {d.remaining < 20 ? 'bg-destructive' : d.remaining < 40 ? 'bg-warning' : 'bg-success'}"
             style="width:{Math.max(0, d.remaining)}%"></div>
      </div>
      {#if d.bat_time > 0}
        <div class="text-[11px] text-warning mt-0.5">剩余约 {Math.floor(d.bat_time / 60)}分{d.bat_time % 60}秒</div>
      {/if}
    </div>
    <div class="bg-background rounded-lg p-3">
      <div class="text-[11px] text-muted-foreground uppercase">航点 / 机型</div>
      <div class="text-lg font-bold mt-1">#{d.wp} <span class="text-sm text-muted-foreground">{d.vtype || '---'}</span></div>
      <div class="text-[11px] text-muted-foreground">链路 {d.link_age >= 0 ? d.link_age.toFixed(1) + 's' : '---'} | 帧 {d.frames}</div>
    </div>
  </div>

  <div class="flex gap-1.5 mt-2 flex-wrap">
    <Badge variant={gpsOk ? 'default' : 'secondary'} class="text-[10px]">GPS</Badge>
    <Badge variant={satsOk ? 'default' : 'secondary'} class="text-[10px]">卫星</Badge>
    <Badge variant={batOk ? 'default' : 'secondary'} class="text-[10px]">电量</Badge>
    <Badge variant={homeOk ? 'default' : 'secondary'} class="text-[10px]">起飞点</Badge>
    {#if gpsOk && satsOk && batOk && homeOk}
      <Badge class="text-[10px] bg-green-700 text-white">就绪</Badge>
    {/if}
  </div>
</div>
