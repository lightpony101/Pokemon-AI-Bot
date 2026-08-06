import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class Button(Enum):
    A = "A"
    B = "B"
    START = "START"
    SELECT = "SELECT"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    R = "R"
    L = "L"


BUTTONS: Set[str] = {b.value for b in Button}

ACTIONS: List[str] = [
    "A",
    "B",
    "START",
    "SELECT",
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "UP_A",
    "UP_B",
    "DOWN_A",
    "DOWN_B",
    "LEFT_A",
    "LEFT_B",
    "RIGHT_A",
    "RIGHT_B",
    "UP_START",
    "UP_SELECT",
]


def parse_action(raw: str) -> Optional[List[Button]]:
    """Parse a raw model response into a list of buttons to press."""
    cleaned = raw.strip().upper().replace(" ", "_").replace("-", "_")
    if cleaned not in ACTIONS:
        logger.warning("Model returned invalid action: %r", raw)
        return None
    buttons = []
    i = 0
    while i < len(cleaned):
        if cleaned[i:i + 3] == "UP_":
            buttons.append(Button.UP)
            i += 3
        elif cleaned[i:i + 4] == "DOWN_":
            buttons.append(Button.DOWN)
            i += 5
        elif cleaned[i:i + 5] == "LEFT_":
            buttons.append(Button.LEFT)
            i += 5
        elif cleaned[i:i + 6] == "RIGHT_":
            buttons.append(Button.RIGHT)
            i += 6
        elif cleaned[i:i + 3] == "UP\b":
            buttons.append(Button.UP)
            i += 2
        elif cleaned[i:i + 4] == "DOWN\b":
            buttons.append(Button.DOWN)
            i += 4
        elif cleaned[i:i + 5] == "LEFT\b":
            buttons.append(Button.LEFT)
            i += 4
        elif cleaned[i:i + 6] == "RIGHT\b":
            buttons.append(Button.RIGHT)
            i += 5
        elif cleaned == "A":
            buttons.append(Button.A)
            i += 1
        elif cleaned == "B":
            buttons.append(Button.B)
            i += 1
        elif cleaned == "START":
            buttons.append(Button.START)
            i += 5
        elif cleaned == "SELECT":
            buttons.append(Button.SELECT)
            i += 6
        elif cleaned == "R":
            buttons.append(Button.R)
            i += 1
        elif cleaned == "L":
            buttons.append(Button.L)
            i += 1
        else:
            remaining = cleaned[i:]
            for btn in ["UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT", "A", "B", "R", "L"]:
                if remaining.startswith(btn):
                    buttons.append(Button(btn))
                    i += len(btn)
                    break
            else:
                logger.warning("Could not parse action segment: %r", remaining)
                return None
    return buttons if buttons else None


def action_to_mgba_string(buttons: List[Button]) -> str:
    """Convert button list to mGBA joypad string format."""
    return ",".join(b.value for b in buttons)


def action_to_string(action_name: str) -> str:
    """Convert action name to a human-readable string."""
    buttons = parse_action(action_name)
    if not buttons:
        return action_name
    return "+".join(b.value for b in buttons)


@dataclass
class Action:
    """Represents a single game action with timing."""
    name: str
    buttons: List[Button]
    duration_ms: int = 100

    def __post_init__(self):
        if not self.buttons:
            raise ValueError("Action must have at least one button")
