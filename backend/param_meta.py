"""Parameter metadata: legacy ArduPilot XML and versioned translation packs."""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import math
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .config import USER_AGENT, cfg
from .constants import VALID_LOCALES

CACHE_DIR = Path(__file__).resolve().parent.parent / "param_cache"
PACK_DIR = Path(__file__).resolve().parent.parent / "param_i18n"
CACHE_TTL = cfg.PARAM_CACHE_TTL
PACK_MAX_TOTAL = 256 * 1024 * 1024
PACK_MAX_FILES = 512
_MERGED_CACHE_MAX = 8
_SELECTION_CACHE_MAX = 8

_P = "https://autotest.ardupilot.org/Parameters/"
_URLS = {
    "copter": _P + "ArduCopter/apm.pdef.xml",
    "plane": _P + "ArduPlane/apm.pdef.xml",
    "rover": _P + "Rover/apm.pdef.xml",
    "sub": _P + "ArduSub/apm.pdef.xml",
}
_VERSIONED = {"copter": "Copter", "plane": "Plane", "rover": "Rover", "sub": "Sub"}
_PREFIXES = ("ArduCopter:", "ArduPlane:", "Rover:", "ArduSub:")
_SERIES_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_NAME_RE = re.compile(r"[A-Za-z0-9_]{1,16}\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")

_cache: dict[str, dict] = {}
# Merged objects never share nested dictionaries with _cache or the parsed pack.
_merged_cache: dict[tuple[str, str, str, str], dict] = {}
_json_cache: dict[Path, tuple[int, int, object]] = {}
_selection_cache: dict[tuple[str, str, str, str], tuple[str, str, dict]] = {}
_validation_cache: dict[Path, tuple[int, int, int]] = {}
_active_pack: tuple[Path, tuple[int, int, int]] | None = None
_merge_lock = threading.RLock()


class _PackError(Exception):
    """A missing, malformed, or unsafe pack; the caller uses English metadata."""


def get_metadata(vehicle: str) -> dict:
    """The legacy master metadata URL and cache, unchanged for existing callers."""
    vehicle = vehicle.lower()
    if vehicle not in _URLS:
        return {}
    return _metadata_from(vehicle, _URLS[vehicle], vehicle)


def _get_versioned_metadata(vehicle: str, series: str) -> dict:
    if vehicle not in _VERSIONED or not _SERIES_RE.fullmatch(series):
        return {}
    url = _P + f"versioned/{_VERSIONED[vehicle]}/stable-{series}/apm.pdef.xml"
    return _metadata_from(vehicle, url, f"{vehicle}-{series}")


