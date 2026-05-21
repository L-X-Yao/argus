import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const src = fs.readFileSync(path.resolve(__dirname, 'i18n.svelte.ts'), 'utf-8');

function extractKeys(section: string): Set<string> {
  const keys = new Set<string>();
  const re = /^\s+'([^']+)':/gm;
  let m;
  while ((m = re.exec(section)) !== null) keys.add(m[1]);
  return keys;
}

const parts = src.split(/^const en:/m);
const zhSection = parts[0];
const enSection = parts[1] || '';
const zhKeys = extractKeys(zhSection);
const enKeys = extractKeys(enSection);

describe('i18n key parity', () => {
  it('every ZH key has an EN key', () => {
    const missing = [...zhKeys].filter(k => !enKeys.has(k));
    expect(missing, `ZH keys missing from EN: ${missing.join(', ')}`).toEqual([]);
  });

  it('every EN key has a ZH key', () => {
    const extra = [...enKeys].filter(k => !zhKeys.has(k));
    expect(extra, `EN keys missing from ZH: ${extra.join(', ')}`).toEqual([]);
  });

  it('has at least 300 keys', () => {
    expect(zhKeys.size).toBeGreaterThan(300);
    expect(enKeys.size).toBeGreaterThan(300);
  });
});
