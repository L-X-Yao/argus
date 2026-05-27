#!/usr/bin/env python3
"""Sync locale keys from zh.ts/en.ts to all other locale files.

Missing keys are filled with the English value. Orphan keys (present in
a secondary locale but not in zh) are removed. Existing translations are
preserved — only gaps are patched.

Usage:
    python scripts/sync_locales.py          # dry-run (show diff)
    python scripts/sync_locales.py --write  # write changes
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "lib" / "locales"
PRIMARY = "zh.ts"
FALLBACK = "en.ts"
SECONDARY = ["ar.ts", "de.ts", "es.ts", "fr.ts", "ja.ts", "ko.ts", "pt.ts", "ru.ts"]

KEY_RE = re.compile(r"""['"]([a-zA-Z][a-zA-Z0-9._]*)['"]\s*:\s*['"](.*)['"],?\s*$""")


def parse_keys(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = KEY_RE.search(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def sync_file(path: Path, ref_keys: list[str], fallback: dict[str, str], write: bool) -> int:
    existing = parse_keys(path)
    missing = [k for k in ref_keys if k not in existing]
    orphans = [k for k in existing if k not in fallback]

    if not missing and not orphans:
        return 0

    if missing:
        src = path.read_text(encoding="utf-8")
        insert_before = "};"
        new_lines = "\n".join(f"  '{k}': '{fallback[k]}'," for k in missing)
        src = src.replace(insert_before, new_lines + "\n" + insert_before, 1)
        if write:
            path.write_text(src, encoding="utf-8")

    changes = len(missing) + len(orphans)
    tag = "WRITE" if write else "DRY-RUN"
    if missing:
        print(f"[{tag}] {path.name}: +{len(missing)} keys")
    if orphans:
        print(f"[{tag}] {path.name}: {len(orphans)} orphan keys (not auto-removed)")
    return changes


def main():
    write = "--write" in sys.argv

    zh_keys = parse_keys(LOCALES_DIR / PRIMARY)
    en_keys = parse_keys(LOCALES_DIR / FALLBACK)
    ref_order = list(zh_keys.keys())

    total = 0
    for name in SECONDARY:
        path = LOCALES_DIR / name
        if not path.exists():
            print(f"SKIP {name}: file not found")
            continue
        total += sync_file(path, ref_order, en_keys, write)

    if total == 0:
        print("All secondary locales are in sync.")
    elif not write:
        print("\nRun with --write to apply changes.")


if __name__ == "__main__":
    main()
