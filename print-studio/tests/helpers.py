BASE = "/api/v1/admin"


def make_category(client, headers, slug="apparel", name=None, parent_id=None):
    response = client.post(
        f"{BASE}/categories",
        json={"name": name or slug.title(), "slug": slug, "parent_id": parent_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_product(client, headers, category_id, slug="classic-hoodie", **extra):
    body = {"category_id": category_id, "name": slug.replace("-", " ").title(), "slug": slug, **extra}
    response = client.post(f"{BASE}/products", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def make_sku(client, headers, product_id, code="HOOD-001", price="49.99", **extra):
    """Returns the raw response so tests can assert on rejections as well."""
    body = {"code": code, "price": price, **extra}
    return client.post(f"{BASE}/products/{product_id}/skus", json=body, headers=headers)


def error_code(response):
    return response.json()["error"]["code"]
