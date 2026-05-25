"""Contract: backend _build_state() keys must match frontend DroneState fields.

If the backend adds/removes a field in the WS push dict, this test fails until
the TypeScript interface is updated to match (or vice versa). Catches silent
drift between the two sides of the WebSocket protocol.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.drone_link import DroneLink

ROOT = Path(__file__).resolve().parent.parent
TYPES_TS = ROOT / 'src' / 'lib' / 'types.ts'


def _backend_state_keys() -> set[str]:
    """Get all keys from a real _build_state() call."""
    link = DroneLink()
    state = link._build_state()
    return set(state.keys())


def _frontend_state_fields() -> set[str]:
    """Parse DroneState interface fields from types.ts."""
    src = TYPES_TS.read_text(encoding='utf-8')
    # Find the DroneState block, handling nested braces in inline types
    start = src.index('export interface DroneState')
    brace_start = src.index('{', start)
    depth, pos = 1, brace_start + 1
    while depth > 0 and pos < len(src):
        if src[pos] == '{':
            depth += 1
        elif src[pos] == '}':
            depth -= 1
        pos += 1
    block = src[brace_start + 1:pos - 1]
    # Extract top-level field names (at brace depth 0)
    fields: set[str] = set()
    d = 0
    for line in block.splitlines():
        stripped = line.strip()
        d += stripped.count('{') - stripped.count('}')
        if d > 0 or not stripped or stripped.startswith('//') or stripped.startswith('*'):
            continue
        m = re.match(r'(\w+)\??\s*:', stripped)
        if m:
            fields.add(m.group(1))
    return fields


class TestWsProtocolContract:
    def test_backend_keys_match_frontend_fields(self):
        """Every key in _build_state() should have a field in DroneState."""
        backend = _backend_state_keys()
        frontend = _frontend_state_fields()
        # 'type' is a discriminator, always present in both
        only_backend = backend - frontend
        only_frontend = frontend - backend
        assert not only_backend, (
            '\nBackend pushes keys that DroneState does not declare:\n'
            + '\n'.join(f'  {k}' for k in sorted(only_backend))
            + '\n\nAdd these fields to src/lib/types.ts DroneState interface.'
        )
        assert not only_frontend, (
            '\nDroneState declares fields that backend never pushes:\n'
            + '\n'.join(f'  {k}' for k in sorted(only_frontend))
            + '\n\nRemove these fields from src/lib/types.ts or add them to _build_state().'
        )
