import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GameState:
    """Structured representation of the current game state."""
    frame: int
    map_id: int = 0
    player_x: int = 0
    player_y: int = 0
    facing: str = "down"
    battle_state: str = "none"
    menu_state: str = "overworld"
    party_hp: List[int] = None
    money: int = 0
    warp_flag: int = 0
    frame_hash: str = ""
    timestamp: float = 0.0
    raw_bridge_data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.party_hp is None:
            self.party_hp = []

    def to_text(self) -> str:
        """Serialize state to a human-readable text summary for the model."""
        lines = [
            f"Frame: {self.frame}",
            f"Map: {self.map_id}",
            f"Player position: ({self.player_x}, {self.player_y}), facing {self.facing}",
            f"Battle state: {self.battle_state}",
            f"Menu state: {self.menu_state}",
            f"Money: {self.money}",
        ]
        if self.party_hp:
            hp_str = ", ".join(f"{hp}/max" for hp in self.party_hp[:6])
            lines.append(f"Party HP: [{hp_str}]")
        return "\n".join(lines)


class StuckDetector:
    """Detects when the agent is stuck in a loop."""

    def __init__(self, threshold: int = 6, window_seconds: float = 30.0):
        self.threshold = threshold
        self.window_seconds = window_seconds
        self._history: deque = deque()

    def record(self, state: GameState) -> Optional[str]:
        """Record a state and return a hint if stuck, else None."""
        now = time.time()
        key = self._state_key(state)
        self._history.append((now, key))

        cutoff = now - self.window_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        counts: Dict[str, int] = {}
        for _, k in self._history:
            counts[k] = counts.get(k, 0) + 1

        most_common = max(counts.items(), key=lambda x: x[1]) if counts else ("", 0)
        if most_common[1] >= self.threshold:
            logger.warning(
                "Stuck detected: state %r appeared %d times in %.1fs window",
                most_common[0], most_common[1], self.window_seconds,
            )
            return most_common[0]
        return None

    def _state_key(self, state: GameState) -> str:
        return f"map={state.map_id}:x={state.player_x}:y={state.player_y}:battle={state.battle_state}:menu={state.menu_state}"

    def reset(self) -> None:
        self._history.clear()


