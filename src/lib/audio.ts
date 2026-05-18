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
let prevBatLow = false;
let linkLostBeepT = 0;

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

  const batLow = remaining >= 0 && remaining < 20;
  if (batLow && !prevBatLow) {
    beep(300, 500, 3, 200);
    speak('低电量警告');
  }
  prevBatLow = batLow;

  if (connected && linkAge > 3 && Date.now() - linkLostBeepT > 5000) {
    beep(200, 800, 1);
    linkLostBeepT = Date.now();
  }
}