def _metadata_from(vehicle: str, url: str, cache_name: str) -> dict:
    if cache_name in _cache:
        return _cache[cache_name]

    cache_path = CACHE_DIR / ("%s.json" % cache_name)
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_TTL:
            try:
                with open(cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                _cache[cache_name] = data
                return data
            except (OSError, json.JSONDecodeError):
                pass  # fall through to re-fetch

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        raw = urllib.request.urlopen(req, timeout=cfg.PARAM_DOWNLOAD_TIMEOUT).read(cfg.PARAM_META_MAX + 1)
        if len(raw) > cfg.PARAM_META_MAX:
            raise ValueError("parameter metadata too large")
        data = _parse_xml(raw)
        CACHE_DIR.mkdir(exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        _cache[cache_name] = data
        return data
    # HTTPException: a connection cut mid-body raises IncompleteRead, not OSError.
    except (OSError, http.client.HTTPException, json.JSONDecodeError, ValueError, ET.ParseError):
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                _cache[cache_name] = data
                return data
            except (OSError, json.JSONDecodeError):
                pass
        return {}


def _parse_xml(raw: bytes) -> dict:
    root = ET.fromstring(raw)
    meta: dict = {}
    for group in root.iter("parameters"):
        gname = group.get("name", "")
        for param in group.iter("param"):
            name = param.get("name", "")
            if not name:
                continue
            entry: dict = {
                "desc": param.get("documentation", ""),
                "human": param.get("humanName", ""),
                "group": gname,
            }
            for field in param.iter("field"):
                fn = field.get("name", "")
                ft = (field.text or "").strip()
                if fn == "Range":
                    parts = ft.split()
                    if len(parts) == 2:
                        try:
                            entry["range"] = [float(parts[0]), float(parts[1])]
                        except ValueError:
                            pass
                elif fn == "Units":
                    entry["units"] = ft
                elif fn == "Increment":
                    try:
                        entry["step"] = float(ft)
                    except ValueError:
                        pass
                elif fn == "Default":
                    try:
                        entry["default"] = float(ft)
                    except ValueError:
                        pass
                elif fn == "Bitmask":
                    bits = {}
                    for item in ft.split(","):
                        item = item.strip()
                        if ":" in item:
                            k, v = item.split(":", 1)
                            bits[k.strip()] = v.strip()
                    if bits:
                        entry["bitmask"] = bits
            values = {}
            for val in param.iter("value"):
                code = val.get("code", "")
                if code:
                    values[code] = val.text or ""
            if values:
                entry["values"] = values
            meta[name] = entry
    return meta


def _version(series: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in series.split("."))


def _fw_series(fw: str) -> str:
    if not isinstance(fw, str):
        return ""
    value = fw[1:] if fw.startswith("v") else fw
    return value if _SERIES_RE.fullmatch(value) else ""


def _pack_signature() -> tuple[int, int, int]:
    try:
        root = PACK_DIR.stat()
        manifest = (PACK_DIR / "manifest.json").stat()
    except OSError as exc:
        raise _PackError("parameter pack manifest is missing") from exc
    return root.st_mtime_ns, manifest.st_mtime_ns, manifest.st_size


def _validate_pack() -> tuple[int, int, int]:
    if PACK_DIR.is_symlink() or not PACK_DIR.is_dir():
        raise _PackError("parameter pack is absent or not a real directory")
    signature = _pack_signature()
    with _merge_lock:
        if _validation_cache.get(PACK_DIR) == signature:
            return signature
    total = 0
    count = 0
    for path in PACK_DIR.rglob("*"):
        if path.is_symlink():
            raise _PackError("parameter pack contains a symlink")
        if path.is_file():
            size = path.stat().st_size
            if size > cfg.PARAM_META_MAX:
                raise _PackError("parameter pack file is too large")
            total += size
            count += 1
            if total > PACK_MAX_TOTAL or count > PACK_MAX_FILES:
                raise _PackError("parameter pack is too large")
        elif not path.is_dir():
            raise _PackError("parameter pack contains a non-regular file")
    with _merge_lock:
        _validation_cache[PACK_DIR] = signature
    return signature


def _activate_pack(signature: tuple[int, int, int]) -> None:
    global _active_pack
    with _merge_lock:
        identity = (PACK_DIR, signature)
        if _active_pack == identity:
            return
        _merged_cache.clear()
        _selection_cache.clear()
        _json_cache.clear()
        _active_pack = identity


def _trim_cache(cache: dict, limit: int) -> None:
    # Fingerprints change while a parameter list fills. Keep hot requests fast without
    # retaining one full metadata object for every prefix ever seen; dict order is FIFO.
    while len(cache) > limit:
        cache.pop(next(iter(cache)))


def _read_json(path: Path):
    root = PACK_DIR
    try:
        if root.is_symlink():
            raise _PackError("parameter pack root is a symlink")
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
        current = path
        while current != root:
            if current.is_symlink():
                raise _PackError("parameter pack path contains a symlink")
            current = current.parent
        if not path.is_file():
            raise _PackError("parameter pack entry is not a file")
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        with _merge_lock:
            cached = _json_cache.get(resolved)
            if cached is not None and cached[:2] == signature:
                return cached[2]
        with open(path, "rb") as f:
            raw = f.read(cfg.PARAM_META_MAX + 1)
        if len(raw) > cfg.PARAM_META_MAX:
            raise _PackError("parameter pack file grew beyond its limit")
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        _check_finite(value)
        if path.stat().st_mtime_ns != signature[0] or path.stat().st_size != signature[1]:
            raise _PackError("parameter pack file changed while being read")
        with _merge_lock:
            _json_cache[resolved] = (*signature, value)
        return value
    except _PackError:
        raise
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise _PackError("cannot read parameter pack") from exc


def _check_finite(value) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise _PackError("non-finite number in parameter pack")
    if isinstance(value, dict):
        for child in value.values():
            _check_finite(child)
    elif isinstance(value, list):
        for child in value:
            _check_finite(child)


def _manifest(vehicle: str) -> tuple[dict, list[str]]:
    data = _read_json(PACK_DIR / "manifest.json")
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("sources"), list):
        raise _PackError("unsupported parameter pack manifest")
    if not isinstance(data.get("data_version"), str):
        raise _PackError("parameter pack data version is missing")
    available = set()
    for source in data["sources"]:
        if not isinstance(source, dict):
            raise _PackError("bad parameter pack source")
        source_vehicle = source.get("vehicle")
        series = source.get("series")
        if source_vehicle not in _URLS or not isinstance(series, str) or not _SERIES_RE.fullmatch(series):
            raise _PackError("bad parameter pack source name")
        if source_vehicle == vehicle:
            available.add(series)
    return data, sorted(available, key=_version)


def _finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _clean_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise _PackError("parameter metadata entry is not an object")
    clean = {}
    for field in ("desc", "human", "group", "units", "source"):
        value = entry.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise _PackError("parameter metadata text is not a string")
            clean[field] = value
    for field in ("default", "step"):
        value = entry.get(field)
        if value is not None:
            if not _finite_number(value):
                raise _PackError("parameter metadata number is invalid")
            clean[field] = value
    if "range" in entry:
        value = entry["range"]
        if not isinstance(value, list) or len(value) != 2 or any(not _finite_number(n) for n in value):
            raise _PackError("parameter metadata range is invalid")
        clean["range"] = value.copy()
    for field in ("values", "bitmask"):
        value = entry.get(field)
        if value is not None:
            if not isinstance(value, dict) or any(
                not isinstance(code, str) or not isinstance(text, str) for code, text in value.items()
            ):
                raise _PackError("parameter metadata labels are invalid")
            clean[field] = value.copy()
    return clean


def _normalise_entries(data: dict, *, strict: bool = True) -> dict:
    """Normalise a metadata map.

    A pack is untrusted: one bad entry refuses the whole pack. The legacy XML is
    fetched from ArduPilot and can carry a name longer than MAVLink allows (4.5.7
    and 4.6.3 have SIM_PLD_* names of 17 and 18 characters); there, skip the entry
    rather than throwing away every description for the vehicle.
    """
    if not isinstance(data, dict):
        if strict:
            raise _PackError("parameter metadata is not an object")
        return {}
    normalised = {}
    for raw_name, raw_entry in data.items():
        if not isinstance(raw_name, str):
            if strict:
                raise _PackError("parameter name is not a string")
            continue
        name = raw_name
        prefixed = False
        for prefix in _PREFIXES:
            if raw_name.startswith(prefix):
                name = raw_name[len(prefix) :]
                prefixed = True
                break
        if name == "_meta" or not _NAME_RE.fullmatch(name):
            if strict:
                raise _PackError("parameter name is invalid")
            continue
        # The generator promises this, but an untrusted pack must get the same result.
        if prefixed and name in data:
            continue
        try:
            normalised[name] = _clean_entry(raw_entry)
        except _PackError:
            if strict:
                raise
    return normalised


def _aliases(vehicle: str) -> dict[str, str]:
    path = PACK_DIR / "aliases.json"
    if not path.exists():
        return {}
    data = _read_json(path)
    if not isinstance(data, dict):
        raise _PackError("parameter aliases are not an object")
    aliases = data.get(vehicle, {})
    if not isinstance(aliases, dict):
        raise _PackError("vehicle aliases are not an object")
    for old, new in aliases.items():
        if (
            not isinstance(old, str)
            or not isinstance(new, str)
            or old == "_meta"
            or new == "_meta"
            or not _NAME_RE.fullmatch(old)
            or not _NAME_RE.fullmatch(new)
        ):
            raise _PackError("parameter alias is invalid")
    return aliases.copy()


def _overrides(vehicle: str) -> dict:
    path = PACK_DIR / "overrides" / f"{vehicle}.json"
    return _normalise_entries(_read_json(path)) if path.exists() else {}


def _translation_memory(locale: str) -> dict:
    data = _read_json(PACK_DIR / "tm" / f"{locale}.json")
    if not isinstance(data, dict):
        raise _PackError("translation memory is not an object")
    for digest, record in data.items():
        if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest) or not isinstance(record, dict):
            raise _PackError("translation memory key is invalid")
        if not isinstance(record.get("t"), str) or isinstance(record.get("r"), bool) or record.get("r") not in (0, 1):
            raise _PackError("translation memory entry is invalid")
        if "s" in record and record["s"] != "generated":
            raise _PackError("translation memory source is invalid")
    return data


