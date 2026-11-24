# Recovering from a failed firmware flash

> 中文: [RECOVERY.zh.md](RECOVERY.zh.md)

Argus writes an `.apj` through the ArduPilot bootloader over a direct USB serial port. It checks the board id and image size before erasing, verifies the image before rebooting, and does not reboot after a failed erase, program or verify. A failure after erase therefore leaves the controller in its bootloader, never running a partial image. A failure before erase leaves the old firmware running. A reconnect failure after a successful write, verify and reboot leaves the new firmware running while the GCS is disconnected.

## The panel says the flash failed

1. Read the error. It names the phase: reboot, waiting, erase, write, verify or reconnect.
2. Do not unplug the controller while erase, write or verify is running.
3. A failure before erase (reboot, waiting, board check, port discovery) leaves the old firmware running. Correct the file or port and retry; a power-cycle clears a bootloader that is waiting.
4. A failure in erase, write or verify leaves the bootloader. Select the same `.apj` again; the panel's Retry uses the file that failed, not whatever is selected now. Refresh the port list, because the bootloader may enumerate as a different COM or tty port, then flash again. A controller in its bootloader sends no MAVLink heartbeat; this is normal and the panel accepts it.
5. A failure in reconnect comes after a successful write, verify and reboot. The new firmware is running; refresh the port or reconnect. Do not reflash just because the GCS lost the link.

A board-id mismatch is refused before erase. Use an `.apj` built for that board.

## The controller does not answer

1. Leave the USB cable connected. Power-cycle the controller if it has a power switch.
2. After power-up the bootloader waits a few seconds for a new upload. Open Argus and refresh the ports during that window.
3. If the application was erased, the controller stays in the bootloader until a valid image is written.
4. Mission Planner and QGroundControl can flash the same `.apj` through the same bootloader port. Use one program at a time and close the others.
5. Use a direct USB connection, not a radio or telemetry link. A radio cannot carry the bootloader protocol.
6. On Windows, check Device Manager. The bootloader usually needs no extra driver. Try another cable or USB port if nothing appears.
7. If the board never enumerates as a serial port, it may need its vendor's DFU or ST-Link recovery. Argus cannot recover a board it cannot see.

## Before the next flash

- Remove the propellers and keep the vehicle disarmed.
- Keep a known-good `.apj` for the exact board.
- Do not bypass the board check with another board's firmware.
- Do not unplug during erase, write, verify or reboot.

## What Argus does and does not do

- Backend serial link only. A browser cannot reopen the port after the controller re-enumerates.
- Checks the board id and image size before erase.
- Verifies the written image before reboot. There is no force-write option.
- Refuses while armed, over TCP/UDP/replay, while reconnecting, or while another flash runs.
- Refuses external-flash images.

What has actually been tested is in [VERIFICATION.md](VERIFICATION.md).
