#!/usr/bin/env python3
"""Entry point for the GBA AI Player pipeline."""

import logging
import signal
import sys
from typing import Optional

from src.config import Config, ConfigError
from src.keyboard_bridge import KeyboardBridge, KeyboardBridgeError
from src.state_capture import StateCapture, ScreenCaptureError
from src.model_client import ModelClient, ModelClientError
from src.decision_loop import DecisionLoop
from src.action_space import ACTIONS

logger = logging.getLogger("gba_ai_player")


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def check_prerequisites(config) -> bool:
    """Verify that required tools and models are available."""
    import shutil
    import requests

    exe = config["emulator"]["executable"]
    if not shutil.which(exe):
        logger.error("Emulator executable '%s' not found in PATH", exe)
        logger.error("Install mGBA: https://mgba.io/downloads.html")
        return False

    base_url = config["model"]["base_url"]
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5.0)
        if resp.status_code != 200:
            logger.error("Ollama server not responding at %s", base_url)
            return False
    except Exception:
        logger.error("Cannot reach Ollama at %s. Start with: ollama serve", base_url)
        return False

    vision_model = config["model"]["vision_model"]
    text_model = config["model"]["text_model"]
    models = {m["name"] for m in resp.json().get("models", [])}
    missing = []
    if vision_model not in models:
        missing.append(f"ollama pull {vision_model}")
    if text_model not in models:
        missing.append(f"ollama pull {text_model}")
    if missing:
        logger.warning("Missing models. Run: %s", "; ".join(missing))
        logger.warning("Proceeding anyway; model calls may fail until models are pulled.")

    return True


def main(config_path: Optional[str] = None) -> int:
    setup_logging()
    try:
        config = Config(config_path)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    if not check_prerequisites(config):
        return 1

    emulator_cfg = config["emulator"]
    model_cfg = config["model"]

    keyboard_bridge = KeyboardBridge(
        window_title_pattern=emulator_cfg["window_title_pattern"],
        action_duration_ms=emulator_cfg.get("action_duration_ms", 100),
    )

    state_capture = StateCapture(
        capture_region=emulator_cfg["capture_region"],
        window_title_pattern=emulator_cfg["window_title_pattern"],
    )

    model_client = ModelClient(
        base_url=model_cfg["base_url"],
        model=model_cfg["model"],
        vision_model=model_cfg["vision_model"],
        text_model=model_cfg["text_model"],
        context_window=model_cfg["context_window"],
        temperature=model_cfg["temperature"],
        request_timeout=model_cfg["request_timeout"],
        max_retries=model_cfg["max_retries"],
        retry_delay=model_cfg["retry_delay"],
    )

    if not model_client.check_health():
        logger.warning("Model health check failed; continuing but inference may fail")

    loop = DecisionLoop(
        bridge=keyboard_bridge,
        state_capture=state_capture,
        model_client=model_client,
        action_space=ACTIONS,
        config=config.as_dict(),
    )

    def handle_signal(signum, frame):
        logger.info("Received signal %d, shutting down...", signum)
        loop.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("=" * 60)
    logger.info("GBA AI Player (Keyboard Mode)")
    logger.info("  Emulator: %s", emulator_cfg["executable"])
    logger.info("  Model:    %s / %s", model_cfg["vision_model"], model_cfg["text_model"])
    logger.info("  Actions:  %s", ", ".join(ACTIONS))
    logger.info("=" * 60)

    try:
        state_capture.detect_window()
        loop.run()
    except KeyboardBridgeError as exc:
        logger.error("Keyboard bridge error: %s", exc)
        return 1
    except ScreenCaptureError as exc:
        logger.error("Screen capture error: %s", exc)
        return 1
    except ModelClientError as exc:
        logger.error("Model client error: %s", exc)
        return 1
    finally:
        keyboard_bridge.close()

    return 0


if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(config_file))
