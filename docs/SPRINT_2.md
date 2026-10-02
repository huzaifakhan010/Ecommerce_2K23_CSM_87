# Sprint 2: Catalog Data Foundation

**Course:** E-Commerce · **Project:** Custom Print-on-Demand Studio
**Stack (unchanged from Sprint 1):** FastAPI · PostgreSQL · SQLAlchemy 2 / Alembic · pytest

---

## 1. Sprint goal and scope boundary

**Goal.** Given a catalog administrator, the system persists categories, products, variants and SKUs without losing identity, relationship, price or inventory meaning.

| In scope (implemented) | Out of scope (Sprint 3+) |
|---|---|
| Category tree with stable ids + unique slugs (CAT01) | Dynamic-specification *management*, asset upload, public catalog search |
| Product create/edit, status, category assignment (CAT02) | Publication workflows beyond the status rule in §5 |
| Variants and SKUs: unique code, own price and stock (CAT03) | Design upload and live mockup (Sprint 1 feature, deferred) |
| Only valid variant combinations are stored (CAT04) | Cart, checkout, orders, payment, shipping |
| DB-enforced uniqueness, FK, CHECK constraints (CAT05) | Public (non-admin) catalog reads |
| JWT-protected admin API, 401/403 on everything else (CAT06) | |
| Migrations, seed data, automated tests, README | |

**Model-only (not claimed as functionality):** the `assets` table and `products.specifications` column exist in the schema and the specification validation rule is written down and enforced at the API boundary, but there are **no asset-upload endpoints** and no specification-based search. Those start Sprint 3.

---

## 2. Sprint 1 decisions reused or changed

Sprint 1 reference: [`docs/SPRINT_1.md`](SPRINT_1.md).

| Sprint 1 decision | Sprint 2 status | Why |
|---|---|---|
| Stack: Next.js · FastAPI · PostgreSQL · Celery/Redis | **Reused** (FastAPI + PostgreSQL). Frontend, Celery, Redis not needed yet. | Sprint 2 is backend/data only. |
| JWT + password hashing, `customer`/`admin` roles | **Reused** (bcrypt + PyJWT). | CAT06 needs an admin identity. |
| JSONB for flexible customization metadata | **Reused** for `products.specifications` and `variants.option_values` (JSON on SQLite for tests). | Option sets differ per product. |
| `PRODUCTS.base_price`, `PRODUCTS.stock_quantity` | **Changed → moved to `SKUS.price` / `SKUS.stock_quantity`.** | Price and stock belong to the sellable unit, not the product. |
| `CART_ITEMS.product_id`, `ORDER_ITEMS.product_id` | **Changed (planned) → `sku_id`** (+ order-time snapshot columns). | A cart/order line must identify a specific SKU. |
| `string`, `int`, `decimal` in the ERD | **Changed → explicit SQL types** (`VARCHAR(n)`, `INTEGER`, `NUMERIC(10,2)`, `TIMESTAMP`). | Required by the manual; flagged in Sprint 1 review. |
| `CATEGORIES.parent_category_id` (no relationship drawn) | **Changed:** self-relationship drawn, renamed `parent_id`, FK policy + `CHECK (parent_id <> id)`. | Needed for CAT01. |
| `fulfillment_stage` on `ORDERS` | **Planned change → `ORDER_ITEMS`.** | One order can mix print / embroidery / engraving lines. |
| `USERS 1:1 CART` | **Planned change → 1:0..1** (cart created lazily). | Avoids a cart row per registration. |
| Added unique constraints (`users.email`, slugs, SKU code) | **New** | CAT05. |
| Added `is_active`, `status`, `updated_at` | **New** | Soft deactivation and auditing. |

---

## 3. Updated ERD and data dictionary

### 3.1 ERD

