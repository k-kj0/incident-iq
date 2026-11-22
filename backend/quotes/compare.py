"""Side-by-side comparison with coverage-gap flags. Pure functions, no database."""
from .coverage import clean_label


def _first_by_coverage(extraction: dict) -> dict[str, dict]:
    seen: dict[str, dict] = {}
    for cov in extraction.get("coverages", []):
        if cov.get("canonical") and cov["canonical"] not in seen:
            seen[cov["canonical"]] = cov
    return seen


def compare_quotes(quotes: list[dict]) -> dict:
    """quotes: [{id, name, extraction, failed_fields}]. Returns rows, exclusion diffs, unmapped labels."""
    per_quote = {q["id"]: _first_by_coverage(q["extraction"]) for q in quotes}
    names = {q["id"]: q["name"] for q in quotes}
    coverages = sorted({c for m in per_quote.values() for c in m})
    rows = []
    for c in coverages:
        cells, flags = {}, []
        for q in quotes:
            cov = per_quote[q["id"]].get(c)
            if cov is None:
                cells[q["id"]] = None
                continue
            bad = any(f.startswith(f"{c}.") for f in q.get("failed_fields", []))
            cells[q["id"]] = {"label_in_document": cov["label"], "limit": cov["limit"]["value"],
                              "deductible": cov["deductible"]["value"] if cov.get("deductible") else None,
                              "limit_cite": cov["limit"]["cite"], "verified": not bad}
            if bad:
                flags.append(f"{names[q['id']]}: a value could not be verified against the document")
        missing = [names[i] for i, v in cells.items() if v is None]
        if missing:
            flags.insert(0, f"gap: not quoted by {', '.join(missing)}")
        limits = {i: v["limit"] for i, v in cells.items() if v}
        if len(set(limits.values())) > 1:
            top = max(limits.values())
            low = [names[i] for i, v in limits.items() if v < top]
            flags.append(f"lower limit: {', '.join(low)} (best is ${top:,})")
        rows.append({"coverage": c, "by_quote": cells, "flags": flags})

    keys = {q["id"]: {clean_label(e["text"]): e["text"] for e in q["extraction"].get("exclusions", [])}
            for q in quotes}
    only_in = {}
    for q in quotes:
        others = set().union(*(set(keys[o]) for o in keys if o != q["id"])) if len(keys) > 1 else set()
        only_in[q["id"]] = [t for k, t in keys[q["id"]].items() if k not in others]
    unmapped = {q["id"]: [c["label"] for c in q["extraction"].get("coverages", []) if not c.get("canonical")]
                for q in quotes}
    return {"quotes": [{"id": q["id"], "name": names[q["id"]]} for q in quotes],
            "rows": rows, "exclusions_only_in": only_in, "unmapped_labels": unmapped}
