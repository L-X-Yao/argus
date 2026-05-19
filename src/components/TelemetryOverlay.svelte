<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);
  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
  function batColor(r: number): string {
    if (r < 0) return '#888';
    if (r < 20) return '#f44336';
    if (r < 40) return '#ff9800';
    return '#69f0ae';
  }
</script>

<div class="telem-overlay">
  <div class="row-top">
    <span class="mode">{d.mode}</span>
    <span class="armed" class:on={d.armed}>{d.armed ? '已解锁' : '锁定'}</span>
    <span class="gps">{d.gps_fix} {d.gps_sats}星</span>
  </div>
  <div class="row-data">
    <div class="cell">
      <div class="val">{d.alt_rel.toFixed(1)}<span class="u">m</span></div>
      <div class="lbl">高度</div>
    </div>
    <div class="cell">
      <div class="val">{d.gs.toFixed(1)}<span class="u">m/s</span></div>
      <div class="lbl">速度</div>
    </div>
    <div class="cell">
      <div class="val">{d.dist_home.toFixed(0)}<span class="u">m</span></div>
      <div class="lbl">距离</div>
    </div>
    <div class="cell">
      <div class="val" style="color:{batColor(d.remaining)}">{d.voltage.toFixed(1)}<span class="u">V</span></div>
      <div class="lbl">{d.remaining >= 0 ? d.remaining + '%' : '---'}</div>
    </div>
    <div class="cell">
      <div class="val">{d.hdg.toFixed(0)}<span class="u">&deg;</span></div>
      <div class="lbl">航向</div>
    </div>
    {#if d.flight_time > 0}
      <div class="cell">
        <div class="val">{fmtTime(d.flight_time)}</div>
        <div class="lbl">时间</div>
      </div>
    {/if}
  </div>
  {#if d.vz !== 0}
    <div class="vz" style="color:{d.vz > 0 ? '#69f0ae' : '#ff5252'}">{d.vz > 0 ? '↑' : '↓'}{Math.abs(d.vz).toFixed(1)}m/s</div>
  {/if}
</div>

<style>
  .telem-overlay { position:absolute; top:10px; left:10px; z-index:1001; background:rgba(10,10,10,0.88); border:1px solid #444; border-radius:8px; padding:8px 12px; min-width:280px; pointer-events:auto; }
  .row-top { display:flex; gap:8px; align-items:center; margin-bottom:6px; }
  .mode { font-size:18px; font-weight:bold; color:#fff; }
  .armed { padding:2px 8px; border-radius:10px; font-size:11px; font-weight:bold; background:#2e7d32; color:white; }
  .armed.on { background:#d32f2f; }
  .gps { font-size:12px; color:#888; margin-left:auto; }
  .row-data { display:flex; gap:12px; }
  .cell { text-align:center; min-width:40px; }
  .val { font-size:16px; font-weight:bold; color:#e0e0e0; line-height:1.2; }
  .u { font-size:10px; color:#888; font-weight:normal; }
  .lbl { font-size:9px; color:#666; text-transform:uppercase; }
  .vz { position:absolute; top:8px; right:12px; font-size:12px; font-weight:bold; }
</style>
