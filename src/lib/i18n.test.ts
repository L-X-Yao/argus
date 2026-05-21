import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = dirname(fileURLToPath(import.meta.url));

function extractKeys(file: string): Set<string> {
  const src = readFileSync(resolve(__dir, file), 'utf-8');
  const keys = new Set<string>();
  const re = /^\s+'([^']+)':/gm;
  let m;
  while ((m = re.exec(src)) !== null) keys.add(m[1]);
  return keys;
}

const zhKeys = extractKeys('locales/zh.ts');
const enKeys = extractKeys('locales/en.ts');

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
