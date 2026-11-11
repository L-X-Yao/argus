import { describe, it, expect } from 'vitest';
import { cssNumber, escHtml } from './html';

// These run without a DOM. tests/e2e/mission-files.spec.ts has the browser parse the result.
describe('escHtml', () => {
  it('leaves no markup in a value', () => {
    const out = escHtml('<img src=x onerror="alert(1)">');
    expect(out).toBe('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
    expect(out).not.toMatch(/[<>"']/);
  });

  it('cannot close the attribute it is written into', () => {
    expect(escHtml('0deg)" onmouseover="alert(1)')).not.toContain('"');
    expect(escHtml("' onmouseover='alert(1)")).not.toContain("'");
  });

  it('escapes an ampersand once', () => {
    expect(escHtml('a & b &lt;')).toBe('a &amp; b &amp;lt;');
  });

  it('takes what is not a string', () => {
    expect(escHtml(42.5)).toBe('42.5');
    expect(escHtml(null)).toBe('null');
    expect(escHtml(undefined)).toBe('undefined');
    expect(escHtml({ toString: () => '<b>' })).toBe('&lt;b&gt;');
  });
});

describe('cssNumber', () => {
  it('passes a number through', () => {
    expect(cssNumber(271.5)).toBe(271.5);
    expect(cssNumber(-0.25)).toBe(-0.25);
  });

  it('gives 0 for what is not a finite number, text that spells one included', () => {
    for (const value of ['90', '0deg);background:url(//host/x', NaN, Infinity, null, undefined, {}, [90]]) {
      expect(cssNumber(value)).toBe(0);
    }
  });
});
