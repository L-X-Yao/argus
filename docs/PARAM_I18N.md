# Parameter metadata and translations

Status: contract frozen for the multilingual parameter work. Code and the data repository follow this document; change it first if the shape must change.

## Why

The parameter panel reads ArduPilot's `apm.pdef.xml`. The descriptions are English, and the panel cannot explain every parameter in every UI language. Argus therefore ships a data pack with:

- normalized English metadata for the supported vehicle/firmware series, so the panel works offline;
- translations keyed by the hash of the English text, so one translation serves every parameter that repeats it;
- aliases and overrides for renamed or undocumented parameters.

The data is derived from ArduPilot, which is GPL-3.0. It lives in a separate public repository, `L-X-Yao/argus-param-i18n`, under GPL-3.0. The Argus source stays MIT; the pack is an independent data work, included in the zip and installer with its license text and notice.

## Data pack

`param_i18n/` is generated or downloaded; it is not committed. `param_i18n.lock` is committed.

```text
param_i18n/
  manifest.json
  meta/<vehicle>/<series>.json
  tm/<locale>.json
  glossary/<locale>.json
  aliases.json
  overrides/<vehicle>.json
```

The data repository also keeps `source.json` (hash -> English source) for translation and GPL provenance. It need not be in the installed pack; the public repository is the source.

### manifest.json

```json
{
  "schema": 1,
  "data_version": "2026.11.1",
  "created": "2026-11-21T00:00:00Z",
  "license": "GPL-3.0",
  "sources": [
    {"vehicle": "copter", "series": "4.6.3", "url": "...", "sha256": "...", "params": 4853}
  ],
  "locales": {
    "zh": {"total": 8297, "translated": 8297, "reviewed": 0, "provider": "..."}
  },
  "min_argus": "3.15.0"
}
```

`data_version` is the data repository release version. `min_argus` is the oldest Argus version that understands the schema.

### meta/<vehicle>/<series>.json

A flat object keyed by the bare MAVLink parameter name. The value has the same fields as the current `backend.param_meta._parse_xml` result:

```json
{
  "RTL_ALT": {
    "desc": "Minimum altitude...",
    "human": "RTL altitude",
    "group": "ArduCopter",
    "range": [0, 100000],
    "units": "cm",
    "step": 10,
    "default": 1500,
    "values": {"0": "..."},
    "bitmask": {"0": "..."}
  }
}
```

Keys with an ArduPilot vehicle prefix (`ArduCopter:`, `ArduPlane:`, `Rover:`, `ArduSub:`) are normalized to the bare name by the generator. If both forms exist, the bare form wins and a warning is written to the coverage report.

### tm/<locale>.json

```json
{
  "<sha256 of the exact UTF-8 English text>": {"t": "译文", "r": 0, "s": "generated"}
}
```

- Hash: `sha256(text.encode("utf-8")).hexdigest()`, lowercase hex, no normalization. The generator and the backend hash the same exact string.
- `t`: translation.
- `r`: `1` only after a human review; `0` for machine translation.
- `s`: optional `"generated"` for a description Argus generated for a parameter that has no upstream metadata. Omitted for normal translations.
- `en` is the source language. A TM file for `en` is optional and is not used by the runtime.

The same English string has one translation per locale, even when it appears on several parameters, vehicles or firmware series.

### aliases.json and overrides/<vehicle>.json

`aliases.json` maps an old parameter name to the name in the selected metadata:

```json
{"copter": {"OLD_NAME": "NEW_NAME"}}
```

`overrides/<vehicle>.json` supplies metadata that no pdef contains:

```json
{
  "SIM_ACC_TRIM_X": {
    "desc": "Simulated accelerometer trim...",
    "human": "Simulated accelerometer trim",
    "source": "generated"
  }
}
```

The generator adds override text to `source.json` and the translation memory like any other English string. The UI may mark generated text.

## API

`GET /api/param_meta?vehicle=copter&locale=zh&fw=v4.6.3&series=4.6.3`

