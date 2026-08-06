import base64
import hashlib
import io
import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class ModelClientError(Exception):
    pass


class ModelClient:
    """Client for local LLM inference (Ollama or compatible API)."""

    def __init__(
        self,
        base_url: str,
        model: str,
        vision_model: str,
        text_model: str,
        context_window: int = 8192,
        temperature: float = 0.7,
        request_timeout: float = 60.0,
        max_retries: int = 2,
        retry_delay: float = 2.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.vision_model = vision_model
        self.text_model = text_model
        self.context_window = context_window
        self.temperature = temperature
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session = requests.Session()

    def check_health(self) -> bool:
        """Check if the Ollama server is running and the model is available."""
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=5.0)
            if resp.status_code != 200:
                return False
            models = resp.json().get("models", [])
            model_names = {m["name"] for m in models}
            needed = {self.vision_model, self.text_model, self.model}
            missing = needed - model_names
            if missing:
                logger.warning("Missing models: %s. Available: %s", missing, model_names)
            return len(missing) == 0
        except Exception as exc:
            logger.error("Ollama health check failed: %s", exc)
            return False

    def decide(
        self,
        state_text: str,
        frame_b64: Optional[str] = None,
        system_prompt: str = "",
    ) -> str:
        """Send state to the model and return the raw action string.

        If frame_b64 is provided, attempts the vision model first. If the model
        does not support images, falls back to the text model without the image.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content: Any
        if frame_b64:
            user_content = [
                {"type": "text", "text": state_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{frame_b64}",
                    },
                },
            ]
        else:
            user_content = state_text

        messages.append({"role": "user", "content": user_content})

        last_exc = None
        model_name = self.vision_model if frame_b64 else self.text_model

        for attempt in range(1, self.max_retries + 1):
            try:
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_ctx": self.context_window,
                    },
                }
                resp = self._session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.request_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("message", {}).get("content", "").strip()
                if not raw:
                    raise ModelClientError("Model returned empty response")
                logger.debug("Model raw response: %r", raw)
                return raw
            except ModelClientError:
                raise
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                is_vision_error = (
                    frame_b64
                    and model_name == self.vision_model
                    and ("does not support image input" in err_str or "image" in err_str)
                )
                if is_vision_error and attempt < self.max_retries:
                    logger.warning(
                        "Vision model '%s' rejected image input (%s). "
                        "Falling back to text-only model '%s'.",
                        model_name, exc, self.text_model,
                    )
                    model_name = self.text_model
                    messages[-1]["content"] = state_text
                    frame_b64 = None
                    continue
                logger.warning("Model request attempt %d/%d failed: %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

        raise ModelClientError(f"All retries failed: {last_exc}")

    def extract_action(self, raw_response: str, valid_actions: List[str]) -> str:
        """Extract a valid action token from the model's raw response."""
        upper = raw_response.upper().strip()
        for action in valid_actions:
            if action.upper() in upper:
                return action
        words = upper.split()
        for word in words:
            for action in valid_actions:
                if action.upper() == word or action.upper().replace("_", " ") == word:
                    return action
        logger.warning("Could not extract action from response: %r", raw_response)
        return "DOWN"
