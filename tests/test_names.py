from leadfinder.names import (
    domain_candidates,
    fuzzy_match,
    name_matches_domain,
    name_slug,
    normalize_name,
)


def test_normalize_and_slug():
    assert name_slug("Joe's Coffee, LLC") == "joescoffee"
    assert normalize_name("JOE'S  Coffee") == "joe s coffee"


def test_domain_candidates_bounded_and_relevant():
    candidates = domain_candidates("Joe's Coffee")
    assert "joescoffee.com" in candidates
    assert len(candidates) <= 5


def test_domain_candidates_empty_for_blank():
    assert domain_candidates("") == []
    assert domain_candidates("LLC Inc") == []


def test_name_matches_domain():
    assert name_matches_domain("Joes Coffee", "joescoffee.com")
    assert not name_matches_domain("Joes Coffee", "yelp.com")


def test_fuzzy_match():
    assert fuzzy_match("joescoffee", "joescofee", 0.8)
    assert not fuzzy_match("joescoffee", "bobsplumbing", 0.5)
