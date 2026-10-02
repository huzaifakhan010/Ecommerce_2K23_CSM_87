"""Business rules. Routers stay thin; the seed script reuses these functions, so seeded data
passes through exactly the same validation as data created through the API.

Services only flush; the caller (router / seed script) commits.
"""
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.errors import AppError
from app.models import Category, Product, Sku, Variant
from app.schemas import CategoryCreate, ProductCreate, SkuCreate


# =========================================================================== categories
def get_category_or_404(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise AppError(404, "category_not_found", f"Category {category_id} does not exist.")
    return category


def _slug_taken(db: Session, model, slug: str, exclude_id: Optional[int] = None) -> bool:
    stmt = select(model.id).where(model.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    return db.scalar(stmt) is not None


def ancestor_chain(db: Session, category_id: int) -> list[int]:
    """[category_id, parent, grandparent, ...] - guarded against pre-existing loops."""
    chain: list[int] = []
    seen: set[int] = set()
    current: Optional[int] = category_id
    while current is not None and current not in seen:
        seen.add(current)
        chain.append(current)
        current = db.scalar(select(Category.parent_id).where(Category.id == current))
    return chain


def _descendant_ids(db: Session, category_id: int) -> list[int]:
    children: dict[Optional[int], list[int]] = {}
    for cid, parent_id in db.execute(select(Category.id, Category.parent_id)):
        children.setdefault(parent_id, []).append(cid)
    found: list[int] = []
    stack = list(children.get(category_id, []))
    while stack:
        current = stack.pop()
        found.append(current)
        stack.extend(children.get(current, []))
    return found


def create_category(db: Session, data: CategoryCreate) -> Category:
    if _slug_taken(db, Category, data.slug):
        raise AppError(409, "duplicate_slug", f"A category with slug '{data.slug}' already exists.")
    if data.parent_id is not None:
        parent = db.get(Category, data.parent_id)
        if parent is None:
            raise AppError(422, "invalid_reference", f"Parent category {data.parent_id} does not exist.")
        if not parent.is_active:
            raise AppError(409, "parent_inactive", "Cannot create a category under an inactive parent.")
    category = Category(name=data.name, slug=data.slug, parent_id=data.parent_id)
    db.add(category)
    db.flush()
    return category


def update_category(db: Session, category: Category, changes: dict) -> Category:
    if "slug" in changes and changes["slug"] != category.slug:
        if _slug_taken(db, Category, changes["slug"], exclude_id=category.id):
            raise AppError(409, "duplicate_slug", f"A category with slug '{changes['slug']}' already exists.")
        category.slug = changes["slug"]
    if "name" in changes:
        category.name = changes["name"]

    final_active = changes.get("is_active", category.is_active)

    if "parent_id" in changes:
        new_parent_id = changes["parent_id"]
        if new_parent_id is not None:
            if new_parent_id == category.id:
                raise AppError(409, "category_cycle", "A category cannot be its own parent.")
            parent = db.get(Category, new_parent_id)
            if parent is None:
                raise AppError(422, "invalid_reference", f"Parent category {new_parent_id} does not exist.")
            if category.id in ancestor_chain(db, new_parent_id):
                raise AppError(
                    409, "category_cycle", "Move rejected: the new parent is a descendant of this category."
                )
            if not parent.is_active and final_active:
                raise AppError(409, "parent_inactive", "Cannot move an active category under an inactive parent.")
        category.parent_id = new_parent_id

    if "is_active" in changes:
        if changes["is_active"] is False and category.is_active:
            ids = [category.id] + _descendant_ids(db, category.id)
            db.execute(update(Category).where(Category.id.in_(ids)).values(is_active=False))
            category.is_active = False
        elif changes["is_active"] is True and not category.is_active:
            if category.parent_id is not None:
                parent = db.get(Category, category.parent_id)
                if parent is not None and not parent.is_active:
                    raise AppError(409, "parent_inactive", "Activate the parent category first.")
            category.is_active = True
    db.flush()
    return category


def category_tree(db: Session) -> list[dict]:
    rows = db.scalars(select(Category).order_by(Category.name, Category.id)).all()
    nodes = {
        c.id: {
            "id": c.id,
            "parent_id": c.parent_id,
            "name": c.name,
            "slug": c.slug,
            "is_active": c.is_active,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "children": [],
        }
        for c in rows
    }
    roots: list[dict] = []
    for c in rows:
        if c.parent_id is not None and c.parent_id in nodes:
            nodes[c.parent_id]["children"].append(nodes[c.id])
        else:
            roots.append(nodes[c.id])
    return roots


# =========================================================================== products
def get_product_or_404(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise AppError(404, "product_not_found", f"Product {product_id} does not exist.")
    return product


def _require_active_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise AppError(422, "invalid_reference", f"Category {category_id} does not exist.")
    if not category.is_active:
        raise AppError(409, "category_inactive", "The category is inactive.")
    return category


def _active_sku_count(db: Session, product_id: int, exclude_sku_id: Optional[int] = None) -> int:
    stmt = select(func.count()).select_from(Sku).where(Sku.product_id == product_id, Sku.is_active.is_(True))
    if exclude_sku_id is not None:
        stmt = stmt.where(Sku.id != exclude_sku_id)
    return db.scalar(stmt) or 0


def create_product(db: Session, data: ProductCreate) -> Product:
    if _slug_taken(db, Product, data.slug):
        raise AppError(409, "duplicate_slug", f"A product with slug '{data.slug}' already exists.")
    _require_active_category(db, data.category_id)
    product = Product(
        category_id=data.category_id,
        name=data.name,
        slug=data.slug,
        description=data.description,
        status="draft",
        customization_type=data.customization_type,
        specifications=data.specifications,
    )
    db.add(product)
    db.flush()
    return product


def update_product(db: Session, product: Product, changes: dict) -> Product:
    if "slug" in changes and changes["slug"] != product.slug:
        if _slug_taken(db, Product, changes["slug"], exclude_id=product.id):
            raise AppError(409, "duplicate_slug", f"A product with slug '{changes['slug']}' already exists.")
    if "category_id" in changes and changes["category_id"] != product.category_id:
        _require_active_category(db, changes["category_id"])

    if changes.get("status") == "published":
        category_id = changes.get("category_id", product.category_id)
        _require_active_category(db, category_id)
        if _active_sku_count(db, product.id) == 0:
            raise AppError(409, "publish_requires_sku", "A product needs at least one active SKU to be published.")

    for field in ("category_id", "name", "slug", "description", "status", "customization_type", "specifications"):
        if field in changes:
            setattr(product, field, changes[field])
    db.flush()
    return product


def archive_product(db: Session, product: Product) -> Product:
    """Soft delete: keeps rows (future carts/orders reference SKUs) but removes them from sale."""
    product.status = "archived"
    db.execute(update(Sku).where(Sku.product_id == product.id).values(is_active=False))
    db.flush()
    db.refresh(product)
    for sku in product.skus:
        db.refresh(sku)
    return product


def list_products(
    db: Session,
    *,
    status: Optional[str] = None,
    category_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
):
    stmt = select(Product)
    count_stmt = select(func.count()).select_from(Product)
    if status is not None:
        stmt = stmt.where(Product.status == status)
        count_stmt = count_stmt.where(Product.status == status)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
        count_stmt = count_stmt.where(Product.category_id == category_id)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.options(selectinload(Product.variants), selectinload(Product.skus))
        .order_by(Product.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return items, total


# =========================================================================== variants
def combination_key(option_values: dict[str, str]) -> str:
    return "|".join(f"{k}={v.strip().lower()}" for k, v in sorted(option_values.items()))


def create_variant(db: Session, product: Product, option_values: dict[str, str]) -> Variant:
    """Only *valid* combinations are ever stored. A combination that is not offered simply has no row."""
    if product.status == "archived":
        raise AppError(409, "product_archived", "Archived products cannot be changed.")
    existing = db.scalars(select(Variant).where(Variant.product_id == product.id)).all()
    if existing:
        expected = set(existing[0].option_values.keys())
        if set(option_values.keys()) != expected:
            raise AppError(
                422,
                "variant_option_mismatch",
                f"Variants of this product must define exactly these options: {sorted(expected)}.",
            )
    key = combination_key(option_values)
    if any(v.combination_key == key for v in existing):
        raise AppError(409, "duplicate_variant", "This option combination already exists for the product.")
    if db.scalar(select(Sku.id).where(Sku.product_id == product.id, Sku.variant_id.is_(None))) is not None:
        raise AppError(
            409, "default_sku_exists", "The product has a variant-less SKU; it cannot also have variants."
        )
    variant = Variant(product_id=product.id, option_values=option_values, combination_key=key)
    db.add(variant)
    db.flush()
    return variant


# =========================================================================== SKUs
def get_sku_or_404(db: Session, sku_id: int) -> Sku:
    sku = db.get(Sku, sku_id)
    if sku is None:
        raise AppError(404, "sku_not_found", f"SKU {sku_id} does not exist.")
    return sku


def create_sku(db: Session, product: Product, data: SkuCreate) -> Sku:
    if product.status == "archived":
        raise AppError(409, "product_archived", "Archived products cannot be changed.")
    if db.scalar(select(Sku.id).where(Sku.code == data.code)) is not None:
        raise AppError(409, "duplicate_sku_code", f"SKU code '{data.code}' already exists.")

    variant: Optional[Variant] = None
    if data.variant_id is not None:
        variant = db.get(Variant, data.variant_id)
        if variant is None or variant.product_id != product.id:
            raise AppError(422, "invalid_reference", "variant_id does not belong to this product.")
    elif data.option_values is not None:
        key = combination_key(data.option_values)
        variant = db.scalar(select(Variant).where(Variant.product_id == product.id, Variant.combination_key == key))
        if variant is None:
            variant = create_variant(db, product, data.option_values)
    else:
        if db.scalar(select(Variant.id).where(Variant.product_id == product.id)) is not None:
            raise AppError(
                422, "variant_required", "This product has variants: send variant_id or option_values."
            )
        if db.scalar(select(Sku.id).where(Sku.product_id == product.id, Sku.variant_id.is_(None))) is not None:
            raise AppError(409, "default_sku_exists", "The product already has a variant-less SKU.")

    sku = Sku(
        product_id=product.id,
        variant_id=variant.id if variant is not None else None,
        code=data.code,
        price=data.price,
        stock_quantity=data.stock_quantity,
        is_active=data.is_active,
    )
    db.add(sku)
    db.flush()
    return sku


def update_sku(db: Session, sku: Sku, changes: dict) -> Sku:
    if "stock_delta" in changes:
        new_stock = sku.stock_quantity + changes["stock_delta"]
        if new_stock < 0:
            raise AppError(
                409,
                "insufficient_stock",
                f"Stock would become negative ({sku.stock_quantity} {changes['stock_delta']:+d}).",
            )
        sku.stock_quantity = new_stock
    if "stock_quantity" in changes:
        sku.stock_quantity = changes["stock_quantity"]
    if "price" in changes:
        sku.price = changes["price"]
    if "is_active" in changes:
        if changes["is_active"] is False and sku.is_active:
            product = db.get(Product, sku.product_id)
            if product is not None and product.status == "published" and _active_sku_count(db, product.id, sku.id) == 0:
                raise AppError(
                    409,
                    "last_active_sku",
                    "A published product must keep at least one active SKU. Unpublish the product first.",
                )
        sku.is_active = changes["is_active"]
    db.flush()
    return sku
