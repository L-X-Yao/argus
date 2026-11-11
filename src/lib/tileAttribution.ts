/**
 * The credit each map server asks for, shown on the map.
 *
 * Keys are the tile styles of backend/tiles.py (TILE_URLS).
 * tests/test_contract_tile_attribution.py keeps the two lists the same, so a map source
 * cannot be added without its credit.
 *
 * OpenStreetMap wants its credit visible on the map, with a link to its copyright page:
 * https://operations.osmfoundation.org/policies/tiles/ section 2. CARTO asks for both names:
 * https://carto.com/attributions. Esri asks for "Powered by Esri" and the copyrightText of the
 * map service (server.arcgisonline.com/ArcGIS/rest/services/<name>/MapServer?f=json, read
 * 2026-11-11). The map cuts a long credit short and shows all of it under the pointer.
 *
 * Every link opens a new tab: a click must not take the page that controls the vehicle away.
 */

function link(href: string, text: string): string {
  return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
}

const OSM = `© ${link('https://www.openstreetmap.org/copyright', 'OpenStreetMap')} contributors`;
const CARTO = `${OSM} © ${link('https://carto.com/attributions', 'CARTO')}`;
const AUTONAVI = '© AutoNavi 高德地图';
const GOOGLE = '© Google';
const TIANDITU = '© 天地图 Tianditu';
const ESRI = `Powered by ${link('https://www.esri.com', 'Esri')}`;

export const TILE_ATTRIBUTION: Record<string, string> = {
  '6': AUTONAVI,
  '7': AUTONAVI,
  '8': AUTONAVI,
  osm: OSM,
  osm_sat: `${ESRI} | Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community`,
  esri_topo:
    `${ESRI} | Sources: Esri, HERE, Garmin, Intermap, increment P Corp., GEBCO, USGS, FAO, NPS, NRCAN, GeoBase, ` +
    'IGN, Kadaster NL, Ordnance Survey, Esri Japan, METI, Esri China (Hong Kong), © OpenStreetMap contributors, ' +
    'and the GIS User Community',
  google_sat: GOOGLE,
  google_street: GOOGLE,
  google_hybrid: GOOGLE,
  google_terrain: GOOGLE,
  carto_dark: CARTO,
  carto_light: CARTO,
  tdt_vec: TIANDITU,
  tdt_sat: TIANDITU,
  tdt_label: TIANDITU,
};

/** The credit for one tile style. An offline file has none of ours: its maker's terms apply. */
export function tileAttribution(style: string | null | undefined): string {
  return (style && TILE_ATTRIBUTION[style]) || '';
}

/** Elevation for the 3D view comes straight from the Terrain Tiles open data set on AWS. */
export const TERRAIN_ATTRIBUTION = `Terrain: ${link('https://github.com/tilezen/joerd/blob/master/docs/attribution.md', 'Tilezen Joerd')}`;
