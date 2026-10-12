"""HTTP smoke test. Needs fastapi + httpx (see requirements.txt); skipped quietly if they are not installed."""
from tests import helpers

helpers.setup()


def test_api_routes_work_over_http():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("      (skipped: fastapi/httpx not installed)")
        return
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"] is True
        r = c.post("/chat", json={"message": "balance", "customer_id": "C001"}).json()
        assert r["status"] in ("ok", "completed") and r["tier"] == 0
        assert c.post("/chat", json={"message": "balance"}).status_code == 422          # customer_id is required
        assert c.post("/chat", json={"message": "x", "customer_id": "C001", "role": "admin"}).status_code == 422
        fr = c.post("/chat", json={"message": "I did not make this 48000 payment", "customer_id": "C002"}).json()
        gid = fr["approval"]["group_id"]
        assert any(p["group_id"] == gid for p in c.get("/approvals/pending", params={"customer_id": "C002"}).json())
        done = c.post(f"/approvals/{gid}", json={"approve": True, "customer_id": "C002"}).json()
        assert done["status"] == "completed"
        assert c.get("/accounts/A1002/balance").status_code == 200
        assert c.get("/accounts/NOPE/balance").status_code == 404
        assert c.get("/metrics").json()["requests"] >= 1
        assert c.post("/admin/llm", params={"enabled": "false"}).json()["llm_enabled"] is False
        c.post("/admin/llm", params={"enabled": "true"})
