<script lang="ts">
  import { app, addToast } from '../lib/stores.svelte';
  import { t } from '../lib/i18n.svelte';
  import { X, AlertTriangle, Plane as PlaneIcon } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import Switch from '$lib/components/ui/switch/switch.svelte';

  let { onclose }: { onclose: () => void } = $props();

  /* ── Airport database (top 10 Chinese airports) ── */
  const AIRPORTS = [
    { name: '北京首都 PEK', lat: 40.0801, lon: 116.5846, radius: 8500 },
    { name: '北京大兴 PKX', lat: 39.5098, lon: 116.4105, radius: 8500 },
    { name: '上海浦东 PVG', lat: 31.1443, lon: 121.8083, radius: 8500 },
    { name: '上海虹桥 SHA', lat: 31.1979, lon: 121.3363, radius: 6000 },
    { name: '广州白云 CAN', lat: 23.3924, lon: 113.2988, radius: 8500 },
    { name: '深圳宝安 SZX', lat: 22.6393, lon: 113.8107, radius: 6000 },
    { name: '成都天府 TFU', lat: 30.3194, lon: 104.4419, radius: 8500 },
    { name: '西安咸阳 XIY', lat: 34.4371, lon: 108.7519, radius: 8500 },
    { name: '杭州萧山 HGH', lat: 30.2295, lon: 120.4344, radius: 6000 },
    { name: '南京禄口 NKG', lat: 31.7420, lon: 118.8620, radius: 6000 },
  ];

  /* ── Persist enable toggle ── */
  function loadEnabled(): boolean {
    try {
      const v = localStorage.getItem('pllink_v3_airspace');
      if (v === 'true' || v === 'false') return v === 'true';
    } catch {}
    return false;
  }

  let enabled = $state(loadEnabled());

  function toggleEnabled(val: boolean) {
    enabled = val;
    try { localStorage.setItem('pllink_v3_airspace', String(val)); } catch {}
  }

  /* ── Distance calculation (Haversine) ── */
  function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
      Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function fmtDist(m: number): string {
    if (m < 1000) return `${Math.round(m)} m`;
    return `${(m / 1000).toFixed(1)} km`;
  }

  /* ── Airport list with distance, sorted by distance ── */
  let airportList = $derived.by(() => {
    const droneLat = app.drone.lat;
    const droneLon = app.drone.lon;
    const hasPos = droneLat !== 0 || droneLon !== 0;

    return AIRPORTS.map(ap => {
      const dist = hasPos ? haversineM(droneLat, droneLon, ap.lat, ap.lon) : -1;
      const inside = hasPos && dist < ap.radius;
      return { ...ap, dist, inside };
    }).sort((a, b) => {
      if (a.dist < 0) return 1;
      if (b.dist < 0) return -1;
      return a.dist - b.dist;
    });
  });

  /* ── Any violation? ── */
  let violation = $derived(airportList.some(a => a.inside));
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[500px] max-h-[85vh] flex flex-col overflow-hidden">

    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <div class="flex items-center gap-2">
        <PlaneIcon size={16} class="text-primary" />
        <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('airspace.title')}</h2>
      </div>
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
          {t('airspace.enabled')}
          <Switch size="sm" checked={enabled} onCheckedChange={toggleEnabled} />
        </label>
        <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
      </div>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">

      <!-- Violation warning -->
      {#if violation && enabled}
        <div class="p-3 rounded-lg bg-destructive/10 border border-destructive/30 flex items-center gap-2">
          <AlertTriangle size={16} class="text-destructive shrink-0" />
          <span class="text-xs font-semibold text-destructive">{t('airspace.noFly')} — Drone is within an airport no-fly zone!</span>
        </div>
      {/if}

      <!-- Airport list header -->
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('airspace.airport')}</span>
        <span class="text-[10px] text-muted-foreground">({AIRPORTS.length})</span>
      </div>

      <!-- Airport cards -->
      <div class="space-y-2">
        {#each airportList as ap (ap.name)}
          <div class="p-3 rounded-lg border transition-colors
            {ap.inside ? 'bg-destructive/5 border-destructive/30' : 'bg-muted/30 border-border'}">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <PlaneIcon size={14} class={ap.inside ? 'text-destructive' : 'text-muted-foreground'} />
                <span class="text-xs font-semibold text-foreground">{ap.name}</span>
                {#if ap.inside}
                  <span class="text-[10px] font-medium text-destructive bg-destructive/10 px-1.5 py-0.5 rounded">
                    {t('airspace.noFly')}
                  </span>
                {/if}
              </div>
              <span class="text-[10px] text-muted-foreground">
                r={fmtDist(ap.radius)}
              </span>
            </div>
            <div class="grid grid-cols-3 gap-x-3 mt-2 text-[11px]">
              <div class="flex justify-between">
                <span class="text-muted-foreground">Lat</span>
                <span class="font-mono text-foreground">{ap.lat.toFixed(4)}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-muted-foreground">Lon</span>
                <span class="font-mono text-foreground">{ap.lon.toFixed(4)}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-muted-foreground">Dist</span>
                <span class="font-mono font-medium {ap.inside ? 'text-destructive' : 'text-foreground'}">
                  {ap.dist >= 0 ? fmtDist(ap.dist) : '---'}
                </span>
              </div>
            </div>
          </div>
        {/each}
      </div>

      <!-- Hint -->
      {#if !enabled}
        <div class="p-3 rounded-lg bg-primary/5 border border-primary/20">
          <p class="text-xs text-muted-foreground leading-relaxed">
            {t('airspace.restricted')} — Enable the airspace overlay to see no-fly zone warnings on the map.
          </p>
        </div>
      {/if}

    </div>
  </div>
</div>
