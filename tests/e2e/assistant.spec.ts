import { test, expect, type Page } from '@playwright/test';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { connectSimulator, disconnectIfConnected } from './helpers';

// The AI assistant end to end: backend/mcp_server.py as an MCP client starts it, the backend
// and its simulator, and the page, which answers and asks the operator. Needs the backend on
// 8100 with --sim, as the other backend specs.

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

type Json = Record<string, any>;

/** The plainest MCP client: JSON-RPC lines on the server's stdin and stdout. */
class McpClient {
  private proc: ChildProcessWithoutNullStreams;
  private buffer = '';
  private waiting = new Map<number, (msg: Json) => void>();
  private nextId = 1;

  constructor() {
    this.proc = spawn('python', ['-m', 'backend.mcp_server'], {
      cwd: repoRoot,
      env: { ...process.env, ARGUS_URL: 'http://127.0.0.1:8100' },
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

let mcp: McpClient;

test.describe('AI assistant', () => {
  test.beforeEach(async ({ page }) => {
    await connectSimulator(page);
    mcp = new McpClient();
    await mcp.start();
  });

  test.afterEach(async ({ page }) => {
    mcp.close();
    await disconnectIfConnected(page);
  });

  async function dialog(page: Page) {
    const box = page.getByTestId('assistant-dialog');
    await expect(box).toBeVisible({ timeout: 10000 });
    return box;
  }

  test('the page shows it is there, and answers what it shows', async ({ page }) => {
    await expect(page.getByTestId('assistant-present')).toBeVisible({ timeout: 10000 });
    const result = await mcp.call('get_status');
    expect(result.isError).toBe(false);
    expect(result.structuredContent).toMatchObject({ link: 'backend', connected: true, armed: false });
    expect(result.structuredContent.position.lat).toBeCloseTo(34.2583, 2);
  });

  /** A proposal's id, once the page has put it before the operator. */
  async function propose(name: string, args: Json): Promise<string> {
    const result = await mcp.call(name, args);
    expect(result.isError).toBe(false);
    expect(result.structuredContent.state).toBe('waiting');
    return result.structuredContent.proposal;
  }

  const check = async (proposal: string) =>
    (await mcp.call('check_proposal', { proposal, wait_seconds: 30 })).structuredContent;

  test('a proposed mission is drawn, and uploaded only once the operator approves it', async ({ page }) => {
    const proposal = await propose('propose_mission', {
      waypoints: [
        { lat: 34.2593, lon: 108.9425, alt: 20 },
        { lat: 34.2593, lon: 108.944, alt: 25, delay: 5, speed: 3 },
        { lat: 34.2583, lon: 108.944, alt: 25, type: 'loiter_time', loiter_param: 7 },
      ],
      takeoff_alt: 12,
      reason: 'A small square north-east of home',
    });
    const box = await dialog(page);
    await expect(box).toContainText('A small square north-east of home');
    await expect(box.locator('tbody tr')).toHaveCount(3);
    // What the upload does besides flying there is in the table too.
    await expect(box.locator('tbody tr').nth(1)).toContainText(/停留 5 秒|hold 5 s/);
    await expect(box.locator('tbody tr').nth(1)).toContainText('3 m/s');
    await expect(box.locator('tbody tr').nth(2)).toContainText(/盘旋 7 秒|circle 7 s/);
    await expect(page.locator('path.assistant-preview')).toHaveCount(1);
    // Nothing has changed yet: the plan is what it was, and the proposal waits.
    expect((await mcp.call('get_mission')).structuredContent.waypoints).toHaveLength(0);
    expect((await mcp.call('check_proposal', { proposal, wait_seconds: 0 })).structuredContent.state).toBe('waiting');

    await page.getByTestId('assistant-approve').click();
    expect(await check(proposal)).toEqual({
      proposal,
      state: 'done',
      result: { uploaded_waypoints: 3, takeoff_alt_m: 12 },
    });
    await expect(box).toBeHidden();
    await expect(page.locator('path.assistant-preview')).toHaveCount(0);
    expect((await mcp.call('get_mission')).structuredContent.waypoints).toHaveLength(3);
  });

  test('a declined proposal changes nothing, and the assistant is told', async ({ page }) => {
    const proposal = await propose('propose_mission', { waypoints: [{ lat: 34.26, lon: 108.94, alt: 30 }] });
    await dialog(page);
    await page.getByTestId('assistant-decline').click();
    expect(await check(proposal)).toMatchObject({ proposal, state: 'declined' });
    expect((await mcp.call('get_mission')).structuredContent.waypoints).toHaveLength(0);
  });

  test('parameters approved come back as the flight controller confirms them', async ({ page }) => {
    await page.locator('nav button', { hasText: /参数|Params/ }).first().click();
    await page.locator('button', { hasText: /读取|Read/ }).first().click();
    await expect(page.locator('input[type="text"]').first()).toBeVisible({ timeout: 15000 });

    const before = await mcp.call('get_parameters', { names: ['WPNAV_SPEED'] });
    expect(before.structuredContent.values).toEqual({ WPNAV_SPEED: 500 });

    const proposal = await propose('propose_parameters', {
      values: { WPNAV_SPEED: 650 },
      reason: 'Faster between waypoints',
    });
    const box = await dialog(page);
    await expect(box).toContainText('WPNAV_SPEED');
    await expect(box).toContainText('650');
    await page.getByTestId('assistant-approve').click();
    expect(await check(proposal)).toEqual({ proposal, state: 'done', result: { values: { WPNAV_SPEED: 650 } } });

    // Put it back for the specs after this one, the same way.
    const back = await propose('propose_parameters', { values: { WPNAV_SPEED: 500 } });
    await (await dialog(page)).getByTestId('assistant-approve').click();
    expect((await check(back)).state).toBe('done');
  });

  test('a proposal the assistant withdraws leaves the page', async ({ page }) => {
    const proposal = await propose('propose_mission', { waypoints: [{ lat: 34.26, lon: 108.94, alt: 30 }] });
    await dialog(page);
    const withdrawn = await mcp.call('withdraw_proposal', { proposal });
    expect(withdrawn.structuredContent).toMatchObject({ proposal, state: 'withdrawn' });
    await expect(page.getByTestId('assistant-dialog')).toBeHidden({ timeout: 10000 });
    expect((await mcp.call('get_mission')).structuredContent.waypoints).toHaveLength(0);
  });
});
