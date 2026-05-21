"""Tests for backend/connection.py — transport layer parsing and construction."""
from unittest.mock import MagicMock, patch

from backend.connection import TcpWrapper, UdpWrapper, open_port


class TestOpenPortParsing:
    def test_tcp_returns_tcp_wrapper(self):
        mock_sock = MagicMock()
        with patch('backend.connection.socket.socket', return_value=mock_sock):
            result = open_port('tcp:localhost:5770', 57600)
        assert isinstance(result, TcpWrapper)
        mock_sock.connect.assert_called_once_with(('localhost', 5770))

    def test_tcp_custom_host_port(self):
        mock_sock = MagicMock()
        with patch('backend.connection.socket.socket', return_value=mock_sock):
            result = open_port('tcp:192.168.1.100:14550', 57600)
        assert isinstance(result, TcpWrapper)
        mock_sock.connect.assert_called_once_with(('192.168.1.100', 14550))

    def test_udp_with_port_only(self):
        mock_sock = MagicMock()
        with patch('backend.connection.socket.socket', return_value=mock_sock):
            result = open_port('udp:14550', 57600)
        assert isinstance(result, UdpWrapper)

    def test_udp_with_host_and_port(self):
        mock_sock = MagicMock()
        with patch('backend.connection.socket.socket', return_value=mock_sock):
            result = open_port('udp:0.0.0.0:14550', 57600)
        assert isinstance(result, UdpWrapper)

    def test_serial_fallback(self):
        mock_serial = MagicMock()
        with patch('serial.Serial', return_value=mock_serial):
            result = open_port('/dev/ttyUSB0', 115200)
        assert result is mock_serial


class TestTcpWrapper:
    def test_read_returns_bytes(self):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'\xfe\x09'
        wrapper = TcpWrapper(mock_sock)
        assert wrapper.read(1024) == b'\xfe\x09'

    def test_read_timeout_returns_empty(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = TimeoutError
        wrapper = TcpWrapper(mock_sock)
        assert wrapper.read(1024) == b''

    def test_write_calls_sendall(self):
        mock_sock = MagicMock()
        wrapper = TcpWrapper(mock_sock)
        wrapper.write(b'\x01\x02')
        mock_sock.sendall.assert_called_once_with(b'\x01\x02')

    def test_close(self):
        mock_sock = MagicMock()
        wrapper = TcpWrapper(mock_sock)
        wrapper.close()
        mock_sock.close.assert_called_once()
