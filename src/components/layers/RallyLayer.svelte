<script lang="ts">
  import { app } from '../../lib/stores.svelte';

  type CoordFn = (lat: number, lon: number) => [number, number];
  let { map, coord }: { map: L.Map; coord: CoordFn } = $props();

  $effect(() => {
    const markers = app.rallyPoints.map((p, i) =>
      L.circleMarker(coord(p.lat, p.lon), {
        radius: 7,
        color: '#26a69a',
        fillColor: '#26a69a',
        fillOpacity: app.rallyUploaded ? 0.8 : 0.3,
        weight: 2,
        className: 'rally-point',
      })
        .bindTooltip(`R${i + 1} · ${p.alt} m`)
        .addTo(map),
    );
    return () => markers.forEach((m) => m.remove());
  });
</script>
