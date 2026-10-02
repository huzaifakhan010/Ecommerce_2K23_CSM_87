"""Database-level guarantees: these pass even if the API layer is bypassed entirely (CAT05)."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Category, Product, Sku, Variant


def _category(db, slug="apparel", parent=None):
    category = Category(name=slug.title(), slug=slug, parent_id=parent.id if parent else None)
    db.add(category)
    db.flush()
    return category


def _product(db, category, slug="hoodie"):
    product = Product(category_id=category.id, name=slug.title(), slug=slug)
    db.add(product)
    db.flush()
    return product


def _sku(db, product, code="SKU-001", price="10.00", stock=1, variant_id=None):
    sku = Sku(product_id=product.id, variant_id=variant_id, code=code, price=Decimal(price), stock_quantity=stock)
    db.add(sku)
    db.flush()
    return sku


def test_defaults_are_applied(db):
    product = _product(db, _category(db))
    assert product.status == "draft"
    assert product.specifications == {}
    assert product.created_at is not None


def test_duplicate_category_slug_is_rejected_by_database(db):
    _category(db, "apparel")
    with pytest.raises(IntegrityError):
        _category(db, "apparel")


def test_duplicate_product_slug_is_rejected_by_database(db):
    category = _category(db)
    _product(db, category, "hoodie")
    with pytest.raises(IntegrityError):
        _product(db, category, "hoodie")


def test_duplicate_sku_code_is_rejected_by_database(db):
    product = _product(db, _category(db))
    _sku(db, product, "DUP-1")
    with pytest.raises(IntegrityError):
        _sku(db, product, "DUP-1")


def test_negative_stock_is_rejected_by_database(db):
    product = _product(db, _category(db))
    with pytest.raises(IntegrityError):
        _sku(db, product, stock=-1)


def test_negative_price_is_rejected_by_database(db):
    product = _product(db, _category(db))
    with pytest.raises(IntegrityError):
        _sku(db, product, price="-0.01")


def test_invalid_product_status_is_rejected_by_database(db):
    category = _category(db)
    db.add(Product(category_id=category.id, name="X", slug="x-product", status="live"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_category_cannot_be_its_own_parent(db):
    category = _category(db)
    category.parent_id = category.id
    with pytest.raises(IntegrityError):
        db.flush()


def test_foreign_key_is_enforced(db):
    db.add(Product(category_id=9999, name="Orphan", slug="orphan"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_category_with_products_cannot_be_deleted_restrict(db):
    category = _category(db)
    _product(db, category)
    db.delete(category)
    with pytest.raises(IntegrityError):
        db.flush()


def test_category_with_children_cannot_be_deleted_restrict(db):
    parent = _category(db, "apparel")
    _category(db, "hoodies", parent)
    db.delete(parent)
    with pytest.raises(IntegrityError):
        db.flush()


def test_only_one_default_sku_per_product(db):
    product = _product(db, _category(db))
    _sku(db, product, "DEF-1")
    with pytest.raises(IntegrityError):
        _sku(db, product, "DEF-2")


def test_same_variant_combination_cannot_repeat(db):
    product = _product(db, _category(db))
    db.add(Variant(product_id=product.id, option_values={"size": "M"}, combination_key="size=m"))
    db.flush()
    db.add(Variant(product_id=product.id, option_values={"size": "M"}, combination_key="size=m"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_a_product_cascades_to_variants_and_skus(db):
    product = _product(db, _category(db))
    variant = Variant(product_id=product.id, option_values={"size": "M"}, combination_key="size=m")
    db.add(variant)
    db.flush()
    _sku(db, product, "CAS-1", variant_id=variant.id)
    db.delete(product)
    db.flush()
    assert db.scalar(select(func.count()).select_from(Sku)) == 0
    assert db.scalar(select(func.count()).select_from(Variant)) == 0


def test_price_keeps_exact_decimal_value(db):
    product = _product(db, _category(db))
    sku = _sku(db, product, price="19.99")
    db.commit()
    db.expire_all()
    assert db.get(Sku, sku.id).price == Decimal("19.99")
