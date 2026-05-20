<script lang="ts">
  import { paramState } from '../lib/paramStore.svelte';
  import { sendCommand } from '../lib/ws';
  import { addToast } from '../lib/stores.svelte';
  import type { Param } from '../lib/types';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { Battery, ShieldAlert, Sliders, Navigation, Radio, ToggleLeft, Cpu, FileText, List } from '@lucide/svelte';
  import type { Component } from 'svelte';

  const DESC: Record<string, string> = {
    BATT_CAPACITY: '电池容量 (mAh)', BATT_MONITOR: '电池监测类型',
    ARMING_CHECK: '解锁检查掩码', ARMING_REQUIRE: '解锁方式',
    FS_THR_ENABLE: '油门失控保护', FS_THR_VALUE: '油门失控阈值 (PWM)',
    FS_GCS_ENABLE: '地面站失联保护',
    FS_BATT_ENABLE: '电池失控保护', FS_BATT_MAH: '电池mAh保护阈值',
    FS_BATT_VOLTAGE: '电池电压保护阈值 (V)',
    ATC_RAT_RLL_P: '横滚速率 P', ATC_RAT_RLL_I: '横滚速率 I', ATC_RAT_RLL_D: '横滚速率 D',
    ATC_RAT_PIT_P: '俯仰速率 P', ATC_RAT_PIT_I: '俯仰速率 I', ATC_RAT_PIT_D: '俯仰速率 D',
    ATC_RAT_YAW_P: '偏航速率 P', ATC_RAT_YAW_I: '偏航速率 I', ATC_RAT_YAW_D: '偏航速率 D',
    INS_GYRO_FILTER: '陀螺仪滤波频率 (Hz)', INS_ACCEL_FILTER: '加速度计滤波频率 (Hz)',
    INS_LOG_BAT_MASK: 'IMU 批量日志掩码',
    LOG_BITMASK: '日志记录掩码', LOG_BACKEND_TYPE: '日志后端类型',
    RC1_MAX: '通道1最大 (PWM)', RC1_MIN: '通道1最小 (PWM)', RC1_TRIM: '通道1中位 (PWM)',
    RC2_MAX: '通道2最大 (PWM)', RC2_MIN: '通道2最小 (PWM)', RC2_TRIM: '通道2中位 (PWM)',
    WPNAV_SPEED: '航线速度 (cm/s)', WPNAV_SPEED_UP: '上升速度 (cm/s)', WPNAV_SPEED_DN: '下降速度 (cm/s)',
    RTL_ALT: '返航高度 (cm)', RTL_SPEED: '返航速度 (cm/s, 0=默认)',
    FLTMODE1: '模式开关1', FLTMODE2: '模式开关2', FLTMODE3: '模式开关3',
    FLTMODE4: '模式开关4', FLTMODE5: '模式开关5', FLTMODE6: '模式开关6',
  };

  const CATS: { key: string; label: string; icon: Component; match: (n: string) => boolean }[] = [
    { key: 'battery', label: '电池', icon: Battery, match: n => n.startsWith('BATT') || n === 'FS_BATT_ENABLE' || n === 'FS_BATT_MAH' || n === 'FS_BATT_VOLTAGE' },
    { key: 'failsafe', label: '保护', icon: ShieldAlert, match: n => n.startsWith('FS_') },
    { key: 'pid', label: 'PID', icon: Sliders, match: n => n.startsWith('ATC_RAT_') },
    { key: 'nav', label: '导航', icon: Navigation, match: n => n.startsWith('WPNAV') || n.startsWith('RTL') },
    { key: 'rc', label: '遥控', icon: Radio, match: n => /^RC\d/.test(n) },
    { key: 'modes', label: '模式', icon: ToggleLeft, match: n => n.startsWith('FLTMODE') },
    { key: 'sensor', label: '传感器', icon: Cpu, match: n => n.startsWith('INS_') },
    { key: 'log', label: '日志', icon: FileText, match: n => n.startsWith('LOG_') },
    { key: 'all', label: '全部', icon: List, match: () => true },
  ];

  let category = $state('all');
  let search = $state('');
  let editName = $state<string | null>(null);
  let editValue = $state('');
  let modified = $state<Set<string>>(new Set());

  let filtered = $derived.by(() => {
    const cat = CATS.find(c => c.key === category)!;
    let list = paramState.list.filter(p => cat.match(p.name));
    if (search) {
      const q = search.toUpperCase();
      list = list.filter(p => p.name.includes(q) || (DESC[p.name] || '').includes(search));
    }
    return list;
  });

  let progress = $derived(paramState.total > 0 ? Math.round(paramState.received / paramState.total * 100) : 0);

  function startEdit(p: Param) { editName = p.name; editValue = fmtValue(p.value); }
  function cancelEdit() { editName = null; }

  function submitEdit() {
    if (!editName) return;
    const val = parseFloat(editValue);
    if (isNaN(val)) { addToast('无效数值', 'error'); return; }
    const name = editName;
    sendCommand('param_set', undefined, { name, value: val });
    modified.add(name);
    modified = new Set(modified);
    editName = null;
    addToast(`${name} = ${val} 已发送`, 'info', 2000);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') submitEdit();
    else if (e.key === 'Escape') cancelEdit();
  }

  function fmtValue(v: number): string {
    if (Number.isInteger(v) || Math.abs(v) >= 100) return v.toFixed(0);
    if (Math.abs(v) >= 1) return v.toFixed(2);
    return v.toFixed(4);
  }

  function requestAll() { sendCommand('param_request_all'); }
  function saveParams() { sendCommand('param_save'); addToast('参数文件已保存', 'success'); }

  function exportParams() {
    if (!paramState.list.length) return;
    const lines = paramState.list.map(p => `${p.name}\t${fmtValue(p.value)}`).join('\n');
    const blob = new Blob([lines], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '参数_' + new Date().toISOString().slice(0, 10) + '.param';
    a.click();
    URL.revokeObjectURL(a.href);
    addToast(`已导出 ${paramState.list.length} 个参数`, 'success');
  }

  function importParams() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.param,.txt';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        const text: string = ev.target.result;
        const existing = new Map(paramState.list.map(p => [p.name, p.value]));
        let changed = 0;
        for (const line of text.split('\n')) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith('#')) continue;
          const parts = trimmed.split(/[\t,\s]+/);
          if (parts.length < 2) continue;
          const name = parts[0], val = parseFloat(parts[1]);
          if (isNaN(val)) continue;
          const cur = existing.get(name);
          if (cur !== undefined && Math.abs(cur - val) > 1e-6) {
            sendCommand('param_set', undefined, { name, value: val });
            modified.add(name);
            changed++;
          }
        }
        modified = new Set(modified);
        addToast(changed > 0 ? `已写入 ${changed} 个变更参数` : '无参数变更', changed > 0 ? 'success' : 'info');
      };
      reader.readAsText(file);
    };
    input.click();
  }
