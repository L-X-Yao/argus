"""ArduPilot parameter metadata — XML download, parse, and cache."""
from __future__ import annotations
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / 'param_cache'
CACHE_TTL = 86400 * 7

_URLS = {
    'copter': 'https://autotest.ardupilot.org/Parameters/ArduCopter/apm.pdef.xml',
    'plane': 'https://autotest.ardupilot.org/Parameters/ArduPlane/apm.pdef.xml',
    'rover': 'https://autotest.ardupilot.org/Parameters/Rover/apm.pdef.xml',
    'sub': 'https://autotest.ardupilot.org/Parameters/ArduSub/apm.pdef.xml',
}

_cache: dict[str, dict] = {}


def get_metadata(vehicle: str) -> dict:
    vehicle = vehicle.lower()
    if vehicle not in _URLS:
        return {}
    if vehicle in _cache:
        return _cache[vehicle]

    cache_path = CACHE_DIR / ('%s.json' % vehicle)
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_TTL:
            with open(cache_path) as f:
                data = json.load(f)
            _cache[vehicle] = data
            return data

    try:
        req = urllib.request.Request(_URLS[vehicle], headers={'User-Agent': 'GCS/1.0'})
        raw = urllib.request.urlopen(req, timeout=15).read()
        data = _parse_xml(raw)
        CACHE_DIR.mkdir(exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
        _cache[vehicle] = data
        return data
    except Exception:
        if cache_path.exists():
            with open(cache_path) as f:
                data = json.load(f)
            _cache[vehicle] = data
            return data
        return {}


def _parse_xml(raw: bytes) -> dict:
    root = ET.fromstring(raw)
    meta: dict = {}
    for group in root.iter('parameters'):
        gname = group.get('name', '')
        for param in group.iter('param'):
            name = param.get('name', '')
            if not name:
                continue
            entry: dict = {
                'desc': param.get('documentation', ''),
                'human': param.get('humanName', ''),
                'group': gname,
            }
            for field in param.iter('field'):
                fn = field.get('name', '')
                ft = (field.text or '').strip()
                if fn == 'Range':
                    parts = ft.split()
                    if len(parts) == 2:
                        try:
                            entry['range'] = [float(parts[0]), float(parts[1])]
                        except ValueError:
                            pass
                elif fn == 'Units':
                    entry['units'] = ft
                elif fn == 'Increment':
                    try:
                        entry['step'] = float(ft)
                    except ValueError:
                        pass
                elif fn == 'Bitmask':
                    bits = {}
                    for item in ft.split(','):
                        item = item.strip()
                        if ':' in item:
                            k, v = item.split(':', 1)
                            bits[k.strip()] = v.strip()
                    if bits:
                        entry['bitmask'] = bits
            values = {}
            for val in param.iter('value'):
                code = val.get('code', '')
                if code:
                    values[code] = val.text or ''
            if values:
                entry['values'] = values
            meta[name] = entry
    return meta
