from google.maps import places_v1 as p

from leadfinder.models import FieldProfile, SkuTier
from leadfinder.places_client import PlacesGateway
from leadfinder.usage import UsageTracker

FAKE_KEY = "AIzaFAKEKEY_00000000000000000000000000"


def test_search_text_records_usage_and_builds_mask(tmp_path):
    usage = UsageTracker(100, str(tmp_path / "u.json"))
    gateway = PlacesGateway(api_key=FAKE_KEY, usage=usage)

    captured = {}

    def fake_search(request, metadata):
        captured["query"] = request.text_query
        captured["mask"] = dict(metadata)["x-goog-fieldmask"]
        resp = p.SearchTextResponse()
        resp.places.append(p.Place(id="A", website_uri=""))
        return resp

    gateway.client.search_text = fake_search

    places = gateway.search_text("coffee in Austin", FieldProfile.ENTERPRISE, max_results=20)
    assert len(places) == 1
    assert usage.calls_for(SkuTier.ENTERPRISE) == 1
    assert captured["query"] == "coffee in Austin"
    assert captured["mask"].startswith("places.")
    assert "places.websiteUri" in captured["mask"]
