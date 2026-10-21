import json
import os
import tempfile

import pytest

from app.seed import seed_database
from app.server import create_app


@pytest.fixture(scope="module")
def client():
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    seed_database(path, n_members=80, days=40, seed=3)
    return create_app(path).test_client()


def get(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.data[:300])
    return r.get_json()


def test_overview(client):
    d = get(client, "/api/overview")
    assert {"inside_now", "visits_today", "today_hourly", "avg_stay_min"} <= d.keys()
    assert len(d["today_hourly"]) == 24


def test_gate_entry_then_exit(client):
    mid = get(client, "/api/members?limit=1")[0]["member_id"]
    first = client.post("/api/gate/scan", json={"member_id": mid}).get_json()
    second = client.post("/api/gate/scan", json={"member_id": mid}).get_json()
    assert {first["action"], second["action"]} == {"entry", "exit"}
    assert client.post("/api/gate/scan", json={"member_id": "NOPE"}).status_code == 404
    assert len(get(client, "/api/gate/live")["recent"]) > 0
    assert client.post("/api/gate/simulate", json={"n": 5}).get_json()["events"]


def test_member_profile_and_books(client):
    mid = get(client, "/api/members?limit=5")[2]["member_id"]
    p = get(client, f"/api/members/{mid}")
    assert {"member", "stats", "visits", "loans", "taste"} <= p.keys()
    books = get(client, "/api/books?genre=Fantasy")
    assert books and all(b["genre"] == "Fantasy" for b in books)
    assert get(client, "/api/books/1")["similar"]


def test_loan_cycle(client):
    mid = get(client, "/api/members?limit=1")[0]["member_id"]
    book = next(b for b in get(client, "/api/books") if b["available"] > 0)
    r = client.post("/api/loans", json={"member_id": mid, "book_id": book["book_id"]})
    assert r.status_code == 201
    lid = r.get_json()["loan_id"]
    assert client.post(f"/api/loans/{lid}/return").status_code == 200
    assert client.post(f"/api/loans/{lid}/return").status_code == 404


@pytest.mark.parametrize("method", ["hybrid", "content", "user_cf", "item_cf", "svd", "popular"])
def test_recommend(client, method):
    mid = get(client, "/api/members?limit=10")[5]["member_id"]
    d = get(client, f"/api/recommend/{mid}?method={method}&k=5")
    assert len(d["items"]) == 5
    assert all(i["reasons"] and 0 <= i["score"] <= 1 for i in d["items"])


def test_recommend_evaluate_graph_ethics(client):
    ev = get(client, "/api/recommend/evaluate")
    assert set(ev["methods"]) == {"hybrid", "content", "user_cf", "item_cf", "svd", "popular"}
    g = get(client, "/api/graph/books?min_weight=1")
    assert g["nodes"] and g["links"]
    assert "MERGE" in client.get("/api/graph/cypher").get_data(as_text=True)
    e = get(client, "/api/ethics/report")
    assert {"anonymised_sample", "k_anonymity", "consent", "fairness", "transparency"} <= e.keys()
    json.dumps(e, allow_nan=False)
