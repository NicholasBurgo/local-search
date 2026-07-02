from leadfinder.store import LeadStore


def _rec(pid, name="Joe", **kw):
    base = dict(
        place_id=pid,
        name=name,
        city="Covington LA",
        category="food_beverage",
        phone="555",
        quality=80,
        latitude=30.4,
        longitude=-90.1,
        confidence=0.9,
        source="overture",
    )
    base.update(kw)
    return base


def test_upsert_and_saved(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    assert s.upsert([_rec("A"), _rec("B", name="Bob")]) == 2
    saved = s.saved()
    assert len(saved) == 2
    assert {r["name"] for r in saved} == {"Joe", "Bob"}
    assert all(r["stage"] is None for r in saved)  # nothing on the list yet
    assert s.upsert([{"name": "no id"}]) == 0  # rows without place_id skipped


def test_upsert_preserves_stage(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A", name="Joe")])
    s.mark("A", stage="accepted")
    # a fresh search refreshes source data but must NOT wipe the pipeline stage
    s.upsert([_rec("A", name="Joe's Diner", phone="999")])
    row = s.get(["A"])["A"]
    assert row["name"] == "Joe's Diner" and row["phone"] == "999"
    assert row["stage"] == "accepted"


def test_stage_filters_and_stats(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A"), _rec("B"), _rec("C"), _rec("D")])
    s.mark("A", stage="new")
    s.mark("B", stage="possible")
    s.mark("C", stage="accepted")
    # D stays off the list (stage None)
    assert {r["place_id"] for r in s.saved("new")} == {"A"}
    assert {r["place_id"] for r in s.saved("possible")} == {"B"}
    assert {r["place_id"] for r in s.saved("accepted")} == {"C"}
    assert {r["place_id"] for r in s.saved("listed")} == {"A", "B", "C"}
    st = s.stats()
    assert st["total"] == 4 and st["listed"] == 3
    assert st["new"] == 1 and st["possible"] == 1 and st["accepted"] == 1
    assert st["declined"] == 0 and st["completed"] == 0 and st["not_possible"] == 0


def test_mark_can_clear_stage(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A")])
    s.mark("A", stage="new")
    assert s.stats()["listed"] == 1
    s.mark("A", stage="")  # remove from the list
    assert s.stats()["listed"] == 0
    assert s.get(["A"])["A"]["stage"] is None


def test_saved_normalizes_phone(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A", phone="19858457455")])  # stored raw from the source
    assert s.saved()[0]["phone"] == "(985) 845-7455"  # normalized on read
    assert s.get(["A"])["A"]["phone"] == "(985) 845-7455"


def test_update_verification(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A")])
    s.update_verification(
        [
            {
                "place_id": "A",
                "verification_status": "REMOVED_HAS_WEBSITE",
                "verified_date": "2026-07-02",
            }
        ]
    )
    assert s.get(["A"])["A"]["verification_status"] == "REMOVED_HAS_WEBSITE"


def test_persistence_across_reopen(tmp_path):
    path = str(tmp_path / "db.duckdb")
    s = LeadStore(path)
    s.upsert([_rec("A")])
    s.mark("A", stage="accepted")
    s.close()
    s2 = LeadStore(path)  # reopen the same file
    assert s2.stats()["listed"] == 1
    assert s2.saved("accepted")[0]["place_id"] == "A"
