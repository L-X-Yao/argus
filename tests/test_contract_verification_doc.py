"""Contract: docs/VERIFICATION.md covers everything it claims to.

The status doc is only worth reading while it is complete. The checklist before
it went stale at v3.4 because nothing noticed, so a new command, message, route
or panel fails here until someone records how far it has been tested.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pymavlink.dialects.v20 import ardupilotmega as mavlink

from backend import mavlink_dispatch
from backend.commands import _DISPATCH
from backend.drone_link import DroneLink

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "docs" / "VERIFICATION.md").read_text(encoding="utf-8")
LEVELS = ["Real FC", "SITL", "Simulator", "Tests only", "None", "n/a"]


def _section(heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}.*?(?=^## |\Z)", DOC, re.M | re.S)
    assert match, f"section {heading!r} missing from docs/VERIFICATION.md"
    return match.group(0)


def _rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        if not line.startswith("|") or set(line) <= {"|", "-", " "}:
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows[1:]  # drop the header


def _level_counts(heading: str, column: int) -> list[int]:
    cells = [row[column] for row in _rows(_section(heading))]
    unknown = sorted(set(cells) - set(LEVELS))
    assert not unknown, f"{heading}: unknown levels {unknown}"
    return [len(cells)] + [cells.count(level) for level in LEVELS]


def _backend_routes() -> set[str]:
    routes = set()
    for path in (ROOT / "backend").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for verb, route in re.findall(r'@(?:app|router)\.(get|post|put|delete|websocket)\("([^"]+)"', text):
            routes.add(f"{verb.upper()} {route}")
    return routes


class TestEverythingIsListed:
    def test_commands(self):
        listed = _section("Commands")
        assert not [cmd for cmd in _DISPATCH if f"`{cmd}`" not in listed]

    def test_messages(self):
        DroneLink()  # registers the production dispatch table
        listed = _section("Messages")
        names = [mavlink.mavlink_map[mid].msgname for mid in mavlink_dispatch._handlers]
        assert not [name for name in names if f"`{name}`" not in listed]

    def test_routes(self):
        listed = _section("REST routes")
        assert not [route for route in sorted(_backend_routes()) if f"`{route}`" not in listed]

    def test_panels(self):
        listed = _section("Panels")
        panels = [p.stem for p in (ROOT / "src" / "components").rglob("*.svelte")]
        assert not [name for name in panels if f"`{name}`" not in listed]


class TestSummaryMatchesTheTables:
    @pytest.mark.parametrize(
        ("area", "heading", "column"),
        [
            ("Commands, backend", "Commands", 3),
            ("Commands, WebSerial", "Commands", 4),
            ("Messages, backend", "Messages", 3),
            ("Messages, WebSerial", "Messages", 4),
            ("REST routes", "REST routes", 3),
            ("Platform", "Platform", 2),
            ("Panels", "Panels", 3),
        ],
    )
    def test_counts(self, area: str, heading: str, column: int):
        summary = {row[0]: [int(n) for n in row[1:]] for row in _rows(_section("Summary"))}
        assert summary[area] == _level_counts(heading, column)
