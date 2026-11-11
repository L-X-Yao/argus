import { describe, expect, it } from 'vitest';
import { TERRAIN_ATTRIBUTION, TILE_ATTRIBUTION, tileAttribution } from './tileAttribution';

describe('tileAttribution', () => {
  it('credits OpenStreetMap with a link to its copyright page', () => {
    expect(tileAttribution('osm')).toContain('href="https://www.openstreetmap.org/copyright"');
    expect(tileAttribution('osm')).toMatch(/© <a [^>]+>OpenStreetMap<\/a> contributors/);
  });

  it('credits both OpenStreetMap and CARTO for a CARTO map', () => {
    for (const style of ['carto_dark', 'carto_light']) {
      expect(tileAttribution(style)).toContain('OpenStreetMap');
      expect(tileAttribution(style)).toContain('CARTO');
    }
  });

  it('gives the same credit to the layers of one provider, so the map shows it once', () => {
    expect(new Set(['6', '7', '8'].map(tileAttribution)).size).toBe(1);
    expect(new Set(['tdt_vec', 'tdt_sat', 'tdt_label'].map(tileAttribution)).size).toBe(1);
  });

  it('has a credit for every style', () => {
    for (const [style, credit] of Object.entries(TILE_ATTRIBUTION)) {
      expect(credit, style).not.toBe('');
    }
  });

  it('opens every link in a new tab, so a click does not take the control page away', () => {
    const links = [...Object.values(TILE_ATTRIBUTION), TERRAIN_ATTRIBUTION].join(' ').match(/<a [^>]*>/g) ?? [];
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toContain('target="_blank"');
      expect(link).toContain('rel="noopener noreferrer"');
    }
  });

  it('has no credit of its own for an offline file or an unknown style', () => {
    expect(tileAttribution('mbtiles:field.mbtiles')).toBe('');
    expect(tileAttribution('nope')).toBe('');
    expect(tileAttribution(null)).toBe('');
    expect(tileAttribution(undefined)).toBe('');
  });
});
