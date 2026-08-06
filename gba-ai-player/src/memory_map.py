"""Memory map definitions for supported GBA Pokémon ROMs.

All addresses are for the EU/US FireRed 1.0 and Emerald 1.0 unless noted.
Addresses are typically 32-bit (IWRAM/EWRAM) or 8/16-bit I/O.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryMap:
    name: str
    rom_title: str
    player_x: int
    player_y: int
    current_map: int
    battle_state: int
    menu_state: int
    player_money: int
    party_count: int
    party_hp_start: int
    facing_direction: int
    warp_flag: int

    def __post_init__(self):
        pass


FIRE_RED = MemoryMap(
    name="FireRed",
    rom_title="POKEMON FIRE",
    player_x=0x02024A6C,
    player_y=0x02024A70,
    current_map=0x020244AC,
    battle_state=0x02000022,
    menu_state=0x0200002B,
    player_money=0x0200002E,
    party_count=0x020240C8,
    party_hp_start=0x020240CC,
    facing_direction=0x02024A74,
    warp_flag=0x02000024,
)

EMERALD = MemoryMap(
    name="Emerald",
    rom_title="POKEMON EMER",
    player_x=0x02024A6C,
    player_y=0x02024A70,
    current_map=0x020244AC,
    battle_state=0x02000022,
    menu_state=0x0200002B,
    player_money=0x0200002E,
    party_count=0x020240C8,
    party_hp_start=0x020240CC,
    facing_direction=0x02024A74,
    warp_flag=0x02000024,
)

LEAF_GREEN = MemoryMap(
    name="LeafGreen",
    rom_title="POKEMON LEAF",
    player_x=0x02024A6C,
    player_y=0x02024A70,
    current_map=0x020244AC,
    battle_state=0x02000022,
    menu_state=0x0200002B,
    player_money=0x0200002E,
    party_count=0x020240C8,
    party_hp_start=0x020240CC,
    facing_direction=0x02024A74,
    warp_flag=0x02000024,
)

RUBY = MemoryMap(
    name="Ruby",
    rom_title="POKEMON RUBY",
    player_x=0x02024A6C,
    player_y=0x02024A70,
    current_map=0x020244AC,
    battle_state=0x02000022,
    menu_state=0x0200002B,
    player_money=0x0200002E,
    party_count=0x020240C8,
    party_hp_start=0x020240CC,
    facing_direction=0x02024A74,
    warp_flag=0x02000024,
)

SAPPHIRE = MemoryMap(
    name="Sapphire",
    rom_title="POKEMON SAPP",
    player_x=0x02024A6C,
    player_y=0x02024A70,
    current_map=0x020244AC,
    battle_state=0x02000022,
    menu_state=0x0200002B,
    player_money=0x0200002E,
    party_count=0x020240C8,
    party_hp_start=0x020240CC,
    facing_direction=0x02024A74,
    warp_flag=0x02000024,
)

MEMORY_MAPS: Dict[str, MemoryMap] = {
    "FireRed": FIRE_RED,
    "Emerald": EMERALD,
    "LeafGreen": LEAF_GREEN,
    "Ruby": RUBY,
    "Sapphire": SAPPHIRE,
}


def get_memory_map(rom_title: str) -> MemoryMap:
    """Match a ROM title prefix to a memory map."""
    title_upper = rom_title.upper().strip()
    for mmap in MEMORY_MAPS.values():
        if title_upper.startswith(mmap.rom_title.upper()):
            logger.debug("Matched ROM '%s' to memory map '%s'", title_upper, mmap.name)
            return mmap
    logger.warning("No memory map found for ROM '%s', falling back to FireRed", title_upper)
    return FIRE_RED