Implemented in Sprint 2: `USERS`, `CATEGORIES`, `PRODUCTS`, `VARIANTS`, `SKUS`, `ASSETS`.
**Planned (Sprint 3+, shown to prove the connection):** `CARTS`, `CART_ITEMS`, `ORDERS`, `ORDER_ITEMS`.
Mermaid cannot write `NUMERIC(10,2)` in a type, so precision is given in the comment strings and the dictionary below.

```mermaid
erDiagram
    USERS ||--o{ ORDERS : places
    USERS ||--o| CARTS : owns
    CARTS ||--o{ CART_ITEMS : contains
    ORDERS ||--|{ ORDER_ITEMS : contains
    CATEGORIES |o--o{ CATEGORIES : "parent of"
    CATEGORIES ||--o{ PRODUCTS : contains
    PRODUCTS ||--o{ VARIANTS : has
    PRODUCTS ||--o{ SKUS : "sold as"
    VARIANTS |o--o{ SKUS : materializes
    PRODUCTS ||--o{ ASSETS : displays
    VARIANTS |o--o{ ASSETS : "illustrated by"
    SKUS ||--o{ CART_ITEMS : "selected as"
    SKUS ||--o{ ORDER_ITEMS : "sold as"

    USERS {
        INTEGER id PK
        VARCHAR(255) email UK
        VARCHAR(255) password_hash
        VARCHAR(120) full_name
        VARCHAR(16) role "customer or admin"
        BOOLEAN is_active
        TIMESTAMP created_at
    }
    CATEGORIES {
        INTEGER id PK
        INTEGER parent_id FK "nullable, RESTRICT"
        VARCHAR(120) name
        VARCHAR(120) slug UK
        BOOLEAN is_active
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }
    PRODUCTS {
        INTEGER id PK
        INTEGER category_id FK "RESTRICT"
        VARCHAR(200) name
        VARCHAR(200) slug UK
        TEXT description
        VARCHAR(16) status "draft, published, archived"
        VARCHAR(16) customization_type "print, embroidery, engraving"
        JSONB specifications "validated object"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }
    VARIANTS {
        INTEGER id PK
        INTEGER product_id FK "CASCADE"
        JSONB option_values "e.g. color, size"
        VARCHAR(255) combination_key "UK with product_id"
        TIMESTAMP created_at
    }
    SKUS {
        INTEGER id PK
        INTEGER product_id FK "CASCADE"
        INTEGER variant_id FK "nullable, CASCADE"
        VARCHAR(64) code UK
        NUMERIC price "10,2 and CHECK >= 0"
        INTEGER stock_quantity "CHECK >= 0"
        BOOLEAN is_active
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }
    ASSETS {
        INTEGER id PK
        INTEGER product_id FK "CASCADE"
        INTEGER variant_id FK "nullable, SET NULL"
        VARCHAR(512) storage_key
        VARCHAR(16) role "primary, gallery, mockup_base"
        VARCHAR(255) alt_text
        INTEGER sort_order "CHECK >= 0"
        TIMESTAMP created_at
    }
    CARTS {
        INTEGER id PK
        INTEGER user_id FK "UK, planned"
        TIMESTAMP updated_at
    }
    CART_ITEMS {
        INTEGER id PK
        INTEGER cart_id FK "planned"
        INTEGER sku_id FK "RESTRICT, planned"
        INTEGER quantity
        VARCHAR(512) design_asset_url
        JSONB customization_data
    }
    ORDERS {
        INTEGER id PK
        INTEGER user_id FK "RESTRICT, planned"
        NUMERIC total_amount "12,2"
        VARCHAR(24) status
        TIMESTAMP created_at
    }
    ORDER_ITEMS {
        INTEGER id PK
        INTEGER order_id FK "planned"
        INTEGER sku_id FK "RESTRICT, planned"
        VARCHAR(64) sku_code "snapshot"
        VARCHAR(200) product_name "snapshot"
        NUMERIC unit_price "10,2 snapshot"
        INTEGER quantity
        VARCHAR(24) fulfillment_stage
        JSONB customization_data
    }
```