</script>

<div class="bg-card border border-border rounded-xl p-4 flex flex-col h-full">
  <div class="flex items-center justify-between flex-wrap gap-2 mb-3">
    <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">参数管理</h2>
    <div class="flex items-center gap-2">
      <Button variant="default" size="sm" onclick={requestAll} disabled={paramState.fetching}>
        {paramState.fetching ? `读取中 ${progress}%` : '读取参数'}
      </Button>
      {#if paramState.list.length > 0}
        <Button variant="secondary" size="sm" onclick={saveParams}>写入闪存</Button>
        <Button variant="outline" size="sm" onclick={exportParams}>导出</Button>
        <Button variant="outline" size="sm" onclick={importParams}>导入</Button>
        <Badge variant="outline" class="text-[10px] font-mono">{paramState.list.length} 参数</Badge>
      {/if}
    </div>
  </div>

  {#if paramState.fetching}
    <div class="h-1 bg-muted rounded-full mb-3 overflow-hidden">
      <div class="h-full bg-primary rounded-full transition-all duration-300" style="width:{progress}%"></div>
    </div>
  {/if}

  {#if paramState.list.length > 0}
    <div class="flex flex-wrap gap-1 mb-2">
      {#each CATS as cat}
        <button class="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-md border transition-all cursor-pointer
          {category === cat.key
            ? 'bg-primary text-primary-foreground border-primary'
            : 'bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted'}"
                onclick={() => category = cat.key}>
          <cat.icon size={11} />{cat.label}
        </button>
      {/each}
    </div>

    <div class="flex items-center gap-2 mb-2">
      <input type="text" placeholder="搜索参数名或说明..." bind:value={search}
             class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50" />
      <span class="text-[11px] text-muted-foreground whitespace-nowrap">{filtered.length} 项</span>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto rounded-lg border border-border">
      {#each filtered as p (p.name)}
        <div class="flex items-center gap-2 px-2 py-1.5 text-xs border-b border-border/50 hover:bg-muted/50 transition-colors
              {modified.has(p.name) ? 'bg-warning/5' : ''}">
          <div class="w-40 shrink-0 font-bold font-mono text-[11px]">{p.name}</div>
          <div class="flex-1 text-muted-foreground text-[11px] truncate min-w-0">{DESC[p.name] || ''}</div>
          {#if editName === p.name}
            <input type="text" bind:value={editValue} onkeydown={onKeydown}
                   class="w-20 h-6 px-1 text-right font-mono text-xs bg-input border-2 border-primary rounded text-foreground focus:outline-none" />
            <Button variant="default" size="xs" onclick={submitEdit}>写入</Button>
            <Button variant="ghost" size="xs" onclick={cancelEdit}>取消</Button>
          {:else}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="w-24 text-right font-mono cursor-pointer px-1 py-0.5 rounded hover:bg-input transition-colors"
                 onclick={() => startEdit(p)}>{fmtValue(p.value)}</div>
          {/if}
        </div>
      {/each}
    </div>
  {:else if !paramState.fetching}
    <div class="text-center py-8 text-muted-foreground text-sm">连接飞控后点击"读取参数"</div>
  {/if}
</div>
