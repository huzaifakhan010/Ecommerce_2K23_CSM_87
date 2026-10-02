"""API validation and duplicate handling: clean 4xx errors, never a server traceback."""
from tests.helpers import BASE, error_code, make_category, make_product, make_sku


def _setup(client, headers):
    category = make_category(client, headers)
    return make_product(client, headers, category["id"])


def test_create_product_is_a_draft_with_expected_fields(client, admin_headers):
    category = make_category(client, admin_headers)
    product = make_product(client, admin_headers, category["id"], description="Warm.", specifications={"material": "cotton"})
    assert product["status"] == "draft"
    assert product["skus"] == [] and product["variants"] == []
    assert product["specifications"] == {"material": "cotton"}


def test_create_product_requires_mandatory_fields(client, admin_headers):
    response = client.post(f"{BASE}/products", json={"name": "No slug"}, headers=admin_headers)
    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert {"category_id", "slug"} <= fields


def test_product_status_cannot_be_chosen_on_create(client, admin_headers):
    category = make_category(client, admin_headers)
    response = client.post(
        f"{BASE}/products",
        json={"category_id": category["id"], "name": "P", "slug": "pp", "status": "published"},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_invalid_slug_is_rejected(client, admin_headers):
    category = make_category(client, admin_headers)
    response = client.post(
        f"{BASE}/products", json={"category_id": category["id"], "name": "P", "slug": "Bad Slug"}, headers=admin_headers
    )
    assert response.status_code == 422


def test_invalid_specifications_are_rejected(client, admin_headers):
    category = make_category(client, admin_headers)
    response = client.post(
        f"{BASE}/products",
        json={"category_id": category["id"], "name": "P", "slug": "pp", "specifications": {"Bad Key": {"nested": 1}}},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_product_in_missing_category_is_a_client_error(client, admin_headers):
    response = client.post(
        f"{BASE}/products", json={"category_id": 999, "name": "P", "slug": "pp"}, headers=admin_headers
    )
    assert response.status_code == 422
    assert error_code(response) == "invalid_reference"


def test_duplicate_product_slug_returns_409(client, admin_headers):
    category = make_category(client, admin_headers)
    make_product(client, admin_headers, category["id"], slug="same-slug")
    response = client.post(
        f"{BASE}/products", json={"category_id": category["id"], "name": "Other", "slug": "same-slug"}, headers=admin_headers
    )
    assert response.status_code == 409
    assert error_code(response) == "duplicate_slug"


def test_duplicate_category_slug_returns_409(client, admin_headers):
    make_category(client, admin_headers, "apparel")
    response = client.post(f"{BASE}/categories", json={"name": "Again", "slug": "apparel"}, headers=admin_headers)
    assert response.status_code == 409
    assert error_code(response) == "duplicate_slug"


def test_sku_creation_with_required_fields(client, admin_headers):
    product = _setup(client, admin_headers)
    response = make_sku(client, admin_headers, product["id"], stock_quantity=7)
    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "HOOD-001"
    assert body["price"] == "49.99"  # exact decimal, serialised as a string - never a float
    assert body["stock_quantity"] == 7
    assert body["availability"] == "in_stock"


def test_sku_requires_code_and_price(client, admin_headers):
    product = _setup(client, admin_headers)
    response = client.post(f"{BASE}/products/{product['id']}/skus", json={"stock_quantity": 1}, headers=admin_headers)
    assert response.status_code == 422


def test_duplicate_sku_code_returns_409_even_with_different_case(client, admin_headers):
    product = _setup(client, admin_headers)
    assert make_sku(client, admin_headers, product["id"], "ABC-100").status_code == 201
    other = make_product(client, admin_headers, product["category_id"], slug="second-product")
    response = make_sku(client, admin_headers, other["id"], "abc-100")
    assert response.status_code == 409
    assert error_code(response) == "duplicate_sku_code"


def test_sku_code_is_normalised_to_upper_case(client, admin_headers):
    product = _setup(client, admin_headers)
    assert make_sku(client, admin_headers, product["id"], " hood-xyz ").json()["code"] == "HOOD-XYZ"


def test_negative_initial_stock_is_rejected(client, admin_headers):
    product = _setup(client, admin_headers)
    assert make_sku(client, admin_headers, product["id"], stock_quantity=-1).status_code == 422


def test_price_with_too_many_decimals_or_negative_is_rejected(client, admin_headers):
    product = _setup(client, admin_headers)
    assert make_sku(client, admin_headers, product["id"], "ABC-1", price="1.999").status_code == 422
    assert make_sku(client, admin_headers, product["id"], "ABC-2", price="-1.00").status_code == 422


def test_two_skus_may_share_a_price(client, admin_headers):
    product = _setup(client, admin_headers)
    assert make_sku(client, admin_headers, product["id"], "ABC-1", option_values={"size": "S"}).status_code == 201
    assert make_sku(client, admin_headers, product["id"], "ABC-2", option_values={"size": "M"}).status_code == 201


def test_stock_cannot_become_negative_via_update(client, admin_headers):
    product = _setup(client, admin_headers)
    sku = make_sku(client, admin_headers, product["id"], stock_quantity=3).json()
    below = client.patch(f"{BASE}/skus/{sku['id']}", json={"stock_delta": -4}, headers=admin_headers)
    assert below.status_code == 409 and error_code(below) == "insufficient_stock"
    absolute = client.patch(f"{BASE}/skus/{sku['id']}", json={"stock_quantity": -1}, headers=admin_headers)
    assert absolute.status_code == 422
    ok = client.patch(f"{BASE}/skus/{sku['id']}", json={"stock_delta": -3}, headers=admin_headers)
    assert ok.status_code == 200 and ok.json()["stock_quantity"] == 0
    assert ok.json()["availability"] == "out_of_stock"


def test_sku_update_rejects_code_changes_and_empty_bodies(client, admin_headers):
    product = _setup(client, admin_headers)
    sku = make_sku(client, admin_headers, product["id"]).json()
    assert client.patch(f"{BASE}/skus/{sku['id']}", json={"code": "NEW-1"}, headers=admin_headers).status_code == 422
    assert client.patch(f"{BASE}/skus/{sku['id']}", json={}, headers=admin_headers).status_code == 422
    assert client.patch(f"{BASE}/skus/{sku['id']}", json={"price": None}, headers=admin_headers).status_code == 422


def test_unknown_ids_return_404_in_the_error_envelope(client, admin_headers):
    assert client.get(f"{BASE}/products/999", headers=admin_headers).status_code == 404
    response = client.patch(f"{BASE}/skus/999", json={"stock_delta": 1}, headers=admin_headers)
    assert response.status_code == 404 and error_code(response) == "sku_not_found"


def test_list_products_supports_filters_and_pagination(client, admin_headers):
    category = make_category(client, admin_headers)
    for index in range(3):
        make_product(client, admin_headers, category["id"], slug=f"product-{index}")
    page = client.get(f"{BASE}/products?limit=2&offset=0", headers=admin_headers).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert client.get(f"{BASE}/products?status=published", headers=admin_headers).json()["total"] == 0
    assert client.get(f"{BASE}/products?limit=0", headers=admin_headers).status_code == 422