### 3.2 Cardinality

| Relationship | Cardinality | Meaning |
|---|---|---|
| CATEGORIES → CATEGORIES (parent) | 0..1 : N | A category has at most one parent (tree). |
| CATEGORIES → PRODUCTS | 1 : N | One **canonical** category per product. |
| PRODUCTS → VARIANTS | 1 : N (zero or more) | A product may have no variants. |
| PRODUCTS → SKUS | 1 : N | A SKU always belongs to a product (denormalised for the `/products/:id/skus` route and a cheap "is anything sellable?" check). |
| VARIANTS → SKUS | 0..1 : N | A SKU has at most one variant; variant-less SKUs are allowed (one per product, DB-enforced). |
| PRODUCTS / VARIANTS → ASSETS | 1 : N / 0..1 : N | Asset belongs to a product, optionally to one variant. |
| SKUS → CART_ITEMS / ORDER_ITEMS | 1 : N | Cart and order lines reference a **SKU** (planned). |
| USERS → CARTS | 1 : 0..1 | Cart created lazily (planned). |

### 3.3 Foreign-key delete / update policies

All foreign keys use `ON UPDATE CASCADE`; primary keys are surrogate integers that are never updated, so this is a formality.

| Foreign key | ON DELETE | Reason |
|---|---|---|
| `categories.parent_id → categories.id` | RESTRICT | Never orphan a subtree; deactivate instead. |
| `products.category_id → categories.id` | RESTRICT | Never lose a product's category. |
| `variants.product_id → products.id` | CASCADE | A variant has no meaning without its product. |
| `skus.product_id → products.id` | CASCADE | Same. (Protected by order lines below.) |
| `skus.variant_id → variants.id` | CASCADE | A SKU materialises a variant. |
| `assets.product_id → products.id` | CASCADE | Assets belong to the product. |
| `assets.variant_id → variants.id` | SET NULL | Keep the image; it becomes product-level. |
| *Planned:* `cart_items.sku_id`, `order_items.sku_id → skus.id` | **RESTRICT** | A SKU that was ordered can never be hard-deleted → history stays intact (see Q7). |
| *Planned:* `cart_items.cart_id → carts.id` | CASCADE | Deleting a cart deletes its lines. |
| *Planned:* `orders.user_id → users.id`, `order_items.order_id → orders.id` | RESTRICT | Orders are records, not deletable by cascade. |

### 3.4 Data dictionary (implemented tables)

**users** — `id INTEGER PK` · `email VARCHAR(255) NOT NULL UNIQUE` · `password_hash VARCHAR(255) NOT NULL` · `full_name VARCHAR(120) NOT NULL` · `role VARCHAR(16) NOT NULL CHECK IN ('customer','admin') DEFAULT 'customer'` · `is_active BOOLEAN NOT NULL DEFAULT true` · `created_at TIMESTAMPTZ NOT NULL`

**categories** — `id INTEGER PK` · `parent_id INTEGER NULL FK` · `name VARCHAR(120) NOT NULL` · `slug VARCHAR(120) NOT NULL UNIQUE` · `is_active BOOLEAN NOT NULL DEFAULT true` · `created_at`, `updated_at TIMESTAMPTZ NOT NULL` · `CHECK (parent_id IS NULL OR parent_id <> id)`

**products** — `id INTEGER PK` · `category_id INTEGER NOT NULL FK` · `name VARCHAR(200) NOT NULL` · `slug VARCHAR(200) NOT NULL UNIQUE` · `description TEXT NOT NULL DEFAULT ''` · `status VARCHAR(16) NOT NULL DEFAULT 'draft' CHECK IN ('draft','published','archived')` · `customization_type VARCHAR(16) NOT NULL DEFAULT 'print' CHECK IN ('print','embroidery','engraving')` · `specifications JSONB NOT NULL DEFAULT '{}'` · timestamps

