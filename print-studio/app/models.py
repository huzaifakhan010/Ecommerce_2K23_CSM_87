"""SQLAlchemy models. Every constraint is named so the Alembic migration can mirror it exactly.

Money: NUMERIC(10,2) (never float).  Stock: INTEGER with CHECK (>= 0).
Delete policies are documented in docs/SPRINT_2.md (section 3).
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite is used for fast tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _created():
    return mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())


def _updated():
    return mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("role IN ('customer', 'admin')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="customer", server_default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = _created()


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_categories_slug"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_categories_not_own_parent"),
        Index("ix_categories_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_products_slug"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_products_status"),
        CheckConstraint(
            "customization_type IN ('print', 'embroidery', 'engraving')", name="ck_products_customization_type"
        ),
        Index("ix_products_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    customization_type: Mapped[str] = mapped_column(String(16), nullable=False, default="print", server_default="print")
    # Validated JSON object (rules: app/schemas.py::validate_specifications). Sprint 3 builds on it.
    specifications: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    variants: Mapped[list["Variant"]] = relationship(
        cascade="all, delete", passive_deletes=True, order_by="Variant.id"
    )
    skus: Mapped[list["Sku"]] = relationship(cascade="all, delete", passive_deletes=True, order_by="Sku.id")


class Variant(Base):
    """One valid option combination of a product, e.g. {"color": "Black", "size": "M"}."""

    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("product_id", "combination_key", name="uq_variants_product_combination"),
        Index("ix_variants_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    option_values: Mapped[dict] = mapped_column(JSONType, nullable=False)
    combination_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = _created()


class Sku(Base):
    """A sellable unit: unique code, own price, own stock."""

    __tablename__ = "skus"
    __table_args__ = (
        UniqueConstraint("code", name="uq_skus_code"),
        CheckConstraint("price >= 0", name="ck_skus_price_non_negative"),
        CheckConstraint("stock_quantity >= 0", name="ck_skus_stock_non_negative"),
        Index("ix_skus_product_id", "product_id"),
        Index("ix_skus_variant_id", "variant_id"),
        # At most one variant-less ("default") SKU per product.
        Index(
            "uq_skus_one_default_per_product",
            "product_id",
            unique=True,
            sqlite_where=text("variant_id IS NULL"),
            postgresql_where=text("variant_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("variants.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Asset(Base):
    """Data model only in Sprint 2 (no upload endpoints - Sprint 3)."""

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("role IN ('primary', 'gallery', 'mockup_base')", name="ck_assets_role"),
        CheckConstraint("sort_order >= 0", name="ck_assets_sort_order_non_negative"),
        Index("ix_assets_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("variants.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="gallery", server_default="gallery")
    alt_text: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = _created()
