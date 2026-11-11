"""Every map source has its credit on the map.

The backend knows the map servers (backend/tiles.py TILE_URLS), the page knows what each of
them wants shown (src/lib/tileAttribution.ts). A source added to one and not to the other
would be shown without credit, which its terms forbid: for OpenStreetMap see
https://operations.osmfoundation.org/policies/tiles/ section 2.
"""

import re
from pathlib import Path

from backend.tiles import TILE_URLS

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "src" / "lib" / "tileAttribution.ts").read_text(encoding="utf-8")


def _credited_styles() -> set[str]:
    table = re.search(r"TILE_ATTRIBUTION: Record<string, string> = \{(.*?)\n\};", SOURCE, re.DOTALL).group(1)
    return {key.strip("'") for key in re.findall(r"^\s*('[^']+'|\w+):", table, re.MULTILINE)}


def test_the_page_credits_exactly_the_styles_the_backend_serves():
    assert _credited_styles() == set(TILE_URLS)


def test_every_layer_of_both_maps_is_made_with_its_credit():
    """A layer made without the helper, or a source without the option, shows no credit."""
    flat = (ROOT / "src" / "components" / "core" / "MapView.svelte").read_text(encoding="utf-8")
    assert flat.count("L.tileLayer(") == 1
    assert "attribution: tileAttribution(style)" in flat
    assert "attributionControl: false" in flat and "L.control.attribution(" in flat

    globe = (ROOT / "src" / "components" / "map" / "Map3DView.svelte").read_text(encoding="utf-8")
    raster_sources = len(re.findall(r"type: 'raster',\s+tiles:", globe))
    assert raster_sources == globe.count("attribution: tileAttribution(src.sat)") == 2
    assert "attribution: TERRAIN_ATTRIBUTION" in globe
    assert "attributionControl: false" not in globe
