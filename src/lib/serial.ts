/**
 * WebSerial connection layer.
 *
 * Wraps the Web Serial API to provide a simple open/read/write/close
 * interface for connecting to a flight controller via USB.
 */

export interface SerialConnection {
  readable: ReadableStream<Uint8Array>;
  writable: WritableStream<Uint8Array>;
  _writer: WritableStreamDefaultWriter<Uint8Array>;
  _reader: ReadableStreamDefaultReader<Uint8Array> | null;
  _readLoop: Promise<void> | null;
  close(): Promise<void>;
  info: { usbVendorId?: number; usbProductId?: number };
}

export function isWebSerialSupported(): boolean {
  return typeof navigator !== 'undefined' && 'serial' in navigator;
}

const BAUD_RATES = [57600, 115200, 921600, 460800, 230400] as const;
export type BaudRate = (typeof BAUD_RATES)[number];
export { BAUD_RATES };

const KNOWN_FC_FILTERS: SerialPortFilter[] = [
  { usbVendorId: 0x1209 }, // STM32 bootloader (generic)
  { usbVendorId: 0x0483 }, // STMicroelectronics
  { usbVendorId: 0x26ac }, // 3DRobotics / Pixhawk
  { usbVendorId: 0x2dae }, // Holybro
  { usbVendorId: 0x3162 }, // CubePilot
  { usbVendorId: 0x2341 }, // Arduino (for testing)
];

/**
 * Prompt the user to select a serial port and open it.
 *
 * Returns a SerialConnection object with readable/writable streams.
 * The caller is responsible for reading from the stream and calling close().
 */
export async function openSerial(baudRate: number = 115200): Promise<SerialConnection> {
  if (!isWebSerialSupported()) throw new Error('WebSerial not supported');

  const port = await navigator.serial!.requestPort({ filters: KNOWN_FC_FILTERS });
  await port.open({ baudRate, bufferSize: 4096 });

  const readable = port.readable as ReadableStream<Uint8Array>;
  const writable = port.writable as WritableStream<Uint8Array>;
  const info = port.getInfo();
  const writer = writable.getWriter();

  const conn: SerialConnection = {
    readable,
    writable,
    _writer: writer,
    _reader: null,
    _readLoop: null,
    info: { usbVendorId: info.usbVendorId, usbProductId: info.usbProductId },
    async close() {
      // serialReadLoop holds the stream's only reader, and port.close() rejects
      // while the stream is locked. Cancel that reader and wait for the loop to
      // release the lock, or the port stays open and frames keep arriving.
      try {
        await conn._reader?.cancel();
      } catch {}
      await conn._readLoop;
      // Not writer.close(): that waits for the writes to drain, which a hung FC
      // never does. port.close() aborts them, but needs the lock released.
      writer.releaseLock();
      try {
        await port.close();
      } catch {}
    },
  };
  return conn;
}

/**
 * Write data to a serial connection.
 *
 * Uses the connection's persistent writer — safe to call concurrently;
 * the Streams API queues writes internally.
 */
export async function serialWrite(conn: SerialConnection, data: Uint8Array): Promise<void> {
  await conn._writer.write(data);
}

/**
 * Read loop — reads from serial port and calls onData for each chunk.
 * Returns when the port is closed or an error occurs.
 */
export function serialReadLoop(conn: SerialConnection, onData: (chunk: Uint8Array) => void): Promise<void> {
  const reader = conn.readable.getReader();
  conn._reader = reader;
  const loop = (async () => {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value) onData(value);
      }
    } catch (e: unknown) {
      if (!(e instanceof Error) || e.name !== 'AbortError') throw e;
    } finally {
      conn._reader = null;
      reader.releaseLock();
    }
  })();
  conn._readLoop = loop.catch(() => {});
  return loop;
}
