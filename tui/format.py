"""Small formatting helpers shared across the TUI."""

from __future__ import annotations

import re

_WORD_DURATION = re.compile(
    r"(\d+)\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b", re.IGNORECASE)


def parse_duration(value) -> int:
    """Parse a duration: "h:mm:ss", "m:ss", seconds, or words.

    Podcast episodes report word forms like "25 min" or "1 hr 7 min".
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip()
    if not text:
        return 0
    if ":" in text:
        total = 0
        try:
            for part in text.split(":"):
                total = total * 60 + int(part)
        except ValueError:
            return 0
        return total
    words = _WORD_DURATION.findall(text)
    if words:
        total = 0
        for amount, unit in words:
            unit = unit.lower()
            if unit.startswith("h"):
                total += int(amount) * 3600
            elif unit.startswith("min"):
                total += int(amount) * 60
            elif unit.startswith("s"):
                total += int(amount)
        return total
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            break
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def total_duration_text(durations) -> str:
    total = sum(parse_duration(d) for d in durations)
    if total >= 3600:
        return f"{total // 3600} h {(total % 3600) // 60} min"
    if total >= 60:
        return f"{total // 60} min"
    return f"{total} s"
