<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);
  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

<div class="telem-strip">
  <div class="cell">
    <span class="val">{d.alt_rel.toFixed(1)}</span>
    <span class="lbl">H</span>
  </div>
  <div class="sep"></div>
  <div class="cell">
    <span class="val">{d.gs.toFixed(1)}</span>
    <span class="lbl">H.S</span>
  </div>
  <div class="sep"></div>
  <div class="cell">
    <span class="val" style="color:{d.vz > 0.3 ? '#69f0ae' : d.vz < -0.3 ? '#ff5252' : ''}">{d.vz.toFixed(1)}</span>
    <span class="lbl">V.S</span>
  </div>
  <div class="sep"></div>
  <div class="cell">
    <span class="val">{d.dist_home.toFixed(0)}</span>
    <span class="lbl">D</span>
  </div>
  <div class="sep"></div>
  <div class="cell">
    <span class="val">{d.hdg.toFixed(0)}&deg;</span>
    <span class="lbl">HDG</span>
  </div>
  {#if d.flight_time > 0}
    <div class="sep"></div>
    <div class="cell">
      <span class="val">{fmtTime(d.flight_time)}</span>
      <span class="lbl">时间</span>
    </div>
  {/if}
</div>

<style>
  .telem-strip { position:absolute; bottom:32px; left:50%; transform:translateX(-50%); z-index:1001;
    display:flex; align-items:center; gap:0;
    background:rgba(10,10,10,0.85); border:1px solid #444; border-radius:20px;
    padding:4px 16px; pointer-events:auto; }
  .cell { display:flex; flex-direction:column; align-items:center; padding:0 10px; min-width:40px; }
  .val { font-size:17px; font-weight:bold; color:#e0e0e0; line-height:1.1; font-variant-numeric:tabular-nums; }
  .lbl { font-size:9px; color:#666; text-transform:uppercase; letter-spacing:0.5px; }
  .sep { width:1px; height:24px; background:#444; }
</style>
