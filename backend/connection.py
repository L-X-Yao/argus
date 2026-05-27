"""Transport wrappers for TCP, UDP, and serial connections."""

from __future__ import annotations

import socket

from .config import cfg


class TcpWrapper:
    def __init__(self, sock: socket.socket):
        self._sock = sock

    def read(self, n: int) -> bytes:
        try:
            return self._sock.recv(n)
        except (TimeoutError, OSError):
            return b""

    def write(self, data: bytes) -> None:
        self._sock.sendall(data)

    def close(self) -> None:
        self._sock.close()


class UdpWrapper:
    def __init__(self, port: int, host: str = ""):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(cfg.UDP_READ_TIMEOUT)
        self._sock.bind((host or "", port))
        self._remote: tuple | None = None
        # Track when we last heard from _remote. If a different sender appears
        # while the current peer has been silent for `_PEER_HIJACK_GUARD`
        # seconds we follow the new peer (legitimate FC IP change). Otherwise
        # the new sender is ignored — an attacker can't inject one packet to
        # divert outbound commands to themselves (auditor finding).
        self._remote_last_seen: float = 0.0
        self._PEER_HIJACK_GUARD: float = 30.0

    def read(self, n: int) -> bytes:
        try:
            import time as _t

            data, addr = self._sock.recvfrom(n)
            now = _t.monotonic()
            if self._remote is None or (
                addr != self._remote and (now - self._remote_last_seen) > self._PEER_HIJACK_GUARD
            ):
                self._remote = addr
            elif addr != self._remote:
                # Same socket, different sender, current peer still active —
                # drop. Either a misdirected packet or an attempted hijack.
                return b""
            self._remote_last_seen = now
            return data
        except (TimeoutError, OSError):
            return b""

    def write(self, data: bytes) -> None:
        if self._remote:
            try:
                self._sock.sendto(data, self._remote)
            except OSError:
                pass

    def close(self) -> None:
        self._sock.close()


def open_port(port: str, baudrate: int):
    if port.startswith("udp:"):
        parts = port[4:].split(":")
        try:
            if len(parts) == 2:
                host, udp_port = parts[0], int(parts[1])
            else:
                host, udp_port = "", int(parts[0])
        except ValueError:
            raise OSError("Invalid UDP port: %s" % port)
        return UdpWrapper(udp_port, host)
    elif port.startswith("tcp:"):
        parts = port[4:].split(":")
        try:
            host, tcp_port = parts[0], int(parts[1])
        except (ValueError, IndexError):
            raise OSError("Invalid TCP address: %s" % port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(cfg.TCP_CONNECT_TIMEOUT)
        sock.connect((host, tcp_port))
        sock.settimeout(cfg.TCP_READ_TIMEOUT)
        return TcpWrapper(sock)
    else:
        import serial

        s = serial.Serial(port, baudrate, timeout=cfg.SERIAL_READ_TIMEOUT)
        s.reset_input_buffer()
        return s
