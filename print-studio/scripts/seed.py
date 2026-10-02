"""Reproducible, idempotent demo data.   Usage:  python -m scripts.seed

Run `alembic upgrade head` first. Running the seed twice changes nothing the second time.
All catalog data goes through app.services, so it obeys the same rules as the admin API.
"""
import os
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import services
from app.database import SessionLocal, get_engine
from app.models import Category, Product, Sku, User, Variant
from app.schemas import CategoryCreate, ProductCreate, SkuCreate
from app.security import hash_password


def _admin(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(password), full_name="Catalog Admin", role="admin")
        db.add(user)
        db.flush()
    return user


def _category(db: Session, name: str, slug: str, parent: Category | None = None) -> Category:
    existing = db.scalar(select(Category).where(Category.slug == slug))
    if existing is not None:
        return existing
    return services.create_category(db, CategoryCreate(name=name, slug=slug, parent_id=parent.id if parent else None))


def _product(db: Session, category: Category, name: str, slug: str, ctype: str, description: str, specs: dict) -> Product:
    existing = db.scalar(select(Product).where(Product.slug == slug))
    if existing is not None:
        return existing
    return services.create_product(
        db,
        ProductCreate(
            category_id=category.id,
            name=name,
            slug=slug,
            description=description,
            customization_type=ctype,
            specifications=specs,
        ),
    )


def _sku(db: Session, product: Product, code: str, price: str, stock: int, options: dict | None = None) -> None:
    if db.scalar(select(Sku.id).where(Sku.code == code)) is not None:
        return
    services.create_sku(
        db, product, SkuCreate(code=code, price=Decimal(price), stock_quantity=stock, option_values=options)
    )


def _publish(db: Session, product: Product) -> None:
    if product.status != "published":
        services.update_product(db, product, {"status": "published"})


def seed(db: Session, admin_email: str, admin_password: str) -> dict:
    _admin(db, admin_email, admin_password)

    # --- category tree (two levels) ---------------------------------------------------------
    apparel = _category(db, "Apparel", "apparel")
    hoodies = _category(db, "Hoodies", "hoodies", apparel)
    tshirts = _category(db, "T-Shirts", "t-shirts", apparel)
    drinkware = _category(db, "Drinkware", "drinkware")
    mugs = _category(db, "Mugs", "mugs", drinkware)
    awards = _category(db, "Awards & Plaques", "awards-plaques")

    # --- product 1: two options (color x size). White/L is intentionally NOT offered. -------------
    hoodie = _product(
        db, hoodies, "Classic Custom Hoodie", "classic-custom-hoodie", "print",
        "Heavyweight fleece hoodie, DTG print on the chest or back.",
        {"material": "cotton blend", "weight_gsm": 320, "care": ["machine wash cold", "do not bleach"]},
    )
    for code, color, size, price, stock in [
        ("HOOD-BLK-S", "Black", "S", "59.00", 25),
        ("HOOD-BLK-M", "Black", "M", "59.00", 40),
        ("HOOD-BLK-L", "Black", "L", "62.00", 18),
        ("HOOD-WHT-S", "White", "S", "59.00", 12),
        ("HOOD-WHT-M", "White", "M", "59.00", 0),  # out of stock but still a valid combination
    ]:
        _sku(db, hoodie, code, price, stock, {"color": color, "size": size})
    _publish(db, hoodie)

    # --- product 2: one option (size) --------------------------------------------------------
    tee = _product(
        db, tshirts, "Premium Cotton T-Shirt", "premium-cotton-t-shirt", "embroidery",
        "Soft ring-spun cotton tee, left-chest embroidery.", {"material": "100% cotton", "weight_gsm": 180},
    )
    for code, size, price, stock in [("TEE-S", "S", "24.50", 40), ("TEE-M", "M", "24.50", 60), ("TEE-L", "L", "24.50", 35)]:
        _sku(db, tee, code, price, stock, {"size": size})
    _publish(db, tee)

    # --- product 3: no variants, a single default SKU -----------------------------------------
    mug = _product(
        db, mugs, "Engraved Steel Mug", "engraved-steel-mug", "engraving",
        "450 ml insulated steel mug with laser engraving.", {"capacity_ml": 450, "dishwasher_safe": False},
    )
    _sku(db, mug, "MUG-STL-450", "18.00", 100)
    _publish(db, mug)

    # --- product 4: a DRAFT with no SKU (a draft may have none; a published product may not) -----
    _product(db, awards, "Custom Engraved Plaque", "custom-engraved-plaque", "engraving", "Walnut plaque (coming soon).", {})

    def count(model):
        return db.scalar(select(func.count()).select_from(model))

    return {
        "categories": count(Category),
        "products": count(Product),
        "variants": count(Variant),
        "skus": count(Sku),
        "intentionally_unavailable": "classic-custom-hoodie: color=White, size=L (no variant, no SKU)",
    }


def main() -> None:
    email = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("SEED_ADMIN_PASSWORD")
    if not password:
        password = "ChangeMe-Dev-1"
        print("WARNING: SEED_ADMIN_PASSWORD not set; using the development default. Change it outside local use.")
    get_engine()
    with SessionLocal() as db:
        summary = seed(db, email, password)
        db.commit()
    print("Seed complete:", summary)
    print(f"Admin login: {email}")


if __name__ == "__main__":
    main()
