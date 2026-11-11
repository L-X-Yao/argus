<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { parseDFLog } from '../../lib/dflog';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, Play, Pause, SkipBack, SkipForward } from '@lucide/svelte';

  interface LogRow {
    t: number;
    roll: number;
    pitch: number;
    yaw: number;
    lat: number;
    lon: number;
    alt_rel: number;
    alt_msl: number;
    gs: number;
    vz: number;
    voltage: number;
    current: number;
    remaining: number;
    mode: number;
    mode_name: string;
    armed: number;
    gps_fix: number;
    sats: number;
    wp: number;
    hdg: number;
    dist: number;
    bat_time: number;
  }

  let { onposition }: { onposition: (lat: number, lon: number, yaw: number) => void } = $props();

  // A log names the type of each of its own columns, and a CSV cell can hold anything: what
  // is not a finite number is 0 here. The map and the readout below call number methods on a row.
  const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
  // A coordinate that did not parse stays out of range, so that emitPosition passes the row
  // over: as 0 it would put the marker on the Greenwich meridian.
  const coordinate = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : Number.NaN);

  let rows: LogRow[] = $state([]);
  let playing = $state(false);
  let cursor = $state(0);
  let speed = $state(1);
  let fileName = $state('');
  let timer: ReturnType<typeof setInterval> | null = null;

  let current = $derived(rows.length > 0 && cursor < rows.length ? rows[cursor] : null);
  let duration = $derived(rows.length > 0 ? rows[rows.length - 1].t : 0);

  function loadFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv,.bin,.log';
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      fileName = file.name;
      if (file.name.endsWith('.bin') || file.name.endsWith('.log')) {
        const reader = new FileReader();
        reader.onload = (ev: ProgressEvent<FileReader>) => {
          parseBinLog(ev.target!.result as ArrayBuffer);
        };
        reader.readAsArrayBuffer(file);
      } else {
        const reader = new FileReader();
        reader.onload = (ev: ProgressEvent<FileReader>) => {
          parseCSV(ev.target!.result as string);
        };
        reader.readAsText(file);
      }
    };
    input.click();
  }

  function parseBinLog(buffer: ArrayBuffer) {
    const log = parseDFLog(buffer);
    const att = log.messages.filter((m) => m.type === 'ATT');
    const gps = log.messages.filter((m) => m.type === 'GPS');
    const bat = log.messages.filter((m) => m.type === 'BAT');
    if (att.length < 2 && gps.length < 2) return;
    const t0 = log.messages[0]?.timestamp || 0;
    const parsed: LogRow[] = [];
    let gi = 0,
      bi = 0;
    for (const a of att) {
      while (gi < gps.length - 1 && gps[gi + 1].timestamp <= a.timestamp) gi++;
      while (bi < bat.length - 1 && bat[bi + 1].timestamp <= a.timestamp) bi++;
      const g = gps[gi] || { fields: {} };
      const b = bat[bi] || { fields: {} };
      parsed.push({
        t: num(a.timestamp - t0),
        roll: num(a.fields['Roll']),
        pitch: num(a.fields['Pitch']),
        yaw: num(a.fields['Yaw']),
        lat: coordinate(g.fields['Lat']),
        lon: coordinate(g.fields['Lng']),
        alt_rel: num(g.fields['Alt']),
        alt_msl: num(g.fields['Alt']),
        gs: num(g.fields['Spd']),
        vz: 0,
        voltage: num(b.fields['Volt']),
        current: num(b.fields['Curr']),
        remaining: num(b.fields['CurrTot']) || -1,
        mode: 0,
        mode_name: '',
        armed: 0,
        gps_fix: num(g.fields['Status']),
        sats: num(g.fields['NSats']),
        wp: 0,
        hdg: num(g.fields['GCrs']),
        dist: 0,
        bat_time: -1,
      });
    }
    rows = parsed;
    cursor = 0;
    playing = false;
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function parseCSV(text: string) {
    const lines = text.trim().split('\n');
    if (lines.length < 2) return;
    const parsed: LogRow[] = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(',');
      if (cols.length < 20) continue;
      parsed.push({
        t: num(parseFloat(cols[0])),
        roll: num(parseFloat(cols[1])),
        pitch: num(parseFloat(cols[2])),
        yaw: num(parseFloat(cols[3])),
        lat: coordinate(parseFloat(cols[4])),
        lon: coordinate(parseFloat(cols[5])),
        alt_rel: num(parseFloat(cols[6])),
        alt_msl: num(parseFloat(cols[7])),
        gs: num(parseFloat(cols[8])),
        vz: num(parseFloat(cols[9])),
        voltage: num(parseFloat(cols[10])),
        current: num(parseFloat(cols[11])),
        remaining: num(parseInt(cols[12])),
        mode: num(parseInt(cols[13])),
        mode_name: cols[14] || '',
        armed: num(parseInt(cols[15])),
        gps_fix: num(parseInt(cols[16])),
        sats: num(parseInt(cols[17])),
        wp: num(parseInt(cols[18])),
        hdg: num(parseFloat(cols[19])),
        dist: num(parseFloat(cols[20])),
        bat_time: num(parseInt(cols[21])) || -1,
      });
    }
    rows = parsed;
    cursor = 0;
    playing = false;
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function togglePlay() {
    if (!rows.length) return;
    playing = !playing;
    if (playing) {
      timer = setInterval(() => {
        if (cursor < rows.length - 1) {
          cursor++;
          emitPosition();
        } else {
          playing = false;
          if (timer) {
            clearInterval(timer);
            timer = null;
          }
        }
      }, 250 / speed);
    } else {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }
  }

  function seek(e: Event) {
    cursor = parseInt((e.target as HTMLInputElement).value);
    emitPosition();
  }

  function setSpeed(s: number) {
    speed = s;
    if (playing && timer) {
      clearInterval(timer);
      timer = setInterval(() => {
        if (cursor < rows.length - 1) {
          cursor++;
          emitPosition();
        } else {
          playing = false;
          if (timer) {
            clearInterval(timer);
            timer = null;
          }
        }
      }, 250 / speed);
    }
  }

  function emitPosition() {
    const r = rows[cursor];
    if (r && Math.abs(r.lat) > 0.001 && Math.abs(r.lat) <= 90 && Math.abs(r.lon) <= 180) {
      onposition(r.lat, r.lon, r.yaw);
    }
  }

  function close() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    rows = [];
    cursor = 0;
    playing = false;
    fileName = '';
  }

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60),
      sec = Math.floor(s % 60);
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

