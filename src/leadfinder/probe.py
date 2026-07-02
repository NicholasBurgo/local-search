"""ToS-clean website probing.

Instead of scraping Google search results, guess a business's likely domains
from its name and probe them over HTTP. This reduces false positives on the
"no website" list (a site Google does not have on file) without touching Google.
Probe output is advisory, not authoritative.
"""

from __future__ import annotations

import asyncio

import httpx

from .domains import classify_domain, extract_domain
from .models import ProbeResult, VerificationStatus
from .names import domain_candidates, name_matches_domain

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

# Substrings that betray a parked / for-sale / registrar placeholder page.
_PARKED_MARKERS = (
    "domain is for sale",
    "buy this domain",
    "this domain is parked",
    "is for sale",
    "hugedomains",
    "sedoparking",
    "domain parking",
    "godaddy.com/domainsearch",
    "parked free",
)


def _is_parked(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _PARKED_MARKERS)


async def _fetch(client: httpx.AsyncClient, url: str, timeout: float):
    """GET a URL following redirects. Returns (status, final_url, text_snippet)."""
    try:
        resp = await client.get(url, timeout=timeout)
    except Exception:
        return None, url, ""
    ctype = resp.headers.get("content-type", "")
    text = resp.text[:2000] if ctype.startswith("text") else ""
    return resp.status_code, str(resp.url), text


def _blank_outcome() -> dict:
    return {
        "probed_domain": "",
        "probe_final_url": "",
        "probe_http_status": "",
        "probe_result": ProbeResult.NOT_PROBED.value,
        "verification_status": VerificationStatus.VERIFIED_NO_WEBSITE.value,
    }


async def probe_business(
    client: httpx.AsyncClient,
    name: str,
    semaphore: asyncio.Semaphore,
    timeout: float = 5.0,
) -> dict:
    """Probe a business's candidate domains and classify the outcome."""
    outcome = _blank_outcome()
    candidates = domain_candidates(name)
    if not candidates:
        return outcome

    best: tuple | None = None  # (domain, final_url, status, ProbeResult) fallback
    async with semaphore:
        for domain in candidates:
            status, final_url, text = await _fetch(client, f"http://{domain}", timeout)
            if status is None or status >= 400:
                continue

            final_domain = extract_domain(final_url)
            kind = classify_domain(final_domain)

            if kind == "chain":
                outcome.update(
                    probed_domain=domain,
                    probe_final_url=final_url,
                    probe_http_status=status,
                    probe_result=ProbeResult.LIVE_UNRELATED.value,
                    verification_status=VerificationStatus.REMOVED_CHAIN.value,
                )
                return outcome
            if kind == "social":
                continue  # a social redirect is not the business's own site
            if _is_parked(text):
                best = best or (domain, final_url, status, ProbeResult.PARKED.value)
                continue
            if name_matches_domain(name, final_domain):
                outcome.update(
                    probed_domain=domain,
                    probe_final_url=final_url,
                    probe_http_status=status,
                    probe_result=ProbeResult.LIVE_MATCH.value,
                    verification_status=VerificationStatus.REMOVED_HAS_WEBSITE.value,
                )
                return outcome
            best = best or (domain, final_url, status, ProbeResult.LIVE_UNRELATED.value)

    if best is not None:
        domain, final_url, status, result = best
        outcome.update(
            probed_domain=domain,
            probe_final_url=final_url,
            probe_http_status=status,
            probe_result=result,
        )
    else:
        outcome["probe_result"] = ProbeResult.NO_RESPONSE.value
    # verification_status stays VERIFIED_NO_WEBSITE unless a match/chain set it.
    return outcome
