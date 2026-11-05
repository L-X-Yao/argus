/**
 * WebSerial connection layer.
 *
 * Wraps the Web Serial API to provide a simple open/read/write/close
 * interface for connecting to a flight controller via USB.
 */

export interface SerialConnection {
  readonly readable: ReadableStream<Uint8Array> | null;
  writable: WritableStream<Uint8Array>;
  _writer: WritableStreamDefaultWriter<Uint8Array>;
  _reader: ReadableStreamDefaultReader<Uint8Array> | null;
  _readLoop: Promise<void> | null;
  _closing: boolean;
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

  const writable = port.writable as WritableStream<Uint8Array>;
  const info = port.getInfo();
  const writer = writable.getWriter();

  const conn: SerialConnection = {
    // Not a captured value: the port replaces this stream after a read error.
    get readable() {
      return port.readable as ReadableStream<Uint8Array> | null;
    },
    writable,
    _writer: writer,
    _reader: null,
    _readLoop: null,
    _closing: false,
    info: { usbVendorId: info.usbVendorId, usbProductId: info.usbProductId },
    async close() {
      // serialReadLoop holds the stream's only reader, and port.close() rejects
      // while the stream is locked. Cancel that reader and wait for the loop to
      // release the lock, or the port stays open and frames keep arriving.
      conn._closing = true;
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

// The port stays open after these and offers a new stream (Web Serial spec).
// Treating them as fatal dropped the session, often right after connecting: a
// real FC's port reported a break as it opened.
const RECOVERABLE_READ_ERRORS = new Set(['BreakError', 'BufferOverrunError', 'FramingError', 'ParityError']);

/**
 * Read loop — reads from serial port and calls onData for each chunk.
 * Returns when the port is closed or an error occurs.
 */
export function serialReadLoop(conn: SerialConnection, onData: (chunk: Uint8Array) => void): Promise<void> {
  const loop = (async () => {
    let stream: ReadableStream<Uint8Array> | null;
    while (!conn._closing && (stream = conn.readable)) {
      const reader = stream.getReader();
      conn._reader = reader;
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) return;
          if (value) onData(value);
        }
      } catch (e: unknown) {
        const name = (e as { name?: string } | null)?.name ?? '';
        if (name === 'AbortError') return;
        if (!RECOVERABLE_READ_ERRORS.has(name)) throw e;
        console.warn('[Serial] recovered from read error', name);
      } finally {
        conn._reader = null;
        reader.releaseLock();
      }
    }
  })();
  conn._readLoop = loop.catch(() => {});
  return loop;
}