def _select_series(vehicle, available, fw, requested, names):
    if requested in available:
        return requested, "manual", _normalise_entries(_read_json(PACK_DIR / "meta" / vehicle / f"{requested}.json"))
    if names:
        loaded = {
            series: _normalise_entries(_read_json(PACK_DIR / "meta" / vehicle / f"{series}.json"))
            for series in available
        }
        fw_version = _version(_fw_series(fw)) if _fw_series(fw) else None

        def rank(series):
            score = sum(name in loaded[series] for name in names)
            distance = (
                tuple(abs(a - b) for a, b in zip(_version(series), fw_version, strict=True))
                if fw_version
                else (0, 0, 0)
            )
            return (-score, distance, tuple(-part for part in _version(series)))

        selected = min(available, key=rank)
        return selected, "coverage", loaded[selected]
    fw_series = _fw_series(fw)
    if fw_series and fw_series in available:
        selected = fw_series
    elif fw_series:
        below = [series for series in available if _version(series) <= _version(fw_series)]
        selected = max(below or available, key=_version)
    else:
        selected = max(available, key=_version)
    return selected, "fw", _normalise_entries(_read_json(PACK_DIR / "meta" / vehicle / f"{selected}.json"))


def _fingerprint(names: tuple[str, ...]) -> str:
    if not names:
        return ""
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _translated_entry(entry: dict, tm: dict):
    result = copy.deepcopy(entry)
    tr = {}
    expected = 0
    translated = 0
    reviews = []
    generated = entry.get("source") == "generated"

    def translate(text):
        record = tm.get(hashlib.sha256(text.encode("utf-8")).hexdigest())
        if not record or not record["t"]:
            return None
        reviews.append(record["r"])
        generated_source = record.get("s") == "generated"
        return record["t"], generated_source

    for field in ("desc", "human"):
        text = entry.get(field)
        if not text:
            continue
        expected += 1
        found = translate(text)
        if found:
            value, was_generated = found
            tr[field] = value
            translated += 1
            generated = generated or was_generated
    for field in ("values", "bitmask"):
        labels = entry.get(field)
        if not labels:
            continue
        output = {}
        for code, text in labels.items():
            expected += 1
            found = translate(text)
            if found:
                value, was_generated = found
                output[code] = value
                translated += 1
                generated = generated or was_generated
        if output:
            tr[field] = output
    if expected == 0:
        return result, "reviewed", True
    if translated < expected:
        status = "partial"
    elif generated:
        status = "generated"
    elif 0 in reviews:
        status = "machine"
    else:
        status = "reviewed"
    tr["status"] = status
    result["tr"] = tr
    return result, status, status != "partial"


