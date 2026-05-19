<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);
  let pitchPx = $derived(Math.max(-60, Math.min(60, d.pitch * 2)));
  let rollDeg = $derived(-d.roll);

  function hdgTicks(hdg: number): { x: number; label: string; major: boolean }[] {
    const ticks: { x: number; label: string; major: boolean }[] = [];
    const cardinals: Record<number, string> = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };
    for (let i = -6; i <= 6; i++) {
      let deg = Math.round(hdg / 10) * 10 + i * 10;
      if (deg < 0) deg += 360;
      if (deg >= 360) deg -= 360;
      const offset = (deg - hdg);
      const adj = offset > 180 ? offset - 360 : offset < -180 ? offset + 360 : offset;
      const x = 250 + adj * 3;
      const label = cardinals[deg] || (deg === 0 ? 'N' : String(deg));
      ticks.push({ x, label, major: deg % 30 === 0 });
    }
    return ticks;
  }

  function spdTicks(spd: number): { y: number; label: string }[] {
    const ticks: { y: number; label: string }[] = [];
    const base = Math.floor(spd / 5) * 5;
    for (let i = -3; i <= 3; i++) {
      const v = base + i * 5;
      if (v < 0) continue;
      const y = 155 - (v - spd) * 8;
      ticks.push({ y, label: String(v) });
    }
    return ticks;
  }

  function altTicks(alt: number): { y: number; label: string }[] {
    const ticks: { y: number; label: string }[] = [];
    const base = Math.floor(alt / 10) * 10;
    for (let i = -3; i <= 3; i++) {
      const v = base + i * 10;
      const y = 155 - (v - alt) * 4;
      ticks.push({ y, label: String(Math.round(v)) });
    }
    return ticks;
  }

  let pitchLines = $derived.by(() => {
    const lines: { y: number; label: string; width: number }[] = [];
    for (let deg = -30; deg <= 30; deg += 5) {
      if (deg === 0) continue;
      const y = -deg * 2 - pitchPx;
      if (y < -80 || y > 80) continue;
      lines.push({ y, label: String(Math.abs(deg)), width: deg % 10 === 0 ? 40 : 20 });
    }
    return lines;
  });
</script>