**variants** — `id INTEGER PK` · `product_id INTEGER NOT NULL FK` · `option_values JSONB NOT NULL` · `combination_key VARCHAR(255) NOT NULL` · `created_at` · `UNIQUE (product_id, combination_key)`

**skus** — `id INTEGER PK` · `product_id INTEGER NOT NULL FK` · `variant_id INTEGER NULL FK` · `code VARCHAR(64) NOT NULL UNIQUE` · `price NUMERIC(10,2) NOT NULL CHECK (price >= 0)` · `stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0)` · `is_active BOOLEAN NOT NULL DEFAULT true` · timestamps · partial `UNIQUE INDEX (product_id) WHERE variant_id IS NULL`

**assets** *(model only)* — `id PK` · `product_id FK` · `variant_id FK NULL` · `storage_key VARCHAR(512)` · `role VARCHAR(16) CHECK IN ('primary','gallery','mockup_base')` · `alt_text VARCHAR(255)` · `sort_order INTEGER CHECK (>= 0)` · `created_at`

**Money** is `NUMERIC(10,2)` in the database, `Decimal` in Python and a **string** in JSON (`"59.00"`); floats are never used. **Slug rule:** `^[a-z0-9]+(?:-[a-z0-9]+)*$`. **SKU code rule:** trimmed, upper-cased, `^[A-Z0-9][A-Z0-9-]{2,63}$` (so uniqueness is effectively case-insensitive).

**Specification validation rule (written):** `products.specifications` must be a JSON object with ≤ 20 keys; keys are `snake_case` (`^[a-z][a-z0-9_]{0,39}$`); each value is a string (≤ 200 chars), number, boolean, or list (≤ 20) of those scalars; nested objects are rejected. Implemented in `app/schemas.py::validate_specifications`. The EAV alternative was not chosen: JSONB keeps variant-independent attributes in one row, and Sprint 3 can add GIN indexes if search needs them.

**Variant option rule:** `option_values` has 1–3 options; keys are `snake_case`; values are 1–50 chars. All variants of one product must define exactly the same option names (so a product is a consistent grid, e.g. `color × size`), and each combination exists at most once (case-insensitive).

---

## 4. Administration routes

All routes: base path `/api/v1/admin`, **`Authorization: Bearer <JWT>` required, role `admin` only** (one router-level dependency protects every route in `app/routers/admin.py`). Interactive reference: Swagger UI at `/docs`.

**Authentication helpers (not admin):** `POST /api/v1/auth/register` (always creates a *customer*), `POST /api/v1/auth/login` → `{"access_token": "...", "token_type": "bearer"}`, `GET /api/v1/auth/me`.

**Common error envelope** (every non-2xx response):

```json
{ "error": { "code": "duplicate_sku_code", "message": "SKU code 'HOOD-BLK-M' already exists.", "details": [] } }
```

| Status | `code` values | When |
|---|---|---|
| 401 | `not_authenticated`, `invalid_token`, `invalid_credentials` | Missing / bad / expired token |
| 403 | `forbidden` | Valid token, role is not `admin` |
| 404 | `product_not_found`, `category_not_found`, `sku_not_found`, `not_found` | Unknown path id / route |
| 409 | `duplicate_slug`, `duplicate_sku_code`, `duplicate_variant`, `default_sku_exists`, `category_cycle`, `parent_inactive`, `category_inactive`, `publish_requires_sku`, `last_active_sku`, `insufficient_stock`, `product_archived`, `constraint_violation` | State conflicts / uniqueness |
| 422 | `validation_error` (with `details: [{field, message}]`), `invalid_reference`, `variant_required`, `variant_option_mismatch` | Bad input |

### Route table

