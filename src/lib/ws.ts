import type { WSMessage } from './types';
import { app, updateState, addEvent, setWsConnected, addToast, loadDownloadedMission } from './stores.svelte';
import { handleParamBatch, handleParamsComplete, handleParamTimeout, clearParams } from './paramStore.svelte';
import { setLogList, completeDownload, updateDownloadProgress, appendLogChunk } from './logStore.svelte';
import { updateInspector, appendConsole } from './inspectorStore.svelte';
import { saveFlightRecord } from './flightDb';
import { getWsUrl } from './backend';
import { onLocaleChange, getLocale, t } from './i18n.svelte';

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;
let lastMessageTime = 0;
let staleCheckTimer: ReturnType<typeof setInterval> | null = null;

/**
 * JSON has no NaN and no infinity, so the backend sends each as null and lists in
 * `_nonfinite` where they were: a path, then which of the three it was. Put them back, so
 * that a value the FC sent as NaN reads NaN here as it does over USB. A null left in place
 * of a number would read as 0 in arithmetic and throw at the first toFixed.
 */
export function restoreNonFinite(msg: Record<string, unknown>): void {
  const marks = msg._nonfinite;
  if (!Array.isArray(marks)) return;
  delete msg._nonfinite;
  for (const mark of marks) {
    if (!Array.isArray(mark) || mark.length < 2) continue;
    const path = mark.slice(0, -1);
    const last = path.pop() as string | number;
    let at: unknown = msg;
    for (const key of path) {
      at = at !== null && typeof at === 'object' && Object.hasOwn(at, key) ? (at as never)[key] : undefined;
    }
    // Only where the backend left a null of its own, whatever the list says.
    if (at !== null && typeof at === 'object' && Object.hasOwn(at, last) && (at as never)[last] === null) {
      (at as Record<string | number, unknown>)[last] = Number(mark[mark.length - 1]);
    }
  }
}

export function connectWs(): void {
  if (socket && socket.readyState <= 1) return;
  const ws = new WebSocket(getWsUrl());
  socket = ws;

  ws.onopen = () => {
    setWsConnected(true);
    reconnectAttempts = 0;
    lastMessageTime = Date.now();
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (staleCheckTimer) clearInterval(staleCheckTimer);
    staleCheckTimer = setInterval(() => {
      if (lastMessageTime > 0 && Date.now() - lastMessageTime > 15000) {
        console.warn('[WS] connection stale, reconnecting');
        ws.close();
      }
    }, 5000);
    sendMessage({ type: 'set_locale', locale: getLocale() });
    onLocaleChange((l) => sendMessage({ type: 'set_locale', locale: l }));
  };

  ws.onmessage = (ev) => {
    lastMessageTime = Date.now();
    try {
      const msg = JSON.parse(ev.data) as WSMessage;
      restoreNonFinite(msg as unknown as Record<string, unknown>);
      switch (msg.type) {
        case 'state':
          if (msg.flight_summary && !app.drone.flight_summary) {
            const s = msg.flight_summary;
            // Delta states omit unchanged fields — fall back to current app
            // state for vtype/fw_version if they weren't included in this push.
            saveFlightRecord({
              date: new Date().toISOString(),
              duration: s.duration,
              maxAlt: s.max_alt,
              maxSpeed: s.max_speed,
              totalDist: s.total_dist,
              batUsed: s.bat_used,
              vtype: msg.vtype ?? app.drone.vtype,
              fw: msg.fw_version ?? app.drone.fw_version,
              eventCount: app.events.length,
            });
          }
          updateState(msg);
          break;
        case 'event':
          addEvent(msg);
          switch (msg.event_type) {
            case 'armed':
              addToast(t('toast.armed'), 'warn', 5000);
              break;
            case 'disarmed':
              addToast(t('toast.disarmed'), 'success', 4000);
              break;
            case 'connected':
              // Drop stale params from a previous vehicle so the new connection
              // starts with a clean slate.
              clearParams();
              addToast(msg.text, 'success');
              break;
            case 'disconnected':
            case 'link_lost':
              addToast(t('toast.disconnected'), 'info');
              break;
            case 'mission_ack_ok':
              addToast(msg.text, 'success');
              break;
            case 'mission_ack_fail':
              addToast(msg.text, 'error');
              break;
            case 'fence_ack_ok':
              addToast(msg.text, 'success');
              app.fenceUploaded = true;
              break;
            case 'fence_ack_fail':
              addToast(msg.text, 'error');
              break;
            case 'fence_clear_ok':
              addToast(msg.text, 'success');
              app.fenceUploaded = false;
              break;
            case 'fence_clear_fail':
              addToast(msg.text, 'error');
              break;
            case 'rally_ack_ok':
              addToast(msg.text, 'success');
              app.rallyUploaded = true;
              break;
            case 'rally_clear_ok':
              addToast(msg.text, 'success');
              app.rallyUploaded = false;
              break;
            case 'rally_ack_fail':
            case 'rally_clear_fail':
            case 'mission_clear_fail':
            case 'param_set_fail':
              addToast(msg.text, 'error');
              break;
            case 'cmd_ack_fail':
              addToast(msg.text, 'error', 5000);
              break;
            case 'rtl':
              addToast(msg.text, 'error', 8000);
              break;
            case 'unsupported_fc':
              addToast(msg.text, 'error', 10000);
              break;
            default:
              break;
          }
          break;
        case 'cmd_result':
          // sendCommand is fire-and-forget — a refused command (unsupported
          // autopilot gate, validation error, handler exception) would
          // otherwise fail with no visible feedback anywhere.
          if (msg.ok === false && msg.error) addToast(String(msg.error), 'error', 6000);
          break;
        case 'param_batch':
          handleParamBatch(msg.params);
          break;
        case 'params_complete':
          handleParamsComplete();
          break;
        case 'param_timeout':
          handleParamTimeout();
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
        case 'log_chunk':
          appendLogChunk(msg.id, msg.ofs, msg.data);
          break;
        case 'log_complete':
          completeDownload(msg.id, msg.data, msg.size);
          // truncated covers the count==0 EOF sentinel, stall give-up, and
          // detected frame-loss holes — a success toast over a corrupted
          // file would undo the honesty the backend just signalled.
          if (msg.truncated) {
            addToast(t('toast.logDoneTrunc').replace('{n}', String(msg.id)), 'error', 5000);
          } else {
            addToast(t('toast.logDone').replace('{n}', String(msg.id)), 'success');
          }
          break;
        case 'inspector':
          updateInspector(msg.messages);
          break;
        case 'console_output':
          appendConsole(msg.text);
          break;
      }
    } catch (e) {
      if (e instanceof SyntaxError) console.warn('[WS] parse error:', e.message);
    }
  };

  ws.onclose = () => {
    setWsConnected(false);
    socket = null;
    if (staleCheckTimer) {
      clearInterval(staleCheckTimer);
      staleCheckTimer = null;
    }
    scheduleReconnect();
  };

  ws.onerror = (ev) => {
    console.error('[WS] connection error', ev);
    ws.close();
  };
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectAttempts++;
  const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 30000);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, delay);
}

type OutgoingMessage =
  | { type: 'connect'; port: string; baud: number }
  | { type: 'disconnect' }
  | { type: 'set_locale'; locale: string }
  | { type: 'set_role'; role: string }
  | { type: 'command'; cmd: string; param?: number; [key: string]: unknown }
  | { type: 'request_handoff' }
  | { type: 'handoff_accept' };

export function sendMessage(msg: OutgoingMessage): void {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg));
  } else if (msg.type === 'command') {
    addToast(t('toast.cmdNotSent'), 'error');
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
