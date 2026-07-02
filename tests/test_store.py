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
    assert all(r["contacted"] is False and r["decision"] is None for r in saved)
    assert s.upsert([{"name": "no id"}]) == 0  # rows without place_id skipped


def test_upsert_preserves_marks(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A", name="Joe")])
    s.mark("A", decision="keep", contacted=True)
    # a fresh search refreshes source data but must NOT wipe the triage marks
    s.upsert([_rec("A", name="Joe's Diner", phone="999")])
    row = s.get(["A"])["A"]
    assert row["name"] == "Joe's Diner" and row["phone"] == "999"
    assert row["decision"] == "keep" and row["contacted"] is True


def test_mark_filters_and_stats(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A"), _rec("B"), _rec("C")])
    s.mark("A", decision="keep")
    s.mark("B", decision="reject")
    s.mark("C", contacted=True)
    assert {r["place_id"] for r in s.saved("keep")} == {"A"}
    assert {r["place_id"] for r in s.saved("reject")} == {"B"}
    assert {r["place_id"] for r in s.saved("undecided")} == {"C"}
    assert {r["place_id"] for r in s.saved("contacted")} == {"C"}
    assert s.stats() == {"total": 3, "keep": 1, "reject": 1, "undecided": 1, "contacted": 1}


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
    s.mark("A", decision="keep")
    s.close()
    s2 = LeadStore(path)  # reopen the same file
    assert s2.stats()["total"] == 1
    assert s2.saved("keep")[0]["place_id"] == "A"
