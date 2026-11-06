<script lang="ts">
  import { app, addToast } from '../../lib/stores.svelte';
  import { dispatch } from '../../lib/transport';
  import { t } from '../../lib/i18n.svelte';
  import { paramState } from '../../lib/paramStore.svelte';
  import { X } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let { onclose }: { onclose: () => void } = $props();

  /* ── Helpers ── */

  function getParam(name: string, fallback: number): number {
    const p = paramState.list.find((p) => p.name === name);
    return p !== undefined ? p.value : fallback;
  }

  let paramsAvailable = $derived(paramState.list.length > 0);

  /* ── Frame class definitions ── */

  interface FrameClassDef {
    value: number;
    labelKey: string;
    ascii: string;
    types: number[];
  }

  // FRAME_CLASS @Values, ArduCopter/Parameters.cpp:689. Helicopters need firmware of their
  // own, and the scripted classes a script on the FC. types: what each matrix takes,
  // AP_MotorsMatrix.cpp:576 setup_quad_matrix and the setup_* after it. Any other
  // combination leaves the FC refusing to arm, so only these are on offer.
  const frameClasses: FrameClassDef[] = [
    {
      value: 1,
      labelKey: 'frame.quad',
      ascii: '  X\n / \\\n|   |\n \\ /\n  X',
      types: [0, 1, 2, 3, 4, 5, 12, 13, 14, 19],
    },
    {
      value: 2,
      labelKey: 'frame.hexa',
      ascii: ' X   X\n  \\ /\n   O\n  / \\\n X   X\n  |  |\n  X  X',
      types: [0, 1, 3, 13, 14],
    },
    { value: 3, labelKey: 'frame.octa', ascii: 'X   X\n X X\n  O\n X X\nX   X', types: [0, 1, 2, 3, 13, 14, 15] },
    { value: 4, labelKey: 'frame.octaQuad', ascii: 'XX XX\n  O\nXX XX', types: [0, 1, 2, 3, 12, 14] },
    { value: 5, labelKey: 'frame.y6', ascii: ' X   X\n  \\ /\n   O\n   |\n   X', types: [10, 11] },
    { value: 7, labelKey: 'frame.tri', ascii: ' X\n |\n O\n/ \\\nX   X', types: [] },
    { value: 8, labelKey: 'frame.single', ascii: '  X\n  |\n  O', types: [] },
    { value: 9, labelKey: 'frame.coax', ascii: '  X\n  X\n  |\n  O', types: [] },
  ];

  // FRAME_TYPE @Values, ArduCopter/Parameters.cpp:233.
  const frameTypeNames: Record<number, string> = {
    0: '+',
    1: 'X',
    2: 'V',
    3: 'H',
    4: 'V-Tail',
    5: 'A-Tail',
    10: 'Y6B',
    11: 'Y6F',
    12: 'BetaFlight X',
    13: 'DJI X',
    14: 'CW X',
    15: 'I',
    19: 'Y4',
  };

  /* ── State ── */

  let selectedClass = $state(1);
  let selectedType = $state(1);

  /* ── Load current values from paramState (one-shot) ── */
  // paramState.list grows across multiple PARAM_BATCH frames during the
  // initial fetch (~10s, 700-1000 params). A naive $effect would re-fire
  // on every batch and clobber the user's selection mid-stream. Matches
  // the _loaded guard used by sibling panels (FlightModePanel, PidPanel).
  let _loaded = $state(false);
  $effect(() => {
    if (!paramsAvailable || _loaded) return;
    _loaded = true;
    selectedClass = getParam('FRAME_CLASS', 1);
    selectedType = getParam('FRAME_TYPE', 1);
  });

  let frameTypes = $derived(frameClasses.find((c) => c.value === selectedClass)?.types ?? []);
  let showTypeGrid = $derived(frameTypes.length > 0);

  function pickClass(fc: FrameClassDef) {
    selectedClass = fc.value;
    if (fc.types.length > 0 && !fc.types.includes(selectedType)) selectedType = fc.types[0];
  }

  let currentClassParam = $derived(getParam('FRAME_CLASS', -1));
  let currentTypeParam = $derived(getParam('FRAME_TYPE', -1));

  /* ── Write to FC ── */

  function writeFrame() {
    dispatch('param_set', undefined, { name: 'FRAME_CLASS', value: selectedClass });
    if (showTypeGrid) {
      dispatch('param_set', undefined, { name: 'FRAME_TYPE', value: selectedType });
    }
    addToast(t('frame.saved'), 'success');
  }
