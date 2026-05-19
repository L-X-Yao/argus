<script lang="ts">
  import { app } from '../lib/stores.svelte';

  const panels: { key: keyof typeof toggles; label: string; hotkey: string }[] = [
    { key: 'showParams', label: '参数', hotkey: 'P' },
    { key: 'showRc', label: '遥控', hotkey: 'I' },
    { key: 'showVibe', label: '振动', hotkey: 'V' },
    { key: 'showServo', label: '舵机', hotkey: 'O' },
    { key: 'showSurvey', label: '测绘', hotkey: '' },
    { key: 'showFence', label: '围栏', hotkey: '' },
  ];

  const toggles = {
    showParams: () => app.showParams = !app.showParams,
    showRc: () => app.showRc = !app.showRc,
    showVibe: () => app.showVibe = !app.showVibe,
    showServo: () => app.showServo = !app.showServo,
    showSurvey: () => app.showSurvey = !app.showSurvey,
    showFence: () => app.showFence = !app.showFence,
  };

  function isActive(key: string): boolean {
    return (app as any)[key] === true;
  }
</script>

<div class="diag-toolbar">
  <span class="label">工具</span>
  {#each panels as p}
    <button class="diag-btn" class:active={isActive(p.key)} onclick={toggles[p.key]}
            title={p.hotkey ? `快捷键: ${p.hotkey}` : ''}>
      {p.label}
    </button>
  {/each}
  <button class="diag-btn" class:active={app.chartsOpen} onclick={() => app.chartsOpen = !app.chartsOpen}
          title="快捷键: C">图表</button>
</div>

<style>
  .diag-toolbar { display:flex; align-items:center; gap:4px; padding:4px 10px; background:var(--bg-panel); border-bottom:1px solid var(--border-color); }
  .label { font-size:11px; color:var(--text-dim); margin-right:4px; }
  .diag-btn { padding:3px 10px; background:var(--bg-card); border:1px solid var(--border-color); border-radius:4px; cursor:pointer; font-size:11px; color:var(--text-dim); font-weight:bold; }
  .diag-btn:hover { border-color:var(--text-accent); color:var(--text-accent); }
  .diag-btn.active { background:#1565c0; color:white; border-color:#1565c0; }
</style>
