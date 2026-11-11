"""Every server Argus asks is asked under its own name.

OpenStreetMap requires a User-Agent that names the application, and blocks clients that pose
as a browser: https://operations.osmfoundation.org/policies/tiles/ section 3.1. Argus sent
"Mozilla/5.0" to every server until v3.7.9.
"""

import ast
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


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name
    ]


@pytest.mark.parametrize("module", [tiles, terrain, firmware, param_meta])
def test_every_request_of_a_module_carries_the_name(module):
    """Read from the code of each request: one of two reverted would pass a search for the text."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    requests = _calls(tree, "Request")
    assert requests
    for call in requests:
        headers = next((kw.value for kw in call.keywords if kw.arg == "headers"), None)
        assert headers is not None, f"line {call.lineno}: a request without headers"
        assert ast.unparse(headers) == "{'User-Agent': USER_AGENT}", f"line {call.lineno}"
    # A bare urlopen(url) would go out as "Python-urllib": every one takes a prepared request.
    opened = _calls(tree, "urlopen")
    assert len(opened) == len(requests)
    for call in opened:
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == "req", f"line {call.lineno}"


def test_no_other_module_asks_a_server():
    """A new download elsewhere would be missed by the test above. The start-up script asks
    only its own /health."""
    asking = sorted(
        str(path.relative_to(BACKEND))
        for path in BACKEND.rglob("*.py")
        if _calls(ast.parse(path.read_text(encoding="utf-8")), "urlopen")
    )
    assert asking == ["firmware.py", "param_meta.py", "server.py", "terrain.py", "tiles.py"]


def test_no_request_poses_as_a_browser():
    posing = [
        str(path.relative_to(BACKEND))
        for path in BACKEND.rglob("*.py")
        if re.search(r"Mozilla|AppleWebKit|Chrome/", path.read_text(encoding="utf-8"))
    ]
    assert posing == []
