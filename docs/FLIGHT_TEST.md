# Flight test protocol

> 中文: [FLIGHT_TEST.zh.md](FLIGHT_TEST.zh.md)

Argus has been tested on the bench and in SITL, not in the air. This is a conservative first-flight protocol for an ArduCopter vehicle. It is a starting point: follow the law and the airspace rules where you fly, and the procedures of the people responsible for the aircraft.

## Roles

- **Pilot in command:** holds the RC transmitter and can take over at any moment.
- **GCS operator:** drives Argus and reads the telemetry aloud.
- **Spotter:** watches the airspace, people and the aircraft; does not look at the screen.

One person may not fill every role on a first flight. Agree on the abort call before arming.

## Before the field

- Review the parameters, failsafes, compass, accelerometer and RC calibration.
- Confirm a 3D GPS fix, a healthy EKF and a clear home position before arming.
- Charge the battery and set a timer; do not plan to use the last 30%.
- Keep the fence and the planned mission inside the area you may legally fly.
- Use one GCS at a time. Close other ground stations and MAVLink clients.
- Props on only outdoors, with the pilot ready and the area clear.

## Release check at v3.16.8

Before the first flight on this release, with the vehicle on the bench:

1. Settings shows **3.16.8**. The parameter pack is `data-v2026.11.6`.
2. Read all parameters. On the test Copter this is about 1,396 names; the panel should show Chinese descriptions for the flight parameters, not an `EN` fallback.
3. Check two 4.7 renames resolve through aliases: `SR0_ADSB` and `CAM_RC_TYPE` should show the same descriptions as `MAV1_ADSB` and `CAM1_RC_TYPE`.
4. Disconnect the network and reopen the parameter panel: the bundled descriptions must still appear.
5. Calibration: run the gyro calibration from the panel. It must end by itself on the flight controller's answer, with no message and no Cancel; the barometer run then ends on "Barometer calibration complete".
6. Logs: list and download one log before trying Erase All. Erase All is irreversible and is not part of the first flight.

## Bench check, props off

1. Connect the flight controller in Argus. Both the WebSerial and backend serial links are acceptable for this step.
2. Read the status bar and the preflight panel: battery voltage, mode, disarmed, no prearm errors.
3. Arm with the slide. Expect the arm acknowledgement and the phase change; do not expect the motors to be a test of flight behaviour.
4. Change one mode and back. Disarm.
5. If a disarm is refused, use Force Disarm with the slide. Find out why the controller refused before the field.
6. Open the event log and the flight log. The session should contain the arm, mode and disarm events.

A bench arm is not a flight. It does not change the "Real flight" row in [VERIFICATION.md](VERIFICATION.md) from None.

## First field flight

Fly at a site with room for a return and a landing, away from people and property. The pilot keeps the transmitter in hand throughout.

1. Connect, wait for a 3D fix and a healthy EKF, and read the battery voltage.
2. Set the altitude field beside Take Off to 10 m; the default is 30 m. Arm. Take off and hold. Confirm the altitude and position on the HUD and from the spotter.
3. RTL. Confirm the climb to the configured return altitude, the return, the landing and the disarm.
4. Arm again on the ground. Upload a short mission of three waypoints inside the test area, then start it. Watch the waypoint counter advance.
5. RTL at the second waypoint. Confirm the return, landing and disarm.
6. Check the flight summary, then clear the mission.

Do not combine the first flight with a new calibration, a new firmware, a new airframe or a long mission. Change one thing at a time.

## Abort

Abort the flight for any prearm refusal, EKF failsafe, battery sag, oscillation, unexpected mode or altitude, lost GPS, a fence breach, an aircraft or person in the area, or a link that does not come back.

- The pilot takes over first; the GCS operator says what the aircraft is doing.
- Use Land or RTL as the situation allows. Disarm only on the ground.
- Do not chase the aircraft with the GCS. The RC link is the primary control.
- If the GCS link is lost, WebSerial reconnects from the USB button; the backend link reconnects by itself. The pilot does not wait for either.

## Record

Keep a record with the date, vehicle type, firmware version, Argus version, link type, wind, battery, flight times, log filenames and anything unexpected. Keep board names, serial numbers and locations out of the public repository.

## After the flight

- Download the logs before flying again.
- Update [VERIFICATION.md](VERIFICATION.md): the `Real flight` row gets the date and what flew; the command rows get the date in Evidence.
- Update the status wording in `README.md` only after the flight actually happened. A successful short flight is not proof that every mission is safe.
