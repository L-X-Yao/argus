"""Cross-stack agreement on the largest log a download may allocate."""

import math
import re
from pathlib import Path

from backend.commands._setup import MAX_LOG_SIZE
from backend.locale_text import lt

ROOT = Path(__file__).resolve().parent.parent


def test_log_size_cap_matches_the_frontend_and_error_text():
    source = (ROOT / "src/lib/logStore.svelte.ts").read_text(encoding="utf-8")
    match = re.search(r"MAX_LOG_SIZE\s*=\s*(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)", source)
    assert match, "frontend MAX_LOG_SIZE must stay an explicit byte count"
    assert math.prod(int(part) for part in match.groups()) == MAX_LOG_SIZE
    assert MAX_LOG_SIZE == 256 * 1024 * 1024
    for locale in ("zh", "en"):
        assert f"{MAX_LOG_SIZE // (1024 * 1024)} MB" in lt("err_log_too_large", locale)
