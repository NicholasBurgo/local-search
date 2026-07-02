from leadfinder.models import normalize_phone


def test_normalize_phone_us_formats():
    # the assorted shapes sources return all collapse to one format
    assert normalize_phone("9858457455") == "(985) 845-7455"
    assert normalize_phone("19858457455") == "(985) 845-7455"
    assert normalize_phone("+19858457455") == "(985) 845-7455"
    assert normalize_phone("+1 (985) 845-7455") == "(985) 845-7455"
    assert normalize_phone("985.845.7455") == "(985) 845-7455"
    assert normalize_phone("(985) 845-7455") == "(985) 845-7455"  # idempotent


def test_normalize_phone_passthrough_and_empty():
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""
    assert normalize_phone("   ") == ""
    assert normalize_phone("18939802") == "18939802"  # not 10 digits -> left as-is
    assert normalize_phone("+44 20 7946 0958") == "+44 20 7946 0958"  # foreign kept intact
