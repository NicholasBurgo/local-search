import json

import httpx

from leadfinder.geocode import USER_AGENT, city_bbox, expand_city_query, suggest_places


def test_suggest_places(monkeypatch):
    import httpx as _httpx

    def handler(request):
        assert request.headers["user-agent"] == USER_AGENT
        return _httpx.Response(
            200,
            json=[{"display_name": "Mandeville, St. Tammany, LA", "lat": "30.36", "lon": "-90.06"}],
        )

    client = _httpx.Client(
        transport=_httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
    )
    out = suggest_places("Mandeville", client=client)
    client.close()
    assert out[0]["label"].startswith("Mandeville")
    assert out[0]["lat"] == 30.36
    assert suggest_places("ab") == []  # too short -> no network call


def test_expand_city_query():
    # "LA" must become Louisiana, not read as "Lane" by the geocoder
    assert expand_city_query("Covington LA") == "Covington, Louisiana"
    assert expand_city_query("New Orleans LA") == "New Orleans, Louisiana"
    assert expand_city_query("Austin, TX") == "Austin, Texas"
    assert expand_city_query("Paris France") == "Paris France"  # non-US passthrough


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})


def test_bbox_order_and_parse(tmp_path):
    def handler(request):
        assert "nominatim" in request.url.host
        assert request.headers["user-agent"] == USER_AGENT
        # Nominatim returns [south, north, west, east]
        return httpx.Response(200, json=[{"boundingbox": ["30.43", "30.55", "-90.17", "-90.05"]}])

    with _client(handler) as client:
        bbox = city_bbox("Covington LA", cache_path=str(tmp_path / "c.json"), client=client)
    # city_bbox returns (west, south, east, north)
    assert bbox == (-90.17, 30.43, -90.05, 30.55)


def test_cache_hit_skips_network(tmp_path):
    cache_path = tmp_path / "c.json"
    cache_path.write_text(json.dumps({"Covington LA": [-90.17, 30.43, -90.05, 30.55]}))

    def handler(request):
        raise AssertionError("network should not be hit on cache hit")

    with _client(handler) as client:
        bbox = city_bbox("Covington LA", cache_path=str(cache_path), client=client)
    assert bbox == (-90.17, 30.43, -90.05, 30.55)


def test_no_results_raises(tmp_path):
    def handler(request):
        return httpx.Response(200, json=[])

    with _client(handler) as client:
        try:
            city_bbox("Nowhereville ZZ", cache_path=str(tmp_path / "c.json"), client=client)
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "Nowhereville" in str(exc)
