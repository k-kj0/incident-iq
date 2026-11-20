"""Explainable account scoring. Every point in the score has a sentence attached."""
from dataclasses import dataclass
from datetime import datetime, timezone

# signal -> (points, phrase shown to the rep)
SIGNAL_WEIGHTS: dict[str, tuple[int, str]] = {
    "customer_asked_for_certification": (30, "one of their customers asked them for a security certification"),
    "hiring_security_role": (25, "hiring for a security or compliance role"),
    "mentions_soc2_or_iso": (20, "mentions SOC 2 / ISO 27001 publicly"),
    "recent_funding": (15, "raised funding recently"),
    "no_trust_center": (10, "no public trust center"),
}

EUROPE = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "GB", "CH", "NO", "IS", "LI",
}
SIZE_MIN, SIZE_MAX = 20, 500
RECENT_TOUCH_DAYS = 7
STALE_TOUCH_DAYS = 30
CALL_THRESHOLD = 50


@dataclass(frozen=True)
class ScoreResult:
    score: int
    recommendation: str   # coordinate | wait | call_today | nurture
    reasons: list[str]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def score_account(*, signals: list[str], country: str | None, employee_count: int | None,
                  owners: list[str], last_touch_at: datetime | None,
                  now: datetime) -> ScoreResult:
    score = 0
    reasons: list[str] = []

    known = sorted((s for s in set(signals) if s in SIGNAL_WEIGHTS),
                   key=lambda s: -SIGNAL_WEIGHTS[s][0])
    for s in known:
        pts, phrase = SIGNAL_WEIGHTS[s]
        score += pts
        reasons.append(f"{phrase} (+{pts})")

    if country in EUROPE:
        score += 15
        reasons.append(f"based in {country}, a core market (+15)")
    if employee_count is not None and SIZE_MIN <= employee_count <= SIZE_MAX:
        score += 15
        reasons.append(f"{employee_count} employees, inside the {SIZE_MIN}-{SIZE_MAX} target size (+15)")

    days: int | None = None
    if last_touch_at is not None:
        days = max(0, (_aware(now) - _aware(last_touch_at)).days)
    if days is None:
        score += 5
        reasons.append("never contacted (+5)")
    elif days <= RECENT_TOUCH_DAYS:
        score -= 25
        reasons.append(f"last touched {days}d ago, let it breathe (-25)")
    elif days >= STALE_TOUCH_DAYS:
        score += 5
        reasons.append(f"no contact for {days} days (+5)")

    score = max(0, min(100, score))

    if len(owners) >= 2:
        recommendation = "coordinate"
        reasons.insert(0, f"{len(owners)} reps have touched this account ({', '.join(owners)}): "
                          "agree who calls before anyone does")
    elif days is not None and days <= RECENT_TOUCH_DAYS:
        recommendation = "wait"
    elif score >= CALL_THRESHOLD:
        recommendation = "call_today"
    else:
        recommendation = "nurture"
    return ScoreResult(score, recommendation, reasons)
