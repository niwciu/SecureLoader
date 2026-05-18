"""Product-ID section definitions.

A 64-bit ``productId`` is represented as a 16-character uppercase hex string.
:class:`IdSectionDef` names a contiguous slice of that string at nibble
(hex-digit) granularity, allowing users to mirror any server directory layout.

Default layout (matches the original hard-coded convention)::

    hex position:  0  1  2  3  4  5  6  7    8  9 10 11 12 13 14 15
                   ╔══════════════════════╗  ╔══╗ ╔══╗  ╔════════╗
                   ║  custom_id  [0:8]   ║  ║hw║ ║lic║  ║unique  ║
                   ╚══════════════════════╝  ╚══╝ ╚══╝  ╚════════╝

Config key: ``[product_id] sections = name:start:end, …`` (comma-separated).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

_HEX_LEN: int = 16


@dataclass(frozen=True, slots=True)
class IdSectionDef:
    """One named slice of the 16-nibble product ID hex string.

    Positions are 0-based indices into the zero-padded 16-character uppercase
    hex representation of the 64-bit ``productId``.  Slicing follows Python
    convention (left-inclusive, right-exclusive), so
    ``IdSectionDef("lic", 10, 12)`` extracts nibbles at positions 10 and 11.

    Constraints: ``0 <= start < end <= 16``.
    """

    name: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("section name must not be empty")
        if not (0 <= self.start < self.end <= _HEX_LEN):
            raise ValueError(
                f"invalid nibble range [{self.start}:{self.end}] for section {self.name!r}; "
                f"must satisfy 0 <= start < end <= {_HEX_LEN}"
            )

    def extract(self, hex_id: str) -> str:
        """Return the nibbles ``[start:end]`` from a 16-char uppercase hex string."""
        return hex_id[self.start : self.end]


DEFAULT_ID_SECTIONS: list[IdSectionDef] = [
    IdSectionDef("custom_id", 0, 8),
    IdSectionDef("hw_id", 8, 10),
    IdSectionDef("license_id", 10, 12),
    IdSectionDef("unique_id", 12, 16),
]
"""Default four-section layout matching the original hard-coded convention."""


def serialize_id_sections(defs: list[IdSectionDef]) -> str:
    """Serialize section definitions to the INI config string format.

    Format: ``name:start:end,name:start:end,…``
    """
    return ",".join(f"{d.name}:{d.start}:{d.end}" for d in defs)


def parse_id_sections(s: str) -> list[IdSectionDef]:
    """Parse a comma-separated list of ``name:start:end`` section definitions.

    Returns :data:`DEFAULT_ID_SECTIONS` when ``s`` is blank.  Raises
    :class:`ValueError` on malformed input; the caller should log and fall
    back to defaults.
    """
    s = s.strip()
    if not s:
        return list(DEFAULT_ID_SECTIONS)

    result: list[IdSectionDef] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":")
        if len(pieces) != 3:
            raise ValueError(f"expected NAME:START:END, got {part!r}")
        name, start_s, end_s = pieces
        try:
            result.append(IdSectionDef(name.strip(), int(start_s), int(end_s)))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid section definition {part!r}: {exc}") from exc

    return result if result else list(DEFAULT_ID_SECTIONS)
