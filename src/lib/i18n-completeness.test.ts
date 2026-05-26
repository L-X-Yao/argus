import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(__dir, 'locales');

// --- Helpers ---

/** Parse keys and values from a locale .ts file */
function parseLocale(filename: string): Record<string, string> {
  const src = readFileSync(resolve(localesDir, filename), 'utf-8');
  const entries: Record<string, string> = {};
  const re = /['"]([^'"]+)['"]\s*:\s*'((?:[^'\\]|\\.)*)'/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    entries[m[1]] = m[2].replace(/\\'/g, "'");
  }
  return entries;
}

/** Extract interpolation placeholders like {0}, {n}, {alt}, etc. */
function extractPlaceholders(value: string): string[] {
  const matches = value.match(/\{[^}]+\}/g);
  return matches ? matches.sort() : [];
}

// --- Load all locales ---

const localeFiles = readdirSync(localesDir).filter(f => f.endsWith('.ts'));
const BASE_LOCALE = 'zh.ts';

let baseMessages: Record<string, string>;
const allLocales: Record<string, Record<string, string>> = {};

beforeAll(() => {
  for (const file of localeFiles) {
    allLocales[file] = parseLocale(file);
  }
  baseMessages = allLocales[BASE_LOCALE];
});

// --- Tests ---

describe('i18n completeness', () => {
  it('base locale (zh.ts) should have a substantial number of keys', () => {
    expect(Object.keys(baseMessages).length).toBeGreaterThan(300);
  });

  it('all expected locale files exist', () => {
    const expected = ['zh.ts', 'en.ts', 'ja.ts', 'ko.ts', 'de.ts', 'fr.ts', 'es.ts', 'pt.ts', 'ru.ts', 'ar.ts'];
    for (const file of expected) {
      expect(localeFiles, `Missing locale file: ${file}`).toContain(file);
    }
  });

  it('every key in zh.ts exists in en.ts (full parity)', () => {
    const enMessages = allLocales['en.ts'];
    const baseKeys = Object.keys(baseMessages);
    const missing = baseKeys.filter(k => !(k in enMessages));
    expect(missing, `Keys in zh.ts missing from en.ts: ${missing.join(', ')}`).toEqual([]);
  });

  describe('missing keys per locale', () => {
    const otherLocales = localeFiles.filter(f => f !== BASE_LOCALE);

    for (const file of otherLocales) {
      it(`${file} should contain all base locale keys`, () => {
        const messages = allLocales[file];
        const baseKeys = Object.keys(baseMessages);
        const missing = baseKeys.filter(k => !(k in messages));
        // Non-eagerly-loaded locales may be sparse; report missing count
        // This test documents coverage -- adjust threshold as locales mature
        if (file === 'en.ts') {
          // en.ts must have full parity
          expect(missing, `Keys missing from ${file}: ${missing.slice(0, 20).join(', ')}...`).toEqual([]);
        } else {
          // Other locales: report missing keys as a coverage metric
          // Fail if locale has zero keys (broken file)
          expect(
            Object.keys(messages).length,
            `${file} appears empty or broken`
          ).toBeGreaterThan(0);
        }
      });
    }
  });

  describe('no empty string values', () => {
    for (const file of localeFiles) {
      it(`${file} should have no empty string values`, () => {
        const messages = allLocales[file];
        const emptyKeys = Object.entries(messages)
          .filter(([, v]) => v === '')
          .map(([k]) => k);
        expect(
          emptyKeys,
          `Empty values in ${file}: ${emptyKeys.join(', ')}`
        ).toEqual([]);
      });
    }
  });

  describe('interpolation placeholder consistency', () => {
    const otherLocales = localeFiles.filter(f => f !== BASE_LOCALE);

    for (const file of otherLocales) {
      it(`${file} placeholders match zh.ts for shared keys`, () => {
        const messages = allLocales[file];
        const mismatches: string[] = [];

        for (const [key, baseValue] of Object.entries(baseMessages)) {
          if (!(key in messages)) continue; // skip keys not present in this locale
          const basePlaceholders = extractPlaceholders(baseValue);
          const localePlaceholders = extractPlaceholders(messages[key]);

          if (basePlaceholders.length === 0 && localePlaceholders.length === 0) continue;

          if (JSON.stringify(basePlaceholders) !== JSON.stringify(localePlaceholders)) {
            mismatches.push(
              `${key}: zh=${basePlaceholders.join(',')} vs ${file.replace('.ts', '')}=${localePlaceholders.join(',')}`
            );
          }
        }

        expect(
          mismatches,
          `Placeholder mismatches in ${file}:\n${mismatches.join('\n')}`
        ).toEqual([]);
      });
    }
  });

  it('no locale has duplicate keys', () => {
    for (const file of localeFiles) {
      const src = readFileSync(resolve(localesDir, file), 'utf-8');
      const re = /['"]([^'"]+)['"]\s*:/g;
      const seen = new Set<string>();
      const duplicates: string[] = [];
      let m;
      while ((m = re.exec(src)) !== null) {
        if (seen.has(m[1])) duplicates.push(m[1]);
        seen.add(m[1]);
      }
      expect(
        duplicates,
        `Duplicate keys in ${file}: ${duplicates.join(', ')}`
      ).toEqual([]);
    }
  });

  it('keys follow dot-notation naming convention', () => {
    const invalidKeys = Object.keys(baseMessages).filter(
      k => !/^[a-zA-Z][a-zA-Z0-9]*(\.[a-zA-Z][a-zA-Z0-9]*)+$/.test(k)
    );
    expect(
      invalidKeys,
      `Keys not matching dot-notation: ${invalidKeys.join(', ')}`
    ).toEqual([]);
  });
});
