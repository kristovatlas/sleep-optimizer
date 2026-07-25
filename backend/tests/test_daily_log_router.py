"""Tests for daily log HTTP endpoints."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import SleepRecord
from backend.services.stats_engine import prepare_analysis_dataframe

# The SPA's fetch client always sends this header; the T-02 CSRF guard on the
# bodiless copy-from POST requires it (requests with a JSON body get it from
# the client's `json=` parameter automatically).
JSON_HEADERS = {"Content-Type": "application/json"}

# --- PUT (upsert) ---


def test_put_creates_log(client: TestClient) -> None:
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={
            "is_sick": False,
            "notes": "Felt great",
            "caffeine_entries": [
                {"amount_mg": 95, "source": "drip_coffee"},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["date"] == "2025-06-15"
    assert body["data"]["notes"] == "Felt great"
    assert len(body["data"]["caffeine_entries"]) == 1
    assert body["warnings"] == []


def test_put_upserts_replaces(client: TestClient) -> None:
    client.put(
        "/api/daily-log/2025-06-15",
        json={"caffeine_entries": [{"amount_mg": 95, "source": "other"}]},
    )
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"caffeine_entries": [{"amount_mg": 200, "source": "cold_brew"}]},
    )
    assert resp.status_code == 200
    entries = resp.json()["data"]["caffeine_entries"]
    assert len(entries) == 1
    assert entries[0]["amount_mg"] == 200


def test_put_returns_warnings(client: TestClient) -> None:
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"caffeine_entries": [{"amount_mg": 500, "source": "other"}]},
    )
    assert resp.status_code == 200
    assert len(resp.json()["warnings"]) > 0


def test_put_empty_log(client: TestClient) -> None:
    resp = client.put("/api/daily-log/2025-06-15", json={})
    assert resp.status_code == 200
    assert resp.json()["data"]["date"] == "2025-06-15"


def test_put_with_all_entry_types(client: TestClient) -> None:
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={
            "is_sick": False,
            "caffeine_entries": [{"amount_mg": 95, "source": "espresso"}],
            "meal_entries": [{"notes": "dinner"}],
            "supplement_entries": [{"name": "magnesium", "dose_mg": 144}],
            "habit_entries": [{"habit_type": "exercise", "duration_minutes": 45}],
            "stimulating_activity_entries": [{"activity_type": "video_games"}],
            "sexual_activity_entry": {"activity_type": "partnered"},
            "pre_bed_ritual_entries": [{"ritual_type": "deep_breathing", "duration_minutes": 10}],
            "nap_entries": [{"duration_minutes": 20}],
            "sunlight_entries": [{"duration_minutes": 15}],
            "red_light_entries": [{"duration_minutes": 10}],
            "nsdr_entries": [{"duration_minutes": 15, "nsdr_type": "yoga_nidra"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["caffeine_entries"]) == 1
    assert len(data["meal_entries"]) == 1
    assert len(data["supplement_entries"]) == 1
    assert len(data["habit_entries"]) == 1
    assert len(data["stimulating_activity_entries"]) == 1
    assert data["sexual_activity_entry"] is not None
    assert len(data["pre_bed_ritual_entries"]) == 1
    assert len(data["nap_entries"]) == 1
    assert len(data["sunlight_entries"]) == 1
    assert len(data["red_light_entries"]) == 1
    assert len(data["nsdr_entries"]) == 1


# --- GET single ---


def test_get_existing_log(client: TestClient) -> None:
    client.put("/api/daily-log/2025-06-15", json={"notes": "test"})
    resp = client.get("/api/daily-log/2025-06-15")
    assert resp.status_code == 200
    assert resp.json()["notes"] == "test"


def test_get_nonexistent_log(client: TestClient) -> None:
    resp = client.get("/api/daily-log/2025-06-15")
    assert resp.status_code == 404


# --- DELETE ---


def test_delete_existing_log(client: TestClient) -> None:
    client.put("/api/daily-log/2025-06-15", json={})
    resp = client.delete("/api/daily-log/2025-06-15")
    assert resp.status_code == 204
    # Verify it's gone
    resp = client.get("/api/daily-log/2025-06-15")
    assert resp.status_code == 404


def test_delete_nonexistent_log(client: TestClient) -> None:
    resp = client.delete("/api/daily-log/2025-06-15")
    assert resp.status_code == 404


# --- GET list ---


def test_list_logs_empty(client: TestClient) -> None:
    resp = client.get("/api/daily-log")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_logs(client: TestClient) -> None:
    client.put("/api/daily-log/2025-06-15", json={})
    client.put("/api/daily-log/2025-06-16", json={"is_sick": True})
    resp = client.get("/api/daily-log")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["date"] == "2025-06-15"
    assert data[1]["date"] == "2025-06-16"
    assert data[1]["is_sick"] is True


def test_list_logs_with_date_range(client: TestClient) -> None:
    client.put("/api/daily-log/2025-06-15", json={})
    client.put("/api/daily-log/2025-06-16", json={})
    client.put("/api/daily-log/2025-06-17", json={})
    resp = client.get("/api/daily-log?start_date=2025-06-16&end_date=2025-06-16")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["date"] == "2025-06-16"


def test_list_logs_has_entries_flag(client: TestClient) -> None:
    client.put(
        "/api/daily-log/2025-06-15",
        json={"caffeine_entries": [{"amount_mg": 95, "source": "other"}]},
    )
    client.put("/api/daily-log/2025-06-16", json={})
    resp = client.get("/api/daily-log")
    data = resp.json()
    assert data[0]["has_entries"] is True
    assert data[1]["has_entries"] is False


def test_list_logs_has_entries_counts_absence_only_day(client: TestClient) -> None:
    """A day with only a 'none today' absence record has recorded data (ADR 003
    amendment) — the summary must report has_entries=True; a truly blank day
    stays False."""
    client.put("/api/daily-log/2025-06-15", json={"section_absences": ["caffeine"]})
    client.put("/api/daily-log/2025-06-16", json={})
    resp = client.get("/api/daily-log")
    data = resp.json()
    assert data[0]["date"] == "2025-06-15"
    assert data[0]["has_entries"] is True
    assert data[1]["date"] == "2025-06-16"
    assert data[1]["has_entries"] is False


# --- Copy day ---


def test_copy_day(client: TestClient) -> None:
    client.put(
        "/api/daily-log/2025-06-15",
        json={
            "is_sick": True,
            "notes": "Source notes",
            "caffeine_entries": [{"amount_mg": 95, "source": "espresso"}],
        },
    )
    resp = client.post("/api/daily-log/2025-06-16/copy-from/2025-06-15", headers=JSON_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2025-06-16"
    assert data["copied_from_date"] == "2025-06-15"
    assert data["is_sick"] is True
    assert data["notes"] is None  # Notes NOT copied
    assert len(data["caffeine_entries"]) == 1


def test_copy_day_source_not_found(client: TestClient) -> None:
    resp = client.post("/api/daily-log/2025-06-16/copy-from/2025-06-15", headers=JSON_HEADERS)
    assert resp.status_code == 404


def test_copy_day_rejects_non_json_content_type(client: TestClient) -> None:
    # T-02: a CORS-simple (non-JSON) cross-site POST must be rejected so the
    # bodiless copy-from can't be driven by a hostile form submission.
    client.put("/api/daily-log/2025-06-15", json={"is_sick": True})
    resp = client.post(
        "/api/daily-log/2025-06-16/copy-from/2025-06-15",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 415
    # The target day must not have been created
    assert client.get("/api/daily-log/2025-06-16").status_code == 404


def test_copy_day_rejects_absent_content_type(client: TestClient) -> None:
    # T-02: a bodiless POST with *no* Content-Type at all is also CORS-simple —
    # the guard must 415 it before the destructive overwrite runs.
    client.put("/api/daily-log/2025-06-15", json={"is_sick": True})
    resp = client.post("/api/daily-log/2025-06-16/copy-from/2025-06-15")
    assert resp.status_code == 415
    assert client.get("/api/daily-log/2025-06-16").status_code == 404


# --- Sub-entry routes (testing a few representative types) ---


def test_add_caffeine_entry(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/caffeine",
        json={"amount_mg": 95, "source": "drip_coffee"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount_mg"] == 95
    assert data["date"] == "2025-06-15"
    assert "id" in data


def test_add_entry_creates_log(client: TestClient) -> None:
    """Adding a sub-entry should auto-create the DailyLog if needed."""
    resp = client.post(
        "/api/daily-log/2025-06-15/naps",
        json={"duration_minutes": 20},
    )
    assert resp.status_code == 201
    # Log should now exist
    resp = client.get("/api/daily-log/2025-06-15")
    assert resp.status_code == 200


def test_update_caffeine_entry(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/caffeine",
        json={"amount_mg": 95, "source": "other"},
    )
    entry_id = resp.json()["id"]
    resp = client.put(
        f"/api/daily-log/2025-06-15/caffeine/{entry_id}",
        json={"amount_mg": 200, "source": "espresso"},
    )
    assert resp.status_code == 200
    assert resp.json()["amount_mg"] == 200


def test_update_entry_not_found(client: TestClient) -> None:
    resp = client.put(
        "/api/daily-log/2025-06-15/caffeine/999",
        json={"amount_mg": 200, "source": "other"},
    )
    assert resp.status_code == 404


def test_update_entry_invalid_data_422(client: TestClient) -> None:
    # T-05: invalid body on the update path must be 422, not an unhandled 500
    resp = client.post(
        "/api/daily-log/2025-06-15/caffeine",
        json={"amount_mg": 95, "source": "other"},
    )
    entry_id = resp.json()["id"]
    resp = client.put(
        f"/api/daily-log/2025-06-15/caffeine/{entry_id}",
        json={"amount_mg": 0},  # below minimum
    )
    assert resp.status_code == 422


def test_delete_caffeine_entry(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/caffeine",
        json={"amount_mg": 95, "source": "other"},
    )
    entry_id = resp.json()["id"]
    resp = client.delete(f"/api/daily-log/2025-06-15/caffeine/{entry_id}")
    assert resp.status_code == 204


def test_delete_entry_not_found(client: TestClient) -> None:
    resp = client.delete("/api/daily-log/2025-06-15/caffeine/999")
    assert resp.status_code == 404


def test_add_habit_entry(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/habits",
        json={"habit_type": "exercise", "duration_minutes": 45},
    )
    assert resp.status_code == 201
    assert resp.json()["habit_type"] == "exercise"


def test_add_nap_entry(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/naps",
        json={"duration_minutes": 20, "start_time": "13:00:00"},
    )
    assert resp.status_code == 201
    assert resp.json()["duration_minutes"] == 20


def test_add_nsdr_entry(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/nsdr",
        json={"duration_minutes": 15, "nsdr_type": "yoga_nidra"},
    )
    assert resp.status_code == 201
    assert resp.json()["nsdr_type"] == "yoga_nidra"


def test_invalid_entry_data(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/caffeine",
        json={"amount_mg": 0},  # Below minimum
    )
    assert resp.status_code == 422


def _assert_no_sql_leak(detail: str) -> None:
    """T-05: a DB fault must never echo SQL text or bound parameters."""
    for marker in ("SQL", "sqlite3", "INSERT", "UPDATE", "FOREIGN KEY", "parameters"):
        assert marker not in detail


def test_add_entry_unknown_panel_id_409_without_sql_leak(client: TestClient) -> None:
    # T-05 × T-09: the enforced red_light_entries.panel_id FK makes an
    # IntegrityError reachable from a client body — it must surface as a clean
    # 409, not a 422 echoing the failed statement.
    resp = client.post(
        "/api/daily-log/2025-06-15/red-light",
        json={"panel_id": 999, "duration_minutes": 10},
    )
    assert resp.status_code == 409
    _assert_no_sql_leak(resp.json()["detail"])


def test_update_entry_unknown_panel_id_409_without_sql_leak(client: TestClient) -> None:
    resp = client.post(
        "/api/daily-log/2025-06-15/red-light",
        json={"duration_minutes": 10},
    )
    entry_id = resp.json()["id"]
    resp = client.put(
        f"/api/daily-log/2025-06-15/red-light/{entry_id}",
        json={"panel_id": 999, "duration_minutes": 10},
    )
    assert resp.status_code == 409
    _assert_no_sql_leak(resp.json()["detail"])


def test_composite_put_unknown_product_id_409_without_sql_leak(client: TestClient) -> None:
    """T-05: a supplement_entries[].product_id no library product has must map
    to a clean 409, not an unhandled 500 whose traceback logs bound parameters
    (supplement name/dose = health data, T-16-adjacent)."""
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"supplement_entries": [{"name": "Ghost", "product_id": 9999}]},
    )
    assert resp.status_code == 409
    _assert_no_sql_leak(resp.json()["detail"])
    # Nothing persisted — the day was never created.
    assert client.get("/api/daily-log/2025-06-15").status_code == 404


def test_composite_put_fk_failure_preserves_existing_day(client: TestClient) -> None:
    """Empirical rollback check: save_daily_log DELETES the old log before the
    re-insert, so a mid-save FK failure could lose the day if the delete were
    committed separately. Delete + insert run in one transaction, so the 409's
    rollback must restore the pre-existing day byte-for-byte."""
    ok = client.put(
        "/api/daily-log/2025-06-15",
        json={
            "notes": "original day",
            "caffeine_entries": [{"amount_mg": 95, "source": "drip_coffee"}],
            "section_absences": ["sauna"],
        },
    )
    assert ok.status_code == 200, ok.text

    bad = client.put(
        "/api/daily-log/2025-06-15",
        json={
            "notes": "should never land",
            "supplement_entries": [{"name": "Ghost", "product_id": 9999}],
        },
    )
    assert bad.status_code == 409

    after = client.get("/api/daily-log/2025-06-15")
    assert after.status_code == 200
    body = after.json()
    assert body["notes"] == "original day"
    assert len(body["caffeine_entries"]) == 1
    assert body["caffeine_entries"][0]["amount_mg"] == 95
    assert body["section_absences"] == ["sauna"]
    assert body["supplement_entries"] == []


# --- section_absences item bounds (schema, #161 Lane 3a review) ---


def test_put_absence_key_too_long_422(client: TestClient) -> None:
    """Keys are bounded to the section_key column (String(150))."""
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"section_absences": ["k" * 151]},
    )
    assert resp.status_code == 422


def test_put_absence_key_at_column_limit_ok(client: TestClient) -> None:
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"section_absences": ["k" * 150]},
    )
    assert resp.status_code == 200


def test_put_empty_absence_key_422(client: TestClient) -> None:
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"section_absences": [""]},
    )
    assert resp.status_code == 422


# --- supplement:* absence keys must resolve to a library product (#161 r3) ---


def _create_product(client: TestClient, name: str = "Melatonin") -> int:
    resp = client.post("/api/supplement-products", json={"name": name})
    assert resp.status_code == 201, resp.text
    pid: int = resp.json()["id"]
    return pid


def test_put_unknown_supplement_absence_key_422_nothing_persisted(client: TestClient) -> None:
    """`supplement:9999` (no such product) would make the stats engine
    manufacture an unlabeled ghost predictor (supplement_dose_9999) — it must
    422 at save with a static detail (T-05: the key is user text, not echoed)
    and persist nothing."""
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"section_absences": ["supplement:9999"]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "section_absences contains a supplement key referencing an unknown product"
    )
    assert "9999" not in resp.text
    # Nothing persisted — the day was never created.
    assert client.get("/api/daily-log/2025-06-15").status_code == 404


def test_put_malformed_supplement_absence_key_422(client: TestClient) -> None:
    """Non-canonical suffixes are junk (or would evade the exact-string
    reference guards, e.g. leading zeros) — all 422."""
    pid = _create_product(client)
    for bad in ("supplement:abc", "supplement:", f"supplement:+{pid}", f"supplement:00{pid}"):
        resp = client.put(
            "/api/daily-log/2025-06-15",
            json={"section_absences": [bad]},
        )
        assert resp.status_code == 422, f"{bad}: {resp.status_code} {resp.text}"
    assert client.get("/api/daily-log/2025-06-15").status_code == 404


def test_put_unknown_supplement_absence_key_preserves_existing_day(client: TestClient) -> None:
    """Same single-transaction guarantee as the FK-failure path: the 422's
    rollback must restore a pre-existing day intact."""
    ok = client.put(
        "/api/daily-log/2025-06-15",
        json={
            "notes": "original day",
            "caffeine_entries": [{"amount_mg": 95, "source": "drip_coffee"}],
            "section_absences": ["sauna"],
        },
    )
    assert ok.status_code == 200, ok.text

    bad = client.put(
        "/api/daily-log/2025-06-15",
        json={
            "notes": "should never land",
            "section_absences": ["supplement:9999"],
        },
    )
    assert bad.status_code == 422

    after = client.get("/api/daily-log/2025-06-15")
    assert after.status_code == 200
    body = after.json()
    assert body["notes"] == "original day"
    assert len(body["caffeine_entries"]) == 1
    assert body["section_absences"] == ["sauna"]


def test_put_valid_supplement_absence_ok_and_aggregates_zero(
    client: TestClient, db: Session
) -> None:
    """A supplement:<real id> key saves fine and reaches the analysis layer as
    an explicit 0.0 dose (none today) for that product."""
    pid = _create_product(client)
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={"section_absences": [f"supplement:{pid}"]},
    )
    assert resp.status_code == 200, resp.text
    day = client.get("/api/daily-log/2025-06-15")
    assert day.json()["section_absences"] == [f"supplement:{pid}"]

    # The dataframe needs a SleepRecord row for the date to emit the day.
    db.add(SleepRecord(date=dt.date(2025, 6, 15), sleep_score=80))
    db.commit()
    df = prepare_analysis_dataframe(db)
    assert df.loc[dt.date(2025, 6, 15)][f"supplement_dose_{pid}"] == 0.0


def test_copy_day_with_valid_supplement_absence(client: TestClient) -> None:
    """copy_day clones supplement absences (validated at save; the delete guard
    keeps the product alive) — the copy must succeed and carry the key."""
    pid = _create_product(client)
    ok = client.put(
        "/api/daily-log/2025-06-15",
        json={"section_absences": [f"supplement:{pid}", "sauna"]},
    )
    assert ok.status_code == 200, ok.text

    resp = client.post(
        "/api/daily-log/2025-06-16/copy-from/2025-06-15",
        headers=JSON_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()["section_absences"]) == sorted([f"supplement:{pid}", "sauna"])


def test_redlight_dose_inverse_square_by_distance(client: TestClient) -> None:
    """#60: session dose scales (reference/actual)^2 with distance."""
    panel_id = client.post(
        "/api/red-light-panels",
        json={"name": "P", "irradiance_mw_cm2": 100, "default_distance_inches": 6},
    ).json()["id"]

    # At the reference distance (6"): unadjusted → 100 mW/cm² * 600s / 1000 = 60 J/cm²
    r = client.put(
        "/api/daily-log/2026-07-16",
        json={
            "red_light_entries": [
                {"panel_id": panel_id, "duration_minutes": 10, "distance_inches": 6}
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["red_light_entries"][0]["dose_joules_cm2"] == 60.0

    # Twice the distance (12") → factor (6/12)^2 = 0.25 → 15 J/cm²
    r = client.put(
        "/api/daily-log/2026-07-16",
        json={
            "red_light_entries": [
                {"panel_id": panel_id, "duration_minutes": 10, "distance_inches": 12}
            ]
        },
    )
    assert r.json()["data"]["red_light_entries"][0]["dose_joules_cm2"] == 15.0

    # No session distance → unadjusted (pre-#60 behavior preserved)
    r = client.put(
        "/api/daily-log/2026-07-16",
        json={"red_light_entries": [{"panel_id": panel_id, "duration_minutes": 10}]},
    )
    assert r.json()["data"]["red_light_entries"][0]["dose_joules_cm2"] == 60.0


def test_redlight_rejects_nonpositive_distance(client: TestClient) -> None:
    panel_id = client.post("/api/red-light-panels", json={"name": "P"}).json()["id"]
    r = client.put(
        "/api/daily-log/2026-07-16",
        json={
            "red_light_entries": [
                {"panel_id": panel_id, "duration_minutes": 10, "distance_inches": 0}
            ]
        },
    )
    assert r.status_code == 422


def test_redlight_distance_upper_bound_rejected(client: TestClient) -> None:
    """#60 (Codex): distance is bounded to a realistic range, so a
    pathological value can't overflow the dose and poison the row."""
    panel_id = client.post(
        "/api/red-light-panels", json={"name": "P", "irradiance_mw_cm2": 100}
    ).json()["id"]
    r = client.put(
        "/api/daily-log/2026-07-16",
        json={
            "red_light_entries": [
                {"panel_id": panel_id, "duration_minutes": 10, "distance_inches": 1e9}
            ]
        },
    )
    assert r.status_code == 422
