<script lang="ts">
  import { paramState } from '../../lib/paramStore.svelte';
  import { app, addToast } from '../../lib/stores.svelte';
  import { sendCommand } from '../../lib/ws';
  import { t } from '../../lib/i18n.svelte';
  import { apiUrl } from '../../lib/backend';
  import type { Param } from '../../lib/types';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { Battery, ShieldAlert, Sliders, Navigation, Radio, ToggleLeft, Cpu, FileText, List } from '@lucide/svelte';
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

  const VTYPE_RAW_MAP: Record<number, string> = {
    2: 'copter', 3: 'copter', 4: 'copter', 13: 'copter', 14: 'copter',
    1: 'plane', 19: 'plane', 20: 'plane', 21: 'plane', 22: 'plane', 23: 'plane', 24: 'plane', 25: 'plane',
    10: 'rover',
    12: 'sub',
  };

  let lastVtypeRaw = 0;
  $effect(() => {
    const vr = app.drone.vtype_raw;
    if (vr > 0 && vr !== lastVtypeRaw && VTYPE_RAW_MAP[vr]) {
      lastVtypeRaw = vr;
      fetchMeta(VTYPE_RAW_MAP[vr]);
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

  function getBitmaskEntries(name: string, val: number): { bit: number; label: string; set: boolean }[] {
    const bm = meta[name]?.bitmask;
    if (!bm) return [];
    const iv = Math.round(val);
    return Object.entries(bm).map(([k, v]) => {
      const bit = parseInt(k);
      return { bit, label: v, set: (iv & (1 << bit)) !== 0 };
    }).sort((a, b) => a.bit - b.bit);
  }

  interface TreeGroup { name: string; params: typeof filtered; expanded: boolean }
  let treeGroups = $derived.by((): TreeGroup[] => {
    if (viewMode !== 'tree') return [];
    const groups = new Map<string, typeof filtered>();
    for (const p of filtered) {
      const prefix = p.name.split('_').slice(0, p.name.startsWith('BRD') || p.name.startsWith('LOG') || p.name.startsWith('GPS') ? 1 : Math.min(2, p.name.split('_').length - 1)).join('_');
      const key = prefix || 'OTHER';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(p);
    }
    return Array.from(groups.entries()).map(([name, params]) => ({ name, params, expanded: false }));
  });

  const CAT_DEFS: { key: string; i18nKey: string; icon: Component; match: (n: string) => boolean }[] = [
    { key: 'battery', i18nKey: 'cat.battery', icon: Battery, match: n => n.startsWith('BATT') || n === 'FS_BATT_ENABLE' || n === 'FS_BATT_MAH' || n === 'FS_BATT_VOLTAGE' },
    { key: 'failsafe', i18nKey: 'cat.failsafe', icon: ShieldAlert, match: n => n.startsWith('FS_') },
    { key: 'pid', i18nKey: 'cat.pid', icon: Sliders, match: n => n.startsWith('ATC_RAT_') || n.startsWith('ATC_ANG_') },
    { key: 'nav', i18nKey: 'cat.nav', icon: Navigation, match: n => n.startsWith('WPNAV') || n.startsWith('RTL') || n.startsWith('LOIT') },
    { key: 'rc', i18nKey: 'cat.rc', icon: Radio, match: n => /^RC\d/.test(n) },
    { key: 'modes', i18nKey: 'cat.modes', icon: ToggleLeft, match: n => n.startsWith('FLTMODE') || n.startsWith('MODE') },
    { key: 'sensor', i18nKey: 'cat.sensor', icon: Cpu, match: n => n.startsWith('INS_') || n.startsWith('COMPASS') || n.startsWith('BARO') },
    { key: 'log', i18nKey: 'cat.log', icon: FileText, match: n => n.startsWith('LOG_') },
    { key: 'all', i18nKey: 'cat.all', icon: List, match: () => true },
  ];

  let category = $state('all');
  let search = $state('');
  let showModifiedOnly = $state(false);
  let editName = $state<string | null>(null);
  let editValue = $state('');
  let modified = $state<Set<string>>(new Set());
  let expandedParam = $state<string | null>(null);
  let viewMode = $state<'flat' | 'tree'>('flat');

  function hasDefaultDiff(name: string, value: number): boolean {
    const m = meta[name];
    if (!m || !('default' in m)) return false;
    return Math.abs(value - (m as any).default) > 1e-6;
  }

  let modifiedCount = $derived(
    metaLoaded ? paramState.list.filter(p => hasDefaultDiff(p.name, p.value)).length : 0
  );

  let filtered = $derived.by(() => {
    const cat = CAT_DEFS.find(c => c.key === category)!;
    let list = paramState.list.filter(p => cat.match(p.name));
    if (showModifiedOnly && metaLoaded) {
      list = list.filter(p => hasDefaultDiff(p.name, p.value));
    }
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

  let visibleStart = $state(0);
  const PAGE_SIZE = 100;
  let visibleParams = $derived(filtered.slice(visibleStart, visibleStart + PAGE_SIZE));

  function onScroll(e: Event) {
    const el = e.target as HTMLDivElement;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 50 && visibleStart + PAGE_SIZE < filtered.length) {
      visibleStart = Math.min(visibleStart + 50, Math.max(0, filtered.length - PAGE_SIZE));
    }
    if (el.scrollTop < 50 && visibleStart > 0) {
      visibleStart = Math.max(0, visibleStart - 50);
    }
  }

  $effect(() => { filtered; visibleStart = 0; });

  function startEdit(p: Param) { editName = p.name; editValue = fmtValue(p.value); }
  function cancelEdit() { editName = null; }

  function submitEdit() {
    if (!editName) return;
    const val = parseFloat(editValue);
    if (isNaN(val)) { addToast(t('param.invalidNum'), 'error'); return; }
    const r = meta[editName]?.range;
    if (r && (val < r[0] || val > r[1])) {
      addToast(`${t('param.outOfRange')} ${r[0]} ~ ${r[1]}`, 'warn');
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
  function saveParams() { sendCommand('param_save'); addToast(t('param.saved'), 'success'); }

  function exportParams() {
    if (!paramState.list.length) return;
    const lines = paramState.list.map(p => `${p.name}\t${fmtValue(p.value)}`).join('\n');
    const blob = new Blob([lines], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'params_' + new Date().toISOString().slice(0, 10) + '.param';
    a.click();
    URL.revokeObjectURL(a.href);
    addToast(t('param.exported').replace('{n}', String(paramState.list.length)), 'success');
  }

  function exportDiff() {
    if (!metaLoaded || !paramState.list.length) return;
    const diffs = paramState.list.filter(p => hasDefaultDiff(p.name, p.value));
    if (!diffs.length) { addToast(t('param.noChange'), 'info'); return; }
    const lines = diffs.map(p => {
      const def = (meta[p.name] as any)?.default;
      return `${p.name}\t${fmtValue(p.value)}\t# default=${def !== undefined ? def : '?'}`;
    }).join('\n');
    const blob = new Blob([`# ${diffs.length} parameters differ from defaults\n${lines}\n`], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'params_diff_' + new Date().toISOString().slice(0, 10) + '.param';
    a.click();
    URL.revokeObjectURL(a.href);
    addToast(t('param.exported').replace('{n}', String(diffs.length)), 'success');
  }

  function toggleBitmaskBit(name: string, currentVal: number, bit: number) {
    const newVal = currentVal ^ (1 << bit);
    sendCommand('param_set', undefined, { name, value: newVal });
    modified.add(name);
    modified = new Set(modified);
    addToast(`${name} = ${newVal}`, 'info', 2000);
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
        addToast(changed > 0 ? t('param.imported').replace('{n}', String(changed)) : t('param.noChange'), changed > 0 ? 'success' : 'info');
      };
      reader.readAsText(file);
    };
    input.click();
  }
</script>

{#snippet paramRow(p: Param)}
  {@const desc = getDesc(p.name)}
  {@const units = getUnits(p.name)}
  {@const rangeStr = getRangeStr(p.name)}
  {@const valLabel = getValueLabel(p.name, p.value)}
  {@const isExpanded = expandedParam === p.name}
  {@const bmEntries = getBitmaskEntries(p.name, p.value)}
  <div>
    <div class="flex items-center gap-2 px-2 py-1.5 text-xs border-b border-border/50 hover:bg-muted/50 transition-colors
          {modified.has(p.name) ? 'bg-warning/5' : ''}">
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="w-40 shrink-0 cursor-pointer" onclick={() => expandedParam = isExpanded ? null : p.name}>
        <div class="font-bold font-mono text-[11px] leading-tight flex items-center gap-1">
          {#if metaLoaded}<span class="text-[9px] text-muted-foreground/40">{isExpanded ? '▼' : '▶'}</span>{/if}
          {p.name}
        </div>
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
          <Button variant="default" size="xs" onclick={submitEdit}>{t('param.write')}</Button>
          <Button variant="ghost" size="xs" onclick={cancelEdit}>{t('param.cancel')}</Button>
        </div>
      {:else}
        <div class="flex-1 flex items-center gap-1.5 min-w-0">
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div class="font-mono cursor-pointer px-1.5 py-0.5 rounded hover:bg-input transition-colors text-right min-w-[60px] {hasDefaultDiff(p.name, p.value) ? 'text-warning' : ''}"
               onclick={() => startEdit(p)}>{fmtValue(p.value)}</div>
          {#if units}<span class="text-[10px] text-muted-foreground">{units}</span>{/if}
          {#if valLabel}<span class="text-[10px] text-primary/70 truncate">{valLabel}</span>{/if}
          {#if hasDefaultDiff(p.name, p.value)}
            <button class="text-[9px] text-muted-foreground/60 hover:text-warning px-0.5 cursor-pointer bg-transparent border-none"
                    onclick={() => { sendCommand('param_set', undefined, { name: p.name, value: (meta[p.name] as any).default }); modified.add(p.name); modified = new Set(modified); }}
                    title={t('tip.resetDefault').replace('{v}', String((meta[p.name] as any).default))}>↩</button>
          {/if}
          {#if rangeStr}<span class="text-[10px] text-muted-foreground/50 ml-auto whitespace-nowrap">[{rangeStr}]</span>{/if}
        </div>
      {/if}
    </div>
    {#if isExpanded && metaLoaded}
      <div class="px-3 py-2 bg-muted/30 border-b border-border/50 text-[11px] space-y-1.5">
        {#if meta[p.name]?.desc}
          <p class="text-muted-foreground leading-relaxed">{meta[p.name]!.desc}</p>
        {/if}
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
          {#if meta[p.name]?.group}<span class="text-muted-foreground/60">Group: <span class="text-foreground">{meta[p.name]!.group}</span></span>{/if}
          {#if units}<span class="text-muted-foreground/60">Units: <span class="text-foreground">{units}</span></span>{/if}
          {#if rangeStr}<span class="text-muted-foreground/60">Range: <span class="text-foreground">{rangeStr}</span></span>{/if}
          {#if meta[p.name]?.step}<span class="text-muted-foreground/60">Step: <span class="text-foreground">{meta[p.name]!.step}</span></span>{/if}
          {#if 'default' in (meta[p.name] || {})}<span class="text-muted-foreground/60">Default: <span class="text-foreground">{(meta[p.name] as any).default}</span></span>{/if}
        </div>
        {#if meta[p.name]?.values}
          <div class="flex flex-wrap gap-1">
            {#each Object.entries(meta[p.name]!.values!) as [code, label]}
              <span class="px-1.5 py-0.5 rounded text-[10px] border
                {String(Math.round(p.value)) === code ? 'bg-primary/20 text-primary border-primary/50' : 'bg-muted text-muted-foreground border-border/50'}">
                {code}: {label}
              </span>
            {/each}
          </div>
        {/if}
        {#if bmEntries.length > 0}
          <div class="space-y-0.5">
            <span class="text-[10px] text-muted-foreground/60 font-semibold">Bitmask:</span>
            <div class="flex flex-wrap gap-1">
              {#each bmEntries as bm}
                <button class="px-1.5 py-0.5 rounded text-[10px] border cursor-pointer transition-colors
                  {bm.set ? 'bg-green-500/20 text-green-400 border-green-500/50' : 'bg-muted text-muted-foreground border-border/50 hover:border-primary/50'}"
                        onclick={() => toggleBitmaskBit(p.name, p.value, bm.bit)}>
                  {bm.bit}: {bm.label} {bm.set ? '✓' : ''}
                </button>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

<div class="bg-card border border-border rounded-xl p-4 flex flex-col h-full">
  <div class="flex items-center justify-between flex-wrap gap-2 mb-3">
    <div class="flex items-center gap-2">
      <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('param.title')}</h2>
      {#if metaLoaded}
        <span class="text-[10px] text-muted-foreground/60">{t('param.metaLoaded')}</span>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      <Button variant="default" size="sm" onclick={requestAll} disabled={paramState.fetching}>
        {paramState.fetching ? `${t('param.reading')} ${progress}%` : t('param.readAll')}
      </Button>
      {#if paramState.list.length > 0}
        <Button variant="secondary" size="sm" onclick={saveParams}>{t('param.writeFlash')}</Button>
        <Button variant="outline" size="sm" onclick={exportParams}>{t('param.export')}</Button>
        {#if metaLoaded && modifiedCount > 0}
          <Button variant="outline" size="sm" onclick={exportDiff}>Diff</Button>
        {/if}
        <Button variant="outline" size="sm" onclick={importParams}>{t('param.import')}</Button>
        <Badge variant="outline" class="text-[10px] font-mono">{paramState.list.length} {t('param.params')}</Badge>
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
      {#each CAT_DEFS as cat}
        <button class="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-md border transition-all cursor-pointer
          {category === cat.key
            ? 'bg-primary text-primary-foreground border-primary'
            : 'bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted'}"
                onclick={() => category = cat.key}>
          <cat.icon size={11} />{t(cat.i18nKey)}
          {#if cat.key !== 'all' && paramState.list.length > 0}
            {@const cnt = paramState.list.filter(p => cat.match(p.name)).length}
            {#if cnt > 0}<span class="text-[9px] opacity-60">{cnt}</span>{/if}
          {/if}
        </button>
      {/each}
    </div>

    <div class="flex items-center gap-2 mb-2">
      <input type="text" placeholder={t('param.search')} bind:value={search}
             class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50" />
      <button class="text-[11px] px-2 py-0.5 rounded border transition-all cursor-pointer
        {viewMode === 'tree' ? 'bg-primary/20 text-primary border-primary/50' : 'text-muted-foreground border-border hover:text-foreground'}"
              onclick={() => viewMode = viewMode === 'flat' ? 'tree' : 'flat'}
              title={viewMode === 'flat' ? 'Tree view' : 'Flat view'}>
        {viewMode === 'flat' ? '🌲' : '☰'}
      </button>
      {#if metaLoaded && modifiedCount > 0}
        <button class="text-[11px] px-2 py-0.5 rounded border transition-all cursor-pointer
          {showModifiedOnly ? 'bg-warning/20 text-warning border-warning/50' : 'text-muted-foreground border-border hover:text-foreground'}"
                onclick={() => showModifiedOnly = !showModifiedOnly}>
          Diff ({modifiedCount})
        </button>
      {/if}
      <span class="text-[11px] text-muted-foreground whitespace-nowrap">{filtered.length}</span>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto rounded-lg border border-border" onscroll={onScroll}>
      {#if viewMode === 'tree' && treeGroups.length > 0}
        {#each treeGroups as group}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div class="flex items-center gap-2 px-2 py-1.5 text-xs border-b border-border bg-muted/30 cursor-pointer hover:bg-muted/60 transition-colors"
               onclick={() => group.expanded = !group.expanded}>
            <span class="text-[10px] text-muted-foreground w-4">{group.expanded ? '▼' : '▶'}</span>
            <span class="font-bold font-mono text-primary text-[11px]">{group.name}</span>
            <span class="text-[10px] text-muted-foreground">({group.params.length})</span>
          </div>
          {#if group.expanded}
            {#each group.params as p (p.name)}
              {@render paramRow(p)}
            {/each}
          {/if}
        {/each}
      {:else}
        {#each visibleParams as p (p.name)}
          {@render paramRow(p)}
        {/each}
      {/if}
    </div>
  {:else if !paramState.fetching}
    <div class="text-center py-8 text-muted-foreground text-sm">{t('param.connectHint')}</div>
  {/if}
</div>
