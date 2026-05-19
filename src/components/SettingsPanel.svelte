<script lang="ts">
  import { app, saveSettings } from '../lib/stores.svelte';
  let { onclose }: { onclose: () => void } = $props();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="overlay" onclick={onclose}>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="box" onclick={(e) => e.stopPropagation()}>
    <h3>设置</h3>
    <div class="row">
      <label for="s-alt">默认高度 (m)</label>
      <input id="s-alt" type="number" bind:value={app.defaultAlt} min="5" max="500" step="5"
             onchange={saveSettings} />
    </div>
    <div class="row">
      <label for="s-radius">围栏半径 (m)</label>
      <input id="s-radius" type="number" bind:value={app.geoRadius} min="0" max="10000" step="100"
             onchange={saveSettings} />
    </div>
    <div class="row">
      <label for="s-mute">声音提示</label>
      <button id="s-mute" class="toggle-btn" class:on={!app.audioMuted}
              onclick={() => { app.audioMuted = !app.audioMuted; saveSettings(); }}>
        {app.audioMuted ? '已关闭' : '已开启'}
      </button>
    </div>
    <div class="row">
      <label for="s-voice">语音播报</label>
      <button id="s-voice" class="toggle-btn" class:on={app.voiceEnabled}
              onclick={() => { app.voiceEnabled = !app.voiceEnabled; }}>
        {app.voiceEnabled ? '已开启' : '已关闭'}
      </button>
    </div>
    <div class="row">
      <label for="s-theme">深色主题</label>
      <button id="s-theme" class="toggle-btn" class:on={app.darkTheme}
              onclick={() => { app.darkTheme = !app.darkTheme; saveSettings(); }}>
        {app.darkTheme ? '深色' : '浅色'}
      </button>
    </div>
    <button class="close-btn" onclick={onclose}>关闭</button>
  </div>
</div>

<style>
  .overlay { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.6); z-index:9999; display:flex; align-items:center; justify-content:center; }
  .box { background:var(--bg-panel); border:2px solid var(--text-accent); border-radius:12px; padding:25px 35px; min-width:320px; }
  h3 { color:var(--text-accent); margin:0 0 15px; font-size:18px; }
  .row { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid var(--border); }
  label { font-size:14px; color:var(--text-dim); }
  input[type=number] { width:80px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); padding:5px 8px; border-radius:4px; font-size:14px; text-align:right; }
  .toggle-btn { padding:4px 12px; border-radius:4px; border:1px solid #555; cursor:pointer; font-size:13px; background:#37474f; color:#aaa; }
  .toggle-btn.on { background:#2e7d32; color:white; border-color:#4caf50; }
  .close-btn { margin-top:15px; width:100%; padding:8px; background:#37474f; color:var(--text-main); border:none; border-radius:4px; cursor:pointer; font-size:14px; }
</style>
