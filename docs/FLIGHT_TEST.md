# Flight test protocol

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
2. Arm. Take off to 10 m and hold. Confirm the altitude and position on the HUD and from the spotter.
3. RTL. Confirm the climb to the configured return altitude, the return, the landing and the disarm.
4. Upload a short mission of three waypoints inside the test area. Start it. Watch the waypoint counter advance.
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