<div class="bg-card border border-border rounded-xl p-3 mx-2 mb-2">
  {#if rows.length === 0}
    <button
      class="w-full py-2.5 bg-transparent border-2 border-dashed border-border rounded-lg cursor-pointer
                    text-sm font-bold text-muted-foreground hover:border-primary hover:text-primary transition-colors"
      onclick={loadFile}
    >
      {t('replay.loadCsv')}
    </button>
  {:else}
    <div class="flex items-center gap-2 mb-2">
      <span class="text-xs font-bold text-primary flex-1 truncate">{fileName}</span>
      <span class="text-[11px] text-muted-foreground">{rows.length} frames | {fmtTime(duration)}</span>
      <button class="text-destructive leading-none bg-transparent border-none cursor-pointer px-0.5" onclick={close}
        ><X size={14} /></button
      >
    </div>
    <div class="flex items-center gap-2">
      <Button
        variant="ghost"
        size="icon-xs"
        class="shrink-0"
        onclick={() => {
          cursor = Math.max(0, cursor - 10);
          emitPosition();
        }}
        aria-label={t('ui.skipBack')}
      >
        <SkipBack size={12} />
      </Button>
      <Button
        variant="default"
        size="icon-sm"
        class="rounded-full shrink-0"
        onclick={togglePlay}
        aria-label={playing ? t('ctrl.pauseMission') : t('panel.script.run')}
      >
        {#if playing}<Pause size={14} />{:else}<Play size={14} />{/if}
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        class="shrink-0"
        onclick={() => {
          cursor = Math.min(rows.length - 1, cursor + 10);
          emitPosition();
        }}
        aria-label={t('ui.skipForward')}
      >
        <SkipForward size={12} />
      </Button>
      <input
        type="range"
        class="flex-1 h-1 accent-primary"
        min="0"
        max={rows.length - 1}
        value={cursor}
        oninput={seek}
      />
      <span class="text-xs text-muted-foreground font-mono min-w-[40px]">{fmtTime(current?.t || 0)}</span>
    </div>
    <div class="flex gap-1 mt-1.5">
      {#each [0.5, 1, 2, 4, 8] as s}
        <button
          class="px-2 py-0.5 text-[10px] rounded border cursor-pointer transition-colors
          {speed === s ? 'text-primary border-primary' : 'text-muted-foreground border-border hover:text-foreground'}"
          onclick={() => setSpeed(s)}>{s}x</button
        >
      {/each}
    </div>
    {#if current}
      <div class="flex gap-3 mt-1.5 text-[11px] text-muted-foreground">
        <span>{t('telem.alt')} {current.alt_rel.toFixed(1)}m</span>
        <span>{t('telem.speed')} {current.gs.toFixed(1)}m/s</span>
        <span>{t('chart.voltage')} {current.voltage.toFixed(1)}V</span>
        <span>{t('telem.dist')} {current.dist.toFixed(0)}m</span>
        <span>R:{current.roll.toFixed(0)} P:{current.pitch.toFixed(0)} Y:{current.yaw.toFixed(0)}</span>
      </div>
    {/if}
  {/if}
</div>