class DecisionLoop:
    """Main orchestrator connecting state capture, model inference, and emulator input.

    Model inference runs asynchronously in a background thread so that emulator
    state capture and input application are never blocked by model latency.
    """

    def __init__(
        self,
        bridge: Any,
        state_capture: Any,
        model_client: Any,
        action_space: List[str],
        config: Dict[str, Any],
    ):
        self.bridge = bridge
        self.state_capture = state_capture
        self.model_client = model_client
        self.action_space = action_space
        self.config = config
        self._running = False

        self._pending_action: Optional[str] = None
        self._inference_lock = threading.Lock()
        self._inference_pending = False
        self._last_action: str = ""
        self._consecutive_same: int = 0

        self._decision_interval = config.get("loop", {}).get("decision_interval", 1.5)
        self._action_duration_ms = config.get("loop", {}).get("action_duration_ms", 100)
        self._max_consecutive_same = config.get("loop", {}).get("max_consecutive_same", 4)
        self._stuck_threshold = config.get("loop", {}).get("stuck_threshold", 6)
        self._stuck_window = config.get("loop", {}).get("stuck_state_window", 30.0)
        self._system_prompt = config.get("prompt", {}).get("system_prompt", "")

        self._stuck_detector = StuckDetector(
            threshold=self._stuck_threshold,
            window_seconds=self._stuck_window,
        )
        self._state_history: deque = deque(maxlen=20)

    def run(self) -> None:
        """Run the main decision loop until stopped."""
        self._running = True
        logger.info("Starting decision loop (interval=%.1fs)", self._decision_interval)

        last_decision = 0.0
        last_state: Optional[GameState] = None
        last_screen: Any = None

        try:
            while self._running:
                loop_start = time.time()

                # 1. Capture state from bridge (if available) and screen
                bridge_state = None
                if hasattr(self.bridge, "read_state"):
                    bridge_state = self.bridge.read_state()
                screen_img = None
                try:
                    screen_img = self.state_capture.capture_frame()
                    last_screen = screen_img
                except Exception as exc:
                    logger.warning("Screen capture error: %s", exc)

                state = self._assemble_state(bridge_state, screen_img, last_state)
                last_state = state

                stuck_key = None
                if state:
                    self._state_history.append(state)
                    stuck_key = self._stuck_detector.record(state)

                # 2. Decide whether to query the model (async, non-blocking)
                should_decide = False
                if state and not self._inference_pending:
                    elapsed = time.time() - last_decision
                    if elapsed >= self._decision_interval:
                        should_decide = True
                    elif stuck_key:
                        should_decide = True
                        logger.info("Triggering early decision due to stuck state")

                if should_decide and state:
                    self._start_inference(state, last_screen)
                    last_decision = time.time()
                    self._stuck_detector.reset()

                # 3. Check for pending action to apply
                action_to_apply = None
                with self._inference_lock:
                    if self._pending_action:
                        action_to_apply = self._pending_action
                        self._pending_action = None

                if action_to_apply:
                    if action_to_apply == self._last_action:
                        self._consecutive_same += 1
                    else:
                        self._consecutive_same = 0
                    self._last_action = action_to_apply
                    self._apply_action(action_to_apply)

                    if self._consecutive_same >= self._max_consecutive_same:
                        logger.info("Too many repeated actions (%d), injecting exploration next cycle",
                                    self._consecutive_same)

                elapsed = time.time() - loop_start
                target_sleep = max(0.0, (1.0 / 30.0) - elapsed)
                if target_sleep > 0:
                    time.sleep(target_sleep)

        except KeyboardInterrupt:
            logger.info("Decision loop interrupted")
        finally:
            self.stop()

    def _assemble_state(
        self,
        bridge_state: Optional[Dict[str, Any]],
        screen_img: Any,
        previous: Optional[GameState],
    ) -> Optional[GameState]:
        if bridge_state is None and screen_img is None:
            return None

        frame_hash = ""
        if screen_img:
            frame_hash = self.state_capture.frame_hash(screen_img)

        frame = bridge_state.get("frame", 0) if bridge_state else 0

        if bridge_state is None and previous is not None:
            return GameState(
                frame=frame, frame_hash=frame_hash, timestamp=time.time(),
                player_x=previous.player_x, player_y=previous.player_y,
                map_id=previous.map_id, battle_state=previous.battle_state,
                menu_state=previous.menu_state,
            )

        if bridge_state is None:
            return GameState(frame=frame, frame_hash=frame_hash, timestamp=time.time())

        battle_map = {0: "none", 1: "active", 2: "transition"}
        menu_map = {0: "overworld", 1: "menu", 2: "bag", 3: "pokemon", 4: "save", 5: "option", 6: "battle_menu"}
        facing_map = {0: "down", 1: "up", 2: "left", 3: "right"}

        return GameState(
            frame=bridge_state.get("frame", frame),
            map_id=bridge_state.get("map", 0),
            player_x=bridge_state.get("x", 0),
            player_y=bridge_state.get("y", 0),
            facing=facing_map.get(bridge_state.get("facing", 0), "unknown"),
            battle_state=battle_map.get(bridge_state.get("battle", 0), "unknown"),
            menu_state=menu_map.get(bridge_state.get("menu", 0), "unknown"),
            party_hp=bridge_state.get("party_hp", []),
            money=bridge_state.get("money", 0),
            warp_flag=bridge_state.get("warp", 0),
            frame_hash=frame_hash,
            timestamp=time.time(),
            raw_bridge_data=bridge_state,
        )

    def _start_inference(self, state: GameState, screen_img: Any) -> None:
        """Launch async model inference in a daemon thread."""
        with self._inference_lock:
            if self._inference_pending:
                logger.debug("Inference already pending, skipping")
                return
            self._inference_pending = True

        explore = self._consecutive_same >= self._max_consecutive_same

        def _infer():
            try:
                if explore:
                    logger.info("Injecting exploration action due to stuck state")
                    action = self._explore_action(state)
                else:
                    state_text = state.to_text()
                    frame_b64 = None
                    if screen_img:
                        try:
                            frame_b64 = self.state_capture.frame_to_base64(screen_img)
                        except Exception as exc:
                            logger.warning("Failed to encode frame: %s", exc)

                    raw = self.model_client.decide(
                        state_text=state_text,
                        frame_b64=frame_b64,
                        system_prompt=self._system_prompt,
                    )
                    action = self.model_client.extract_action(raw, self.action_space)
                    logger.info("Model chose action: %s", action)
            except Exception as exc:
                logger.error("Decision failed: %s", exc)
                action = "DOWN"

            with self._inference_lock:
                self._pending_action = action
                self._inference_pending = False

        thread = threading.Thread(target=_infer, daemon=True, name="model-inference")
        thread.start()

    def _explore_action(self, state: GameState) -> str:
        import random
        candidates = [a for a in self.action_space if a not in ("START", "SELECT")]
        return random.choice(candidates) if candidates else "DOWN"

    def _apply_action(self, action: str) -> None:
        try:
            self.bridge.send_action(action)
            logger.info("Applied action: %s", action)
        except Exception as exc:
            logger.error("Failed to apply action %s: %s", action, exc)

    def stop(self) -> None:
        self._running = False
        logger.info("Decision loop stopped")

    @property
    def running(self) -> bool:
        return self._running
