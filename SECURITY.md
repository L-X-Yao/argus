# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Argus GCS, please report it responsibly.

**On GitHub, in private (preferred):** open the [Security tab](https://github.com/L-X-Yao/argus/security) and choose "Report a vulnerability", or go straight to the [report form](https://github.com/L-X-Yao/argus/security/advisories/new). Only the maintainer sees the report.

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

Fixed vulnerabilities are published as [security advisories](https://github.com/L-X-Yao/argus/security/advisories).

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
- A file you open (a mission, a fence, a KML overlay, a log) is read as data. A field of the wrong type is refused, a name from a file is shown as text, and the page takes its scripts from Argus itself only, so markup inside a file does not run. That says nothing about the route in it: read a mission from someone else before you fly it.
- Play only video streams you trust. That rule covers the address you type: ffmpeg then follows the redirects and playlists the server sends it, wherever they point.
- An AI assistant (`backend/mcp_server.py`) reads what the page shows and can only ask for changes. Each one waits for the operator's approval in the page, none is taken while the vehicle is armed, and it cannot arm, take off or change mode. It connects as a page does, with the token when Argus has one. What it reads goes to its AI provider. A note from the assistant is shown with its request: judge what the request does, not the note.
- The Windows package and its installer are not code-signed. Check them against `SHA256SUMS.txt` and the build attestation of their release.
- The Windows package and its installer bundle their own Python and libraries, as they were on the day they were built. They are not updated in place: take the newest release. The installer puts the program in a folder of your account, which any program running as you can change.

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest release | Yes |
| Older releases | Best effort |
