import logging
import shutil
import subprocess
import time
from typing import List, Optional

from src.action_space import Button

logger = logging.getLogger(__name__)


class KeyboardBridgeError(Exception):
    pass


class KeyboardBridge:
    """Sends GBA button presses to mGBA using xdotool (X11) or wtype (Wayland).

    mGBA default keyboard mapping:
      A → x, B → z, Start → Return, Select → Shift_L
      Up/Down/Left/Right → arrow keys
      L → a, R → s
    """

    KEY_MAP = {
        Button.A: "x",
        Button.B: "z",
        Button.START: "Return",
        Button.SELECT: "Shift_L",
        Button.UP: "Up",
        Button.DOWN: "Down",
        Button.LEFT: "Left",
        Button.RIGHT: "Right",
        Button.L: "a",
        Button.R: "s",
    }

    def __init__(self, window_title_pattern: str = "mGBA", action_duration_ms: int = 100):
        self.window_title_pattern = window_title_pattern
        self.action_duration_ms = action_duration_ms
        self._window_id: Optional[str] = None
        self._backend = self._detect_backend()
        logger.info("Keyboard bridge backend: %s", self._backend)

    def _detect_backend(self) -> str:
        if shutil.which("xdotool"):
            return "xdotool"
        if shutil.which("wtype"):
            return "wtype"
        raise KeyboardBridgeError(
            "No keyboard backend found. Install xdotool (X11) or wtype (Wayland):\n"
            "  sudo dnf install xdotool    # for X11/XWayland\n"
            "  sudo dnf install wtype      # for Wayland"
        )

    def _find_window(self) -> Optional[str]:
        """Find the mGBA window ID using the configured backend."""
        if self._backend == "xdotool":
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--name", self.window_title_pattern],
                    capture_output=True, text=True, timeout=5.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0]
            except Exception as exc:
                logger.warning("Window search failed: %s", exc)
        elif self._backend == "wtype":
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--name", self.window_title_pattern],
                    capture_output=True, text=True, timeout=5.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0]
            except Exception:
                pass
        return None

    def _ensure_window(self) -> str:
        if self._window_id is None:
            win = self._find_window()
            if not win:
                raise KeyboardBridgeError(
                    f"Cannot find mGBA window matching '{self.window_title_pattern}'. "
                    "Make sure mGBA is running."
                )
            self._window_id = win
            logger.info("Found mGBA window: %s", self._window_id)
        return self._window_id

    def send_action(self, action_name: str) -> None:
        """Send an action to mGBA by simulating keyboard input."""
        from src.action_space import parse_action
        buttons = parse_action(action_name)
        if not buttons:
            logger.error("Refusing to send invalid action: %r", action_name)
            return

        win = self._ensure_window()
        duration = self.action_duration_ms / 1000.0

        if self._backend == "xdotool":
            self._send_xdotool(win, buttons, duration)
        elif self._backend == "wtype":
            self._send_wtype(buttons, duration)

    def _send_xdotool(self, window_id: str, buttons: List[Button], duration: float) -> None:
        """Use xdotool to send key events to the mGBA window."""
        keys = [self.KEY_MAP[b] for b in buttons if b in self.KEY_MAP]
        if not keys:
            return

        try:
            # Focus the window first
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", window_id],
                capture_output=True, timeout=2.0,
            )

            # For single key, use key press with optional delay
            if len(keys) == 1:
                subprocess.run(
                    ["xdotool", "windowactivate", "--sync", window_id,
                     "key", "--clearmodifiers", "--delay", str(int(self.action_duration_ms)), keys[0]],
                    capture_output=True, timeout=5.0,
                )
            else:
                # Multiple simultaneous keys: keydown all, sleep, keyup all
                keydown_cmd = ["xdotool", "windowactivate", "--sync", window_id,
                               "keydown", "--clearmodifiers"] + keys
                keyup_cmd = ["xdotool", "windowactivate", "--sync", window_id,
                             "keyup", "--clearmodifiers"] + list(reversed(keys))

                subprocess.run(keydown_cmd, capture_output=True, timeout=2.0)
                time.sleep(duration)
                subprocess.run(keyup_cmd, capture_output=True, timeout=2.0)

        except subprocess.TimeoutExpired:
            logger.error("xdotool command timed out")
            self._window_id = None
        except Exception as exc:
            logger.error("xdotool failed: %s", exc)
            self._window_id = None

    def _send_wtype(self, buttons: List[Button], duration: float) -> None:
        """Use wtype for Wayland (global input, no window targeting)."""
        keys = [self.KEY_MAP[b] for b in buttons if b in self.KEY_MAP]
        if not keys:
            return

        try:
            for key in keys:
                subprocess.run(["wtype", "-k", key], capture_output=True, timeout=2.0)
            time.sleep(duration)
            for key in reversed(keys):
                subprocess.run(["wtype", "-k", key], capture_output=True, timeout=2.0)
        except Exception as exc:
            logger.error("wtype failed: %s", exc)

    def close(self) -> None:
        self._window_id = None
        logger.info("Keyboard bridge closed")
