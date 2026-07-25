"""Supplement library API routes — CRUD for SupplementProduct (#161 Lane 3a).

The library is the set of distinct supplement products (name + brand + form +
default dose/unit/step, plus a sticky flag) that a logged ``SupplementEntry``
links to by ``product_id``. Each product is its own analysis predictor (Lane 2),
so the library is the schema those predictors key off.

Delete policy: a product referenced by any logged entry cannot be hard-deleted
(that would orphan historical entries and silently drop a predictor). Such a
delete returns 409; only an unreferenced product deletes. This is the simplest
safe rule with no extra schema — no ``is_retired`` column/migration — and it
never corrupts history.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import SupplementEntry, SupplementProduct
from backend.schemas import (
    SupplementProductCreate,
    SupplementProductOut,
    SupplementProductUpdate,
)

router = APIRouter(prefix="/api/supplement-products", tags=["supplements"])


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
    """Partially update a supplement library product (only supplied fields)."""
    product = db.get(SupplementProduct, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Supplement product not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return SupplementProductOut.model_validate(product)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a product — only if no logged entry references it, else 409.

    A referenced product must not be hard-deleted (it would orphan historical
    entries and drop a predictor); the caller keeps it in the library instead.
    """
    product = db.get(SupplementProduct, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Supplement product not found")
    referenced = (
        db.query(SupplementEntry).filter(SupplementEntry.product_id == product_id).first()
        is not None
    )
    if referenced:
        raise HTTPException(
            status_code=409,
            detail="Product is referenced by logged entries and cannot be deleted",
        )
    db.delete(product)
    db.commit()
