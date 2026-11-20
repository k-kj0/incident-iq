"""Pure helpers that turn messy rep-entered values into comparable keys."""
import difflib
import re
import unicodedata
from urllib.parse import urlparse

FREE_MAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "proton.me", "protonmail.com", "gmx.de", "gmx.net", "web.de",
    "live.com", "aol.com", "yandex.com", "mail.com",
}

# Pages that identify a profile, not a company. Never use them as an account key.
NON_COMPANY_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "github.com", "github.io", "vercel.app", "netlify.app", "herokuapp.com",
    "crunchbase.com", "google.com", "notion.site", "wixsite.com", "linktr.ee",
}

SECOND_LEVEL_TLDS = {
    "co.uk", "org.uk", "ac.uk", "com.au", "co.in", "com.br", "co.jp",
    "co.nz", "com.sg", "co.za", "com.tr", "com.mx",
}

LEGAL_SUFFIXES = {
    "gmbh", "mbh", "ag", "ug", "kg", "se", "sa", "sas", "sarl", "srl", "spa", "bv", "nv",
    "ab", "as", "oy", "aps", "ltd", "limited", "llc", "inc", "incorporated",
    "corp", "corporation", "co", "company", "plc", "pvt", "private", "pty",
    "gesellschaft", "holding", "group",
}

COUNTRY_NAMES = {
    "germany": "DE", "deutschland": "DE", "austria": "AT", "switzerland": "CH",
    "france": "FR", "netherlands": "NL", "the netherlands": "NL", "belgium": "BE",
    "spain": "ES", "italy": "IT", "portugal": "PT", "ireland": "IE",
    "denmark": "DK", "sweden": "SE", "finland": "FI", "norway": "NO",
    "poland": "PL", "czechia": "CZ", "czech republic": "CZ", "estonia": "EE",
    "latvia": "LV", "lithuania": "LT", "luxembourg": "LU", "greece": "GR",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "england": "GB",
    "united states": "US", "usa": "US", "india": "IN", "canada": "CA",
    "australia": "AU",
}


def normalize_domain(value: str | None) -> str | None:
    """'https://www.Acme.com/about' or 'jo@acme.com' -> 'acme.com'. None if unusable."""
    if not value:
        return None
    v = value.strip().lower()
    if "@" in v and "://" not in v:
        v = v.rsplit("@", 1)[1]
    if "://" not in v:
        v = "//" + v
    host = urlparse(v).hostname or ""
    host = host.removeprefix("www.")
    labels = [x for x in host.split(".") if x]
    if len(labels) < 2:
        return None
    if len(labels) >= 3 and ".".join(labels[-2:]) in SECOND_LEVEL_TLDS:
        registrable = ".".join(labels[-3:])
    else:
        registrable = ".".join(labels[-2:])
    if registrable in FREE_MAIL or registrable in NON_COMPANY_DOMAINS:
        return None
    return registrable


def normalize_name(name: str | None) -> str:
    """'Müller & Söhne GmbH' -> 'muller and sohne'. Empty string if nothing usable."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = n.replace("&", " and ")
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    tokens = n.split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES | {"and"}:
        tokens.pop()
    return " ".join(tokens)


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if len(v) == 2 and v.isalpha():
        v = v.upper()
        return "GB" if v == "UK" else v
    return COUNTRY_NAMES.get(v.lower())


def compact(name_key: str) -> str:
    return name_key.replace(" ", "")


def name_similarity(a: str, b: str) -> float:
    """0..1 similarity of two normalized names. 'data dog' vs 'datadog' scores 1.0."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    plain = difflib.SequenceMatcher(None, a, b).ratio()
    squashed = difflib.SequenceMatcher(None, compact(a), compact(b)).ratio()
    return max(plain, squashed)
