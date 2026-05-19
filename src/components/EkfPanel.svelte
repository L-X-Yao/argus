<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';

  let d = $derived(app.drone);

  const FLAG_ATTITUDE       = 0x001;
  const FLAG_VEL_HORIZ      = 0x002;
  const FLAG_VEL_VERT       = 0x004;
  const FLAG_POS_HORIZ_REL  = 0x008;
  const FLAG_POS_HORIZ_ABS  = 0x010;
  const FLAG_POS_VERT_ABS   = 0x020;
  const FLAG_POS_VERT_AGL   = 0x040;
  const FLAG_CONST_POS      = 0x080;
  const FLAG_PRED_POS_REL   = 0x100;
  const FLAG_PRED_POS_ABS   = 0x200;
  const FLAG_UNINITIALIZED  = 0x400;

  interface FlagDef {
    mask: number;
    label: string;
    bad?: boolean;
  }

  const flags: FlagDef[] = [
    { mask: FLAG_ATTITUDE,      label: '姿态' },
    { mask: FLAG_VEL_HORIZ,     label: '水平速度' },
    { mask: FLAG_VEL_VERT,      label: '垂直速度' },
    { mask: FLAG_POS_HORIZ_REL, label: '相对位置' },
    { mask: FLAG_POS_HORIZ_ABS, label: '绝对位置' },
    { mask: FLAG_POS_VERT_ABS,  label: '绝对高度' },
    { mask: FLAG_POS_VERT_AGL,  label: '对地高度' },
    { mask: FLAG_CONST_POS,     label: '定点模式', bad: true },
    { mask: FLAG_PRED_POS_REL,  label: '预测相对' },
    { mask: FLAG_PRED_POS_ABS,  label: '预测绝对' },
    { mask: FLAG_UNINITIALIZED, label: '未初始化', bad: true },
  ];

  interface VarDef {
    key: 'ekf_vel' | 'ekf_pos_h' | 'ekf_pos_v' | 'ekf_compass';
    label: string;
    color: string;
  }

  const variances: VarDef[] = [
    { key: 'ekf_vel',     label: '速度',   color: '#4fc3f7' },
    { key: 'ekf_pos_h',   label: '水平位置', color: '#69f0ae' },
    { key: 'ekf_pos_v',   label: '垂直位置', color: '#ffd54f' },
    { key: 'ekf_compass', label: '罗盘',   color: '#ff8a65' },
  ];

  function varColor(v: number): string {
    if (v < 0.5) return '#22c55e';
    if (v < 1.0) return '#eab308';
    return '#ef4444';
  }

  function varLevel(v: number): string {
    if (v < 0.5) return '优';
    if (v < 1.0) return '警';
    return '差';
  }

  function overallHealth(f: number, vel: number, posH: number, posV: number, comp: number): { label: string; variant: 'default' | 'secondary' | 'destructive' } {
    if (f & FLAG_UNINITIALIZED) return { label: '未初始化', variant: 'destructive' };
    if (f & FLAG_CONST_POS) return { label: '定点降级', variant: 'destructive' };
    const maxVar = Math.max(vel, posH, posV, comp);
    if (maxVar >= 1.0) return { label: '异常', variant: 'destructive' };
    if (maxVar >= 0.5 || !(f & FLAG_POS_HORIZ_ABS)) return { label: '警告', variant: 'secondary' };
    return { label: '正常', variant: 'default' };
  }

  let health = $derived(overallHealth(d.ekf_flags, d.ekf_vel, d.ekf_pos_h, d.ekf_pos_v, d.ekf_compass));
</script>

<div class="bg-card border border-border rounded-xl p-4">
  <div class="flex items-center gap-2 mb-3">
    <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">导航滤波器</h2>
    <Badge variant={health.variant} class="text-[10px]">{health.label}</Badge>
  </div>

  <div class="space-y-2 mb-3">
    {#each variances as v}
      {@const val = d[v.key]}
      {@const pct = Math.min(val / 1.5 * 100, 100)}
      <div class="flex items-center gap-2 text-xs">
        <span class="w-16 text-muted-foreground font-mono truncate">{v.label}</span>
        <div class="flex-1 h-3 bg-muted rounded-full overflow-hidden">
          <div class="h-full rounded-full transition-all duration-300"
               style="width: {pct}%; background-color: {varColor(val)};">
          </div>
        </div>
        <span class="w-14 text-right font-mono" style="color: {varColor(val)}">
          {val.toFixed(3)}
        </span>
        <span class="w-6 text-center text-[10px] font-semibold" style="color: {varColor(val)}">
          {varLevel(val)}
        </span>
      </div>
    {/each}
  </div>

  <div class="border-t border-border pt-2">
    <div class="text-[10px] text-muted-foreground mb-1.5 font-semibold">标志位状态</div>
    <div class="flex flex-wrap gap-1">
      {#each flags as f}
        {@const active = !!(d.ekf_flags & f.mask)}
        {#if f.bad}
          {#if active}
            <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-destructive/15 text-destructive border border-destructive/30">
              {f.label}
            </span>
          {/if}
        {:else}
          <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors
            {active ? 'bg-primary/15 text-primary border border-primary/30' : 'bg-muted text-muted-foreground/50 border border-transparent'}">
            {f.label}
          </span>
        {/if}
      {/each}
    </div>
  </div>

  <div class="text-center mt-2 text-[9px] text-muted-foreground">
    方差: <span class="text-green-500">&#9632;</span>&lt;0.5 正常
    <span class="text-yellow-500"> &#9632;</span>&lt;1.0 警告
    <span class="text-red-500"> &#9632;</span>&ge;1.0 异常
  </div>
</div>
