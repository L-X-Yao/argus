<script lang="ts">
  import { app, saveSettings } from '../lib/stores.svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, Volume2, VolumeOff, Mic, MicOff, Sun, Moon } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center" onclick={onclose}>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="bg-card border-2 border-primary rounded-xl p-6 min-w-[340px] shadow-2xl" onclick={(e) => e.stopPropagation()}>
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-bold text-primary">设置</h3>
      <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
    </div>

    <div class="flex justify-between items-center py-2.5 border-b border-border">
      <label for="s-alt" class="text-sm text-muted-foreground">默认高度 (m)</label>
      <input id="s-alt" type="number" bind:value={app.defaultAlt} min="5" max="500" step="5"
             onchange={saveSettings}
             class="w-20 h-8 px-2 text-right bg-input border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring/50" />
    </div>
    <div class="flex justify-between items-center py-2.5 border-b border-border">
      <label for="s-radius" class="text-sm text-muted-foreground">围栏半径 (m)</label>
      <input id="s-radius" type="number" bind:value={app.geoRadius} min="0" max="10000" step="100"
             onchange={saveSettings}
             class="w-20 h-8 px-2 text-right bg-input border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring/50" />
    </div>
    <div class="flex justify-between items-center py-2.5 border-b border-border">
      <label class="text-sm text-muted-foreground">声音提示</label>
      <Button variant={app.audioMuted ? 'secondary' : 'default'} size="sm" class="gap-1"
              onclick={() => { app.audioMuted = !app.audioMuted; saveSettings(); }}>
        {#if app.audioMuted}<VolumeOff size={14} />已关闭{:else}<Volume2 size={14} />已开启{/if}
      </Button>
    </div>
    <div class="flex justify-between items-center py-2.5 border-b border-border">
      <label class="text-sm text-muted-foreground">语音播报</label>
      <Button variant={app.voiceEnabled ? 'default' : 'secondary'} size="sm" class="gap-1"
              onclick={() => { app.voiceEnabled = !app.voiceEnabled; saveSettings(); }}>
        {#if app.voiceEnabled}<Mic size={14} />已开启{:else}<MicOff size={14} />已关闭{/if}
      </Button>
    </div>
    <div class="flex justify-between items-center py-2.5 border-b border-border">
      <label class="text-sm text-muted-foreground">深色主题</label>
      <Button variant={app.darkTheme ? 'default' : 'secondary'} size="sm" class="gap-1"
              onclick={() => { app.darkTheme = !app.darkTheme; saveSettings(); }}>
        {#if app.darkTheme}<Moon size={14} />深色{:else}<Sun size={14} />浅色{/if}
      </Button>
    </div>

    <Button variant="secondary" class="w-full mt-4" onclick={onclose}>关闭</Button>
  </div>
</div>
