// backend/mcp_server.py against the client of the official MCP TypeScript SDK, the one
// Claude Desktop and Claude Code are built on. Not in package.json: CI installs a pinned SDK
// into a folder of its own, copies this file there, and runs it (ci.yml, job check):
//
//   node mcp_sdk_check.mjs <repository> <python>
//
// No Argus runs: the tools answer that it cannot be reached, which is a tool result like any.
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const [repo, python] = process.argv.slice(2);
if (!repo || !python) {
  console.error('usage: node mcp_sdk_check.mjs <repository> <python>');
  process.exit(2);
}

const failures = [];
const check = (what, ok, detail = '') => {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${what}${detail ? `  ${detail}` : ''}`);
  if (!ok) failures.push(what);
};

const transport = new StdioClientTransport({
  command: python,
  args: ['-m', 'backend.mcp_server'],
  cwd: repo,
  // Port 9 (discard): nothing of Argus answers there.
  env: { ...process.env, ARGUS_URL: 'http://127.0.0.1:9' },
  stderr: 'ignore',
});
const client = new Client({ name: 'argus-sdk-check', version: '1.0.0' });

try {
  await client.connect(transport);
  const server = client.getServerVersion();
  check('the handshake names the server', server?.name === 'argus-gcs', JSON.stringify(server));
  check('it offers tools', client.getServerCapabilities()?.tools !== undefined);
  check('it gives instructions', typeof client.getInstructions() === 'string' && client.getInstructions().length > 0);

  const { tools } = await client.listTools();
  const names = tools.map((t) => t.name);
  check(
    'the tools, as the SDK reads them',
    JSON.stringify(names) ===
      JSON.stringify([
        'get_status',
        'get_mission',
        'get_parameters',
        'propose_mission',
        'propose_parameters',
        'propose_flight_command',
        'check_proposal',
        'withdraw_proposal',
      ]),
    names.join(', '),
  );

  const status = await client.callTool({ name: 'get_status', arguments: {} });
  check('a call with no Argus is a tool error the model reads', status.isError === true, status.content?.[0]?.text);
  check('which says what to do', /Start Argus/.test(status.content?.[0]?.text ?? ''));

  const none = await client.callTool({ name: 'check_proposal', arguments: { proposal: 'p-none' } });
  check('a proposal this server never made', none.isError === true && /No proposal/.test(none.content?.[0]?.text ?? ''));

  const bad = await client.callTool({ name: 'propose_parameters', arguments: { values: { BATT_CAPACITY: 'large' } } });
  check('arguments are checked before anything is asked', bad.isError === true && /must be a number/.test(bad.content?.[0]?.text ?? ''));

  let unknown = null;
  try {
    await client.callTool({ name: 'arm', arguments: {} });
  } catch (e) {
    unknown = e;
  }
  check('an unknown tool is a protocol error', unknown !== null, String(unknown?.message ?? ''));

  await client.ping();
  check('ping', true);
} catch (e) {
  check('the session', false, e instanceof Error ? e.stack : String(e));
} finally {
  await client.close().catch(() => {});
}

console.log(`${failures.length} failed`);
process.exit(failures.length ? 1 : 0);
