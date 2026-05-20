import type { WSMessage } from './types';
import { app, updateState, addEvent, setWsConnected, addToast, loadDownloadedMission } from './stores.svelte';
import { handleParamBatch, handleParamsComplete } from './paramStore.svelte';
import { setLogList, completeDownload, updateDownloadProgress } from './logStore.svelte';
import { getWsUrl } from './backend';
import { onLocaleChange, getLocale, t } from './i18n.svelte';

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectWs(): void {
  if (socket && socket.readyState <= 1) return;
  const ws = new WebSocket(getWsUrl());
  socket = ws;

  ws.onopen = () => {
    setWsConnected(true);
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    sendMessage({ type: 'set_locale', locale: getLocale() });
    onLocaleChange((l) => sendMessage({ type: 'set_locale', locale: l }));
  };

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data) as WSMessage;
      switch (msg.type) {
        case 'state':
          updateState(msg);
          break;
        case 'event':
          addEvent(msg);
          if (msg.text.includes('失控') || msg.text.includes('碰撞') || msg.text.includes('紧急'))
            addToast(msg.text, 'error', 8000);
          else if (msg.text.includes('已解锁'))
            addToast(t('toast.armed'), 'warn', 5000);
          else if (msg.text.includes('已锁定') && !msg.text.includes('发送'))
            addToast(t('toast.disarmed'), 'success', 4000);
          else if (msg.text.includes('任务确认') || msg.text.includes('围栏确认')) {
            addToast(msg.text, msg.text.includes('成功') ? 'success' : 'error');
            if (msg.text.includes('围栏确认') && msg.text.includes('成功'))
              app.fenceUploaded = true;
          }
          else if (msg.text.includes('已连接'))
            addToast(msg.text, 'success');
          else if (msg.text.includes('已断开'))
            addToast(t('toast.disconnected'), 'info');
          else if (msg.text.includes('低电量') || msg.text.includes('电量极低'))
            addToast(msg.text, 'error', 8000);
          else if (msg.text.includes('指令应答') && msg.text.includes('失败'))
            addToast(msg.text, 'error', 5000);
          break;
        case 'param_batch':
          handleParamBatch(msg.params);
          break;
        case 'params_complete':
          handleParamsComplete();
          break;
        case 'mission_downloaded':
          loadDownloadedMission(msg.waypoints);
          addToast(t('toast.missionDown').replace('{n}', String(msg.waypoints.length)), 'success');
          break;
        case 'log_list':
          setLogList(msg.logs);
          addToast(t('toast.logList').replace('{n}', String(msg.logs.length)), 'success');
          break;
        case 'log_progress':
          updateDownloadProgress(msg.received, msg.total);
          break;
        case 'log_complete':
          completeDownload(msg.id, msg.data, msg.size);
          addToast(t('toast.logDone').replace('{n}', String(msg.id)), 'success');
          break;
      }
    } catch {}
  };

  ws.onclose = () => {
    setWsConnected(false);
    socket = null;
    scheduleReconnect();
  };

  ws.onerror = () => { ws.close(); };
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWs(); }, 2000);
}

export function sendMessage(msg: Record<string, unknown>): void {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg));
  } else if (msg.type === 'command') {
    addToast(t('toast.cmdNotSent'), 'error');
  }
}

export function sendConnect(port: string, baud: number, protocol: string = 'auto'): void {
  sendMessage({ type: 'connect', port, baud, protocol });
}

export function sendDisconnect(): void {
  sendMessage({ type: 'disconnect' });
}

export function sendCommand(cmd: string, param?: number, data?: Record<string, unknown>): void {
  sendMessage({ type: 'command', cmd, param, ...data });
}