<svg class="hud-svg" viewBox="0 0 500 310" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="ahClip"><circle cx="250" cy="155" r="85"/></clipPath>
    <clipPath id="spdClip"><rect x="10" y="65" width="60" height="180"/></clipPath>
    <clipPath id="altClip"><rect x="430" y="65" width="60" height="180"/></clipPath>
    <clipPath id="hdgClip"><rect x="100" y="8" width="300" height="40"/></clipPath>
  </defs>

  <rect width="500" height="310" rx="8" fill="rgba(0,0,0,0.75)"/>

  <!-- Heading tape -->
  <rect x="100" y="8" width="300" height="32" rx="4" fill="rgba(0,0,0,0.6)" stroke="#444" stroke-width="0.5"/>
  <g clip-path="url(#hdgClip)">
    {#each hdgTicks(d.hdg) as t}
      <line x1={t.x} y1="32" x2={t.x} y2={t.major ? 22 : 27} stroke={t.major ? '#aaa' : '#666'} stroke-width="1"/>
      {#if t.major}
        <text x={t.x} y="19" text-anchor="middle" fill={t.label === 'N' ? '#f44336' : t.label === 'S' || t.label === 'E' || t.label === 'W' ? '#4fc3f7' : '#ccc'} font-size="11" font-weight={t.label.length === 1 ? 'bold' : 'normal'}>{t.label}</text>
      {/if}
    {/each}
  </g>
  <polygon points="250,36 247,42 253,42" fill="#ffa726"/>
  <text x="250" y="55" text-anchor="middle" fill="#ffa726" font-size="14" font-weight="bold">{d.hdg.toFixed(0)}°</text>

  <!-- Attitude indicator -->
  <circle cx="250" cy="155" r="86" fill="none" stroke="#555" stroke-width="1.5"/>
  <g clip-path="url(#ahClip)">
    <g transform="rotate({rollDeg}, 250, 155)">
      <rect x="50" y={55 - pitchPx} width="400" height="100" fill="#1565c0"/>
      <rect x="50" y={155 - pitchPx} width="400" height="200" fill="#6d4c41"/>
      <line x1="50" y1={155 - pitchPx} x2="450" y2={155 - pitchPx} stroke="white" stroke-width="1.5"/>
      {#each pitchLines as pl}
        <line x1={250 - pl.width} y1={155 + pl.y} x2={250 + pl.width} y2={155 + pl.y} stroke="white" stroke-width="0.8" opacity="0.7"/>
        <text x={250 + pl.width + 4} y={155 + pl.y + 3} fill="white" font-size="8" opacity="0.6">{pl.label}</text>
      {/each}
    </g>
  </g>
  <!-- Fixed aircraft reference -->
  <line x1="200" y1="155" x2="235" y2="155" stroke="#ffa726" stroke-width="3" stroke-linecap="round"/>
  <line x1="265" y1="155" x2="300" y2="155" stroke="#ffa726" stroke-width="3" stroke-linecap="round"/>
  <circle cx="250" cy="155" r="4" fill="none" stroke="#ffa726" stroke-width="2"/>
  <!-- Roll indicator -->
  <polygon points="250,70 247,63 253,63" fill="#ffa726"/>
  {#each [-60, -45, -30, -20, -10, 10, 20, 30, 45, 60] as angle}
    <line x1={250 + 85 * Math.sin(angle * Math.PI / 180)} y1={155 - 85 * Math.cos(angle * Math.PI / 180)}
          x2={250 + 80 * Math.sin(angle * Math.PI / 180)} y2={155 - 80 * Math.cos(angle * Math.PI / 180)}
          stroke={Math.abs(angle) <= 30 ? '#aaa' : '#666'} stroke-width="1.5"/>
  {/each}

  <!-- Speed tape (left) -->
  <rect x="10" y="65" width="60" height="180" rx="4" fill="rgba(0,0,0,0.6)" stroke="#444" stroke-width="0.5"/>
  <text x="40" y="62" text-anchor="middle" fill="#666" font-size="9">速度</text>
  <g clip-path="url(#spdClip)">
    {#each spdTicks(d.gs) as t}
      <line x1="60" y1={t.y} x2="68" y2={t.y} stroke="#666" stroke-width="1"/>
      <text x="55" y={t.y + 3} text-anchor="end" fill="#aaa" font-size="10">{t.label}</text>
    {/each}
  </g>
  <rect x="15" y="145" width="50" height="20" rx="3" fill="#1a1a1a" stroke="#4fc3f7" stroke-width="1.5"/>
  <text x="40" y="159" text-anchor="middle" fill="#4fc3f7" font-size="13" font-weight="bold">{d.gs.toFixed(1)}</text>

  <!-- Altitude tape (right) -->
  <rect x="430" y="65" width="60" height="180" rx="4" fill="rgba(0,0,0,0.6)" stroke="#444" stroke-width="0.5"/>
  <text x="460" y="62" text-anchor="middle" fill="#666" font-size="9">高度</text>
  <g clip-path="url(#altClip)">
    {#each altTicks(d.alt_rel) as t}
      <line x1="428" y1={t.y} x2="432" y2={t.y} stroke="#666" stroke-width="1"/>
      <text x="437" y={t.y + 3} text-anchor="start" fill="#aaa" font-size="10">{t.label}</text>
    {/each}
  </g>
  <rect x="435" y="145" width="50" height="20" rx="3" fill="#1a1a1a" stroke="#69f0ae" stroke-width="1.5"/>
  <text x="460" y="159" text-anchor="middle" fill="#69f0ae" font-size="13" font-weight="bold">{d.alt_rel.toFixed(1)}</text>
  <!-- VZ arrow -->
  {#if Math.abs(d.vz) > 0.2}
    <polygon points={d.vz > 0 ? '497,145 500,140 494,140' : '497,165 500,170 494,170'}
             fill={d.vz > 0 ? '#69f0ae' : '#ff5252'}/>
    <text x="497" y={d.vz > 0 ? 138 : 180} text-anchor="middle" fill={d.vz > 0 ? '#69f0ae' : '#ff5252'} font-size="9">{Math.abs(d.vz).toFixed(1)}</text>
  {/if}

  <!-- Bottom info bar -->
  <rect x="80" y="260" width="340" height="40" rx="4" fill="rgba(0,0,0,0.6)" stroke="#444" stroke-width="0.5"/>
  <text x="115" y="277" text-anchor="middle" fill={d.armed ? '#ff5252' : '#69f0ae'} font-size="12" font-weight="bold">{d.armed ? '已解锁' : '已锁定'}</text>
  <text x="200" y="277" text-anchor="middle" fill="#ffa726" font-size="14" font-weight="bold">{d.mode}</text>
  <text x="300" y="277" text-anchor="middle" fill="#4fc3f7" font-size="11">{d.gps_fix} {d.gps_sats}星</text>
  <text x="380" y="277" text-anchor="middle" fill={d.remaining < 20 ? '#ff5252' : d.remaining < 40 ? '#ffa726' : '#69f0ae'} font-size="11">{d.voltage.toFixed(1)}V {d.remaining >= 0 ? d.remaining + '%' : ''}</text>
  {#if d.flight_time > 0}
    <text x="200" y="294" text-anchor="middle" fill="#888" font-size="10">{Math.floor(d.flight_time / 60)}:{(d.flight_time % 60).toString().padStart(2, '0')} | {d.dist_home.toFixed(0)}m</text>
  {/if}
</svg>

<style>
  .hud-svg { position:absolute; bottom:50px; left:50%; transform:translateX(-50%); z-index:1000; width:min(500px, 90vw); pointer-events:none; }
</style>
