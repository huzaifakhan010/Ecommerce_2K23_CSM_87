"""CAT03/CAT04 and the publication-related business rules."""
from tests.helpers import BASE, error_code, make_category, make_product, make_sku


def _product(client, headers, slug="classic-hoodie", category_slug=None):
    category = make_category(client, headers, slug=category_slug or f"cat-{slug}")
    return make_product(client, headers, category["id"], slug=slug)


def test_draft_product_may_have_no_sku(client, admin_headers):
    product = _product(client, admin_headers)
    fetched = client.get(f"{BASE}/products/{product['id']}", headers=admin_headers).json()
    assert fetched["status"] == "draft" and fetched["skus"] == []


def test_published_product_must_have_an_active_sku(client, admin_headers):
    product = _product(client, admin_headers)
    response = client.patch(f"{BASE}/products/{product['id']}", json={"status": "published"}, headers=admin_headers)
    assert response.status_code == 409 and error_code(response) == "publish_requires_sku"
    make_sku(client, admin_headers, product["id"])
    ok = client.patch(f"{BASE}/products/{product['id']}", json={"status": "published"}, headers=admin_headers)
    assert ok.status_code == 200 and ok.json()["status"] == "published"


def test_inactive_sku_does_not_count_for_publication(client, admin_headers):
    product = _product(client, admin_headers)
    make_sku(client, admin_headers, product["id"], is_active=False)
    response = client.patch(f"{BASE}/products/{product['id']}", json={"status": "published"}, headers=admin_headers)
    assert response.status_code == 409


def test_last_active_sku_of_a_published_product_cannot_be_deactivated(client, admin_headers):
    product = _product(client, admin_headers)
    first = make_sku(client, admin_headers, product["id"], "ABC-1", option_values={"size": "S"}).json()
    second = make_sku(client, admin_headers, product["id"], "ABC-2", option_values={"size": "M"}).json()
    client.patch(f"{BASE}/products/{product['id']}", json={"status": "published"}, headers=admin_headers)
    assert client.patch(f"{BASE}/skus/{first['id']}", json={"is_active": False}, headers=admin_headers).status_code == 200
    blocked = client.patch(f"{BASE}/skus/{second['id']}", json={"is_active": False}, headers=admin_headers)
    assert blocked.status_code == 409 and error_code(blocked) == "last_active_sku"


def test_product_with_variants_requires_a_variant_for_every_sku(client, admin_headers):
    product = _product(client, admin_headers)
    assert make_sku(client, admin_headers, product["id"], "ABC-1", option_values={"size": "M"}).status_code == 201
    response = make_sku(client, admin_headers, product["id"], "ABC-2")
    assert response.status_code == 422 and error_code(response) == "variant_required"


def test_variants_of_a_product_must_share_the_same_option_names(client, admin_headers):
    product = _product(client, admin_headers)
    client.post(f"{BASE}/products/{product['id']}/variants", json={"option_values": {"size": "M"}}, headers=admin_headers)
    response = client.post(
        f"{BASE}/products/{product['id']}/variants", json={"option_values": {"color": "Black"}}, headers=admin_headers
    )
    assert response.status_code == 422 and error_code(response) == "variant_option_mismatch"


def test_duplicate_variant_combination_is_rejected_case_insensitively(client, admin_headers):
    product = _product(client, admin_headers)
    url = f"{BASE}/products/{product['id']}/variants"
    assert client.post(url, json={"option_values": {"size": "M", "color": "Black"}}, headers=admin_headers).status_code == 201
    dup = client.post(url, json={"option_values": {"color": "black", "size": "m"}}, headers=admin_headers)
    assert dup.status_code == 409 and error_code(dup) == "duplicate_variant"


def test_sku_by_option_values_reuses_an_existing_variant(client, admin_headers):
    product = _product(client, admin_headers)
    variant = client.post(
        f"{BASE}/products/{product['id']}/variants", json={"option_values": {"size": "M"}}, headers=admin_headers
    ).json()
    sku = make_sku(client, admin_headers, product["id"], "ABC-1", option_values={"size": "m"}).json()
    assert sku["variant_id"] == variant["id"]


def test_missing_combination_is_not_created_as_a_fake_sku(client, admin_headers):
    """CAT04: offer 3 of the 4 colour/size combinations; the 4th must simply not exist."""
    product = _product(client, admin_headers)
    offered = [("Black", "S"), ("Black", "M"), ("White", "S")]  # White/M is intentionally not offered
    for index, (color, size) in enumerate(offered, start=1):
        response = make_sku(
            client, admin_headers, product["id"], f"HOOD-{index}", option_values={"color": color, "size": size}
        )
        assert response.status_code == 201
    fetched = client.get(f"{BASE}/products/{product['id']}", headers=admin_headers).json()
    combos = {(v["option_values"]["color"], v["option_values"]["size"]) for v in fetched["variants"]}
    assert combos == set(offered)
    assert {sku["code"] for sku in fetched["skus"]} == {"HOOD-1", "HOOD-2", "HOOD-3"}  # no zero-stock placeholder


def test_variant_less_product_allows_exactly_one_default_sku(client, admin_headers):
    product = _product(client, admin_headers)
    assert make_sku(client, admin_headers, product["id"], "MUG-1").status_code == 201
    second = make_sku(client, admin_headers, product["id"], "MUG-2")
    assert second.status_code == 409 and error_code(second) == "default_sku_exists"
    variant = client.post(
        f"{BASE}/products/{product['id']}/variants", json={"option_values": {"size": "M"}}, headers=admin_headers
    )
    assert variant.status_code == 409 and error_code(variant) == "default_sku_exists"


def test_variant_from_another_product_is_rejected(client, admin_headers):
    one = _product(client, admin_headers, "product-one")
    two = _product(client, admin_headers, "product-two")
    variant = client.post(
        f"{BASE}/products/{one['id']}/variants", json={"option_values": {"size": "M"}}, headers=admin_headers
    ).json()
    response = make_sku(client, admin_headers, two["id"], "ABC-1", variant_id=variant["id"])
    assert response.status_code == 422 and error_code(response) == "invalid_reference"


def test_cannot_send_variant_id_and_option_values_together(client, admin_headers):
    product = _product(client, admin_headers)
    response = make_sku(client, admin_headers, product["id"], variant_id=1, option_values={"size": "M"})
    assert response.status_code == 422


def test_out_of_stock_and_inactive_sku_are_represented_explicitly(client, admin_headers):
    product = _product(client, admin_headers)
    sku = make_sku(client, admin_headers, product["id"], stock_quantity=0).json()
    assert sku["availability"] == "out_of_stock" and sku["is_active"] is True
    inactive = client.patch(f"{BASE}/skus/{sku['id']}", json={"is_active": False}, headers=admin_headers).json()
    assert inactive["availability"] == "inactive"


def test_archiving_a_product_keeps_rows_but_deactivates_skus(client, admin_headers):
    product = _product(client, admin_headers)
    make_sku(client, admin_headers, product["id"], "ABC-1")
    assert client.delete(f"{BASE}/products/{product['id']}", headers=admin_headers).status_code == 204
    fetched = client.get(f"{BASE}/products/{product['id']}", headers=admin_headers).json()
    assert fetched["status"] == "archived"
    assert [s["is_active"] for s in fetched["skus"]] == [False]
    blocked = make_sku(client, admin_headers, product["id"], "ABC-2")
    assert blocked.status_code == 409 and error_code(blocked) == "product_archived"
