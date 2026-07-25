"""Tests for the supplement library CRUD router (#161 Lane 3a)."""

from typing import Any

from fastapi.testclient import TestClient


def _create(client: TestClient, **overrides: object) -> dict[str, Any]:
    payload: dict[str, object] = {
        "name": "Magnesium Glycinate",
        "brand": "Pure Encapsulations",
        "form": "capsule",
    }
    payload.update(overrides)
    resp = client.post("/api/supplement-products", json=payload)
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


# --- create ---


def test_create_product_defaults(client: TestClient) -> None:
    body = _create(client, name="Melatonin")
    assert body["name"] == "Melatonin"
    assert body["unit"] == "mg"  # default
    assert body["step"] == 0.5  # default
    assert body["is_sticky"] is False  # default
    assert isinstance(body["id"], int)


def test_create_product_full_fields(client: TestClient) -> None:
    body = _create(
        client,
        name="Melatonin",
        brand="Life Extension",
        form="sublingual",
        default_dose=0.3,
        unit="mg",
        step=0.1,
        is_sticky=True,
    )
    assert body["default_dose"] == 0.3
    assert body["step"] == 0.1
    assert body["is_sticky"] is True
    assert body["form"] == "sublingual"


def test_create_product_rejects_blank_name(client: TestClient) -> None:
    resp = client.post("/api/supplement-products", json={"name": ""})
    assert resp.status_code == 422


# --- list ---


def test_list_products_ordered_by_name_case_insensitive(client: TestClient) -> None:
    # Binary collation would sort "Zinc" before "ashwagandha"; the list route
    # orders by lower(name) so casing doesn't scramble the library.
    _create(client, name="Zinc")
    _create(client, name="ashwagandha")
    _create(client, name="Melatonin")
    resp = client.get("/api/supplement-products")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert names == ["ashwagandha", "Melatonin", "Zinc"]


def test_list_products_empty(client: TestClient) -> None:
    resp = client.get("/api/supplement-products")
    assert resp.status_code == 200
    assert resp.json() == []


# --- get ---


def test_get_product(client: TestClient) -> None:
    pid = _create(client)["id"]
    resp = client.get(f"/api/supplement-products/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


def test_get_product_not_found(client: TestClient) -> None:
    assert client.get("/api/supplement-products/999").status_code == 404


# --- update (PATCH, partial) ---


def test_update_product_partial(client: TestClient) -> None:
    pid = _create(client, name="Magnesium", is_sticky=False)["id"]
    resp = client.patch(f"/api/supplement-products/{pid}", json={"is_sticky": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_sticky"] is True
    assert body["name"] == "Magnesium"  # untouched field preserved


def test_update_product_not_found(client: TestClient) -> None:
    resp = client.patch("/api/supplement-products/999", json={"is_sticky": True})
    assert resp.status_code == 404


def test_update_product_rejects_blank_name(client: TestClient) -> None:
    pid = _create(client)["id"]
    resp = client.patch(f"/api/supplement-products/{pid}", json={"name": ""})
    assert resp.status_code == 422


def test_update_product_rejects_explicit_null_on_non_nullable(client: TestClient) -> None:
    """`{"name": null}` used to pass validation (PATCH fields are `X | None`),
    survive exclude_unset, and blow up as a NOT NULL 500 at commit — it must
    422 at the boundary instead. Same for unit/step/is_sticky."""
    pid = _create(client)["id"]
    for field in ("name", "unit", "step", "is_sticky"):
        resp = client.patch(f"/api/supplement-products/{pid}", json={field: None})
        assert resp.status_code == 422, f"{field}: {resp.status_code} {resp.text}"


def test_update_product_null_clears_nullable_fields(client: TestClient) -> None:
    """Explicit null must still clear the genuinely nullable fields."""
    pid = _create(client, brand="Pure Encapsulations", form="capsule", default_dose=200)["id"]
    resp = client.patch(
        f"/api/supplement-products/{pid}",
        json={"brand": None, "form": None, "default_dose": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["brand"] is None
    assert body["form"] is None
    assert body["default_dose"] is None
    assert body["name"] == "Magnesium Glycinate"  # untouched


# --- delete (unreferenced allowed; referenced -> 409) ---


def test_delete_unreferenced_product(client: TestClient) -> None:
    pid = _create(client)["id"]
    assert client.delete(f"/api/supplement-products/{pid}").status_code == 204
    assert client.get(f"/api/supplement-products/{pid}").status_code == 404


def test_delete_product_not_found(client: TestClient) -> None:
    assert client.delete("/api/supplement-products/999").status_code == 404


def test_delete_referenced_product_conflicts(client: TestClient) -> None:
    """A product a logged entry references must not hard-delete (would orphan
    history + drop a predictor) — it returns 409 and stays in the library."""
    pid = _create(client, name="Melatonin")["id"]
    resp = client.put(
        "/api/daily-log/2025-06-15",
        json={
            "supplement_entries": [{"name": "Melatonin", "dose_mg": 3, "product_id": pid}],
        },
    )
    assert resp.status_code == 200, resp.text

    del_resp = client.delete(f"/api/supplement-products/{pid}")
    assert del_resp.status_code == 409
    # Still present.
    assert client.get(f"/api/supplement-products/{pid}").status_code == 200