def _with_meta(merged, vehicle, series, locale, selection, manifest, tm):
    total = len(merged)
    if locale == "en":
        translated, translation = total, "reviewed"
    elif tm is None:
        translated, translation = 0, "unavailable"
    else:
        output = {}
        translated = 0
        worst = "reviewed"
        rank = {"reviewed": 0, "machine": 1, "generated": 2, "partial": 3}
        for name, entry in merged.items():
            new_entry, status, complete = _translated_entry(entry, tm)
            output[name] = new_entry
            translated += int(complete)
            if rank[status] > rank[worst]:
                worst = status
        merged = output
        translation = worst
    meta = {
        "vehicle": vehicle,
        "series": series,
        "locale": locale,
        "selection": selection,
        "translation": translation,
        "translated": translated,
        "total": total,
        "available_series": sorted(
            {source["series"] for source in manifest["sources"] if source["vehicle"] == vehicle}, key=_version
        ),
        "data_version": manifest["data_version"],
        "schema": 1,
    }
    return {"_meta": meta, **merged}


def _request_result(result: dict, selection: str, locale_was_invalid: bool) -> dict:
    # Selection is request metadata, not part of the frozen cache key. Two requests can choose
    # the same series by manual and firmware paths, so never leak the first request's label.
    # Deep-copy the entries too: a caller must not mutate the cached translations or labels.
    result = copy.deepcopy(result)
    result["_meta"]["selection"] = selection
    if locale_was_invalid:
        result["_meta"]["translation"] = "unavailable"
        result["_meta"]["translated"] = 0
    return result


