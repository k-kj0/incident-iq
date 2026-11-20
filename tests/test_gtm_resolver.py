from datetime import datetime, timedelta, timezone
from itertools import combinations

from backend.gtm.normalize import normalize_country, normalize_domain, normalize_name
from backend.gtm.resolver import Candidate, Incoming, resolve
from backend.gtm.scoring import score_account

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def test_normalize_domain():
    assert normalize_domain("https://www.Acme.com/about?x=1") == "acme.com"
    assert normalize_domain("jo@eu.acme.io") == "acme.io"
    assert normalize_domain("acme.co.uk") == "acme.co.uk"
    assert normalize_domain("jo@gmail.com") is None
    assert normalize_domain("https://linkedin.com/company/acme") is None
    assert normalize_domain("acme-labs.github.io") is None
    assert normalize_domain("not a url") is None
    assert normalize_domain(None) is None


def test_normalize_name():
    assert normalize_name("Müller & Söhne GmbH") == "muller and sohne"
    assert normalize_name("The Acme Corp.") == "acme"
    assert normalize_name("Acme GmbH & Co. KG") == "acme"
    assert normalize_name("Group") == "group"       # never strip the only token
    assert normalize_name("---") == ""


def test_normalize_country():
    assert normalize_country("de") == "DE"
    assert normalize_country("UK") == "GB"
    assert normalize_country("Deutschland") == "DE"
    assert normalize_country("Narnia") is None


# (source_record_id, company_name, website_or_email, country, true_company)
FIXTURE = [
    ("a1", "Acme GmbH", "https://www.acme.de", "DE", "acme"),
    ("a2", "ACME", "acme.de/contact", "Germany", "acme"),
    ("a3", "Acme Gesellschaft mbH", None, "DE", "acme"),
    ("b1", "Datadog Inc", "datadoghq.com", "US", "datadog"),
    ("b2", "Data Dog", None, "US", "datadog"),
    ("c1", "Müller & Söhne GmbH", "mueller-soehne.de", "DE", "muller"),
    ("c2", "Mueller and Soehne", "info@mueller-soehne.de", "DE", "muller"),
    ("d1", "Northwind Traders Ltd", "northwind.co.uk", "GB", "northwind"),
    ("d2", "The Northwind Traders", "https://northwind.co.uk/", "UK", "northwind"),
    ("e1", "Stripe", "stripe.com", "US", "stripe"),
    ("e2", "Stripes", "stripes.com", "US", "stripes"),                 # different company
    ("f1", "Helio Labs", "heliolabs.io", "NL", "helio-nl"),
    ("f2", "Helio Labs", "helio-labs.com", "DE", "helio-de"),          # same name, other country
    ("g1", "Orbit Security", "orbitsec.com", "FR", "orbit-security"),
    ("g2", "Orbit Securities", "orbitsecurities.fr", "FR", "orbit-securities"),  # different company
    ("h1", "Zeta Analytics", "zeta-analytics.com", "SE", "zeta"),
    ("h2", "Zeta Analytik", "jo@zeta-analytics.com", "SE", "zeta"),    # typo, same domain
    ("i1", "International Business Machines", "ibm.com", "US", "ibm"),
    ("i2", "IBM Corp", None, "US", "ibm"),                             # not resolvable by name: expected miss
    ("j1", "Blue Harbor", "blueharbor.io", "IE", "blue-harbor"),
    ("j2", "Blue Harbour", None, "IE", "blue-harbor"),                 # spelling variant, same country
]


def _cluster(fixture):
    cands, clusters, next_id = [], {}, 1
    flagged = set()
    for rid, name, web, country, _truth in fixture:
        inc = Incoming(normalize_name(name), normalize_domain(web), normalize_country(country))
        d = resolve(inc, cands)
        if d.account_id is None:
            cid = next_id
            next_id += 1
            cands.append(Candidate(cid, inc.name_key, inc.domain, inc.country))
            if d.review_candidate_id:
                flagged.add(rid)
        else:
            cid = d.account_id
            c = next(x for x in cands if x.id == cid)
            c.domain = c.domain or inc.domain
            c.country = c.country or inc.country
        clusters[rid] = cid
    return clusters, flagged


def test_dedupe_precision_and_recall_on_labeled_fixture():
    clusters, flagged = _cluster(FIXTURE)
    truth = {rid: t for rid, *_rest, t in FIXTURE}
    tp = fp = fn = 0
    for a, b in combinations(clusters, 2):
        same_pred = clusters[a] == clusters[b]
        same_true = truth[a] == truth[b]
        tp += same_pred and same_true
        fp += same_pred and not same_true
        fn += (not same_pred) and same_true
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    print(f"precision={precision:.3f} recall={recall:.3f} tp={tp} fp={fp} fn={fn}")
    assert precision == 1.0          # a wrong merge is the expensive mistake
    assert recall >= 0.85
    # near-misses stay separate and go to human review instead of being merged
    assert {"e2", "g2"} <= flagged
    assert clusters["e1"] != clusters["e2"]
    assert clusters["g1"] != clusters["g2"]
    assert clusters["j1"] == clusters["j2"]


def test_same_name_different_country_never_merges():
    clusters, _ = _cluster(FIXTURE)
    assert clusters["f1"] != clusters["f2"]


def test_score_explains_itself():
    s = score_account(
        signals=["hiring_security_role", "customer_asked_for_certification"],
        country="DE", employee_count=120, owners=["anna"], last_touch_at=None, now=NOW)
    assert s.score == 90 and s.recommendation == "call_today"
    assert s.reasons[0].startswith("one of their customers asked")
    assert any("never contacted" in r for r in s.reasons)


def test_recently_touched_waits_and_two_owners_coordinate():
    base = dict(signals=["hiring_security_role", "customer_asked_for_certification"],
                country="DE", employee_count=120, now=NOW)
    wait = score_account(owners=["anna"], last_touch_at=NOW - timedelta(days=3), **base)
    assert wait.recommendation == "wait"
    clash = score_account(owners=["anna", "raj"], last_touch_at=NOW - timedelta(days=40), **base)
    assert clash.recommendation == "coordinate"
    assert "anna, raj" in clash.reasons[0]


def test_unknown_signals_are_ignored_and_score_is_clamped():
    s = score_account(signals=["made_up"], country=None, employee_count=None,
                      owners=[], last_touch_at=NOW - timedelta(days=2), now=NOW)
    assert s.score == 0 and s.recommendation == "wait"
