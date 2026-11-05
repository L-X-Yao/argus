import { describe, it, expect, vi, afterEach } from 'vitest';
import { openSerial, serialReadLoop } from './serial';

// Like Chrome: a port cannot close while its stream is locked.
function fakePort() {
  const port = {
    readable: null as ReadableStream<Uint8Array> | null,
    writable: null as WritableStream<Uint8Array> | null,
    closed: false,
    getInfo: () => ({ usbVendorId: 0x1209, usbProductId: 0x5740 }),
    async open() {
      port.readable = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new Uint8Array([1, 2, 3]));
        },
      });
      port.writable = new WritableStream<Uint8Array>({ write: () => new Promise(() => {}) });
    },
    async close() {
      if (port.readable?.locked || port.writable?.locked) throw new TypeError('Cannot close a locked stream');
      port.closed = true;
    },
  };
  vi.stubGlobal('navigator', { serial: { requestPort: async () => port } });
  return port;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SerialConnection.close', () => {
  it('ends a running read loop and really closes the port', async () => {
    const port = fakePort();
    const conn = await openSerial(115200);
    const chunks: Uint8Array[] = [];
    const loop = serialReadLoop(conn, (c) => chunks.push(c));
    await vi.waitFor(() => expect(chunks.length).toBe(1));

    await conn.close();

    await expect(loop).resolves.toBeUndefined();
    expect(port.readable?.locked).toBe(false);
    expect(port.closed).toBe(true);
  });

  it('does not wait for a stalled write to drain', async () => {
    // A hung FC that is still enumerated never finishes draining, and that
    // used to leave Disconnect waiting for good.
    const port = fakePort();
    const conn = await openSerial(115200);
    port.closed = false;
    const stalled = conn._writer.write(new Uint8Array([1])).catch(() => {});
    await conn.close();
    expect(port.closed).toBe(true);
    void stalled;
  });

  it('closes a port whose read loop never started', async () => {
    const port = fakePort();
    const conn = await openSerial(115200);
    await conn.close();
    expect(port.closed).toBe(true);
  });
});
