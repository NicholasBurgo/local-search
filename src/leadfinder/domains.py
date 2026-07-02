"""Domain classification: known chains and social/directory sites.

A business's own website is a real lead disqualifier; a chain or a social/
directory listing is not the same thing, so we classify domains before deciding.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Known chain/franchise domains: finding one of these means it is a chain, not a
# small business worth pitching.
CHAIN_DOMAINS: frozenset[str] = frozenset(
    {
        "starbucks.com",
        "mcdonalds.com",
        "subway.com",
        "dunkindonuts.com",
        "tacobell.com",
        "kfc.com",
        "pizzahut.com",
        "dominos.com",
        "papajohns.com",
        "burgerking.com",
        "wendys.com",
        "chickfila.com",
        "popeyes.com",
        "arbys.com",
        "jimmyjohns.com",
        "chipotle.com",
        "pandaexpress.com",
        "olivegarden.com",
        "redlobster.com",
        "applebees.com",
        "chilis.com",
        "crackerbarrel.com",
        "ihop.com",
        "dennys.com",
        "goldencorral.com",
        "walmart.com",
        "target.com",
        "costco.com",
        "samsclub.com",
        "kroger.com",
        "walgreens.com",
        "cvs.com",
        "riteaid.com",
        "homedepot.com",
        "lowes.com",
        "bestbuy.com",
        "macys.com",
        "tjmaxx.com",
        "marshalls.com",
        "ross.com",
    }
)

# Social media and directory domains: not counted as a business's own website.
SOCIAL_DIRECTORY_DOMAINS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "youtube.com",
        "tiktok.com",
        "pinterest.com",
        "snapchat.com",
        "yelp.com",
        "yellowpages.com",
        "whitepages.com",
        "mapquest.com",
        "tripadvisor.com",
        "foursquare.com",
        "zomato.com",
        "opentable.com",
        "grubhub.com",
        "doordash.com",
        "ubereats.com",
        "postmates.com",
        "seamless.com",
        "bbb.org",
        "manta.com",
        "bizapedia.com",
        "chamberofcommerce.com",
        "local.com",
        "citysearch.com",
        "superpages.com",
        "merchantcircle.com",
        "showmelocal.com",
        "kudzu.com",
        "hotfrog.com",
        "google.com",
        "maps.google.com",
        "bing.com",
        "apple.com",
        "linktr.ee",
    }
)


def extract_domain(url: str) -> str:
    """Base domain of a URL, lowercased, without a leading 'www.'."""
    try:
        parsed = urlparse((url or "").lower())
        domain = parsed.netloc or parsed.path
        domain = domain.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def classify_domain(domain: str) -> str:
    """Classify a bare domain as 'chain', 'social', or 'other'."""
    domain = domain.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain in CHAIN_DOMAINS:
        return "chain"
    if domain in SOCIAL_DIRECTORY_DOMAINS:
        return "social"
    return "other"
