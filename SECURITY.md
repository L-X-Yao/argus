# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Argus GCS, please report it responsibly.

**Email:** lsc1476907630@gmail.com

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Potential impact

**Response:** Argus is in maintenance and has one maintainer, so there is no guaranteed response time. Security reports are read before anything else, and a confirmed problem gets a fix or a documented workaround.

**Please do NOT:**
- Open a public GitHub issue for security vulnerabilities
- Exploit the vulnerability beyond what is necessary to demonstrate it

## Scope

Argus GCS is a ground control station that runs on a local network. Security concerns include:

- **WebSocket/REST API** — authentication bypass, injection, unauthorized command execution
- **MAVLink protocol handling** — malformed message processing, buffer overflows
- **File handling** — path traversal, arbitrary file read/write
- **Network** — SSRF, CORS misconfiguration
- **Dependencies** — known CVEs in third-party packages

## Running It Safely

- Argus listens on 127.0.0.1. Any other address needs `GCS_AUTH_TOKEN`, and it will not start without one: whoever reaches it can arm the vehicle.
- Without a token it answers only to a loopback name such as `localhost`, so that a web page cannot reach it through a name of its own (DNS rebinding). A page opened under another name needs its origin in `ARGUS_CORS_ORIGINS`.
- The token is one shared secret. Everyone who holds it can command the vehicle: the observer role keeps a second browser from sending commands by accident, and is not access control. Use a long random value.
- It speaks plain HTTP. On a network you do not trust, put it behind a TLS proxy, or the token and the commands can be read on the way.
- It does not sign MAVLink. Use a radio link with encryption of its own, or anyone on the frequency can send the vehicle commands.
- Video and NTRIP connect to the address you type, a private one included: that is where a vehicle's camera and an RTK base are. They refuse this machine itself, link-local addresses and cloud metadata services.
- Play only video streams you trust. That rule covers the address you type: ffmpeg then follows the redirects and playlists the server sends it, wherever they point.
- The Windows package is not code-signed. Check it against `SHA256SUMS.txt` and the build attestation of its release.
- The Windows package bundles its own Python and libraries, as they were on the day it was built. They are not updated in place: take the newest release.

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest release | Yes |
| Older releases | Best effort |