def _legacy_result(vehicle, locale, fw, locale_was_invalid):
    fw_series = _fw_series(fw)
    raw = _get_versioned_metadata(vehicle, fw_series) if fw_series else get_metadata(vehicle)
    from_master = False
    if not raw and fw_series:
        # A firmware newer than the versioned folders, or a URL that failed. The
        # content is the master metadata, so it must not be labelled with the
        # firmware's series.
        raw = get_metadata(vehicle)
        from_master = bool(raw)
    # Legacy XML is ArduPilot's, not an untrusted pack: skip entries it cannot
    # represent instead of returning nothing for the whole vehicle.
    try:
        merged = _normalise_entries(copy.deepcopy(raw), strict=False)
    except _PackError:
        merged = {}
    total = len(merged)
    english = locale == "en" and not locale_was_invalid
    return {
        "_meta": {
            "vehicle": vehicle,
            "series": "" if from_master else fw_series,
            "locale": locale,
            "selection": "fw",
            "translation": "reviewed" if english else "unavailable",
            "translated": total if english else 0,
            "total": total,
            "available_series": [] if from_master else ([fw_series] if fw_series else []),
            "data_version": "",
            "schema": 1,
        },
        **merged,
    }


def get_param_metadata(vehicle="copter", locale="en", fw="", series="", param_names=()) -> dict:
    vehicle = vehicle.lower() if isinstance(vehicle, str) else ""
    if vehicle not in _URLS:
        return {}
    requested_locale = locale.lower() if isinstance(locale, str) else "en"
    locale_was_invalid = requested_locale not in VALID_LOCALES
    locale = "en" if locale_was_invalid else requested_locale
    names = tuple(sorted({name for name in param_names if isinstance(name, str)}))
    fingerprint = _fingerprint(names)
    fw = fw if isinstance(fw, str) else ""
    series = series if isinstance(series, str) else ""
    try:
        signature = _validate_pack()
        _activate_pack(signature)
        manifest, available = _manifest(vehicle)
        if not available:
            raise _PackError("no metadata series for vehicle")
        selection_key = (vehicle, fw, series, fingerprint)
        with _merge_lock:
            chosen = _selection_cache.get(selection_key)
        if chosen is None:
            chosen = _select_series(vehicle, available, fw, series, names)
            with _merge_lock:
                if _active_pack == (PACK_DIR, signature):
                    _selection_cache[selection_key] = chosen
                    _trim_cache(_selection_cache, _SELECTION_CACHE_MAX)
        selected, selection, base = chosen
        key = (vehicle, selected, locale, fingerprint)
        with _merge_lock:
            cached = _merged_cache.get(key)
        if cached is not None:
            return _request_result(cached, selection, locale_was_invalid)
        merged = copy.deepcopy(base)
        for old, new in _aliases(vehicle).items():
            if new in merged:
                merged[old] = copy.deepcopy(merged[new])
        for name, entry in _overrides(vehicle).items():
            merged[name] = copy.deepcopy(entry)
        tm = None
        if locale != "en":
            try:
                tm = _translation_memory(locale)
            except _PackError:
                pass  # English metadata remains useful when one locale is absent or bad.
        result = _with_meta(merged, vehicle, selected, locale, selection, manifest, tm)
        with _merge_lock:
            # A pack update may have cleared and replaced the generation while this request
            # was merging. The old caller can keep its answer, but must not refill new caches.
            if _active_pack == (PACK_DIR, signature):
                result = _merged_cache.setdefault(key, result)
                _trim_cache(_merged_cache, _MERGED_CACHE_MAX)
        return _request_result(result, selection, locale_was_invalid)
    except _PackError:
        return _legacy_result(vehicle, locale, fw, locale_was_invalid)
