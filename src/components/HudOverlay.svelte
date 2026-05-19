<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);
  let pitchPx = $derived(Math.max(-25, Math.min(25, d.pitch * 1.2)));
  let rollDeg = $derived(-d.roll);

  const cardinals: [number, string][] = [[0,'N'],[45,'45'],[90,'E'],[135,'135'],[180,'S'],[225,'225'],[270,'W'],[315,'315']];
</script>

<svg class="ahi-compass" viewBox="-62 -62 124 124" xmlns="http://www.w3.org/2000/svg">
  <!-- Compass ring -->
  <circle r="58" fill="none" stroke="#444" stroke-width="1"/>
  <g transform="rotate({-d.hdg})">
    {#each cardinals as [deg, label]}
      <g transform="rotate({deg})">
        <line x1="0" y1="-56" x2="0" y2="-50" stroke={label === 'N' ? '#f44336' : '#888'} stroke-width={label.length === 1 ? 1.5 : 0.8}/>
        {#if label.length <= 1}
          <text x="0" y="-42" text-anchor="middle" fill={label === 'N' ? '#f44336' : '#aaa'} font-size="8" font-weight="bold"
                transform="rotate({-deg}, 0, -42)">{label}</text>
        {/if}
      </g>
    {/each}
    {#each Array(36) as _, i}
      {#if i % 4.5 !== 0}
        <line transform="rotate({i * 10})" x1="0" y1="-56" x2="0" y2="-53" stroke="#555" stroke-width="0.5"/>
      {/if}
    {/each}
  </g>
  <polygon points="0,-58 -3,-53 3,-53" fill="#ffa726"/>

  <!-- AHI circle -->
  <defs><clipPath id="ahC"><circle r="38"/></clipPath></defs>
  <circle r="39" fill="rgba(0,0,0,0.6)" stroke="#555" stroke-width="0.5"/>
  <g transform="rotate({rollDeg})" clip-path="url(#ahC)">
    <rect x="-50" y={-50 - pitchPx} width="100" height="50" fill="#1565c0"/>
    <rect x="-50" y={-pitchPx} width="100" height="50" fill="#6d4c41"/>
    <line x1="-50" y1={-pitchPx} x2="50" y2={-pitchPx} stroke="white" stroke-width="0.8"/>
    {#each [-20, -10, 10, 20] as deg}
      {@const y = -deg * 1.2 - pitchPx}
      {#if y > -35 && y < 35}
        <line x1={Math.abs(deg) === 20 ? -14 : -8} y1={y} x2={Math.abs(deg) === 20 ? 14 : 8} y2={y}
              stroke="white" stroke-width="0.5" opacity="0.5"/>
      {/if}
    {/each}
  </g>
  <!-- Aircraft reference -->
  <line x1="-18" y1="0" x2="-6" y2="0" stroke="#ffa726" stroke-width="2" stroke-linecap="round"/>
  <line x1="6" y1="0" x2="18" y2="0" stroke="#ffa726" stroke-width="2" stroke-linecap="round"/>
  <circle r="2.5" fill="none" stroke="#ffa726" stroke-width="1.5"/>
  <!-- Roll pointer -->
  <polygon points="0,-35 -2,-31 2,-31" fill="#ffa726"/>
  <!-- Heading readout -->
  <text x="0" y="55" text-anchor="middle" fill="#aaa" font-size="9" font-weight="bold">{d.hdg.toFixed(0)}°</text>
</svg>

<style>
  .ahi-compass { position:absolute; bottom:50px; right:10px; z-index:1001; width:120px; height:130px; pointer-events:none; }
</style>
