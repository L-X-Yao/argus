<script lang="ts">
  import { onMount } from 'svelte';
  import { paramState } from '../lib/paramStore.svelte';
  import { app, addToast } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { apiUrl } from '../lib/backend';
  import type { Param } from '../lib/types';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { Battery, ShieldAlert, Sliders, Navigation, Radio, ToggleLeft, Cpu, FileText, List, Info } from '@lucide/svelte';
  import type { Component } from 'svelte';

  interface ParamMeta {
    desc?: string;
    human?: string;
    group?: string;
    range?: [number, number];
    units?: string;
    step?: number;
    values?: Record<string, string>;
    bitmask?: Record<string, string>;
  }

  let meta = $state<Record<string, ParamMeta>>({});
  let metaLoaded = $state(false);

  const VTYPE_MAP: Record<string, string> = {
    '多旋翼': 'copter', '固定翼': 'plane', '地面车': 'rover', '水下机器人': 'sub',
  };

  let lastVtype = '';
  $effect(() => {
    const vt = app.drone.vtype;
    if (vt && vt !== lastVtype && VTYPE_MAP[vt]) {
      lastVtype = vt;
      fetchMeta(VTYPE_MAP[vt]);
    }
  });

  async function fetchMeta(vehicle: string) {
    try {
      const r = await fetch(apiUrl(`/api/param_meta?vehicle=${vehicle}`));
      if (r.ok) {
        meta = await r.json();
        metaLoaded = true;
      }
    } catch {}
  }

  function getDesc(name: string): string {
    const m = meta[name];
    if (m) return m.human || m.desc || '';
    return '';
  }

  function getUnits(name: string): string {
    return meta[name]?.units || '';
  }

  function getRangeStr(name: string): string {
    const r = meta[name]?.range;
    if (!r) return '';
    return `${r[0]} ~ ${r[1]}`;
  }

  function getValueLabel(name: string, val: number): string {
    const v = meta[name]?.values;
    if (!v) return '';
    const key = String(Math.round(val));
    return v[key] || '';
  }

  const CATS: { key: string; label: string; icon: Component; match: (n: string) => boolean }[] = [
    { key: 'battery', label: '电池', icon: Battery, match: n => n.startsWith('BATT') || n === 'FS_BATT_ENABLE' || n === 'FS_BATT_MAH' || n === 'FS_BATT_VOLTAGE' },
    { key: 'failsafe', label: '保护', icon: ShieldAlert, match: n => n.startsWith('FS_') },
    { key: 'pid', label: 'PID', icon: Sliders, match: n => n.startsWith('ATC_RAT_') || n.startsWith('ATC_ANG_') },
    { key: 'nav', label: '导航', icon: Navigation, match: n => n.startsWith('WPNAV') || n.startsWith('RTL') || n.startsWith('LOIT') },
    { key: 'rc', label: '遥控', icon: Radio, match: n => /^RC\d/.test(n) },
    { key: 'modes', label: '模式', icon: ToggleLeft, match: n => n.startsWith('FLTMODE') || n.startsWith('MODE') },
    { key: 'sensor', label: '传感器', icon: Cpu, match: n => n.startsWith('INS_') || n.startsWith('COMPASS') || n.startsWith('BARO') },
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
      const q = search.toLowerCase();
      list = list.filter(p => {
        if (p.name.toLowerCase().includes(q)) return true;
        const d = getDesc(p.name);
        if (d && d.toLowerCase().includes(q)) return true;
        const m = meta[p.name];
        if (m?.human && m.human.toLowerCase().includes(q)) return true;
        return false;
      });
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
    const r = meta[editName]?.range;
    if (r && (val < r[0] || val > r[1])) {
      addToast(`超出范围 ${r[0]} ~ ${r[1]}`, 'warn');
    }
    const name = editName;
    sendCommand('param_set', undefined, { name, value: val });
    modified.add(name);
    modified = new Set(modified);
    editName = null;
    addToast(`${name} = ${val}`, 'info', 2000);
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
    <div class="flex items-center gap-2">
      <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">参数管理</h2>
      {#if metaLoaded}
        <span class="text-[10px] text-muted-foreground/60" title="已加载参数说明数据库">说明已加载</span>
      {/if}
    </div>
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
        {@const desc = getDesc(p.name)}
        {@const units = getUnits(p.name)}
        {@const rangeStr = getRangeStr(p.name)}
        {@const valLabel = getValueLabel(p.name, p.value)}
        <div class="flex items-center gap-2 px-2 py-1.5 text-xs border-b border-border/50 hover:bg-muted/50 transition-colors
              {modified.has(p.name) ? 'bg-warning/5' : ''}">
          <div class="w-40 shrink-0">
            <div class="font-bold font-mono text-[11px] leading-tight">{p.name}</div>
            {#if desc}
              <div class="text-[10px] text-muted-foreground leading-tight truncate" title={desc}>{desc}</div>
            {/if}
          </div>
          {#if editName === p.name}
            <div class="flex-1 flex items-center gap-1 min-w-0">
              <input type="text" bind:value={editValue} onkeydown={onKeydown}
                     class="w-24 h-6 px-1 text-right font-mono text-xs bg-input border-2 border-primary rounded text-foreground focus:outline-none" />
              {#if units}<span class="text-[10px] text-muted-foreground">{units}</span>{/if}
              {#if rangeStr}<span class="text-[10px] text-muted-foreground/60">[{rangeStr}]</span>{/if}
              <Button variant="default" size="xs" onclick={submitEdit}>写入</Button>
              <Button variant="ghost" size="xs" onclick={cancelEdit}>取消</Button>
            </div>
          {:else}
            <div class="flex-1 flex items-center gap-1.5 min-w-0">
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <!-- svelte-ignore a11y_no_static_element_interactions -->
              <div class="font-mono cursor-pointer px-1.5 py-0.5 rounded hover:bg-input transition-colors text-right min-w-[60px]"
                   onclick={() => startEdit(p)}>{fmtValue(p.value)}</div>
              {#if units}<span class="text-[10px] text-muted-foreground">{units}</span>{/if}
              {#if valLabel}<span class="text-[10px] text-primary/70 truncate">{valLabel}</span>{/if}
              {#if rangeStr}<span class="text-[10px] text-muted-foreground/50 ml-auto whitespace-nowrap">[{rangeStr}]</span>{/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {:else if !paramState.fetching}
    <div class="text-center py-8 text-muted-foreground text-sm">连接飞控后点击"读取参数"</div>
  {/if}
</div>
