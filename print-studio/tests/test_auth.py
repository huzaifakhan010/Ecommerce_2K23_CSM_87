from tests.conftest import PASSWORD
from tests.helpers import error_code


def test_register_creates_a_customer_and_login_works(client):
    body = {"email": "New.User@Example.com", "password": PASSWORD, "full_name": "New User"}
    created = client.post("/api/v1/auth/register", json=body)
    assert created.status_code == 201
    assert created.json()["role"] == "customer" and created.json()["email"] == "new.user@example.com"
    assert "password" not in created.text and "password_hash" not in created.text
    login = client.post("/api/v1/auth/login", json={"email": "new.user@example.com", "password": PASSWORD})
    assert login.status_code == 200 and login.json()["token_type"] == "bearer"
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "new.user@example.com"


def test_duplicate_email_is_rejected(client):
    body = {"email": "dup@example.com", "password": PASSWORD, "full_name": "Dup"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    again = client.post("/api/v1/auth/register", json=body)
    assert again.status_code == 409 and error_code(again) == "duplicate_email"


def test_registration_cannot_choose_a_role(client):
    body = {"email": "evil@example.com", "password": PASSWORD, "full_name": "Evil", "role": "admin"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 422


def test_short_password_is_rejected(client):
    body = {"email": "a@example.com", "password": "short", "full_name": "A"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 422


def test_wrong_password_and_unknown_user_look_identical(client):
    client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": PASSWORD, "full_name": "A"})
    wrong = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "Wrong-Password-1"})
    unknown = client.post("/api/v1/auth/login", json={"email": "zz@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
