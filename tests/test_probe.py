import asyncio

import httpx

from leadfinder.models import ProbeResult, VerificationStatus
from leadfinder.probe import probe_business


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


async def test_live_match_removes_lead():
    def handler(request):
        if request.url.host == "joediner.com":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="Joe Diner")
        raise httpx.ConnectError("no route", request=request)

    async with _client(handler) as client:
        out = await probe_business(client, "Joe Diner", asyncio.Semaphore(2))
    assert out["verification_status"] == VerificationStatus.REMOVED_HAS_WEBSITE.value
    assert out["probe_result"] == ProbeResult.LIVE_MATCH.value


async def test_no_response_keeps_lead():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    async with _client(handler) as client:
        out = await probe_business(client, "Nowhere Cafe", asyncio.Semaphore(2))
    assert out["verification_status"] == VerificationStatus.VERIFIED_NO_WEBSITE.value
    assert out["probe_result"] == ProbeResult.NO_RESPONSE.value


async def test_parked_page_keeps_lead():
    def handler(request):
        if request.url.host == "parkedplace.com":
            return httpx.Response(
                200, headers={"content-type": "text/html"}, text="This domain is for sale"
            )
        raise httpx.ConnectError("no route", request=request)

    async with _client(handler) as client:
        out = await probe_business(client, "Parked Place", asyncio.Semaphore(2))
    assert out["verification_status"] == VerificationStatus.VERIFIED_NO_WEBSITE.value
    assert out["probe_result"] == ProbeResult.PARKED.value


async def test_chain_redirect_flags_chain():
    def handler(request):
        if request.url.host == "bigburger.com":
            return httpx.Response(301, headers={"location": "https://mcdonalds.com/"})
        if request.url.host == "mcdonalds.com":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="mc")
        raise httpx.ConnectError("no route", request=request)

    async with _client(handler) as client:
        out = await probe_business(client, "Big Burger", asyncio.Semaphore(2))
    assert out["verification_status"] == VerificationStatus.REMOVED_CHAIN.value
