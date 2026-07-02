from google.maps import places_v1 as p

from leadfinder.mapping import place_to_lead


def _display_name(text):
    return p.Place.meta.fields["display_name"].message(text=text)


def test_populated_place():
    place = p.Place(
        id="ChIJ_test",
        display_name=_display_name("Joe's Coffee"),
        formatted_address="123 Main St",
        website_uri="",
        rating=4.6,
        user_rating_count=87,
        price_level=p.PriceLevel.PRICE_LEVEL_MODERATE,
        business_status=p.Place.BusinessStatus.OPERATIONAL,
        types=["cafe", "food"],
        takeout=True,
        delivery=False,
    )
    place.regular_opening_hours.weekday_descriptions.append("Monday: 7AM-5PM")
    place.current_opening_hours.open_now = True
    place.accessibility_options.wheelchair_accessible_entrance = True

    row = place_to_lead(place, city="Austin TX", keyword="coffee shop").to_row()
    assert row["name"] == "Joe's Coffee"
    assert row["price_level"] == "$$"
    assert row["rating"] == 4.6
    assert row["currently_open"] == "true"
    assert row["takeout"] == "true"
    assert row["delivery"] == "false"
    assert row["serves_beer"] == ""  # unset optional bool stays blank
    assert row["wheelchair_accessible"] == "true"
    assert row["category"] == "food_beverage"
    assert row["hours"] == "Monday: 7AM-5PM"
    assert row["city"] == "Austin TX"


def test_empty_place_no_crash():
    row = place_to_lead(p.Place()).to_row()
    assert row["name"] == ""
    assert row["rating"] == ""
    assert row["business_status"] == "OPERATIONAL"
    assert row["currently_open"] == "Unknown"
    assert row["price_level"] == ""


def test_price_level_free_is_not_a_dollar_sign():
    place = p.Place(price_level=p.PriceLevel.PRICE_LEVEL_FREE)
    assert place_to_lead(place).to_row()["price_level"] == "Free"
