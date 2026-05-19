<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);
  let pitchPx = $derived(Math.max(-30, Math.min(30, d.pitch * 1.5)));
  let rollDeg = $derived(-d.roll);
</script>

<svg class="ahi" viewBox="-55 -55 110 110" xmlns="http://www.w3.org/2000/svg">
  <defs><clipPath id="ahC"><circle r="48"/></clipPath></defs>
  <circle r="50" fill="rgba(0,0,0,0.5)" stroke="#555" stroke-width="1"/>
  <g transform="rotate({rollDeg})" clip-path="url(#ahC)">
    <rect x="-60" y={-60 - pitchPx} width="120" height="60" fill="#1565c0"/>
    <rect x="-60" y={-pitchPx} width="120" height="60" fill="#6d4c41"/>
    <line x1="-60" y1={-pitchPx} x2="60" y2={-pitchPx} stroke="white" stroke-width="1"/>
    {#each [-20, -10, 10, 20] as deg}
      {@const y = -deg * 1.5 - pitchPx}
      {#if y > -45 && y < 45}
        <line x1={deg % 20 === 0 ? -18 : -10} y1={y} x2={deg % 20 === 0 ? 18 : 10} y2={y} stroke="white" stroke-width="0.6" opacity="0.5"/>
      {/if}
    {/each}
  </g>
  <line x1="-22" y1="0" x2="-8" y2="0" stroke="#ffa726" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="8" y1="0" x2="22" y2="0" stroke="#ffa726" stroke-width="2.5" stroke-linecap="round"/>
  <circle r="3" fill="none" stroke="#ffa726" stroke-width="1.5"/>
  <polygon points="0,-44 -3,-39 3,-39" fill="#ffa726"/>
  <text x="0" y="42" text-anchor="middle" fill="#aaa" font-size="9" font-weight="bold">{d.roll.toFixed(0)}° / {d.pitch.toFixed(0)}°</text>
</svg>

<style>
  .ahi { position:absolute; top:10px; right:10px; z-index:1001; width:100px; height:100px; pointer-events:none; }
</style>
