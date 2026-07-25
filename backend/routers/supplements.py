"""Supplement library API routes — CRUD for SupplementProduct (#161 Lane 3a).

The library is the set of distinct supplement products (name + brand + form +
default dose/unit/step, plus a sticky flag) that a logged ``SupplementEntry``
links to by ``product_id``. Each product is its own analysis predictor (Lane 2),
so the library is the schema those predictors key off.

Delete policy: a product referenced by any logged entry — or by any explicit
"none today" absence record (``SectionAbsence`` with
``section_key == "supplement:<id>"``) — cannot be hard-deleted (that would
orphan historical data and silently drop a predictor; a product tracked only
via absence days is still recorded data per ADR 003). Such a delete returns
409; only an unreferenced product deletes. This is the simplest safe rule with
no extra schema — no ``is_retired`` column/migration — and it never corrupts
history.

Unit policy (same reasoning): ``SupplementEntry.dose_mg`` stores a bare number
whose meaning comes from ``SupplementProduct.unit``, so changing the unit on a
product with logged history would retroactively reinterpret every historical
dose (3 mg melatonin silently becomes 3 g in exports/labels). PATCHing ``unit``
to a *different* value on a referenced product therefore returns 409; the user
creates a new product instead. Unit stays freely editable while unreferenced,
and all other fields (name/brand/form/default_dose/step/is_sticky) remain
editable always — they are labels/defaults, not reinterpretations of stored
numbers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import SectionAbsence, SupplementEntry, SupplementProduct
from backend.schemas import (
    SupplementProductCreate,
    SupplementProductOut,
    SupplementProductUpdate,
)

router = APIRouter(prefix="/api/supplement-products", tags=["supplements"])


def _has_logged_history(db: Session, product_id: int) -> bool:
    """True if any logged entry OR "none today" absence references the product.

    Mirrors the delete-policy reference check: both a ``SupplementEntry`` row
    and a ``SectionAbsence`` keyed ``supplement:<id>`` are recorded history
    whose dose semantics depend on the product's unit (an explicit 0 is a dose
    too, ADR 003).
    """
    referenced_by_entry = (
        db.query(SupplementEntry).filter(SupplementEntry.product_id == product_id).first()
        is not None
    )
    if referenced_by_entry:
        return True
    return (
        db.query(SectionAbsence)
        .filter(SectionAbsence.section_key == f"supplement:{product_id}")
        .first()
        is not None
    )


@router.get("", response_model=list[SupplementProductOut])
def list_products(db: Session = Depends(get_db)) -> list[SupplementProductOut]:
    """List all supplement library products."""
    products = db.query(SupplementProduct).order_by(func.lower(SupplementProduct.name)).all()
    return [SupplementProductOut.model_validate(p) for p in products]


@router.post("", response_model=SupplementProductOut, status_code=201)
def create_product(
    data: SupplementProductCreate,
    db: Session = Depends(get_db),
) -> SupplementProductOut:
    """Create a new supplement library product."""
    product = SupplementProduct(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return SupplementProductOut.model_validate(product)


@router.get("/{product_id}", response_model=SupplementProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)) -> SupplementProductOut:
    """Get a single supplement library product."""
    product = db.get(SupplementProduct, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Supplement product not found")
    return SupplementProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=SupplementProductOut)
def update_product(
    product_id: int,
    data: SupplementProductUpdate,
    db: Session = Depends(get_db),
) -> SupplementProductOut:
    """Partially update a supplement library product (only supplied fields).

    ``unit`` is immutable once the product has logged history (entries or
    "none today" absences): dose values are bare numbers interpreted in the
    product's unit, so a unit change would rewrite the meaning of every
    historical dose. Changing it then returns 409 (see module docstring);
    sending the *current* unit is a no-op and stays 200.
    """
    product = db.get(SupplementProduct, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Supplement product not found")
    updates = data.model_dump(exclude_unset=True)
    if (
        "unit" in updates
        and updates["unit"] != product.unit
        and _has_logged_history(db, product_id)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Unit cannot change once the product has logged history; "
                "create a new product instead"
            ),
        )
    for key, value in updates.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return SupplementProductOut.model_validate(product)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a product — only if nothing recorded references it, else 409.

    A referenced product must not be hard-deleted (it would orphan historical
    data and drop a predictor); the caller keeps it in the library instead.
    References are logged entries AND explicit "none today" absence records
    (``SectionAbsence`` rows keyed ``supplement:<id>``) — a product tracked
    only via absence days is still recorded data (ADR 003).
    """
    product = db.get(SupplementProduct, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Supplement product not found")
    referenced_by_entry = (
        db.query(SupplementEntry).filter(SupplementEntry.product_id == product_id).first()
        is not None
    )
    if referenced_by_entry:
        raise HTTPException(
            status_code=409,
            detail="Product is referenced by logged entries and cannot be deleted",
        )
    referenced_by_absence = (
        db.query(SectionAbsence)
        .filter(SectionAbsence.section_key == f"supplement:{product_id}")
        .first()
        is not None
    )
    if referenced_by_absence:
        raise HTTPException(
            status_code=409,
            detail='Product is referenced by "none today" absence records and cannot be deleted',
        )
    db.delete(product)
    db.commit()