</script>

<div
  role="dialog"
  aria-modal="true"
  tabindex="-1"
  class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
  onclick={(e) => {
    if (e.target === e.currentTarget) onclose();
  }}
  onkeydown={(e) => {
    if (e.key === 'Escape') onclose();
  }}
>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[500px] max-h-[85vh] flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('frame.title')}</h2>
      <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label={t('error.close')}><X size={16} /></Button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4">
      {#if !paramsAvailable}
        <div class="p-4 rounded-lg bg-muted/50 border border-border/50 text-center">
          <p class="text-xs text-muted-foreground">{t('param.connectHint')}</p>
        </div>
      {:else}
        <!-- Current values -->
        <div class="flex items-center gap-2 mb-4 text-xs text-muted-foreground">
          <span class="font-semibold">{t('frame.current')}:</span>
          <span class="font-mono">FRAME_CLASS={currentClassParam}</span>
          <span class="font-mono">FRAME_TYPE={currentTypeParam}</span>
        </div>

        <!-- ════════════════════════════════════════════ -->
        <!-- Frame Class grid                              -->
        <!-- ════════════════════════════════════════════ -->
        <div class="mb-4">
          <p class="text-xs font-semibold text-foreground uppercase tracking-wider mb-2">{t('frame.class')}</p>
          <div class="grid grid-cols-4 gap-2">
            {#each frameClasses as fc (fc.value)}
              <button
                class="flex flex-col items-center p-3 rounded-lg border-2 transition-all cursor-pointer
                  {selectedClass === fc.value
                  ? 'border-primary bg-primary/10 shadow-sm'
                  : 'border-border/50 bg-muted/20 hover:border-muted-foreground/30 hover:bg-muted/40'}"
                onclick={() => pickClass(fc)}
              >
                <pre
                  class="text-[9px] leading-tight font-mono text-center mb-1.5
                  {selectedClass === fc.value ? 'text-primary' : 'text-muted-foreground/70'}">{fc.ascii}</pre>
                <span
                  class="text-[11px] font-medium
                  {selectedClass === fc.value ? 'text-primary' : 'text-foreground'}"
                >
                  {t(fc.labelKey)}
                </span>
                <span class="text-[9px] text-muted-foreground mt-0.5">={fc.value}</span>
              </button>
            {/each}
          </div>
        </div>

        <!-- ════════════════════════════════════════════ -->
        <!-- Frame Type grid (only for multi-rotor)        -->
        <!-- ════════════════════════════════════════════ -->
        {#if showTypeGrid}
          <div class="mb-4">
            <p class="text-xs font-semibold text-foreground uppercase tracking-wider mb-2">{t('frame.type')}</p>
            <div class="grid grid-cols-5 gap-2">
              {#each frameTypes as value (value)}
                <button
                  class="flex flex-col items-center p-2.5 rounded-lg border-2 transition-all cursor-pointer
                    {selectedType === value
                    ? 'border-primary bg-primary/10 shadow-sm'
                    : 'border-border/50 bg-muted/20 hover:border-muted-foreground/30 hover:bg-muted/40'}"
                  onclick={() => {
                    selectedType = value;
                  }}
                >
                  <span
                    class="text-xs font-bold font-mono mb-1
                    {selectedType === value ? 'text-primary' : 'text-muted-foreground'}"
                  >
                    {frameTypeNames[value]}
                  </span>
                  <span class="text-[9px] text-muted-foreground mt-0.5">={value}</span>
                </button>
              {/each}
            </div>
          </div>
        {/if}

        <!-- Write button -->
        <div class="flex justify-end pt-2">
          <Button
            variant="default"
            size="sm"
            class="h-8 text-xs px-6"
            onclick={writeFrame}
            disabled={!app.drone.connected}
          >
            {t('frame.write')}
          </Button>
        </div>
      {/if}
    </div>
  </div>
</div>
