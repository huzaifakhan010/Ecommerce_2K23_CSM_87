"""Administrative catalog API. The router-level dependency protects EVERY route in this file."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.deps import require_admin
from app.schemas import (
    CategoryCreate,
    CategoryNode,
    CategoryOut,
    CategoryUpdate,
    ProductCreate,
    ProductOut,
    ProductPage,
    ProductStatus,
    ProductUpdate,
    SkuCreate,
    SkuOut,
    SkuUpdate,
    VariantCreate,
    VariantOut,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ------------------------------------------------------------------ categories
@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryCreate, db: Session = Depends(get_db)):
    category = services.create_category(db, body)
    db.commit()
    db.refresh(category)
    return category


@router.get("/categories", response_model=list[CategoryNode])
def list_category_tree(db: Session = Depends(get_db)):
    return services.category_tree(db)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryUpdate, db: Session = Depends(get_db)):
    category = services.get_category_or_404(db, category_id)
    services.update_category(db, category, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(category)
    return category


# ------------------------------------------------------------------ products
@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, db: Session = Depends(get_db)):
    product = services.create_product(db, body)
    db.commit()
    db.refresh(product)
    return product


@router.get("/products", response_model=ProductPage)
def list_products(
    status: Optional[ProductStatus] = Query(default=None),
    category_id: Optional[int] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = services.list_products(db, status=status, category_id=category_id, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return services.get_product_or_404(db, product_id)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate, db: Session = Depends(get_db)):
    product = services.get_product_or_404(db, product_id)
    services.update_product(db, product, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
def archive_product(product_id: int, db: Session = Depends(get_db)):
    """Soft delete: status -> archived and every SKU deactivated. Rows are kept on purpose."""
    product = services.get_product_or_404(db, product_id)
    services.archive_product(db, product)
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ variants & SKUs
@router.post("/products/{product_id}/variants", response_model=VariantOut, status_code=201)
def create_variant(product_id: int, body: VariantCreate, db: Session = Depends(get_db)):
    product = services.get_product_or_404(db, product_id)
    variant = services.create_variant(db, product, body.option_values)
    db.commit()
    db.refresh(variant)
    return variant


@router.post("/products/{product_id}/skus", response_model=SkuOut, status_code=201)
def create_sku(product_id: int, body: SkuCreate, db: Session = Depends(get_db)):
    product = services.get_product_or_404(db, product_id)
    sku = services.create_sku(db, product, body)
    db.commit()
    db.refresh(sku)
    return sku


@router.patch("/skus/{sku_id}", response_model=SkuOut)
def update_sku(sku_id: int, body: SkuUpdate, db: Session = Depends(get_db)):
    sku = services.get_sku_or_404(db, sku_id)
    services.update_sku(db, sku, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(sku)
    return sku
