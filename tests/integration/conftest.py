import httpx
import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.main import app

ADMIN_KEY = "test-admin-key"

# One fresh Postgres container for the whole test run
@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("pgvector/pgvector:pg17", driver=None) as pg:
        yield pg.get_connection_url()

# One fresh Redis container for the whole test run
@pytest.fixture(scope="session")
def redis_url():
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}"

# Start the app against the test database and give each test an HTTP client

@pytest.fixture
async def client(postgres_url, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    monkeypatch.setenv("REDIS_URL", redis_url)  
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("CONFIG_PATH", "tests/integration/models.test.yaml")

    async with app.router.lifespan_context(app):
        # Empty tables so every test starts clean
        await app.state.db.execute("TRUNCATE usage_logs, api_keys RESTART IDENTITY")
        await app.state.redis.flushdb() # no leftover rate-limit buckets
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {ADMIN_KEY}"}



# A real gateway key created through the admin endpoint
@pytest.fixture
async def api_key(client, admin_headers):
    res = await client.post("/admin/keys", json={"name": "test"}, headers=admin_headers)
    assert res.status_code == 201
    return res.json()