<script lang="ts">
  import { paramState } from '../../lib/paramStore.svelte';
  import { app, addToast } from '../../lib/stores.svelte';
  import { dispatch } from '../../lib/transport';
  import { getLocale, t } from '../../lib/i18n.svelte';
  import { paramLine, parseParamNumber } from '../../lib/paramText';
  import { apiUrl } from '../../lib/backend';
  import type { Param } from '../../lib/types';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { Battery, ShieldAlert, Sliders, Navigation, Radio, ToggleLeft, Cpu, FileText, List, GitCompareArrows } from '@lucide/svelte';
  import type { Component } from 'svelte';

  type TranslationStatus = 'reviewed' | 'machine' | 'generated' | 'partial';

  interface ParamTranslation {
    desc?: string;
    human?: string;
    values?: Record<string, string>;
    bitmask?: Record<string, string>;
    status?: TranslationStatus;
  }

  interface ParamMeta {
    desc?: string;
    human?: string;
    group?: string;
    range?: [number, number];
    units?: string;
    step?: number;
    values?: Record<string, string>;
    bitmask?: Record<string, string>;
    default?: number;
    tr?: ParamTranslation;
  }

  interface ParamMetaInfo {
    vehicle: string;
    series: string;
    locale: string;
    selection: 'coverage' | 'fw' | 'manual';
    translation: 'reviewed' | 'machine' | 'generated' | 'partial' | 'unavailable';
    translated: number;
    total: number;
    available_series: string[];
    data_version?: string;
    schema?: number;
  }

  interface MetaResult {
    raw: Record<string, ParamMeta>;
    info: ParamMetaInfo | null;
  }

  let _metaRaw: Record<string, ParamMeta> = {};
  let _metaInfo = $state<ParamMetaInfo | null>(null);
  let _metaVersion = $state(0);
  function getMeta(): Record<string, ParamMeta> { void _metaVersion; return _metaRaw; }
  let metaLoaded = $state(false);
  let metaSeries = $state('');
  let metaLoading = $state(false);
  let showEnglishFor = $state<string | null>(null);
  let lastVehicle = '';
  let lastMetaKey = '';
  let lastRequestedSeries = '';
  let lastProbeKey = '';
  let probingKey = '';
  let metaAbort: AbortController | null = null;
  const META_CACHE_MAX = 6;
  const metaCache = new Map<string, MetaResult>();

  function cacheMeta(key: string, result: MetaResult) {
    metaCache.set(key, result);
    while (metaCache.size > META_CACHE_MAX) {
      const oldest = metaCache.keys().next().value;
      if (oldest === undefined || oldest === key) break;
      metaCache.delete(oldest);
    }
  }

  const VTYPE_RAW_MAP: Record<number, string> = {
    2: 'copter', 3: 'copter', 4: 'copter', 13: 'copter', 14: 'copter',
    1: 'plane', 19: 'plane', 20: 'plane', 21: 'plane', 22: 'plane', 23: 'plane', 24: 'plane', 25: 'plane',
    10: 'rover',
    11: 'rover',
    12: 'sub',
  };

  $effect(() => {
    const vr = app.drone.vtype_raw;
    const vehicle = VTYPE_RAW_MAP[vr];
    if (!vehicle) return;
    if (vehicle !== lastVehicle) {
      lastVehicle = vehicle;
      metaSeries = '';
      showEnglishFor = null;
    }
    const locale = getLocale();
    const fw = app.drone.fw_version || '';
    const series = metaSeries;
    const key = `${vehicle}|${locale}|${fw}|${series}`;
    if (key === lastMetaKey) return;
    if (series !== lastRequestedSeries) {
      lastRequestedSeries = series;
      // Manual -> Auto must be allowed to probe again; the cached Auto answer may be the
      // low-coverage series the earlier probe was meant to replace.
      lastProbeKey = '';
      probingKey = '';
    }
    lastMetaKey = key;
    showEnglishFor = null;
    void fetchMeta(vehicle, locale, fw, series, key);
  });

  $effect(() => {
    const fetching = paramState.fetching;
    const count = paramState.list.length;
    if (fetching || !count || !metaLoaded || !_metaInfo || !lastMetaKey) return;
    const [vehicle, locale, fw] = lastMetaKey.split('|');
    if (!vehicle || !locale) return;
    void maybeImproveSeries(vehicle, locale, fw, { raw: _metaRaw, info: _metaInfo }, lastMetaKey);
  });

  async function requestMeta(
    vehicle: string,
    locale: string,
    fw: string,
    series: string,
    signal?: AbortSignal,
  ): Promise<MetaResult> {
    const query = new URLSearchParams({ vehicle, locale });
    if (fw) query.set('fw', fw);
    if (series) query.set('series', series);
    const r = await fetch(apiUrl(`/api/param_meta?${query.toString()}`), { signal });
    if (!r.ok) throw new Error(`param_meta ${r.status}`);
    const data = (await r.json()) as Record<string, unknown>;
    const info = (data._meta as ParamMetaInfo | undefined) ?? null;
    const raw: Record<string, ParamMeta> = {};
    for (const [name, value] of Object.entries(data)) {
      if (name !== '_meta') raw[name] = value as ParamMeta;
    }
    return { raw, info };
  }

  function applyMeta(result: MetaResult) {
    _metaRaw = result.raw;
    _metaInfo = result.info;
    _metaVersion++;
    metaLoaded = true;
  }

  async function fetchMeta(vehicle: string, locale: string, fw: string, series: string, key: string) {
    // A cached answer must cancel a request for the previous series; otherwise that request
    // can land later and replace the cached metadata with another series' data.
    metaAbort?.abort();
    const cached = metaCache.get(key);
    if (cached) {
      metaAbort = null;
      metaLoading = false;
      applyMeta(cached);
      return;
    }
    const ctrl = new AbortController();
    metaAbort = ctrl;
    metaLoading = true;
    try {
      const result = await requestMeta(vehicle, locale, fw, series, ctrl.signal);
      if (ctrl.signal.aborted) return;
      cacheMeta(key, result);
      applyMeta(result);
      void maybeImproveSeries(vehicle, locale, fw, result, key);
    } catch {
      // Keep the previous language's metadata rather than blanking the panel.
    } finally {
      if (metaAbort === ctrl) {
        metaAbort = null;
        metaLoading = false;
      }
    }
  }

  function metaCoverage(result: MetaResult): number {
    const list = paramState.list;
    if (!list.length) return 1;
    let hit = 0;
    for (const p of list) if (result.raw[p.name]) hit++;
    return hit / list.length;
  }

  async function maybeImproveSeries(
    vehicle: string,
    locale: string,
    fw: string,
    current: MetaResult,
    key: string,
  ) {
    // WebSerial has no live parameter names on the backend. The panel has them, so it can
    // choose the metadata series itself when the firmware's reported version is misleading.
    if (app.activeTransport !== 'serial' || metaSeries || !paramState.list.length) return;
    if (!current.info?.available_series?.length) return;
    const base = metaCoverage(current);
    if (base >= 0.9) return;
    const probeKey = `${key}|${paramState.list.length}|${current.info.series}`;
    if (probeKey === lastProbeKey || probingKey === probeKey) return;
    probingKey = probeKey;
    let best = current;
    let bestCoverage = base;
    let failed = false;
    const candidates = current.info.available_series.filter((s) => s !== current.info?.series).slice(0, 2);
    try {
      for (const candidate of candidates) {
        try {
          const result = await requestMeta(vehicle, locale, fw, candidate);
          const coverage = metaCoverage(result);
          if (coverage > bestCoverage + 0.01) {
            best = result;
            bestCoverage = coverage;
          }
        } catch {
          // A transient failure must not latch this series forever: the next read or
          // locale/vehicle change gets another attempt.
          failed = true;
          break;
        }
      }
      if (bestCoverage > base + 0.01 && getLocale() === locale && lastMetaKey === key) {
        applyMeta(best);
        cacheMeta(`${vehicle}|${locale}|${fw}|${best.info?.series ?? ''}`, best);
      }
    } finally {
      probingKey = '';
      if (!failed) lastProbeKey = probeKey;
    }
  }

  function currentTranslation(name: string): ParamTranslation | undefined {
    const m = getMeta()[name];
    if (!m?.tr) return undefined;
    // Do not show one language's translation under another language's UI.
    if (_metaInfo && _metaInfo.locale !== getLocale()) return undefined;
    return m.tr;
  }

  function getLabel(name: string): string {
    const m = getMeta()[name];
    const tr = currentTranslation(name);
    return tr?.human || m?.human || m?.desc || '';
  }

  function getDescription(name: string): string {
    const m = getMeta()[name];
    const tr = currentTranslation(name);
    return tr?.desc || m?.desc || tr?.human || m?.human || '';
  }

  function descriptionIsEnglish(name: string): boolean {
    const m = getMeta()[name];
    const tr = currentTranslation(name);
    if (tr?.desc) return false;
    if (m?.desc) return true;
    if (tr?.human) return false;
    return !!m?.human;
  }

  function valueLabelIsTranslated(name: string, val: number): boolean {
    const tr = currentTranslation(name);
    return !!tr?.values?.[String(Math.round(val))];
  }

  function statusLabel(status: TranslationStatus): string {
    if (status === 'reviewed') return t('param.reviewed');
    if (status === 'generated') return t('param.generated');
    if (status === 'partial') return t('param.partial');
    return t('param.machine');
  }

  function getUnits(name: string): string {
    return getMeta()[name]?.units || '';
  }

  function getRangeStr(name: string): string {
    const r = getMeta()[name]?.range;
    if (!r) return '';
    return `${r[0]} ~ ${r[1]}`;
  }

  function getValueLabel(name: string, val: number): string {
    const m = getMeta()[name];
    const tr = currentTranslation(name);
    const key = String(Math.round(val));
    return tr?.values?.[key] || m?.values?.[key] || '';
  }

  function getBitmaskEntries(
    name: string,
    val: number,
  ): { bit: number; label: string; set: boolean; translated: boolean }[] {
    const bm = getMeta()[name]?.bitmask;
    if (!bm) return [];
    const tr = currentTranslation(name);
    const iv = Math.round(val);
    return Object.entries(bm)
      .map(([k, v]) => {
        const bit = parseInt(k);
        return {
          bit,
          label: tr?.bitmask?.[k] || v,
          set: (iv & (1 << bit)) !== 0,
          translated: !!tr?.bitmask?.[k],
        };
      })
      .sort((a, b) => a.bit - b.bit);
  }

  interface TreeGroup { name: string; params: typeof filtered; expanded: boolean }
  let treeGroups = $derived.by((): TreeGroup[] => {
    if (viewMode !== 'tree') return [];
    const groups = new Map<string, typeof filtered>();
    for (const p of filtered) {
      const first = p.name.split('_')[0];
      const use1 = /^(BRD|LOG|GPS|BATT|INS|ATC|COMPASS|WPNAV|FENCE|RALLY|SERVO\d*)$/.test(first);
      const prefix = p.name.split('_').slice(0, use1 ? 1 : Math.min(2, p.name.split('_').length - 1)).join('_');
      const key = prefix || 'OTHER';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(p);
    }
    return Array.from(groups.entries()).map(([name, params]) => ({ name, params, expanded: false }));
  });

  const CAT_DEFS: { key: string; i18nKey: string; icon: Component; match: (n: string) => boolean }[] = [
    { key: 'battery', i18nKey: 'cat.battery', icon: Battery, match: n => n.startsWith('BATT') },
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
  let compareMap = $state<Map<string, number>>(new Map());
  let compareActive = $derived(compareMap.size > 0);

  function hasDefaultDiff(name: string, value: number): boolean {
    const m = getMeta()[name];
    if (!m || m.default === undefined) return false;
    return Math.abs(value - m.default!) > 1e-6;
  }

  let categoryCounts = $derived.by(() => {
    if (paramState.fetching) return {};
    const counts: Record<string, number> = {};
    for (const p of paramState.list) {
      for (const cat of CAT_DEFS) {
        if (cat.key !== 'all' && cat.match(p.name)) {
          counts[cat.key] = (counts[cat.key] || 0) + 1;
        }
      }
    }
    return counts;
  });

  let modifiedCount = $derived.by(() => {
    if (!metaLoaded || paramState.fetching) return 0;
    let n = 0;
    for (const p of paramState.list) {
      if (hasDefaultDiff(p.name, p.value)) n++;
    }
    return n;
  });

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
        const tr = currentTranslation(p.name);
        const m = getMeta()[p.name];
        const parts = [
          getLabel(p.name),
          getDescription(p.name),
          m?.human ?? '',
          m?.desc ?? '',
          ...Object.values(tr?.values ?? {}),
          ...Object.values(tr?.bitmask ?? {}),
          ...Object.values(m?.values ?? {}),
          ...Object.values(m?.bitmask ?? {}),
        ];
        return parts.some((part) => part.toLowerCase().includes(q));
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

  function startEdit(p: Param) { editName = p.name; editValue = String(p.value); }
  function cancelEdit() { editName = null; }

  function submitEdit() {
    if (!editName) return;
    // As the operator's locale writes it: "1,5" is 1.5, not 1 (which parseFloat read it as).
    const val = parseParamNumber(editValue);
    if (isNaN(val)) { addToast(t('param.invalidNum'), 'error'); return; }
    const r = getMeta()[editName]?.range;
    if (r && (val < r[0] || val > r[1])) {
      addToast(`${t('param.outOfRange')} ${r[0]} ~ ${r[1]}`, 'warn');
    }
    const name = editName;
    dispatch('param_set', undefined, { name, value: val });
    modified.add(name);
    modified = new Set(modified);
    editName = null;
    addToast(`${name} = ${val}`, 'info', 2000);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') submitEdit();
    else if (e.key === 'Escape') cancelEdit();
  }

  function fmtValue(v: number, ptype?: number): string {
    if (ptype !== undefined && ptype !== 9) return String(Math.round(v));
    if (Number.isInteger(v) || Math.abs(v) >= 100) return v.toFixed(0);
    if (Math.abs(v) >= 1) return v.toFixed(2);
    return v.toFixed(4);
  }

  function requestAll() { dispatch('param_request_all'); }
  function saveParams() { dispatch('param_save'); addToast(t('param.saved'), 'success'); }

  function exportParams() {
    if (!paramState.list.length) return;
    const lines = paramState.list.map(p => `${p.name}\t${p.value}`).join('\n');
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
      const def = getMeta()[p.name]?.default;
      return `${p.name}\t${p.value}\t# default=${def !== undefined ? def : '?'}`;
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
    dispatch('param_set', undefined, { name, value: newVal });
    modified.add(name);
    modified = new Set(modified);
    addToast(`${name} = ${newVal}`, 'info', 2000);
  }

  function exportCsv() {
    if (!paramState.list.length) return;
    const header = 'Name,Value,Default,Units,Range,Description,DescriptionEN';
    const rows = paramState.list.map(p => {
      const m = getMeta()[p.name] || {};
      const def = m.default !== undefined ? String(m.default) : '';
      const units = (m.units || '').replace(/,/g, ';');
      const range = m.range ? `${m.range[0]}~${m.range[1]}` : '';
      const desc = getDescription(p.name).replace(/"/g, '""').replace(/\n/g, ' ');
      const descEn = (m.desc || m.human || '').replace(/"/g, '""').replace(/\n/g, ' ');
      return `${p.name},${p.value},${def},${units},${range},"${desc}","${descEn}"`;
    });
    const csv = [header, ...rows].join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'params_' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    URL.revokeObjectURL(a.href);
    addToast(t('param.exported').replace('{n}', String(paramState.list.length)), 'success');
  }

  function compareWithFile() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.param,.txt,.csv';
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: ProgressEvent<FileReader>) => {
        const text = ev.target!.result as string;
        const map = new Map<string, number>();
        for (const line of text.split('\n')) {
          const parsed = paramLine(line);
          if (parsed) map.set(parsed[0], parsed[1]);
        }
        compareMap = map;
        const diffCount = paramState.list.filter(p => {
          const ref = map.get(p.name);
          return ref !== undefined && Math.abs(ref - p.value) > 1e-6;
        }).length;
        addToast(t('param.compareLoaded').replace('{n}', String(map.size)).replace('{d}', String(diffCount)), 'success');
      };
      reader.readAsText(file);
    };
    input.click();
  }

  function clearCompare() { compareMap = new Map(); }

  function getCompareValue(name: string): number | undefined {
    return compareMap.get(name);
  }

  function importParams() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.param,.txt';
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: ProgressEvent<FileReader>) => {
        const text = ev.target!.result as string;
        const existing = new Map(paramState.list.map(p => [p.name, p.value]));
        let changed = 0;
        for (const line of text.split('\n')) {
          // As a spreadsheet in a comma-decimal locale writes it, and as the edit box reads it.
          const parsed = paramLine(line);
          if (!parsed) continue;
          const [name, val] = parsed;
          const cur = existing.get(name);
          if (cur !== undefined && Math.abs(cur - val) > 1e-6) {
            dispatch('param_set', undefined, { name, value: val });
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
  {@const label = getLabel(p.name)}
  {@const description = getDescription(p.name)}
  {@const tr = currentTranslation(p.name)}
  {@const status = tr?.status}
  {@const units = getUnits(p.name)}
  {@const rangeStr = getRangeStr(p.name)}
  {@const valLabel = getValueLabel(p.name, p.value)}
  {@const valTranslated = valueLabelIsTranslated(p.name, p.value)}
  {@const descriptionEnglish = descriptionIsEnglish(p.name)}
  {@const isExpanded = expandedParam === p.name}
  {@const bmEntries = getBitmaskEntries(p.name, p.value)}
  <div>
    <div class="flex items-center gap-2 px-2 py-1.5 text-xs border-b border-border/50 hover:bg-muted/50 transition-colors
          {modified.has(p.name) ? 'bg-warning/5' : ''}">
            <div role="presentation" class="w-40 shrink-0 cursor-pointer" onclick={() => {
              expandedParam = isExpanded ? null : p.name;
              showEnglishFor = null;
            }}>
        <div class="font-bold font-mono text-[11px] leading-tight flex items-center gap-1">
          {#if metaLoaded}<span class="text-[9px] text-muted-foreground/40">{isExpanded ? '▼' : '▶'}</span>{/if}
          {p.name}
        </div>
        {#if label}
          <div class="text-[10px] text-muted-foreground leading-tight truncate" title={description || label}>
            {label}
          </div>
          {#if getLocale() !== 'en' && !tr?.human}
            <span class="text-[8px] font-bold text-muted-foreground/50">EN</span>
          {/if}
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
                    <div role="presentation" class="font-mono cursor-pointer px-1.5 py-0.5 rounded hover:bg-input transition-colors text-right min-w-[60px] {hasDefaultDiff(p.name, p.value) ? 'text-warning' : ''}"
               onclick={() => startEdit(p)}>{fmtValue(p.value, p.type)}</div>
          {#if units}<span class="text-[10px] text-muted-foreground">{units}</span>{/if}
          {#if valLabel}
            <span class="text-[10px] text-primary truncate">
              {valLabel}{#if getLocale() !== 'en' && !valTranslated}<span
                  class="ml-0.5 text-[8px] font-bold text-muted-foreground/50 align-top">EN</span
                >{/if}
            </span>
          {/if}
          {#if hasDefaultDiff(p.name, p.value)}
            <button class="text-[9px] text-muted-foreground/60 hover:text-warning px-0.5 cursor-pointer bg-transparent border-none"
                    onclick={() => { dispatch('param_set', undefined, { name: p.name, value: getMeta()[p.name]!.default! }); modified.add(p.name); modified = new Set(modified); }}
                    title={t('tip.resetDefault').replace('{v}', String(getMeta()[p.name]!.default))}>↩</button>
          {/if}
          {#if compareActive}
            {@const ref = getCompareValue(p.name)}
            {#if ref !== undefined && Math.abs(ref - p.value) > 1e-6}
              <span class="text-[10px] text-destructive font-mono" title={t('param.refValue')}>ref:{fmtValue(ref)}</span>
            {:else if ref !== undefined}
              <span class="text-[10px] text-green-500 font-mono">=</span>
            {/if}
          {/if}
          {#if rangeStr}<span class="text-[10px] text-muted-foreground/50 ml-auto whitespace-nowrap">[{rangeStr}]</span>{/if}
        </div>
      {/if}
    </div>
    {#if isExpanded && metaLoaded}
      <div class="px-3 py-2 bg-muted/30 border-b border-border/50 text-[11px] space-y-1.5">
        {#if description}
          <p class="text-muted-foreground leading-relaxed">
            {#if showEnglishFor === p.name}
              <span class="text-[9px] font-bold text-muted-foreground/60 mr-1 align-top">EN</span>
              {getMeta()[p.name]?.desc}
            {:else}
              <!-- The source is ArduPilot's apm.pdef.xml. When only the English text is available,
                   say so rather than let it look like a missing translation. -->
              {#if descriptionEnglish && getLocale() !== 'en'}<span
                  class="text-[9px] font-bold text-muted-foreground/60 mr-1 align-top">EN</span
                >{/if}{description}
            {/if}
            {#if status}<span class="ml-1 text-[9px] font-semibold text-muted-foreground/70"
                >{statusLabel(status)}</span
              >{/if}
          </p>
          {#if tr?.desc && getMeta()[p.name]?.desc && tr.desc !== getMeta()[p.name]!.desc}
            <button
              type="button"
              class="text-[10px] text-primary hover:underline cursor-pointer bg-transparent border-none p-0"
              aria-pressed={showEnglishFor === p.name}
              onclick={() => showEnglishFor = showEnglishFor === p.name ? null : p.name}
            >
              {showEnglishFor === p.name ? t('param.hideEnglish') : t('param.showEnglish')}
            </button>
          {/if}
        {/if}
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
          {#if getMeta()[p.name]?.group}<span class="text-muted-foreground/60">{t('meta.group')}: <span class="text-foreground">{getMeta()[p.name]!.group}</span></span>{/if}
          {#if units}<span class="text-muted-foreground/60">{t('meta.units')}: <span class="text-foreground">{units}</span></span>{/if}
          {#if rangeStr}<span class="text-muted-foreground/60">{t('meta.range')}: <span class="text-foreground">{rangeStr}</span></span>{/if}
          {#if getMeta()[p.name]?.step}<span class="text-muted-foreground/60">{t('meta.step')}: <span class="text-foreground">{getMeta()[p.name]!.step}</span></span>{/if}
          {#if getMeta()[p.name]?.default !== undefined}<span class="text-muted-foreground/60">{t('meta.default')}: <span class="text-foreground">{getMeta()[p.name]!.default}</span></span>{/if}
        </div>
        {#if getMeta()[p.name]?.values}
          <div class="flex flex-wrap gap-1">
            {#each Object.entries(getMeta()[p.name]!.values!) as [code, label]}
              <span class="px-1.5 py-0.5 rounded text-[10px] border
                {String(Math.round(p.value)) === code ? 'bg-primary/20 text-primary border-primary/50' : 'bg-muted text-muted-foreground border-border/50'}">
                {code}: {tr?.values?.[code] || label}{#if getLocale() !== 'en' && !tr?.values?.[code]}<span
                    class="ml-0.5 text-[8px] font-bold text-muted-foreground/50 align-top">EN</span
                  >{/if}
              </span>
            {/each}
          </div>
        {/if}
        {#if bmEntries.length > 0}
          <div class="space-y-0.5">
            <span class="text-[10px] text-muted-foreground/60 font-semibold">{t('meta.bitmask')}:</span>
            <div class="flex flex-wrap gap-1">
              {#each bmEntries as bm}
                <button class="px-1.5 py-0.5 rounded text-[10px] border cursor-pointer transition-colors
                  {bm.set ? 'bg-green-500/20 text-green-400 border-green-500/50' : 'bg-muted text-muted-foreground border-border/50 hover:border-primary/50'}"
                        onclick={() => toggleBitmaskBit(p.name, p.value, bm.bit)}>
                  {bm.bit}: {bm.label}{#if getLocale() !== 'en' && !bm.translated}<span
                      class="ml-0.5 text-[8px] font-bold text-muted-foreground/50 align-top">EN</span
                    >{/if}
                  {bm.set ? '✓' : ''}
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
        <span class="text-[10px] text-muted-foreground">{t('param.metaLoaded')}</span>
      {/if}
      {#if metaLoaded && _metaInfo && _metaInfo.total > 0 && getLocale() !== 'en'}
        <span class="text-[10px] text-muted-foreground/70">
          {t('param.coverage').replace('{n}', String(Math.round((_metaInfo.translated / _metaInfo.total) * 100)))}
        </span>
      {/if}
      {#if metaLoading}
        <span class="text-[10px] text-muted-foreground/60">…</span>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      <Button variant="default" size="sm" onclick={requestAll} disabled={paramState.fetching}>
        {paramState.fetching ? `${t('param.reading')} ${progress}%` : t('param.readAll')}
      </Button>
      {#if paramState.list.length > 0}
        <Button variant="secondary" size="sm" onclick={saveParams}>{t('param.saveBackup')}</Button>
        <Button variant="outline" size="sm" onclick={exportParams}>{t('param.export')}</Button>
        <Button variant="outline" size="sm" onclick={exportCsv}>CSV</Button>
        {#if metaLoaded && modifiedCount > 0}
          <Button variant="outline" size="sm" onclick={exportDiff}>Diff</Button>
        {/if}
        <Button variant="outline" size="sm" onclick={importParams}>{t('param.import')}</Button>
        <Button variant={compareActive ? 'default' : 'outline'} size="sm" class="gap-1" onclick={compareActive ? clearCompare : compareWithFile}>
          <GitCompareArrows size={13} />{compareActive ? t('param.clearCompare') : t('param.compare')}
        </Button>
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
          {#if cat.key !== 'all' && (categoryCounts[cat.key] ?? 0) > 0}
            <span class="text-[9px] opacity-60">{categoryCounts[cat.key]}</span>
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
              title={viewMode === 'flat' ? t('label.treeView') : t('label.flatView')}>
        {viewMode === 'flat' ? '🌲' : '☰'}
      </button>
      {#if metaLoaded && _metaInfo && _metaInfo.available_series.length > 1}
        <select
          bind:value={metaSeries}
          aria-label={t('param.series')}
          class="h-7 px-1 text-[11px] bg-input border border-border rounded-md text-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
        >
          <option value="">{t('param.seriesAuto')}</option>
          {#each _metaInfo.available_series as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
      {/if}
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
                    <div role="presentation" class="flex items-center gap-2 px-2 py-1.5 text-xs border-b border-border bg-muted/30 cursor-pointer hover:bg-muted/60 transition-colors"
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
