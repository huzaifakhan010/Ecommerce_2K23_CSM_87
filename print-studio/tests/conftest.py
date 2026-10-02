import os

# Must be set before the app modules are imported. These are test-only values, not secrets.
os.environ.setdefault("JWT_SECRET", "test-only-secret-not-for-production-0123456789")
os.environ.setdefault("BCRYPT_ROUNDS", "4")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base, create_sqlite_memory_engine, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "Correct-Horse-9"


@pytest.fixture()
def engine():
    """In-memory SQLite by default. Set TEST_DATABASE_URL to run the same suite on PostgreSQL
    (use a dedicated, empty database: its tables are dropped before and after every test)."""
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        yield engine
        Base.metadata.drop_all(engine)
    else:
        engine = create_sqlite_memory_engine()
        Base.metadata.create_all(engine)
        yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture()
def client(session_factory):
    def _override():
        with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = _override
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def _login_as(client, session_factory, email, role):
    with session_factory() as session:
        session.add(User(email=email, password_hash=hash_password(PASSWORD), full_name=role.title(), role=role))
        session.commit()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client, session_factory):
    return _login_as(client, session_factory, "admin@example.com", "admin")


@pytest.fixture()
def customer_headers(client, session_factory):
    return _login_as(client, session_factory, "customer@example.com", "customer")
