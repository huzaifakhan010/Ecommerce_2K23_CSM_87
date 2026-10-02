"""CAT06: every administrative route rejects anonymous and non-admin callers."""
import datetime

import jwt
import pytest

from app.config import get_settings
from tests.helpers import BASE, error_code, make_category

ADMIN_ROUTES = [
    ("POST", f"{BASE}/categories", {"name": "X", "slug": "xx"}),
    ("GET", f"{BASE}/categories", None),
    ("PATCH", f"{BASE}/categories/1", {"name": "Y"}),
    ("POST", f"{BASE}/products", {"category_id": 1, "name": "P", "slug": "pp"}),
    ("GET", f"{BASE}/products", None),
    ("GET", f"{BASE}/products/1", None),
    ("PATCH", f"{BASE}/products/1", {"name": "Z"}),
    ("DELETE", f"{BASE}/products/1", None),
    ("POST", f"{BASE}/products/1/variants", {"option_values": {"size": "M"}}),
    ("POST", f"{BASE}/products/1/skus", {"code": "ABC-1", "price": "1.00"}),
    ("PATCH", f"{BASE}/skus/1", {"stock_quantity": 1}),
]
IDS = [f"{m} {p}" for m, p, _ in ADMIN_ROUTES]


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES, ids=IDS)
def test_anonymous_requests_get_401(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES, ids=IDS)
def test_customer_tokens_get_403(client, customer_headers, method, path, body):
    response = client.request(method, path, json=body, headers=customer_headers)
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


def test_admin_is_allowed(client, admin_headers):
    assert client.get(f"{BASE}/categories", headers=admin_headers).status_code == 200


def test_rejected_write_does_not_persist(client, admin_headers, customer_headers):
    client.post(f"{BASE}/categories", json={"name": "Sneaky", "slug": "sneaky"}, headers=customer_headers)
    client.post(f"{BASE}/categories", json={"name": "Sneaky", "slug": "sneaky"})
    assert client.get(f"{BASE}/categories", headers=admin_headers).json() == []


def test_garbage_and_wrong_scheme_tokens_get_401(client):
    assert client.get(f"{BASE}/categories", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    assert client.get(f"{BASE}/categories", headers={"Authorization": "Basic abc"}).status_code == 401


def _token(sub="1", minutes=5, secret=None):
    settings = get_settings()
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    return jwt.encode({"sub": sub, "exp": exp}, secret or settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_expired_token_gets_401(client, admin_headers):
    response = client.get(f"{BASE}/categories", headers={"Authorization": f"Bearer {_token(minutes=-5)}"})
    assert response.status_code == 401 and error_code(response) == "invalid_token"


def test_token_signed_with_another_secret_gets_401(client, admin_headers):
    bad = _token(secret="a-completely-different-secret-value-0123456789")
    assert client.get(f"{BASE}/categories", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_token_for_unknown_user_gets_401(client):
    response = client.get(f"{BASE}/categories", headers={"Authorization": f"Bearer {_token(sub='9999')}"})
    assert response.status_code == 401
