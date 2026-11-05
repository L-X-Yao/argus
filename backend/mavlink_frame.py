"""MAVLink v2 frame construction for everything the GCS sends."""

import struct


def mc(b, e):
    c = 0xFFFF
    for x in b:
        t = x ^ (c & 0xFF)
        t ^= (t << 4) & 0xFF
        c = ((c >> 8) ^ (t << 8) ^ (t << 3) ^ (t >> 4)) & 0xFFFF
    t = e ^ (c & 0xFF)
    t ^= (t << 4) & 0xFF
    c = ((c >> 8) ^ (t << 8) ^ (t << 3) ^ (t >> 4)) & 0xFFFF
    return c


def bm(mid, p, s, ce, sysid=255, compid=1):
    # MAVLink 2 payload length is a single byte; >=256 would silently overflow
    # the header field, producing a malformed frame that the FC would reject
    # (or worse, parse the next bytes as the next frame). Reject early with a
    # clear ValueError — callers should chunk large payloads themselves.
    if len(p) > 255:
        raise ValueError("MAVLink payload too long: %d bytes (max 255)" % len(p))
    h = bytes([len(p), 0, 0, s & 0xFF, sysid & 0xFF, compid & 0xFF, mid & 0xFF, (mid >> 8) & 0xFF, (mid >> 16) & 0xFF])
    return b"\xfd" + h + p + struct.pack("<H", mc(h + p, ce))