| Method | Route | Purpose | Success |
|---|---|---|---|
| POST | `/api/v1/admin/categories` | Create a category | 201 |
| GET | `/api/v1/admin/categories` | Category tree | 200 |
| PATCH | `/api/v1/admin/categories/{id}` | Rename, re-slug, move, (de)activate | 200 |
| POST | `/api/v1/admin/products` | Create a **draft** product | 201 |
| GET | `/api/v1/admin/products` | List (filters `status`, `category_id`; `limit` 1–100, `offset`) | 200 |
| GET | `/api/v1/admin/products/{id}` | One product with variants and SKUs | 200 |
| PATCH | `/api/v1/admin/products/{id}` | Edit content, category, status | 200 |
| DELETE | `/api/v1/admin/products/{id}` | **Soft** delete: archive + deactivate SKUs | 204 |
| POST | `/api/v1/admin/products/{id}/variants` | Add a valid option combination | 201 |
| POST | `/api/v1/admin/products/{id}/skus` | Add a SKU | 201 |
| PATCH | `/api/v1/admin/skus/{id}` | Update price, stock, active flag | 200 |

### Request fields and examples

**`POST /categories`** — body: `name` (1–120, required), `slug` (required), `parent_id` (optional). Errors: 409 `duplicate_slug` / `parent_inactive`, 422 `invalid_reference` / `validation_error`.
```json
// request                                              // 201 response
{"name": "Hoodies", "slug": "hoodies", "parent_id": 1}  {"id": 2, "parent_id": 1, "name": "Hoodies", "slug": "hoodies", "is_active": true, "created_at": "2026-10-05T09:30:00Z", "updated_at": "2026-10-05T09:30:00Z"}
```

**`GET /categories`** — no body. 200 → list of root nodes; each node is a category object plus `"children": [ ...nodes ]`.
```json
[{"id": 1, "parent_id": null, "name": "Apparel", "slug": "apparel", "is_active": true, "created_at": "…", "updated_at": "…",
  "children": [{"id": 2, "parent_id": 1, "name": "Hoodies", "slug": "hoodies", "is_active": true, "created_at": "…", "updated_at": "…", "children": []}]}]
```

**`PATCH /categories/{id}`** — any of `name`, `slug`, `parent_id` (`null` = move to top level), `is_active`. Unknown fields → 422. Errors: 409 `category_cycle` (own parent / own descendant), `duplicate_slug`, `parent_inactive`; 404.
```json
{"parent_id": 2}   // 409 → {"error": {"code": "category_cycle", "message": "Move rejected: the new parent is a descendant of this category.", "details": []}}
```

**`POST /products`** — body: `category_id`, `name`, `slug` (required); `description`, `customization_type` (`print`|`embroidery`|`engraving`, default `print`), `specifications` (optional). `status` is **not** accepted: products are created as drafts. Errors: 409 `duplicate_slug` / `category_inactive`, 422 `invalid_reference` / `validation_error`.
```json
{"category_id": 2, "name": "Classic Custom Hoodie", "slug": "classic-custom-hoodie", "specifications": {"material": "cotton blend"}}
// 201
{"id": 1, "category_id": 2, "name": "Classic Custom Hoodie", "slug": "classic-custom-hoodie", "description": "", "status": "draft",
 "customization_type": "print", "specifications": {"material": "cotton blend"}, "created_at": "…", "updated_at": "…", "variants": [], "skus": []}
```

**`GET /products`** — query: `status`, `category_id`, `limit` (default 20), `offset`. 200 → `{"items": [ProductOut…], "total": 4, "limit": 20, "offset": 0}`.

**`PATCH /products/{id}`** — any of `category_id`, `name`, `slug`, `description`, `status`, `customization_type`, `specifications` (no nulls). Errors: 409 `publish_requires_sku`, `duplicate_slug`, `category_inactive`; 404.
```json
{"status": "published"}   // with no active SKU → 409 {"error": {"code": "publish_requires_sku", "message": "A product needs at least one active SKU to be published.", "details": []}}
```

