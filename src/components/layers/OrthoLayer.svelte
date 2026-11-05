<script lang="ts">
  import { ortho } from '../../lib/orthoOverlays.svelte';

  type CoordFn = (lat: number, lon: number) => [number, number];
  let { map, coord }: { map: L.Map; coord: CoordFn } = $props();

  // Redraws when the list changes, and when a tile source change alters coord.
  $effect(() => {
    const layers = ortho.overlays.map((o) =>
      L.imageOverlay(o.dataUrl, [coord(o.seLat, o.nwLon), coord(o.nwLat, o.seLon)], { opacity: o.opacity }).addTo(map),
    );
    return () => layers.forEach((layer) => layer.remove());
  });
</script>