- `vehicle`: `copter`, `plane`, `rover`, `sub`; anything else returns `{}`.
- `locale`: one of `zh en ja ko de fr es pt ru ar`; anything else falls back to `en` with `_meta.translation = "unavailable"`, never a 500.
- `fw`: firmware version as reported by `AUTOPILOT_VERSION` (`v4.6.3`); used to preselect a series.
- `series`: explicit metadata series (`4.6.3`); overrides automatic selection.

Response:

```json
{
  "_meta": {
    "vehicle": "copter",
    "series": "4.6.3",
    "locale": "zh",
    "selection": "coverage",
    "translation": "machine",
    "translated": 1390,
    "total": 1396,
    "available_series": ["4.5.7", "4.6.3", "4.7.1"],
    "data_version": "2026.11.1",
    "schema": 1
  },
  "RTL_ALT": {
    "desc": "Minimum altitude...",
    "human": "RTL altitude",
    "units": "cm",
    "tr": {
      "desc": "返航最低高度...",
      "human": "返航高度",
      "values": {"0": "..."},
      "bitmask": {"0": "..."},
      "status": "machine"
    }
  }
}
```

- `selection`: `coverage` (chosen by matching the live parameter names), `fw` (chosen from the firmware version), or `manual` (explicit `series`).
- `translation`: `reviewed`, `machine`, `generated`, `partial`, or `unavailable`; the worst status among entries is reported.
- `tr.status`: per parameter. `reviewed` means every translated field was reviewed; `machine` means at least one field is machine translation; `generated` means the English source was generated for an undocumented parameter; `partial` means at least one translated field is missing.
- If a field is absent from `tr`, the client shows the English field. No silent fallback in a non-English locale: the client marks the English fallback.
- `_meta` is not a parameter. Clients must remove it before treating the response as a name map.

The route must not mutate `param_meta._cache`. Build a new merged object per request and cache it by `(vehicle, series, locale, parameter fingerprint)`. The response is gzip-compressed when the client accepts it.

## Metadata selection

1. If `series` is given and present in the pack, use it (`selection = "manual"`).
2. If live parameter names are available (backend link), score every series in the pack by the number of live names it contains; the highest score wins (`selection = "coverage"`). Tie-break by the closest series to `fw`.
3. Otherwise preselect by `fw` (`selection = "fw"`): exact series, else the highest series at or below it, else the highest available.
4. If no pack series is usable, fetch the versioned URL for `fw` or the legacy master URL, keeping the current 7-day disk cache and offline stale-cache fallback.
5. Apply aliases; apply overrides; leave anything still missing to English fallback and report it in coverage.

WebSerial has no live names on the backend. The panel checks coverage against `paramState.list` and may retry up to two other `available_series`, choosing the best; if the best is still low it offers a manual series selector.

## Security

- The pack is untrusted input: validate schema/version, JSON types, key names, maximum file sizes and total size. Never execute anything from it.
- Locale and vehicle are whitelisted; `series` must match `^[0-9]+\.[0-9]+\.[0-9]+$` and exist in the manifest.
- Resolve pack paths under `param_i18n/` only; reject `..`, absolute paths and symlinks.
- The pack is data only. It adds no runtime network call for supported vehicles and no new command or AI tool.

## Release and update

1. A data release `data-vYYYY.MM.N` carries `argus-param-i18n-<version>.tar.gz` and its SHA256.
2. `param_i18n.lock` records `schema`, `version`, asset URL and SHA256. The lock is committed in a normal commit; `scripts/make-release.sh` only stages version files and does not commit it.
3. `scripts/fetch_param_i18n.py` downloads, verifies and safely extracts into `param_i18n/`. `scripts/build_package.py` copies it; the installer includes it.
4. New ArduPilot firmware: regenerate the delta in the data repository, translate new/changed hashes, release a data version, bump the lock. No Argus code change.
5. Translation correction: edit the TM entry, set `r=1`, release a data version, bump the lock. No Argus code change.
6. Schema/API change: bump `schema` and `min_argus`; code change required.

## Ownership

- `argus-param-i18n` is owned by argus-a4; argus-ds reviews it.
- Argus backend metadata/merge is owned by argus-kimi; argus-a4 reviews it.
- Argus panel/packaging is owned by argus-ds; argus-kimi reviews it.
- Claims, worktrees, heavy-test locks and merge order follow `CONTRIBUTING.md`, "Several Sessions at Once".