**`POST /products/{id}/variants`** — body: `option_values` (object of 1–3 options). Errors: 409 `duplicate_variant` / `default_sku_exists` / `product_archived`, 422 `variant_option_mismatch`.
```json
{"option_values": {"color": "Black", "size": "M"}}   // 201 → {"id": 1, "product_id": 1, "option_values": {"color": "Black", "size": "M"}, "created_at": "…"}
```

**`POST /products/{id}/skus`** — body: `code`, `price` (required; string or number, ≥ 0, ≤ 2 decimals), `stock_quantity` (default 0, ≥ 0), `is_active` (default true), and **either** `variant_id` **or** `option_values` (the variant is found or created automatically). A product that has variants requires one of them; a product without variants may have exactly one variant-less SKU. Errors: 409 `duplicate_sku_code` / `default_sku_exists` / `product_archived`, 422 `variant_required` / `variant_option_mismatch` / `invalid_reference` / `validation_error`.
```json
{"code": "HOOD-BLK-M", "price": "59.00", "stock_quantity": 40, "variant_id": 1}
// 201
{"id": 1, "product_id": 1, "variant_id": 1, "code": "HOOD-BLK-M", "price": "59.00", "stock_quantity": 40, "is_active": true,
 "created_at": "…", "updated_at": "…", "availability": "in_stock"}
// duplicate code (any letter case) → 409 {"error": {"code": "duplicate_sku_code", "message": "SKU code 'HOOD-BLK-M' already exists.", "details": []}}
```

**`PATCH /skus/{id}`** — at least one of `price`, `stock_quantity` (absolute, ≥ 0), `stock_delta` (relative, ± integer), `is_active`; `stock_quantity` and `stock_delta` are mutually exclusive; the `code` is immutable. Errors: 409 `insufficient_stock` (delta would go below 0), `last_active_sku`; 422; 404.
```json
{"stock_delta": -50}   // stock is 40 → 409 {"error": {"code": "insufficient_stock", "message": "Stock would become negative (40 -50).", "details": []}}
```

**`DELETE /products/{id}`** — 204, no body. Status becomes `archived`, every SKU is deactivated, nothing is physically deleted.

> The examples above are specification examples. Real recorded request/response pairs are in [`print-studio/DEMO_EVIDENCE.md`](../print-studio/DEMO_EVIDENCE.md) (§6).

---

## 5. Data integrity and authorization decisions

### 5.1 Defence in depth (CAT05)

| Rule | API layer (clean 4xx) | Database layer (cannot be bypassed) |
|---|---|---|
| Unique category / product slug | pre-check → 409 `duplicate_slug` | `UNIQUE (slug)` |
| Unique SKU code (case-insensitive) | normalised to upper case, pre-check → 409 | `UNIQUE (code)` |
| Stock never negative | schema `ge=0`; `stock_delta` check → 409 | `CHECK (stock_quantity >= 0)` |
| Price valid, exact | `Decimal`, ≥ 0, ≤ 2 decimals | `NUMERIC(10,2)`, `CHECK (price >= 0)` |
| Valid FKs | 422 `invalid_reference` | `FOREIGN KEY` with explicit policies (§3.3) |
| Category not its own parent | 409 `category_cycle` | `CHECK (parent_id <> id)` |
| Category never its own *ancestor* | ancestor walk before every move → 409 | not expressible as a simple constraint (see §8) |
| One variant-less SKU per product | 409 `default_sku_exists` | partial `UNIQUE INDEX (product_id) WHERE variant_id IS NULL` |
| No duplicate option combination | 409 `duplicate_variant` | `UNIQUE (product_id, combination_key)` |
| Valid status / role / type values | `Literal` types | `CHECK … IN (…)` |

If a race ever slips past a pre-check, the database raises `IntegrityError` and a global handler returns **409 `constraint_violation`** — never a traceback.

### 5.2 Authorization (CAT06)

