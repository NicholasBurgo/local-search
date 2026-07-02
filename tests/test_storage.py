import csv

from leadfinder.storage import (
    checkpoint_path_for,
    dedupe_rows,
    load_checkpoint,
    save_checkpoint,
    slug_city,
    write_rows_csv,
)


def test_dedupe_on_place_id():
    rows = [
        {"place_id": "A", "name": "X", "city": "Austin"},
        {"place_id": "A", "name": "X", "city": "Austin"},
        {"place_id": "B", "name": "Y", "city": "Austin"},
    ]
    unique, removed = dedupe_rows(rows)
    assert len(unique) == 2
    assert removed == 1


def test_fuzzy_dedupe_is_city_scoped():
    rows = [
        {"place_id": "A", "name": "Joe's Coffee", "city": "Austin"},
        {"place_id": "B", "name": "Joes Coffee", "city": "Austin"},  # fuzzy dup, same city
        {
            "place_id": "C",
            "name": "Joe's Coffee",
            "city": "Denver",
        },  # same name, other city -> kept
    ]
    unique, removed = dedupe_rows(rows)
    assert removed == 1
    assert sorted(r["city"] for r in unique) == ["Austin", "Denver"]


def test_write_rows_csv(tmp_path):
    path = str(tmp_path / "out.csv")
    n = write_rows_csv([{"name": "A", "city": "Austin"}], path, fieldnames=["name", "city"])
    assert n == 1
    assert next(iter(csv.DictReader(open(path))))["name"] == "A"


def test_checkpoint_roundtrip(tmp_path):
    path = str(tmp_path / "ck.json")
    assert save_checkpoint({"processed": ["a|b"], "rows": []}, path)
    assert load_checkpoint(path)["processed"] == ["a|b"]


def test_checkpoint_path_is_order_independent():
    a = checkpoint_path_for("out", ["Austin", "Denver"], ["k1", "k2"])
    b = checkpoint_path_for("out", ["Denver", "Austin"], ["k2", "k1"])
    assert a == b


def test_slug_city():
    assert slug_city("Austin, TX") == "Austin_TX"
