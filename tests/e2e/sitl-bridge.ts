import type { Page } from '@playwright/test';
import net from 'node:net';
import { encodeFrame, encodeMissionRequestInt, encodeMissionRequestList, parseFrames } from '../../src/lib/mavlink';

/**
 * Stands in for navigator.serial and carries the bytes to ArduPilot SITL over
 * TCP, so the whole WebSerial stack above the port meets real firmware. Frames
 * from SITL are also read here, which gives the tests the firmware's own answer
 * rather than what the page made of it.
 */
export interface Bridge {
  acks: { command: number; result: number }[];
  texts: string[];
  missionSeq: () => number;
  logIds: number[];
  logDataFrames: () => number;
  /** How many items the FC holds in a store, asked over the bridge's own socket. */
  storeCount: (missionType: number) => Promise<number>;
  /** One stored item as the FC reads it back, asked the same way. */
  storeItem: (missionType: number, seq: number) => Promise<{ lat: number; lon: number; alt: number } | null>;
  /** Whether a message id has arrived from the FC. */
  seen: (msgId: number) => boolean;
  close: () => void;
}

export async function openBridge(page: Page, target: string): Promise<Bridge> {
  const [host, port] = target.split(':');
  const socket = net.connect(Number(port), host);
  await new Promise((ok, fail) => socket.once('connect', ok).once('error', fail));

  const acks: Bridge['acks'] = [];
  const texts: string[] = [];
  const logIds: number[] = [];
  let logDataFrames = 0;
  const storeCounts = new Map<number, number>();
  const storeItems = new Map<string, { lat: number; lon: number; alt: number }>();
  const seenIds = new Set<number>();
  let missionSeq = -1;
  let pending = new Uint8Array(0);
  let outgoing: number[] = [];
  let feeding = false;

  // One evaluate at a time, carrying everything that arrived during the last one.
  // Per chunk, the page fell seconds behind a sped-up SITL.
  const feed = async () => {
    if (feeding) return;
    feeding = true;
    while (outgoing.length > 0) {
      const bytes = outgoing;
      outgoing = [];
      await page
        .evaluate((b) => (window as unknown as { __sitlFeed: (b: number[]) => void }).__sitlFeed(b), bytes)
        .catch(() => {});
    }
    feeding = false;
  };

  await page.exposeFunction('__sitlWrite', (bytes: number[]) => void socket.write(Buffer.from(bytes)));
  socket.on('data', (chunk) => {
    const joined = new Uint8Array(pending.length + chunk.length);
    joined.set(pending);
    joined.set(chunk, pending.length);
    const { frames, remaining } = parseFrames(joined);
    pending = remaining;
    for (const f of frames) {
      seenIds.add(f.msgId);
      if (f.msgId === 77) {
        acks.push({ command: f.payload.getUint16(0, true), result: f.payloadLen > 2 ? f.payload.getUint8(2) : 0 });
      } else if (f.msgId === 42) {
        missionSeq = f.payload.getUint16(0, true);
      } else if (f.msgId === 44) {
        storeCounts.set(f.payloadLen > 4 ? f.payload.getUint8(4) : 0, f.payload.getUint16(0, true));
      } else if (f.msgId === 73) {
        // MISSION_ITEM_INT: mission_type is the last byte, and seq sits before it.
        const key = `${f.payloadLen > 37 ? f.payload.getUint8(37) : 0}:${f.payload.getUint16(28, true)}`;
        storeItems.set(key, {
          lat: f.payload.getInt32(16, true) / 1e7,
          lon: f.payload.getInt32(20, true) / 1e7,
          alt: f.payload.getFloat32(24, true),
        });
      } else if (f.msgId === 118) {
        logIds.push(f.payload.getUint16(8, true));
      } else if (f.msgId === 120) {
        logDataFrames += 1;
      } else if (f.msgId === 253) {
        const raw = new Uint8Array(f.payload.buffer, f.payload.byteOffset + 1, Math.max(0, f.payloadLen - 1));
        texts.push(Buffer.from(raw).toString('latin1').split('\0')[0]);
      }
    }
    outgoing.push(...chunk);
    void feed();
  });

  await page.addInitScript(() => {
    const w = window as unknown as { __sitlWrite: (b: number[]) => void; __sitlFeed: (b: number[]) => void };
    let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
    w.__sitlFeed = (b) => controller?.enqueue(new Uint8Array(b));
    const fake = {
      readable: null as ReadableStream<Uint8Array> | null,
      writable: null as WritableStream<Uint8Array> | null,
      getInfo: () => ({ usbVendorId: 0x1209, usbProductId: 0x5740 }),
      async open() {
        fake.readable = new ReadableStream<Uint8Array>({
          start(c) {
            controller = c;
          },
        });
        fake.writable = new WritableStream<Uint8Array>({
          write(chunk) {
            w.__sitlWrite(Array.from(chunk));
          },
        });
      },
      async close() {},
    };
    Object.defineProperty(navigator, 'serial', {
      configurable: true,
      value: { requestPort: async () => fake, getPorts: async () => [fake] },
    });
  });

  return {
    acks,
    texts,
    missionSeq: () => missionSeq,
    logIds,
    logDataFrames: () => logDataFrames,
    storeCount: async (missionType) => {
      storeCounts.delete(missionType);
      socket.write(encodeFrame(43, encodeMissionRequestList(1, 1, missionType), 255, 190, 0));
      for (let i = 0; i < 50 && !storeCounts.has(missionType); i++) {
        await new Promise((r) => setTimeout(r, 100));
      }
      return storeCounts.get(missionType) ?? -1;
    },
    storeItem: async (missionType, seq) => {
      const key = `${missionType}:${seq}`;
      storeItems.delete(key);
      socket.write(encodeFrame(51, encodeMissionRequestInt(1, 1, seq, missionType), 255, 190, 0));
      for (let i = 0; i < 50 && !storeItems.has(key); i++) {
        await new Promise((r) => setTimeout(r, 100));
      }
      return storeItems.get(key) ?? null;
    },
    seen: (msgId) => seenIds.has(msgId),
    close: () => socket.destroy(),
  };
}

/** Clicks USB the way a user does. Loads the page twice: on a cold start Vite reloads it once it has bundled the dependencies. */
export async function connectUsb(page: Page) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.locator('button', { hasText: /^USB$/ }).click();
}

/** Reads a field of app.drone. Needs the Vite dev server: the module must be the page's own. */
export const droneField = <T = unknown>(page: Page, key: string): Promise<T> =>
  page.evaluate(async (k) => {
    const url = '/src/lib/stores.svelte.ts';
    const { app } = await import(/* @vite-ignore */ url);
    return app.drone[k];
  }, key);

/** Runs a command the way the UI does, through transport.dispatch. */
export const dispatchCmd = (page: Page, name: string, param?: number, data?: Record<string, unknown>) =>
  page.evaluate(
    async ([n, p, d]) => {
      const url = '/src/lib/transport.ts';
      const { dispatch } = await import(/* @vite-ignore */ url);
      dispatch(n, p ?? undefined, d ?? undefined);
    },
    [name, param ?? null, data ?? null] as const,
  );
