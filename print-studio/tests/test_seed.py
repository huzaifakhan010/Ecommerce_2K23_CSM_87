from sqlalchemy import select

from app.models import Category, Product, Sku, User
from scripts.seed import seed


def test_seed_is_reproducible_and_idempotent(db):
    first = seed(db, "admin@example.com", "Correct-Horse-9")
    db.commit()
    second = seed(db, "admin@example.com", "Correct-Horse-9")
    db.commit()
    assert first == second  # running it twice changes nothing
    assert first["categories"] >= 2 and first["products"] >= 3 and first["skus"] >= 4
    assert db.scalar(select(User).where(User.email == "admin@example.com")).role == "admin"


def test_seed_demonstrates_the_required_model(db):
    seed(db, "admin@example.com", "Correct-Horse-9")
    db.commit()

    # at least two levels in the category tree
    categories = {c.id: c for c in db.scalars(select(Category))}
    assert any(c.parent_id is not None and categories[c.parent_id].parent_id is None for c in categories.values())

    # a product with multiple variants, and one intentionally unavailable combination
    hoodie = db.scalar(select(Product).where(Product.slug == "classic-custom-hoodie"))
    combos = {(v.option_values["color"], v.option_values["size"]) for v in hoodie.variants}
    assert len(combos) == 5 and ("White", "L") not in combos
    assert db.scalar(select(Sku).where(Sku.code == "HOOD-WHT-L")) is None

    # a published product always has an active SKU; the draft has none
    for product in db.scalars(select(Product)):
        active = [s for s in product.skus if s.is_active]
        if product.status == "published":
            assert active
    plaque = db.scalar(select(Product).where(Product.slug == "custom-engraved-plaque"))
    assert plaque.status == "draft" and plaque.skus == []

    # an out-of-stock but valid SKU exists
    assert db.scalar(select(Sku).where(Sku.code == "HOOD-WHT-M")).stock_quantity == 0
