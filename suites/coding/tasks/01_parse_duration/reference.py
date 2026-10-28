import re

_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
_ORDER = "wdhms"


def parse_duration(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError("not a string")
    text = s.strip()
    if not text:
        raise ValueError("empty")
    pos, total, last = 0, 0, -1
    pattern = re.compile(r"\s*(\d+)([a-zA-Z])")
    while pos < len(text):
        m = pattern.match(text, pos)
        if not m:
            raise ValueError(f"invalid at {pos}")
        unit = m.group(2).lower()
        if unit not in _UNITS:
            raise ValueError(f"unknown unit {unit}")
        idx = _ORDER.index(unit)
        if idx <= last:
            raise ValueError("order")
        last = idx
        total += int(m.group(1)) * _UNITS[unit]
        pos = m.end()
    return total
