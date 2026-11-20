"""Entity resolution: decide whether an incoming record is an account we already know.

Precision first. A wrong merge sends one rep's deal notes to another company's
account, which is worse than leaving two records for a human to review.
"""
from dataclasses import dataclass

from .normalize import compact, name_similarity

MERGE_THRESHOLD = 0.92   # fuzzy name match strong enough to merge on its own
REVIEW_THRESHOLD = 0.80  # close enough that a human should look
MIN_FUZZY_LEN = 8        # short names (stripe/stripes) never merge on fuzzy match alone


@dataclass
class Candidate:
    id: int
    name_key: str
    domain: str | None
    country: str | None


@dataclass(frozen=True)
class Incoming:
    name_key: str
    domain: str | None
    country: str | None


@dataclass(frozen=True)
class Decision:
    method: str                      # "domain" | "name" | "new"
    account_id: int | None
    score: float
    review_candidate_id: int | None = None


def resolve(inc: Incoming, candidates: list[Candidate]) -> Decision:
    # 1. Same website domain is the strongest key.
    if inc.domain:
        for c in candidates:
            if c.domain == inc.domain:
                return Decision("domain", c.id, 1.0)

    # 2. Fuzzy name match, only inside the same country and without conflicting domains.
    best_merge: tuple[float, int] | None = None
    best_review: tuple[float, int] | None = None
    for c in candidates:
        if inc.country and c.country and inc.country != c.country:
            continue
        sim = name_similarity(inc.name_key, c.name_key)
        if sim < REVIEW_THRESHOLD:
            continue
        domain_conflict = bool(inc.domain and c.domain and inc.domain != c.domain)
        too_short = sim < 1.0 and min(len(compact(inc.name_key)), len(compact(c.name_key))) < MIN_FUZZY_LEN
        if sim >= MERGE_THRESHOLD and not domain_conflict and not too_short:
            if best_merge is None or (sim, -c.id) > (best_merge[0], -best_merge[1]):
                best_merge = (sim, c.id)
        elif best_review is None or (sim, -c.id) > (best_review[0], -best_review[1]):
            best_review = (sim, c.id)

    if best_merge:
        return Decision("name", best_merge[1], round(best_merge[0], 4))
    if best_review:
        return Decision("new", None, round(best_review[0], 4), review_candidate_id=best_review[1])
    return Decision("new", None, 0.0)
