"""CAT01: category tree, slugs, cycle prevention, deactivation."""
from tests.helpers import BASE, error_code, make_category


def _flatten(nodes):
    for node in nodes:
        yield node
        yield from _flatten(node["children"])


def _chain(client, headers):
    a = make_category(client, headers, "apparel")
    b = make_category(client, headers, "hoodies", parent_id=a["id"])
    c = make_category(client, headers, "zip-hoodies", parent_id=b["id"])
    return a, b, c


def test_category_tree_is_nested(client, admin_headers):
    a, b, c = _chain(client, admin_headers)
    make_category(client, admin_headers, "drinkware")
    tree = client.get(f"{BASE}/categories", headers=admin_headers).json()
    assert [n["slug"] for n in tree] == ["apparel", "drinkware"]
    assert tree[0]["children"][0]["slug"] == "hoodies"
    assert tree[0]["children"][0]["children"][0]["slug"] == "zip-hoodies"


def test_unknown_parent_is_a_client_error(client, admin_headers):
    response = client.post(
        f"{BASE}/categories", json={"name": "X", "slug": "xx", "parent_id": 999}, headers=admin_headers
    )
    assert response.status_code == 422 and error_code(response) == "invalid_reference"


def test_category_cannot_be_its_own_parent(client, admin_headers):
    a = make_category(client, admin_headers)
    response = client.patch(f"{BASE}/categories/{a['id']}", json={"parent_id": a["id"]}, headers=admin_headers)
    assert response.status_code == 409 and error_code(response) == "category_cycle"


def test_category_cannot_become_its_own_ancestor(client, admin_headers):
    a, b, c = _chain(client, admin_headers)
    # apparel -> hoodies -> zip-hoodies ; moving apparel under zip-hoodies would create a loop
    response = client.patch(f"{BASE}/categories/{a['id']}", json={"parent_id": c["id"]}, headers=admin_headers)
    assert response.status_code == 409 and error_code(response) == "category_cycle"
    tree = client.get(f"{BASE}/categories", headers=admin_headers).json()
    assert tree[0]["id"] == a["id"] and tree[0]["parent_id"] is None  # unchanged


def test_valid_move_and_move_to_root(client, admin_headers):
    a, b, c = _chain(client, admin_headers)
    moved = client.patch(f"{BASE}/categories/{c['id']}", json={"parent_id": a["id"]}, headers=admin_headers)
    assert moved.status_code == 200 and moved.json()["parent_id"] == a["id"]
    root = client.patch(f"{BASE}/categories/{c['id']}", json={"parent_id": None}, headers=admin_headers)
    assert root.status_code == 200 and root.json()["parent_id"] is None


def test_slug_update_must_stay_unique(client, admin_headers):
    make_category(client, admin_headers, "apparel")
    b = make_category(client, admin_headers, "drinkware")
    response = client.patch(f"{BASE}/categories/{b['id']}", json={"slug": "apparel"}, headers=admin_headers)
    assert response.status_code == 409 and error_code(response) == "duplicate_slug"


def test_deactivating_a_parent_deactivates_all_descendants(client, admin_headers):
    a, b, c = _chain(client, admin_headers)
    other = make_category(client, admin_headers, "drinkware")
    response = client.patch(f"{BASE}/categories/{a['id']}", json={"is_active": False}, headers=admin_headers)
    assert response.status_code == 200 and response.json()["is_active"] is False
    tree = client.get(f"{BASE}/categories", headers=admin_headers).json()
    by_slug = {n["slug"]: n["is_active"] for n in _flatten(tree)}
    assert by_slug == {"apparel": False, "hoodies": False, "zip-hoodies": False, "drinkware": True}


def test_cannot_reactivate_a_child_under_an_inactive_parent(client, admin_headers):
    a, b, c = _chain(client, admin_headers)
    client.patch(f"{BASE}/categories/{a['id']}", json={"is_active": False}, headers=admin_headers)
    response = client.patch(f"{BASE}/categories/{c['id']}", json={"is_active": True}, headers=admin_headers)
    assert response.status_code == 409 and error_code(response) == "parent_inactive"
    assert client.patch(f"{BASE}/categories/{a['id']}", json={"is_active": True}, headers=admin_headers).status_code == 200


def test_cannot_create_category_or_product_under_inactive_category(client, admin_headers):
    a = make_category(client, admin_headers)
    client.patch(f"{BASE}/categories/{a['id']}", json={"is_active": False}, headers=admin_headers)
    child = client.post(
        f"{BASE}/categories", json={"name": "C", "slug": "cc", "parent_id": a["id"]}, headers=admin_headers
    )
    assert child.status_code == 409 and error_code(child) == "parent_inactive"
    product = client.post(
        f"{BASE}/products", json={"category_id": a["id"], "name": "P", "slug": "pp"}, headers=admin_headers
    )
    assert product.status_code == 409 and error_code(product) == "category_inactive"
