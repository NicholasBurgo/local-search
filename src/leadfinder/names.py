"""Business-name normalization, domain-candidate guessing, and fuzzy matching.

Shared by the CSV de-duplicator (storage) and the website prober (probe).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Legal/entity suffixes and filler words stripped before slugging a name.
_STOPWORDS = {
    "the",
    "llc",
    "inc",
    "co",
    "corp",
    "corporation",
    "ltd",
    "limited",
    "company",
    "and",
    "of",
    "a",
    "an",
}

_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. Keeps word boundaries."""
    lowered = _ALNUM.sub(" ", (name or "").lower())
    return _SPACES.sub(" ", lowered).strip()


def significant_words(name: str) -> list[str]:
    """Normalized words with stopwords/entity suffixes removed."""
    return [w for w in normalize_name(name).split() if w not in _STOPWORDS]


def name_slug(name: str) -> str:
    """Compact slug for de-dup keys, e.g. 'Joe's Coffee, LLC' -> 'joescoffee'."""
    return "".join(significant_words(name))


def domain_candidates(name: str, tlds: tuple[str, ...] = (".com", ".net", ".biz")) -> list[str]:
    """Bounded list of plausible domains for a business name (best-effort)."""
    words = significant_words(name)
    if not words:
        return []
    joined = "".join(words)
    hyphen = "-".join(words)
    first = words[0]

    stems: list[str] = []
    for stem in (joined, hyphen, first):
        if stem and stem not in stems:
            stems.append(stem)

    candidates: list[str] = []
    for stem in stems:
        for tld in tlds:
            candidates.append(f"{stem}{tld}")
    # De-dup while preserving order, and cap the count to keep probing cheap.
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:5]


def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    return fuzzy_ratio(a, b) > threshold


def name_matches_domain(name: str, domain: str) -> bool:
    """True if the business name plausibly owns this domain."""
    slug = name_slug(name)
    domain_core = re.sub(r"[^a-z0-9]", "", domain.split(".")[0].lower())
    if not slug or not domain_core:
        return False
    if slug in domain_core or domain_core in slug:
        return True
    # Any significant word of length > 4 appearing in the domain core.
    for word in significant_words(name):
        if len(word) > 4 and word in domain_core:
            return True
    return False
