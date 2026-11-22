"""Parse dollar amounts the way insurance documents write them."""
import re

_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(million|thousand|mm|m|k)?(?![A-Za-z])", re.I)
_MULT = {"million": 1_000_000, "mm": 1_000_000, "m": 1_000_000, "thousand": 1_000, "k": 1_000}


def find_money(text: str, start: int = 0):
    """First dollar amount at or after `start`. Returns (value, span_start, span_end) or None."""
    m = _MONEY.search(text, start)
    if not m:
        return None
    value = float(m.group(1).replace(",", "")) * _MULT.get((m.group(2) or "").lower(), 1)
    return int(round(value)), m.start(), m.end()


def parse_money(text: str) -> int | None:
    found = find_money(text)
    return found[0] if found else None
