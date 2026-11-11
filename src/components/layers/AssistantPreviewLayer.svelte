<script lang="ts">
  // The route the AI assistant proposes, drawn dashed while it waits for the operator
  // (AssistantDialog). Gone when it is approved, declined or withdrawn.
  import { assistant } from '../../lib/assistant.svelte';

  type CoordFn = (lat: number, lon: number) => [number, number];
  let { map, coord }: { map: L.Map; coord: CoordFn } = $props();

  $effect(() => {
    const proposal = assistant.queue[0];
    if (!proposal || proposal.kind !== 'propose_mission') return;
    const points = proposal.waypoints.map((w) => coord(w.lat, w.lon));
    const layers: L.Layer[] = [
      L.polyline(points, { color: '#f59e0b', weight: 3, dashArray: '8 6', className: 'assistant-preview' }).addTo(map),
      ...points.map((p, i) =>
        L.circleMarker(p, {
          radius: 6,
          color: '#f59e0b',
          fillColor: '#f59e0b',
          fillOpacity: 0.35,
          weight: 2,
          className: 'assistant-preview-point',
        })
          .bindTooltip(String(i + 1), { permanent: true, direction: 'top', offset: [0, -6] })
          .addTo(map),
      ),
    ];
    return () => layers.forEach((layer) => layer.remove());
  });
</script>
