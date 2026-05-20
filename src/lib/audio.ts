import { app } from './stores.svelte';

let audioCtx: AudioContext | null = null;

function getCtx(): AudioContext {
  if (!audioCtx) audioCtx = new AudioContext();
  return audioCtx;
}

export function beep(freq: number, dur: number, count = 1, gap = 100) {
  if (app.audioMuted) return;
  const ctx = getCtx();
  let t = ctx.currentTime;
  for (let i = 0; i < count; i++) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = freq;
    gain.gain.value = 0.15;
    osc.start(t);
    osc.stop(t + dur / 1000);
    t += (dur + gap) / 1000;
  }
}

export function speak(text: string) {
  if (!app.voiceEnabled || !('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'zh-CN';
  u.rate = 1.2;
  u.volume = 0.8;
  speechSynthesis.speak(u);
}

let prevArmed = false;
let prevConnected = false;
let linkLostBeepT = 0;
let linkLostSpoken = false;
let prevMode = '';
let batWarnLevel = 0;
let prevWp = 0;
let altPrev = 0;
let altInit = false;
let descentNext = Infinity;
let ascentIdx = 0;

const RTL_MODES = ['返航', '旋翼返航', '智能返航', '降落', '旋翼降落'];
const DESCENT_THRESHOLDS = [50, 40, 30, 20, 10, 8, 6, 4, 2];
const ASCENT_THRESHOLDS = [10, 20, 30, 50, 100];

export function checkAlerts(connected: boolean, armed: boolean, remaining: number, linkAge: number) {
  if (armed && !prevArmed) {
    beep(880, 200, 2);
    speak('已解锁');
  }
  if (!armed && prevArmed) {
    beep(440, 300, 1);
    speak('已锁定');
  }
  prevArmed = armed;

  if (!connected && prevConnected) {
    beep(200, 1000, 3, 200);
    speak('飞控连接已断开');
  }
  prevConnected = connected;

  const mode = app.drone.mode;
  if (mode && prevMode && mode !== prevMode) {
    if (RTL_MODES.some(m => mode.includes(m))) beep(440, 300, 2, 150);
    speak(`已切换${mode}`);
  }
  prevMode = mode;

  if (remaining >= 0) {
    if (remaining < 10 && batWarnLevel < 3 && armed) {
      beep(200, 800, 5, 100);
      speak('电量严重不足，请立即返航');
      batWarnLevel = 3;
    } else if (remaining < 20 && batWarnLevel < 2) {
      beep(300, 500, 3, 200);
      speak('低电量警告');
      batWarnLevel = 2;
    } else if (remaining < 30 && batWarnLevel < 1 && armed) {
      beep(400, 400, 2, 200);
      speak('电量百分之三十，注意返航');
      batWarnLevel = 1;
    }
  }
  if (remaining >= 30 || remaining < 0) batWarnLevel = 0;

  if (connected && linkAge > 3 && Date.now() - linkLostBeepT > 5000) {
    beep(200, 800, 1);
    linkLostBeepT = Date.now();
    if (!linkLostSpoken) { speak('链路延迟过高'); linkLostSpoken = true; }
  }
  if (connected && linkAge >= 0 && linkAge < 2) linkLostSpoken = false;

  checkAltCallouts(app.drone.alt_rel, armed);

  const wp = app.drone.wp;
  if (wp > prevWp && prevWp >= 2 && armed) {
    speak(`航点${prevWp - 1}`);
  }
  prevWp = armed ? wp : 0;
}

function checkAltCallouts(alt: number, armed: boolean) {
  if (!armed) {
    descentNext = Infinity;
    ascentIdx = 0;
    altInit = false;
    altPrev = 0;
    return;
  }
  if (!altInit) {
    altPrev = alt;
    descentNext = DESCENT_THRESHOLDS.find(t => t <= alt) ?? 0;
    ascentIdx = ASCENT_THRESHOLDS.findIndex(t => t > alt);
    if (ascentIdx < 0) ascentIdx = ASCENT_THRESHOLDS.length;
    altInit = true;
    return;
  }
  const climbing = alt > altPrev + 0.2;
  const descending = alt < altPrev - 0.2;
  altPrev = alt;

  if (climbing && ascentIdx < ASCENT_THRESHOLDS.length && alt >= ASCENT_THRESHOLDS[ascentIdx] - 0.5) {
    speak(`${ASCENT_THRESHOLDS[ascentIdx]}米`);
    ascentIdx++;
  }
  if (ascentIdx > 0 && alt < ASCENT_THRESHOLDS[ascentIdx - 1] - 5) {
    ascentIdx = ASCENT_THRESHOLDS.findIndex(t => t > alt);
    if (ascentIdx < 0) ascentIdx = ASCENT_THRESHOLDS.length;
  }

  if (alt > descentNext + 3) descentNext = Infinity;
  if (descending) {
    for (const t of DESCENT_THRESHOLDS) {
      if (alt <= t + 0.5 && t < descentNext) {
        speak(`${t}米`);
        descentNext = t;
        break;
      }
    }
  }
}
