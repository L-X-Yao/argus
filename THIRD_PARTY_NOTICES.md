# Third-Party Notices

Argus is under the MIT license, see [LICENSE](LICENSE). It contains work of others, and at run time it reads data from servers of others. Their terms are listed here.

## Files in this repository

| What | Where | From | License |
| --- | --- | --- | --- |
| Six calibration pictures | `public/images/cal/` | [QGroundControl](https://github.com/mavlink/qgroundcontrol), `src/AutoPilotPlugins/PX4/Images/`, unchanged | Apache-2.0: [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt). QGroundControl is offered under Apache-2.0 or GPL-3.0, and Argus takes these files under Apache-2.0 |
| Leaflet 1.9.4 | `public/lib/leaflet/` | [leafletjs.com](https://leafletjs.com) | BSD-2-Clause: [LICENSES/BSD-2-Clause-Leaflet.txt](LICENSES/BSD-2-Clause-Leaflet.txt) |

## Libraries in the web build

`npm run build` bundles libraries from npm into `dist/`. The build writes their names, versions and license texts to `dist/THIRD-PARTY-LICENSES.txt`, from the modules that went into the bundle (`vite.config.ts`).

## Software in the Windows package

| What | License text in the package |
| --- | --- |
| CPython, embeddable build | `python/LICENSE.txt` |
| Python libraries | `python/Lib/site-packages/<name>.dist-info/licenses/` |
| pyserial, whose wheel holds no license file | `LICENSES/BSD-3-Clause-pyserial.txt` |
| The web build | `dist/THIRD-PARTY-LICENSES.txt` |

`scripts/build_package.py` stops when a Python library in the package has no license text, and when the list of the web build lacks a library that is always in it. For a web library that ships no license file the list names its license and its source.

pymavlink (LGPL-3.0) is used by the tests only. It is in no package.

## Servers Argus reads at run time

Nothing below is included in Argus. It is fetched when you use the feature, under the terms of each server. The backend sends `Argus-GCS/<version>` as its User-Agent, and the map shows the credit of its server. The terrain of the 3D view is the one thing the browser reads itself.

| Server | Used for | Terms |
| --- | --- | --- |
| `tile.openstreetmap.org` | OpenStreetMap street layer | [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/), data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL. The policy forbids bulk download and offline use, so Argus does not download this layer in bulk |
| `server.arcgisonline.com` | Esri World Imagery and World Topo Map | [Esri Master Agreement and attribution rules](https://www.esri.com/en-us/legal/terms/full-master-agreement) |
| `basemaps.cartocdn.com` | CARTO dark and light maps | [CARTO basemap terms](https://carto.com/attributions), data © OpenStreetMap contributors |
| `t0.tianditu.gov.cn` | Tianditu, with a key of your own | The terms of your Tianditu key |
| `webst01.is.autonavi.com`, `wprd01.is.autonavi.com` | AutoNavi (Amap) maps, the default source | Not a published API: these are the addresses AutoNavi's own web map reads. AutoNavi publishes no terms that allow other software to read them |
| `mt1.google.com` | Google maps | Not a published API: this is the address Google's own web map reads. Google's terms ask that its services are used through the interfaces it provides |
| `elevation-tiles-prod.s3.amazonaws.com` (backend), `s3.amazonaws.com/elevation-tiles-prod` (browser) | Terrain height for missions, and for the 3D view | [Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) open data, [attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) |
| `firmware.ardupilot.org`, `autotest.ardupilot.org` | Firmware list, firmware files and parameter descriptions | ArduPilot, GPL-3.0 |

The offline map download (Offline Maps panel) stores tiles of the AutoNavi layers. Whether you may keep tiles of a server offline is for its terms to say. A map file of your own (`.mbtiles`, put in `mbtiles/`) needs no server.
