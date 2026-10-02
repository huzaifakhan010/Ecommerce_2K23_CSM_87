"""Catalog foundation: users, categories, products, variants, skus, assets.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _created():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _updated():
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="customer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created(),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('customer', 'admin')", name="ck_users_role"),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="RESTRICT", onupdate="CASCADE")
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created(),
        _updated(),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_categories_not_own_parent"),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("customization_type", sa.String(16), nullable=False, server_default="print"),
        sa.Column("specifications", JSON_TYPE, nullable=False, server_default=sa.text("'{}'")),
        _created(),
        _updated(),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_products_status"),
        sa.CheckConstraint(
            "customization_type IN ('print', 'embroidery', 'engraving')", name="ck_products_customization_type"
        ),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])

    op.create_table(
        "variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("option_values", JSON_TYPE, nullable=False),
        sa.Column("combination_key", sa.String(255), nullable=False),
        _created(),
        sa.UniqueConstraint("product_id", "combination_key", name="uq_variants_product_combination"),
    )
    op.create_index("ix_variants_product_id", "variants", ["product_id"])

    op.create_table(
        "skus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id", sa.Integer(), sa.ForeignKey("variants.id", ondelete="CASCADE", onupdate="CASCADE")
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created(),
        _updated(),
        sa.UniqueConstraint("code", name="uq_skus_code"),
        sa.CheckConstraint("price >= 0", name="ck_skus_price_non_negative"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_skus_stock_non_negative"),
    )
    op.create_index("ix_skus_product_id", "skus", ["product_id"])
    op.create_index("ix_skus_variant_id", "skus", ["variant_id"])
    op.create_index(
        "uq_skus_one_default_per_product",
        "skus",
        ["product_id"],
        unique=True,
        sqlite_where=sa.text("variant_id IS NULL"),
        postgresql_where=sa.text("variant_id IS NULL"),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id", sa.Integer(), sa.ForeignKey("variants.id", ondelete="SET NULL", onupdate="CASCADE")
        ),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="gallery"),
        sa.Column("alt_text", sa.String(255), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        _created(),
        sa.CheckConstraint("role IN ('primary', 'gallery', 'mockup_base')", name="ck_assets_role"),
        sa.CheckConstraint("sort_order >= 0", name="ck_assets_sort_order_non_negative"),
    )
    op.create_index("ix_assets_product_id", "assets", ["product_id"])


def downgrade() -> None:
    op.drop_table("assets")
    op.drop_table("skus")
    op.drop_table("variants")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("users")
