<script lang="ts">
  import { paramState } from '../lib/paramStore.svelte';
  import { sendCommand } from '../lib/ws';
  import { addToast } from '../lib/stores.svelte';
  import type { Param } from '../lib/types';

  const DESC: Record<string, string> = {
    BATT_CAPACITY: '电池容量 (mAh)', BATT_MONITOR: '电池监测类型',
    ARMING_CHECK: '解锁检查掩码', ARMING_REQUIRE: '解锁方式',
    FS_THR_ENABLE: '油门失控保护', FS_THR_VALUE: '油门失控阈值 (PWM)',
    FS_GCS_ENABLE: '地面站失联保护',
    FS_BATT_ENABLE: '电池失控保护', FS_BATT_MAH: '电池mAh保护阈值',
    FS_BATT_VOLTAGE: '电池电压保护阈值 (V)',
    ATC_RAT_RLL_P: '横滚速率 P', ATC_RAT_RLL_I: '横滚速率 I', ATC_RAT_RLL_D: '横滚速率 D',
    ATC_RAT_PIT_P: '俯仰速率 P', ATC_RAT_PIT_I: '俯仰速率 I', ATC_RAT_PIT_D: '俯仰速率 D',
    ATC_RAT_YAW_P: '偏航速率 P', ATC_RAT_YAW_I: '偏航速率 I', ATC_RAT_YAW_D: '偏航速率 D',
    INS_GYRO_FILTER: '陀螺仪滤波频率 (Hz)', INS_ACCEL_FILTER: '加速度计滤波频率 (Hz)',
    INS_LOG_BAT_MASK: 'IMU 批量日志掩码',
    LOG_BITMASK: '日志记录掩码', LOG_BACKEND_TYPE: '日志后端类型',
    RC1_MAX: '通道1最大 (PWM)', RC1_MIN: '通道1最小 (PWM)', RC1_TRIM: '通道1中位 (PWM)',
    RC2_MAX: '通道2最大 (PWM)', RC2_MIN: '通道2最小 (PWM)', RC2_TRIM: '通道2中位 (PWM)',
    WPNAV_SPEED: '航线速度 (cm/s)', WPNAV_SPEED_UP: '上升速度 (cm/s)', WPNAV_SPEED_DN: '下降速度 (cm/s)',
    RTL_ALT: '返航高度 (cm)', RTL_SPEED: '返航速度 (cm/s, 0=默认)',
    FLTMODE1: '模式开关1', FLTMODE2: '模式开关2', FLTMODE3: '模式开关3',
    FLTMODE4: '模式开关4', FLTMODE5: '模式开关5', FLTMODE6: '模式开关6',
  };

  const CATS: { key: string; label: string; match: (n: string) => boolean }[] = [
    { key: 'battery', label: '电池', match: n => n.startsWith('BATT') || n === 'FS_BATT_ENABLE' || n === 'FS_BATT_MAH' || n === 'FS_BATT_VOLTAGE' },
    { key: 'failsafe', label: '保护', match: n => n.startsWith('FS_') },
    { key: 'pid', label: 'PID', match: n => n.startsWith('ATC_RAT_') },
    { key: 'nav', label: '导航', match: n => n.startsWith('WPNAV') || n.startsWith('RTL') },
    { key: 'rc', label: '遥控', match: n => /^RC\d/.test(n) },
    { key: 'modes', label: '模式', match: n => n.startsWith('FLTMODE') },
    { key: 'sensor', label: '传感器', match: n => n.startsWith('INS_') },
    { key: 'log', label: '日志', match: n => n.startsWith('LOG_') },
    { key: 'all', label: '全部', match: () => true },
  ];

  let category = $state('all');
  let search = $state('');
  let editName = $state<string | null>(null);
  let editValue = $state('');
  let modified = $state<Set<string>>(new Set());

  let filtered = $derived.by(() => {
    const cat = CATS.find(c => c.key === category)!;
    let list = paramState.list.filter(p => cat.match(p.name));
    if (search) {
      const q = search.toUpperCase();
      list = list.filter(p => p.name.includes(q) || (DESC[p.name] || '').includes(search));
    }
    return list;
  });

  let progress = $derived(paramState.total > 0 ? Math.round(paramState.received / paramState.total * 100) : 0);

  function startEdit(p: Param) {
    editName = p.name;
    editValue = fmtValue(p.value);
  }

  function cancelEdit() { editName = null; }

  function submitEdit() {
    if (!editName) return;
    const val = parseFloat(editValue);
    if (isNaN(val)) { addToast('无效数值', 'error'); return; }
    sendCommand('param_set', undefined, { name: editName, value: val });
    modified.add(editName);
    modified = new Set(modified);
    editName = null;
    addToast(`${editName} 已发送`, 'info', 2000);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') submitEdit();
    else if (e.key === 'Escape') cancelEdit();
  }

  function fmtValue(v: number): string {
    if (Number.isInteger(v) || Math.abs(v) >= 100) return v.toFixed(0);
    if (Math.abs(v) >= 1) return v.toFixed(2);
    return v.toFixed(4);
  }

  function requestAll() {
    sendCommand('param_request_all');
  }

  function saveParams() {
    sendCommand('param_save');
    addToast('参数文件已保存', 'success');
  }
