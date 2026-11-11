"""Every server Argus asks is asked under its own name.

OpenStreetMap requires a User-Agent that names the application, and blocks clients that pose
as a browser: https://operations.osmfoundation.org/policies/tiles/ section 3.1. Argus sent
"Mozilla/5.0" to every server until v3.7.9.
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend import firmware, param_meta, terrain, tiles
from backend.config import USER_AGENT, VERSION

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def test_the_name_says_what_asks_and_where_to_find_it():
    assert f"Argus-GCS/{VERSION} (+https://github.com/L-X-Yao/argus)" == USER_AGENT
    assert re.fullmatch(r"Argus-GCS/\d+\.\d+\.\d+ \(\+https://\S+\)", USER_AGENT)


def test_a_map_tile_is_asked_for_under_that_name(tmp_path):
    response = MagicMock()
    response.read.return_value = b"\x89PNG"
    with patch("backend.tiles.urlreq.urlopen", return_value=response) as fetch:
        tiles._fetch_tile("osm", "https://tile.openstreetmap.org/3/4/2.png")
    assert fetch.call_args.args[0].get_header("User-agent") == USER_AGENT


@pytest.mark.parametrize("module", [tiles, terrain, firmware, param_meta])
def test_every_download_uses_the_same_name(module):
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert '"User-Agent": USER_AGENT' in source


def test_no_request_poses_as_a_browser():
    posing = [
        str(path.relative_to(BACKEND))
        for path in BACKEND.rglob("*.py")
        if re.search(r"Mozilla|AppleWebKit|Chrome/", path.read_text(encoding="utf-8"))
    ]
    assert posing == []
