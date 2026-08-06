import json
import logging
import socket
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class EmulatorBridgeError(Exception):
    """Raised on bridge communication failures."""


class EmulatorBridge:
    """TCP client that communicates with the mGBA Lua bridge script.

    Protocol: newline-delimited JSON over TCP.
    Lua acts as server, Python connects as client.
    """

    def __init__(self, host: str, port: int, connect_timeout: float = 10.0,
                 read_timeout: float = 0.05, reconnect_delay: float = 2.0,
                 max_reconnect_attempts: int = 10):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self._sock: Optional[socket.socket] = None
        self._reconnect_count = 0
        self._buffer = ""
        self._last_state: Optional[Dict[str, Any]] = None

    def connect(self) -> None:
        """Establish TCP connection to the Lua bridge."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        self._reconnect_count = 0
        self._attempt_connect()
        logger.info("Connected to emulator bridge at %s:%d", self.host, self.port)

    def _attempt_connect(self) -> None:
        while self._reconnect_count < self.max_reconnect_attempts:
            try:
                sock = socket.create_connection(
                    (self.host, self.port), timeout=self.connect_timeout
                )
                sock.settimeout(self.read_timeout)
                self._sock = sock
                self._buffer = ""
                self._reconnect_count = 0
                return
            except (OSError, socket.timeout) as exc:
                self._reconnect_count += 1
                logger.warning(
                    "Bridge connection attempt %d/%d failed: %s. Retrying in %.1fs...",
                    self._reconnect_count, self.max_reconnect_attempts, exc, self.reconnect_delay,
                )
                time.sleep(self.reconnect_delay)

        raise EmulatorBridgeError(
            f"Failed to connect to bridge after {self.max_reconnect_attempts} attempts"
        )

    def _ensure_connected(self) -> None:
        if self._sock is None:
            logger.info("Socket disconnected, attempting reconnect...")
            self._attempt_connect()

    def send_action(self, action_name: str) -> None:
        """Send an action command to the emulator."""
        from src.action_space import parse_action, action_to_mgba_string
        buttons = parse_action(action_name)
        if buttons is None:
            logger.error("Refusing to send invalid action: %r", action_name)
            return

        payload = {
            "type": "action",
            "buttons": action_to_mgba_string(buttons),
        }
        self._send_json(payload)
        logger.debug("Sent action: %s -> %s", action_name, action_to_mgba_string(buttons))

    def read_state(self) -> Optional[Dict[str, Any]]:
        """Non-blocking read of the latest state from the emulator."""
        self._ensure_connected()
        if self._sock is None:
            return None

        try:
            data = self._sock.recv(4096)
            if not data:
                logger.warning("Bridge socket closed by peer")
                self._sock = None
                return None
            self._buffer += data.decode("utf-8", errors="replace")
        except socket.timeout:
            pass
        except OSError as exc:
            logger.warning("Socket read error: %s", exc)
            self._sock = None
            return None

        self._buffer, states = self._extract_json_lines(self._buffer)
        for state in states:
            self._last_state = state

        return self._last_state

    def _send_json(self, payload: Dict[str, Any]) -> None:
        """Send a JSON object terminated by newline."""
        self._ensure_connected()
        if self._sock is None:
            raise EmulatorBridgeError("Not connected to emulator bridge")
        try:
            line = json.dumps(payload, separators=(",", ":")) + "\n"
            self._sock.sendall(line.encode("utf-8"))
        except OSError as exc:
            logger.error("Failed to send to bridge: %s", exc)
            self._sock = None
            raise EmulatorBridgeError(f"Send failed: {exc}") from exc

    def _extract_json_lines(self, buffer: str):
        """Extract complete JSON lines from a buffer, return (remaining, parsed_objects)."""
        lines = buffer.split("\n")
        parsed = []
        for line in lines[:-1]:
            line = line.strip()
            if not line:
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug("Incomplete JSON in buffer, waiting for more data")
        return lines[-1], parsed

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        logger.info("Emulator bridge closed")
