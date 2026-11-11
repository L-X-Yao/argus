import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// An MCP client for the e2e specs: backend/mcp_server.py, started as Claude Desktop starts it.

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export type Json = Record<string, any>;

/** The plainest MCP client: JSON-RPC lines on the server's stdin and stdout. */
export class McpClient {
  private proc: ChildProcessWithoutNullStreams;
  private buffer = '';
  private waiting = new Map<number, (msg: Json) => void>();
  private nextId = 1;

  /** For the Argus at url: the backend of the main specs when left out. */
  constructor(url = 'http://127.0.0.1:8100') {
    this.proc = spawn('python', ['-m', 'backend.mcp_server'], {
      cwd: repoRoot,
      env: { ...process.env, ARGUS_URL: url },
    });
    this.proc.stdout.setEncoding('utf8');
    this.proc.stdout.on('data', (chunk: string) => {
      this.buffer += chunk;
      let end: number;
      while ((end = this.buffer.indexOf('\n')) >= 0) {
        const line = this.buffer.slice(0, end);
        this.buffer = this.buffer.slice(end + 1);
        if (!line.trim()) continue;
        const msg = JSON.parse(line);
        this.waiting.get(msg.id)?.(msg);
        this.waiting.delete(msg.id);
      }
    });
  }

  private send(msg: Json) {
    this.proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', ...msg }) + '\n');
  }

  request(method: string, params: Json = {}): Promise<Json> {
    const id = this.nextId++;
    const answer = new Promise<Json>((resolve) => this.waiting.set(id, resolve));
    this.send({ id, method, params });
    return answer;
  }

  async start() {
    const init = await this.request('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'argus-e2e', version: '1' },
    });
    this.send({ method: 'notifications/initialized' });
    return init;
  }

  /** The tools/call result. */
  async call(name: string, args: Json = {}): Promise<Json> {
    return (await this.request('tools/call', { name, arguments: args })).result;
  }

  close() {
    this.proc.stdin.end();
    this.proc.kill();
  }
}
