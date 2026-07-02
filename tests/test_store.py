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
    s.mark("A", stage="qualified")
    # a fresh search refreshes source data but must NOT wipe the pipeline stage
    s.upsert([_rec("A", name="Joe's Diner", phone="999")])
    row = s.get(["A"])["A"]
    assert row["name"] == "Joe's Diner" and row["phone"] == "999"
    assert row["stage"] == "qualified"


def test_stage_filters_and_stats(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A"), _rec("B"), _rec("C"), _rec("D")])
    s.mark("A", stage="new")
    s.mark("B", stage="contacted")
    s.mark("C", stage="qualified")
    # D stays off the list (stage None)
    assert {r["place_id"] for r in s.saved("new")} == {"A"}
    assert {r["place_id"] for r in s.saved("contacted")} == {"B"}
    assert {r["place_id"] for r in s.saved("qualified")} == {"C"}
    assert {r["place_id"] for r in s.saved("listed")} == {"A", "B", "C"}
    st = s.stats()
    assert st["total"] == 4 and st["listed"] == 3
    assert st["new"] == 1 and st["contacted"] == 1 and st["qualified"] == 1
    assert st["proposal_sent"] == 0 and st["won"] == 0 and st["lost"] == 0


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
    s.mark("A", stage="qualified")
    s.close()
    s2 = LeadStore(path)  # reopen the same file
    assert s2.stats()["listed"] == 1
    assert s2.saved("qualified")[0]["place_id"] == "A"


def test_activities_log_and_timeline(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A")])
    a1 = s.log_activity("A", "call", "left a voicemail")
    s.log_activity("A", "note", "warm - call back")
    assert a1["type"] == "call" and a1["body"] == "left a voicemail"
    tl = s.activities_for("A")
    assert [t["body"] for t in tl] == ["warm - call back", "left a voicemail"]  # newest first
    assert tl[0]["id"] != tl[1]["id"]  # distinct ids from the sequence


def test_follow_up_set_and_clear(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A")])
    assert s.set_follow_up("A", days=3) is not None
    assert s.get(["A"])["A"]["next_follow_up"] is not None
    s.set_follow_up("A", days=None)  # clear
    assert s.get(["A"])["A"]["next_follow_up"] is None


def test_follow_up_queue_due_and_stale(tmp_path):
    s = LeadStore(str(tmp_path / "db.duckdb"))
    s.upsert([_rec("A"), _rec("B"), _rec("C"), _rec("D")])
    s.mark("A", stage="contacted")
    s.mark("B", stage="qualified")
    s.mark("C", stage="won")  # closed -> never nagged about
    s.set_follow_up("A", days=-1)  # overdue -> DUE
    # B has no follow-up -> STALE; D is not on the list; C is closed.
    q = s.follow_up_queue(stale_days=-1)  # future cutoff: any past lead counts as stale
    assert {r["place_id"] for r in q["due"]} == {"A"}
    assert {r["place_id"] for r in q["stale"]} == {"B"}
    # scheduling a future follow-up on B takes it out of both buckets
    s.set_follow_up("B", days=2)
    q2 = s.follow_up_queue(stale_days=-1)
    assert {r["place_id"] for r in q2["stale"]} == set()
    assert {r["place_id"] for r in q2["due"]} == {"A"}


def test_legacy_stage_migrates_on_reopen(tmp_path):
    path = str(tmp_path / "db.duckdb")
    s = LeadStore(path)
    s.upsert([_rec("A"), _rec("B")])
    s.mark("A", stage="accepted")  # old triage stage
    s.mark("B", stage="completed")
    s.close()
    s2 = LeadStore(path)  # reopen remaps legacy stages onto the pipeline
    assert s2.get(["A"])["A"]["stage"] == "qualified"
    assert s2.get(["B"])["B"]["stage"] == "won"
