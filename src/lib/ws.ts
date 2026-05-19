import type { WSMessage, DroneState, DroneEvent } from './types';
import { updateState, addEvent, setWsConnected, addToast, loadDownloadedMission } from './stores.svelte';
import { handleParamBatch, handleParamsComplete } from './paramStore.svelte';
import { setLogList, completeDownload } from './logStore.svelte';
import { getWsUrl } from './backend';

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectWs(): void {
  if (socket && socket.readyState <= 1) return;
  const ws = new WebSocket(getWsUrl());
  socket = ws;

  ws.onopen = () => {
    setWsConnected(true);
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };

  ws.onmessage = (ev) => {
    try {
      const msg: WSMessage = JSON.parse(ev.data);
      if (msg.type === 'state') updateState(msg as DroneState);
      else if (msg.type === 'event') {
        const ev = msg as DroneEvent;
        addEvent(ev);
        if (ev.text.includes('失控') || ev.text.includes('碰撞') || ev.text.includes('紧急'))
          addToast(ev.text, 'error', 8000);
        else if (ev.text.includes('已解锁'))
          addToast('飞控已解锁', 'warn', 5000);
        else if (ev.text.includes('已锁定') && !ev.text.includes('发送'))
          addToast('飞控已锁定', 'success', 4000);
        else if (ev.text.includes('任务确认') || ev.text.includes('围栏确认'))
          addToast(ev.text, ev.text.includes('成功') ? 'success' : 'error');
        else if (ev.text.includes('已连接'))
          addToast(ev.text, 'success');
        else if (ev.text.includes('已断开'))
          addToast('已断开连接', 'info');
        else if (ev.text.includes('低电量') || ev.text.includes('电量极低'))
          addToast(ev.text, 'error', 8000);
      }
      else if (msg.type === 'param_batch') handleParamBatch(msg.params);
      else if (msg.type === 'params_complete') handleParamsComplete();
      else if (msg.type === 'mission_downloaded') {
        loadDownloadedMission(msg.waypoints);
        addToast('已下载 ' + msg.waypoints.length + ' 个航点', 'success');
      }
      else if (msg.type === 'log_list') {
        setLogList(msg.logs);
        addToast('获取到 ' + msg.logs.length + ' 条机载日志', 'success');
      }
      else if (msg.type === 'log_complete') {
        completeDownload(msg.id, msg.data, msg.size);
        addToast('日志 #' + msg.id + ' 下载完成', 'success');
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
  }
}

export function sendConnect(port: string, baud: number): void {
  sendMessage({ type: 'connect', port, baud });
}

export function sendDisconnect(): void {
  sendMessage({ type: 'disconnect' });
}

export function sendCommand(cmd: string, param?: number, data?: Record<string, unknown>): void {
  sendMessage({ type: 'command', cmd, param, ...data });
}
