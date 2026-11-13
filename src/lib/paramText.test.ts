import { describe, it, expect } from 'vitest';
import { paramLine, parseParamNumber } from './paramText';

describe('parseParamNumber', () => {
  it('reads a decimal comma as the comma it is', () => {
    expect(parseParamNumber('1,5')).toBe(1.5);
    expect(parseParamNumber('-0,25')).toBe(-0.25);
    expect(parseParamNumber('+3,0')).toBe(3);
  });

  it('reads dot decimals and exponents, and ignores spaces around', () => {
    expect(parseParamNumber('1.5')).toBe(1.5);
    expect(parseParamNumber('1e3')).toBe(1000);
    expect(parseParamNumber(' 42 ')).toBe(42);
  });

  it('is NaN for what is no number', () => {
    expect(parseParamNumber('')).toBeNaN();
    expect(parseParamNumber('abc')).toBeNaN();
    expect(parseParamNumber('1,2,3')).toBeNaN();
    expect(parseParamNumber('Infinity')).toBeNaN();
    expect(parseParamNumber('1e999')).toBeNaN();
  });
});

describe('paramLine', () => {
  it('reads the name and the value of a file line', () => {
    expect(paramLine('WPNAV_SPEED,500')).toEqual(['WPNAV_SPEED', 500]);
    expect(paramLine('WPNAV_SPEED 500')).toEqual(['WPNAV_SPEED', 500]);
    expect(paramLine('WPNAV_SPEED\t500')).toEqual(['WPNAV_SPEED', 500]);
    expect(paramLine('WPNAV_SPEED;5,5')).toEqual(['WPNAV_SPEED', 5.5]);
    expect(paramLine('WPNAV_SPEED\t5,5')).toEqual(['WPNAV_SPEED', 5.5]);
  });

  it('is null for what is no parameter line', () => {
    expect(paramLine('')).toBeNull();
    expect(paramLine('# a comment')).toBeNull();
    expect(paramLine('ONLY_NAME')).toBeNull();
    expect(paramLine('NAME,not-a-number')).toBeNull();
    expect(paramLine('Name,Value,Default')).toBeNull(); // a CSV header
  });
});
