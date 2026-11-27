async def test_new_key_gets_default_limit(client, admin_headers):
    res = await client.post("/admin/keys", json={"name": "a"}, headers=admin_headers)
    assert res.status_code == 201
    assert res.json()["rpm_limit"] == 60


async def test_new_key_with_custom_limit(client, admin_headers):
    res = await client.post("/admin/keys", json={"name": "a", "rpm_limit": 5}, headers=admin_headers)
    assert res.json()["rpm_limit"] == 5

async def test_limit_must_be_positive(client, admin_headers):
    res = await client.post("/admin/keys", json={"name": "a", "rpm_limit": 0}, headers=admin_headers)
    assert res.status_code == 422


async def test_update_limit(client, api_key, admin_headers):
    res = await client.patch(f"/admin/keys/{api_key['id']}", json={"rpm_limit": 10}, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["rpm_limit"] == 10

    [key] = (await client.get("/admin/keys", headers=admin_headers)).json()
    assert key["rpm_limit"] == 10

async def test_update_unknown_key_returns_404(client, admin_headers):
    res = await client.patch("/admin/keys/999", json={"rpm_limit": 10}, headers=admin_headers)
    assert res.status_code == 404