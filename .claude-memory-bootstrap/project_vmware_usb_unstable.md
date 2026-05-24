---
name: project-vmware-usb-unstable
description: "Argus dev VM has unstable VMware USB passthrough for the PLKJ FC — reads work, writes deadlock kernel. Use SITL for protocol validation, not real FC, until USB stabilizes"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2fc6fac5-ef50-46a5-9821-8f991a74a72d
---

The development VM (where `/home/plkj/samba/filght/argus` lives) is a VMware guest. The user's PLKJ industrial FC (USB VID `0x1209`, PID `0x5740`, descriptor "Generic Plkj-Industrial") appears as `/dev/ttyACM0` + `/dev/ttyACM1`. **Pyserial read-only probes work** (~4 KB/s steady MAVLink v2 stream on ACM0). **Any write through `DroneLink` triggers a passthrough deadlock**: the read loop stops returning bytes, eventually the Python process segfaults, and the VM kernel locks up.

**Why:** Two observations on 2026-05-24:
1. A bare `pyserial` loop that only reads got 11521 bytes / 3s with no issues.
2. The same port through `DroneLink.connect()` — which also sends heartbeats + `request_streams()` — saw `frame_count` stuck at 0 forever, thread alive but `_ser.read(1024)` returning empty. A second attempt produced a Python segfault (exit 139). User confirmed: "通过vmware接入飞控不稳定，虚拟机内核会卡死".

**How to apply:** When the user wants to validate Argus against their PLKJ FC in this VM, default to **SITL** (`Tools/autotest/sim_vehicle.py -v ArduCopter --no-rebuild --no-mavproxy` at `/home/plkj/samba/filght/ardupilot`). Don't suggest running `python run.py` connected to `/dev/ttyACM0` — that's the deadlock path. For PLKJ-specific identity-byte rendering (`autopilot=1`, `type=0`, AP-private msgs), use a fake-FC TCP simulator instead — see [[project-audit-state-may2026]] and `docs/audits/sitl_validation_2026-05-24.md` for the pattern.

If USB validation is genuinely needed (firmware upload, calibration, WebSerial), the path forward is: dual-boot Linux host, a different hypervisor with better USB 2.0 stack, USB-over-IP (usbip), or attaching the FC directly to a Linux machine without virtualization.

Pairs with [[feedback-shorten-feedback-loop]] — the bottleneck *was* hardware iteration; switching to SITL closed it.
