# Troubleshooting and FAQ

Start with [VERIFICATION.md](VERIFICATION.md) for what has been tested, and [SECURITY.md](../SECURITY.md) before exposing Argus to a network.

## Connection and access

**The serial port I need is not listed.**
Plug the controller in again and refresh the port list. On Windows, check Device Manager; on Linux, `ls /dev/ttyACM*`. A port held by another program is listed but fails to open.

**The port is busy.**
Close the other program that holds it: another ground station, a terminal, or a second Argus backend. On Linux, `fuser /dev/ttyACM0` names the process. Unplug and replug after closing it.

**WebSerial does not appear.**
WebSerial needs Chrome or Edge and a secure context: `localhost` or `https`. Firefox and Safari do not implement it. Use the backend serial/TCP/UDP link in those browsers.

**The phone cannot reach the computer.**
Follow [From a phone or tablet](../README.md#from-a-phone-or-tablet). The backend must listen beyond this machine, `GCS_AUTH_TOKEN` must be set, and the URL the phone opens (the computer's address, not the phone's) must be in `ARGUS_CORS_ORIGINS`. The phone is a second screen; it cannot use WebSerial and cannot use the offline features over plain HTTP.

**I need to change the token.**
The token is in `.gcs_token` in the program folder, or comes from `GCS_AUTH_TOKEN`; if both exist, the file wins. On this machine only, stop Argus, remove `.gcs_token`, start it, and generate a token:

```bash
curl -X POST http://127.0.0.1:8100/api/auth/generate
```

On a network address this does not work: with no token at all Argus refuses to listen on anything but loopback. Set the new `GCS_AUTH_TOKEN` (or write the new `.gcs_token`) before starting it. If both were set, remove the file for the environment variable to take effect. Then update every phone, browser and AI client. The observer role is not access control: everyone with the token can command the vehicle.

## Map, terrain and video

**The map is blank.**
Map tiles, terrain, parameter descriptions, video and firmware file storage come from the Python backend. Run it even when the flight controller is connected through WebSerial. Parameter descriptions ship in the package (`param_i18n/`) and work offline; map tiles still need the network or an offline `.mbtiles`. Check the map server credit and your network.

**Offline map.**
Put `.mbtiles` files in `mbtiles/` and pick the offline source. The map still needs the backend to serve them.

**Video is black.**
Install `ffmpeg` on the PATH and run the backend. The camera address must be reachable from the computer. RTSP is proxied over TCP. Loopback addresses are refused; a private camera address is allowed.

**NTRIP does not connect.**
NTRIP needs the flight controller on the backend link, not WebSerial. No real base station has been tested yet; see [VERIFICATION.md](VERIFICATION.md).

## Missions and parameters

**Reading parameters times out.**
The link dropped or the controller is busy. Retry, and read the event log. A read that is cut by a lost link reports a timeout instead of waiting forever.

**A mission upload is refused.**
Check that the vehicle is disarmed, that the mission is not empty, and that no other page is editing it. A download followed by an upload round-trips the waypoint commands and their p1 to p4 fields.

**A parameter description is marked machine translated.**
The English source comes from ArduPilot's generated parameter metadata. Descriptions in nine
languages (zh, ar, de, es, fr, ja, ko, pt, ru) ship in the GPL-3.0 `param_i18n/` pack and work
offline; all nine are machine translations unless marked reviewed, and a missing field falls back
to English (with an EN marker). “Machine translation” means no person has reviewed that text;
“Reviewed” means someone has. Expand the parameter and use “Show English original” to compare.
A translated description is guidance, not flight procedure.

**A parameter does not change.**
The controller may round an integer parameter or clamp it to its range. Read it back; Argus shows the value the controller reports.

## Logs

**The onboard log list is empty.**
The controller has no logs, or the vehicle link is not connected. Ask the controller for the list again.

**Erase-all removes every log.**
ArduPilot has no per-log delete. Erase-all is refused while armed or while a download runs, and cannot be undone.

**Which local files can I delete?**
The Logs panel's "This computer" tab lists `logs/*.tlog`. The active session and the AI audit log are kept. A deleted log's `.csv` sibling is deleted with it.

**Where are the logs?**
In `logs/` beside the program. A `.tlog` holds the MAVLink frames Argus saw; the `.csv` is a readable summary.

## Firmware

**Where is the firmware panel?**
The Zap button in the status bar, or `Ctrl+K` and "Firmware upgrade".

**The controller has no heartbeat.**
A controller in its bootloader sends no MAVLink heartbeat. That is the state Argus flashes from, and the panel accepts it.

**The flash was refused for the wrong board.**
Argus compares the `.apj` board id and image size with the bootloader before erasing. Use firmware built for that board.

**The flash failed.**
See [RECOVERY.md](RECOVERY.md). Do not unplug while erase, write or verify is running.

**Uploading the same file again.**
A second upload with the same name replaces the first (since v3.13.1). On an older version it fails with a Windows error; update Argus.

## AI assistant

**How do I connect an AI client?**
See [AI assistant (MCP)](../README.md#ai-assistant-mcp). The client needs the token when Argus has one.

**What can the assistant change?**
It can propose a mission, a parameter change, or return, hold or land while flying. Each proposal waits for the operator's approval in the page; return, hold and land still need the slide. It cannot arm, take off, start a mission or change to another mode.

**Where is the record?**
`logs/assistant_audit.jsonl`: one JSON line per request and decision, with the client's own name. It rotates at 5 MB.

## Windows package

**Windows warns about the publisher.**
The package and installer are not code-signed. Check the download against `SHA256SUMS.txt` and the release attestation before running it; see [Install](../README.md#windows-package).

**The installer refused my folder.**
It installs into an empty folder or an earlier Argus folder, and keeps `logs`, `mbtiles` and `firmware` across an uninstall. Close any other Argus before installing or uninstalling.

**Where is the program?**
The Start menu entry "Argus Ground Station", or the folder chosen during installation. The unzipped package runs `Argus地面站.bat`.

## Updates

**How do I update?**
Install the newest release over the old one. `logs`, `mbtiles` and `firmware` are kept. The Argus version is shown in Settings; the status bar's firmware line is the vehicle's firmware.