* Passwords: bcrypt. Tokens: HS256 JWT with `sub`, `iat`, `exp`; the secret comes from `JWT_SECRET` (never committed).
* `get_current_user` returns **401** for a missing header, wrong scheme, bad signature, expired token, or unknown/inactive user. `require_admin` returns **403** when the user's role is not `admin`.
* The role is read from the database on every request (not trusted from the token), so demoting an admin takes effect immediately.
* One router-level `dependencies=[Depends(require_admin)]` protects **every** admin route, so a new route cannot be added unprotected by accident. Authorization runs before validation and before any database write.
* Public registration cannot choose a role (`role` is rejected as an unknown field); admins are created by `scripts/seed.py`.

### 5.3 Business rules (manual §8)

1. **Can a draft product have no SKU? Can a published product have none?** A draft may have none (`test_draft_product_may_have_no_sku`); the seed's *Custom Engraved Plaque* is such a draft. A product **cannot be published without at least one active SKU** (409 `publish_requires_sku`), and the last active SKU of a published product cannot be deactivated (409 `last_active_sku`).
2. **One canonical category or many?** **One** (`products.category_id NOT NULL`). It gives a single breadcrumb and URL per product and keeps the schema simple; cross-category browsing can be added later with a join table without changing SKUs.
3. **What happens when a parent category is deactivated?** All descendants are deactivated in the same transaction; a child cannot be re-activated while its parent is inactive (409 `parent_inactive`); no new category or product can be created under an inactive category. Products already in it are not modified — Sprint 3 public reads must hide products whose category chain is inactive.
4. **How is an out-of-stock SKU represented?** The row stays (`stock_quantity = 0`) and the response carries a computed `availability`: `in_stock`, `out_of_stock`, or `inactive`. The seed's `HOOD-WHT-M` shows `out_of_stock`. A valid-but-sold-out combination is never deleted and is different from a combination that is **not offered** (which simply has no variant/SKU row).
5. **Can two SKUs share a price? Price override?** Yes, prices may repeat (`test_two_skus_may_share_a_price`; every non-L hoodie costs 59.00). There is no override concept: **each SKU owns its price**; the product has no base price to override. A "from" price is derived by Sprint 3 as `MIN(price)` over active SKUs.
6. **What prevents negative stock and duplicate SKU codes?** The database: `CHECK (stock_quantity >= 0)` and `UNIQUE (code)` (`tests/test_models.py`), backed by API validation that returns clean 422/409 errors (`tests/test_validation.py`).
7. **What happens to a product referenced by a future cart/order after it is deactivated?** Nothing is deleted. `DELETE /products/{id}` archives the product and deactivates its SKUs; rows stay, so cart/order lines keep valid foreign keys. `order_items.sku_id` is `RESTRICT`, so an ordered SKU can never be hard-deleted, and orders copy `sku_code`, `product_name` and `unit_price` as a snapshot so history is stable even if the catalog changes. Carts referencing an inactive SKU must be flagged "unavailable" at checkout (Sprint 3).

---

## 6. Seed data and demonstration

### 6.1 Reproducible seed (clean database)

```bash
alembic upgrade head
python -m scripts.seed          # run it twice: the second run changes nothing (idempotent)
```

Seed content (goes through the same service layer as the API, so it obeys the same rules):

| Category tree | Products | Variants / SKUs |
|---|---|---|
| Apparel → Hoodies, T-Shirts | **Classic Custom Hoodie** (published) | 5 variants/SKUs: Black S·M·L, White S·M. **White / L is intentionally not offered** (no variant, no SKU). `HOOD-WHT-M` has stock 0 (valid but sold out). |
| Drinkware → Mugs | **Premium Cotton T-Shirt** (published) | 3 variants/SKUs: size S·M·L |
| Awards & Plaques | **Engraved Steel Mug** (published) | no variants; 1 default SKU `MUG-STL-450` |
| | **Custom Engraved Plaque** (draft) | none (a draft may have no SKU) |

