<script lang="ts">
  import { app } from '../lib/stores.svelte';

  interface LogRow {
    t: number; roll: number; pitch: number; yaw: number;
    lat: number; lon: number; alt_rel: number; alt_msl: number;
    gs: number; vz: number; voltage: number; current: number;
    remaining: number; mode: number; mode_name: string; armed: number;
    gps_fix: number; sats: number; wp: number; hdg: number;
    dist: number; bat_time: number;
  }

  let { onposition }: { onposition: (lat: number, lon: number, yaw: number) => void } = $props();

  let rows: LogRow[] = $state([]);
  let playing = $state(false);
  let cursor = $state(0);
  let speed = $state(1);
  let fileName = $state('');
  let timer: ReturnType<typeof setInterval> | null = null;

  let current = $derived(rows.length > 0 && cursor < rows.length ? rows[cursor] : null);
  let progress = $derived(rows.length > 0 ? (cursor / (rows.length - 1)) * 100 : 0);
  let duration = $derived(rows.length > 0 ? rows[rows.length - 1].t : 0);

  function loadFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      fileName = file.name;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        parseCSV(ev.target.result as string);
      };
      reader.readAsText(file);
    };
    input.click();
  }

  function parseCSV(text: string) {
    const lines = text.trim().split('\n');
    if (lines.length < 2) return;
    const parsed: LogRow[] = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(',');
      if (cols.length < 20) continue;
      parsed.push({
        t: parseFloat(cols[0]),
        roll: parseFloat(cols[1]),
        pitch: parseFloat(cols[2]),
        yaw: parseFloat(cols[3]),
        lat: parseFloat(cols[4]),
        lon: parseFloat(cols[5]),
        alt_rel: parseFloat(cols[6]),
        alt_msl: parseFloat(cols[7]),
        gs: parseFloat(cols[8]),
        vz: parseFloat(cols[9]),
        voltage: parseFloat(cols[10]),
        current: parseFloat(cols[11]),
        remaining: parseInt(cols[12]),
        mode: parseInt(cols[13]),
        mode_name: cols[14] || '',
        armed: parseInt(cols[15]),
        gps_fix: parseInt(cols[16]),
        sats: parseInt(cols[17]),
        wp: parseInt(cols[18]),
        hdg: parseFloat(cols[19]),
        dist: parseFloat(cols[20]) || 0,
        bat_time: parseInt(cols[21]) || -1,
      });
    }
    rows = parsed;
    cursor = 0;
    playing = false;
    if (timer) { clearInterval(timer); timer = null; }
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
          if (timer) { clearInterval(timer); timer = null; }
        }
      }, 250 / speed);
    } else {
      if (timer) { clearInterval(timer); timer = null; }
    }
  }

  function seek(e: Event) {
    const val = parseInt((e.target as HTMLInputElement).value);
    cursor = val;
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
          if (timer) { clearInterval(timer); timer = null; }
        }
      }, 250 / speed);
    }
  }

  function emitPosition() {
    const r = rows[cursor];
    if (r && Math.abs(r.lat) > 0.001) {
      onposition(r.lat, r.lon, r.yaw);
    }
  }

  function close() {
    if (timer) { clearInterval(timer); timer = null; }
    rows = [];
    cursor = 0;
    playing = false;
    fileName = '';
  }

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

<div class="replay-panel">
  {#if rows.length === 0}
    <button class="load-btn" onclick={loadFile}>加载飞行日志 (.csv)</button>
  {:else}
    <div class="replay-header">
      <span class="fn">{fileName}</span>
      <span class="info">{rows.length} 帧 | {fmtTime(duration)}</span>
      <button class="close-btn" onclick={close}>&times;</button>
    </div>
    <div class="replay-controls">
      <button class="play-btn" onclick={togglePlay}>{playing ? '⏸' : '▶'}</button>
      <input type="range" class="seek" min="0" max={rows.length - 1} value={cursor} oninput={seek} />
      <span class="time">{fmtTime(current?.t || 0)}</span>
    </div>
    <div class="speed-btns">
      {#each [0.5, 1, 2, 4, 8] as s}
        <button class="spd" class:active={speed === s} onclick={() => setSpeed(s)}>{s}x</button>
      {/each}
    </div>
    {#if current}
      <div class="replay-data">
        <span>高度 {current.alt_rel.toFixed(1)}m</span>
        <span>速度 {current.gs.toFixed(1)}m/s</span>
        <span>电压 {current.voltage.toFixed(1)}V</span>
        <span>距离 {current.dist.toFixed(0)}m</span>
      </div>
    {/if}
  {/if}
</div>

<style>
  .replay-panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  .load-btn { width:100%; padding:10px; background:#37474f; color:var(--text-main); border:1px dashed var(--border-light); border-radius:6px; cursor:pointer; font-size:13px; }
  .load-btn:hover { border-color:var(--text-accent); color:var(--text-accent); }
  .replay-header { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
  .fn { font-size:12px; font-weight:bold; color:var(--text-accent); flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .info { font-size:11px; color:var(--text-dim); }
  .close-btn { background:none; border:none; color:#f44336; cursor:pointer; font-size:18px; padding:0 4px; }
  .replay-controls { display:flex; align-items:center; gap:8px; }
  .play-btn { width:32px; height:32px; border-radius:50%; border:none; background:#1565c0; color:white; cursor:pointer; font-size:14px; flex-shrink:0; }
  .seek { flex:1; height:4px; accent-color:#4fc3f7; }
  .time { font-size:12px; color:var(--text-dim); font-family:monospace; min-width:40px; }
  .speed-btns { display:flex; gap:3px; margin-top:4px; }
  .spd { padding:2px 8px; border:1px solid var(--border-light); border-radius:3px; background:transparent; color:var(--text-dim); cursor:pointer; font-size:10px; }
  .spd.active { color:#4fc3f7; border-color:#4fc3f7; }
  .replay-data { display:flex; gap:10px; margin-top:6px; font-size:11px; color:var(--text-dim); }
</style>
