Implement `parse_duration(s: str) -> int` that converts a human duration string into a number of seconds.

Rules:
- A duration is one or more components `<non-negative integer><unit>`, units are `w` (week), `d` (day), `h` (hour), `m` (minute), `s` (second). Units are case-insensitive.
- Components must appear in strictly decreasing unit order (w, d, h, m, s) and each unit at most once.
- Whitespace is allowed between components and at the beginning/end of the string, but not between a number and its unit.
- Anything else (empty string, unknown unit, missing number, sign, decimal numbers, repeated or out-of-order units, number without unit) must raise `ValueError`.

Examples: `"1h30m"` -> 5400, `"2d 3h"` -> 183600, `"1W"` -> 604800, `"0s"` -> 0.