Expected totals by construction: 6 categories (two levels), 4 products, 8 variants, 9 SKUs. The seed prints its own summary; the test `tests/test_seed.py` asserts these properties and idempotency.

### 6.2 Administrator demonstration

`python -m scripts.demo` runs, against a throw-away database, exactly the flow the manual asks for: admin login → create category → create product → create variant → create SKU → retrieve through the admin API, plus the main rejection paths (401, cycle, duplicate slug/SKU, negative stock, publishing without a SKU). Tokens are redacted. Output: **[`print-studio/DEMO_EVIDENCE.md`](../print-studio/DEMO_EVIDENCE.md)**.

> ✅ **Generated:** `python -m scripts.demo` executed and generated [`print-studio/DEMO_EVIDENCE.md`](../print-studio/DEMO_EVIDENCE.md).

---

## 7. Test strategy, command and result

**Strategy.** Every major business rule has at least one *success* test and one *rejection* test. Database constraints are tested directly (bypassing the API) so they cannot silently rely on API validation.

| File | Covers |
|---|---|
| `tests/test_models.py` | Unique slug/code, `CHECK` on stock/price/status/self-parent, FK enforcement, `RESTRICT`/`CASCADE`, one default SKU, exact decimals |
| `tests/test_validation.py` | Required fields, draft-only creation, duplicate slug/SKU (incl. case), negative stock/price, `stock_delta`, immutable code, pagination |
| `tests/test_categories.py` | Tree shape, self-parent, **cycle prevention**, moves, deactivation cascade, inactive-parent rules |
| `tests/test_variants_and_skus.py` | Variant/SKU combinations, **missing combination not created**, publish rule, last-active-SKU, archive, availability |
| `tests/test_authorization.py` | **All 11 admin routes**: 401 anonymous, 403 customer; bad/expired/foreign-secret tokens; rejected writes do not persist |
| `tests/test_auth.py` | Register/login/me, no role escalation, uniform login failure |
| `tests/test_seed.py` | Seed reproducibility, idempotency, required demo shape |
| `tests/test_migrations.py` | `alembic upgrade head` / `downgrade base` match the models |

**Command**

```bash
pip install -r requirements.txt
pytest -v                       # default: in-memory SQLite (fast, no services)
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/printstudio_test pytest -v   # optional: PostgreSQL
```

**Result**

```text
============================= 93 passed in 3.10s ==============================
```

---

## 8. Known limitations and Sprint 3 backlog

**Known limitations**

* **Multi-level category cycles** cannot be prevented by a plain `CHECK`; the service walks the ancestor chain before each move. Two *concurrent* moves could in theory still create a loop; a PostgreSQL trigger or row locking would close this (Sprint 3 hardening).
* The default test run uses SQLite; JSONB and the partial index are exercised on PostgreSQL only through the optional `TEST_DATABASE_URL` run.
* There is no refresh-token / logout / password-reset flow; tokens simply expire.
* `assets` and `specifications` are schema-level only (see §1).
* Admin list endpoints return full variants/SKUs (fine for the demo catalog size; add projection/pagination of children if the catalog grows).

**Sprint 3 backlog (builds on SKU identity, does not duplicate pricing logic)**

1. Dynamic specifications: management UI/API, search/filter (GIN index) — or migrate to EAV if needed.
2. Asset upload + `assets` endpoints (storage key, role, alt text, sort order).
3. Public catalog reads: published products only, active category chain only, `availability` per SKU, search, pagination.
4. Publication rules / scheduling beyond the current status rule.
5. Catalog-to-cart readiness: `carts`, `cart_items(sku_id)`, `orders`, `order_items(sku_id, snapshots, fulfillment_stage)` with the `RESTRICT` policies in §3.3.
6. Reservation / decrement of stock at checkout inside one transaction (`SELECT … FOR UPDATE` + the existing `CHECK`).
7. Re-introduce the Sprint 1 design upload and mockup preview on top of `products.customization_type`.