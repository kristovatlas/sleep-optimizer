"""Add supplement_products library table + SupplementEntry.product_id (#161).

Lane 2 of the v0.1.2 supplement/absence stack: make supplements analyzable per
product. A ``supplement_products`` row is a distinct library product (name +
brand + form + default dose + unit/step/sticky), and ``supplement_entries``
gains a nullable ``product_id`` FK linking a logged entry to its product.

Purely additive: existing free-text supplement entries keep ``product_id``
NULL and their ``name``/``dose_mg`` unchanged — no data migration. The
``dose_mg`` column is intentionally NOT renamed; its value is the per-day dose
in the product's unit (the unit lives on ``supplement_products.unit``).

Revision ID: 005
Revises: 004
Create Date: 2026-07-24
"""

import sqlalchemy as sa

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplement_products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("form", sa.String(length=50), nullable=True),
        sa.Column("default_dose", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=10), nullable=False, server_default="mg"),
        sa.Column("step", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("is_sticky", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )
    # SQLite cannot ALTER-ADD a foreign key, so adding product_id + its FK uses
    # batch mode (copy-and-move table rebuild). The FK is left unnamed to match
    # Base.metadata (the create_all parity test). The T-09 foreign_keys=ON
    # listener would fail the copy, so THIS migration issues PRAGMA
    # foreign_keys=OFF around the rebuild and restores it after — alembic/env.py
    # documents that migrations must do this themselves (it does not disable it).
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("supplement_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_supplement_entries_product_id",
            "supplement_products",
            ["product_id"],
            ["id"],
        )
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("supplement_entries", schema=None) as batch_op:
        batch_op.drop_column("product_id")
    op.execute("PRAGMA foreign_keys=ON")
    op.drop_table("supplement_products")
