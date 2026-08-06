import base64
import io
import logging
import subprocess
import time
from typing import Dict, Optional, Tuple

import mss
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class ScreenCaptureError(Exception):
    pass


class StateCapture:
    """Captures screen frames from the mGBA window and assembles game state."""

    def __init__(self, capture_region: Dict[str, int], window_title_pattern: str = "mGBA"):
        self.capture_region = capture_region
        self.window_title_pattern = window_title_pattern
        self._sct = mss.mss()
        self._frame_count = 0
        self._last_frame_hash: Optional[str] = None
        self._detected_monitor: Optional[Dict[str, int]] = None

    def detect_window(self) -> Optional[Dict[str, int]]:
        """Try to detect the mGBA window geometry using xwininfo."""
        try:
            result = subprocess.run(
                ["xwininfo", "-root", "-tree"],
                capture_output=True, text=True, timeout=5.0,
            )
            if result.returncode != 0:
                logger.debug("xwininfo failed, using configured capture region")
                return None
            for line in result.stdout.splitlines():
                if self.window_title_pattern.lower() in line.lower():
                    logger.info("Found mGBA window: %s", line.strip())
                    geom = self._parse_xwininfo_geometry(result.stdout, line.strip())
                    if geom:
                        self._detected_monitor = geom
                        return geom
        except FileNotFoundError:
            logger.warning("xwininfo not found; using configured capture region")
        except Exception as exc:
            logger.warning("Window detection failed: %s", exc)
        return None

    def _parse_xwininfo_geometry(self, output: str, match_line: str) -> Optional[Dict[str, int]]:
        """Parse geometry from xwininfo output for a matched window."""
        try:
            win_id = match_line.split("(")[0].strip().split()[-1]
            result = subprocess.run(
                ["xwininfo", "-id", win_id],
                capture_output=True, text=True, timeout=5.0,
            )
            if result.returncode != 0:
                return None
            geom = {}
            for line in result.stdout.splitlines():
                if "Absolute upper-left X:" in line:
                    geom["x"] = int(line.split(":")[1].strip())
                elif "Absolute upper-left Y:" in line:
                    geom["y"] = int(line.split(":")[1].strip())
                elif "Width:" in line:
                    geom["width"] = int(line.split(":")[1].strip())
                elif "Height:" in line:
                    geom["height"] = int(line.split(":")[1].strip())
            if all(k in geom for k in ("x", "y", "width", "height")):
                logger.info("Detected window geometry: %s", geom)
                return geom
        except Exception as exc:
            logger.debug("Geometry parse failed: %s", exc)
        return None

    def capture_frame(self) -> Optional[Image.Image]:
        """Capture the current frame from the mGBA window."""
        monitor = self._detected_monitor or self.capture_region
        try:
            sct_monitor = {
                "top": monitor["y"],
                "left": monitor["x"],
                "width": monitor["width"],
                "height": monitor["height"],
            }
            raw = self._sct.grab(sct_monitor)
            img = Image.frombytes("RGB", raw.size, raw.rgb)
            self._frame_count += 1
            return img
        except Exception as exc:
            logger.error("Frame capture failed: %s", exc)
            raise ScreenCaptureError(f"Capture failed: {exc}") from exc

    def frame_to_base64(self, img: Image.Image, format: str = "PNG") -> str:
        """Encode a PIL Image to a base64 string."""
        buffered = io.BytesIO()
        img.save(buffered, format=format)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def frame_hash(self, img: Image.Image) -> str:
        """Compute a perceptual-ish hash for stuck-state detection."""
        small = img.resize((16, 16), Image.Resampling.LANCZOS).convert("L")
        arr = np.array(small, dtype=np.float32)
        avg = arr.mean()
        bits = (arr > avg).flatten()
        packed = np.packbits(bits)
        return packed.tobytes().hex()

    @property
    def frame_count(self) -> int:
        return self._frame_count
