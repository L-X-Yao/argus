import type { WSMessage, DroneState, DroneEvent } from './types';
import { updateState, addEvent, setWsConnected } from './stores.svelte';

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

function getWsUrl(): string {
  const loc = window.location;
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${loc.host}/ws`;
}

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
      else if (msg.type === 'event') addEvent(msg as DroneEvent);
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