</script>

<div class="param-panel">
  <div class="header">
    <h2>参数管理</h2>
    <div class="actions">
      <button class="btn-fetch" onclick={requestAll} disabled={paramState.fetching}>
        {paramState.fetching ? `读取中 ${progress}%` : '读取参数'}
      </button>
      {#if paramState.list.length > 0}
        <button class="btn-sm" onclick={saveParams}>保存文件</button>
        <span class="count">{paramState.list.length} 个参数</span>
      {/if}
    </div>
  </div>

  {#if paramState.fetching}
    <div class="progress-bar">
      <div class="progress-fill" style="width:{progress}%"></div>
    </div>
  {/if}

  {#if paramState.list.length > 0}
    <div class="tabs">
      {#each CATS as cat}
        <button class="tab" class:active={category === cat.key}
                onclick={() => category = cat.key}>{cat.label}</button>
      {/each}
    </div>

    <div class="search-row">
      <input type="text" placeholder="搜索参数名或说明..." bind:value={search} />
      <span class="match-count">{filtered.length} 项</span>
    </div>

    <div class="param-list">
      {#each filtered as p (p.name)}
        <div class="param-row" class:modified={modified.has(p.name)}>
          <div class="param-name">{p.name}</div>
          <div class="param-desc">{DESC[p.name] || ''}</div>
          {#if editName === p.name}
            <input class="param-input" type="text" bind:value={editValue}
                   onkeydown={onKeydown}
                   autofocus />
            <button class="btn-write" onclick={submitEdit}>写入</button>
            <button class="btn-cancel" onclick={cancelEdit}>取消</button>
          {:else}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="param-value" onclick={() => startEdit(p)}>{fmtValue(p.value)}</div>
          {/if}
        </div>
      {/each}
    </div>
  {:else if !paramState.fetching}
    <div class="empty">连接飞控后点击"读取参数"</div>
  {/if}
</div>

<style>
  .param-panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  .header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0; text-transform:uppercase; letter-spacing:1px; }
  .actions { display:flex; align-items:center; gap:6px; }
  .btn-fetch { padding:6px 14px; background:#1565c0; color:white; border:none; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold; }
  .btn-fetch:disabled { opacity:0.6; cursor:default; }
  .btn-sm { padding:4px 8px; background:#546e7a; color:white; border:none; border-radius:3px; cursor:pointer; font-size:11px; }
  .count { font-size:11px; color:var(--text-dim); }
  .progress-bar { height:4px; background:#333; border-radius:2px; margin:8px 0; overflow:hidden; }
  .progress-fill { height:100%; background:#4fc3f7; transition:width 0.3s; }
  .tabs { display:flex; gap:2px; margin:8px 0; flex-wrap:wrap; }
  .tab { padding:4px 10px; background:var(--bg-card); border:1px solid var(--border); border-radius:3px; cursor:pointer; font-size:11px; color:var(--text-dim); }
  .tab.active { background:#1565c0; color:white; border-color:#1565c0; }
  .search-row { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
  .search-row input { flex:1; padding:5px 8px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border); border-radius:4px; font-size:12px; }
  .match-count { font-size:11px; color:var(--text-dim); white-space:nowrap; }
  .param-list { max-height:400px; overflow-y:auto; }
  .param-row { display:flex; align-items:center; gap:6px; padding:4px 6px; border-bottom:1px solid var(--border); font-size:12px; }
  .param-row:hover { background:var(--bg-card); }
  .param-row.modified { background:rgba(255,152,0,0.08); }
  .param-name { width:160px; flex-shrink:0; font-weight:bold; font-family:monospace; font-size:11px; }
  .param-desc { flex:1; color:var(--text-dim); font-size:11px; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .param-value { width:90px; text-align:right; font-family:monospace; cursor:pointer; padding:2px 4px; border-radius:3px; }
  .param-value:hover { background:var(--bg-input); }
  .param-input { width:80px; padding:2px 4px; background:var(--bg-input); color:var(--text-main); border:1px solid #4fc3f7; border-radius:3px; font-family:monospace; font-size:12px; text-align:right; }
  .btn-write { padding:2px 6px; background:#2e7d32; color:white; border:none; border-radius:3px; cursor:pointer; font-size:10px; }
  .btn-cancel { padding:2px 6px; background:#546e7a; color:white; border:none; border-radius:3px; cursor:pointer; font-size:10px; }
  .empty { text-align:center; padding:20px; color:var(--text-dim); font-size:13px; }
</style>
