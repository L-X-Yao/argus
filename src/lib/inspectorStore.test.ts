import { describe, it, expect } from 'vitest';
import { inspectorState, updateInspector, appendConsole } from './inspectorStore.svelte';

describe('updateInspector', () => {
  it('updates messages when not paused', () => {
    inspectorState.paused = false;
    const msgs = [{ id: 0, name: 'HEARTBEAT', hz: 1, count: 10, size: 9, last_fields: {} }];
    updateInspector(msgs);
    expect(inspectorState.messages.length).toBe(1);
    expect(inspectorState.messages[0].name).toBe('HEARTBEAT');
  });

  it('does not update when paused', () => {
    inspectorState.paused = false;
    updateInspector([{ id: 0, name: 'A', hz: 1, count: 1, size: 1, last_fields: {} }]);
    inspectorState.paused = true;
    updateInspector([{ id: 1, name: 'B', hz: 2, count: 2, size: 2, last_fields: {} }]);
    expect(inspectorState.messages[0].name).toBe('A');
  });
});

describe('appendConsole', () => {
  it('appends lines', () => {
    inspectorState.consoleLines = [];
    appendConsole('line1\nline2\n');
    expect(inspectorState.consoleLines).toContain('line1');
    expect(inspectorState.consoleLines).toContain('line2');
  });

  it('trims to 500 when over 1000', () => {
    inspectorState.consoleLines = [];
    for (let i = 0; i < 1001; i++) {
      inspectorState.consoleLines.push(`line${i}`);
    }
    appendConsole('overflow');
    expect(inspectorState.consoleLines.length).toBeLessThanOrEqual(502);
  });

  it('skips empty lines', () => {
    inspectorState.consoleLines = [];
    appendConsole('\n\n\n');
    expect(inspectorState.consoleLines.length).toBe(0);
  });
});
