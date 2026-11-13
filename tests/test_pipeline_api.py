"""Tests d'intégration : pipeline ETL complet -> entraînement -> API (base SQLite + mongomock)."""
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from src.collect import ecb, stooq
from src.db.postgres import fetch_df
from src.etl import pipeline
from tests.conftest import make_creditcard, make_fx, make_prices

HEADERS = {"X-API-Key": "test-key"}
ARTICLES = [{
    "source": "ECB", "title": "Monetary policy decision", "link": "https://example.org/a.html",
    "published_at": datetime(2026, 11, 1, tzinfo=UTC), "summary": None,
    "body": "texte", "ingested_at": datetime.now(UTC),
}]


@pytest.fixture(scope="module")
def loaded(tmp_dir):
    mp = pytest.MonkeyPatch()
    mp.setattr(stooq, "fetch_prices", lambda t: make_prices(400, seed=hash(t) % 100))
    mp.setattr(ecb, "fetch_fx", lambda: make_fx())
    csv = tmp_dir / "creditcard.csv"
    make_creditcard().to_csv(csv, index=False)

    run_id = "run-1"
    pipeline.run(["init"], run_id)
    pipeline.run_step(run_id, "prices", pipeline.step_prices, ["aapl.us", "^spx"], date(2026, 11, 12))
    pipeline.run(["fx"], run_id)
    pipeline.run_step(run_id, "transactions", pipeline.step_transactions, csv)
    pipeline.run_step(run_id, "news", pipeline.step_news, ARTICLES)
    pipeline.run(["risk"], run_id)

    from src.ml.fraud_train import train
    metrics = train(fetch_df("SELECT * FROM fact_transaction ORDER BY transaction_id"))
    yield {"csv": csv, "metrics": metrics}
    mp.undo()


def test_tables_loaded(loaded):
    counts = {t: int(fetch_df(f"SELECT COUNT(*) AS n FROM {t}")["n"][0]) for t in
              ["dim_asset", "fact_price", "fact_fx_rate", "fact_transaction", "risk_metrics"]}
    assert counts == {"dim_asset": 2, "fact_price": 800, "fact_fx_rate": 60,
                      "fact_transaction": 6000, "risk_metrics": 798}


def test_pipeline_is_idempotent(loaded):
    pipeline.run_step("run-2", "prices", pipeline.step_prices, ["aapl.us"], date(2026, 11, 12))
    pipeline.run_step("run-2", "transactions", pipeline.step_transactions, loaded["csv"])
    assert int(fetch_df("SELECT COUNT(*) AS n FROM fact_price")["n"][0]) == 800
    assert int(fetch_df("SELECT COUNT(*) AS n FROM fact_transaction")["n"][0]) == 6000


def test_run_log_and_quality_written(loaded):
    log = fetch_df("SELECT step, status FROM etl_run_log WHERE run_id = 'run-1'")
    assert set(log["step"]) == {"init", "prices", "fx", "transactions", "news", "risk"}
    assert (log["status"] == "success").all()
    q = fetch_df("SELECT COUNT(*) AS n FROM data_quality_check WHERE run_id = 'run-1'")
    assert int(q["n"][0]) > 10


def test_blocking_quality_check_stops_pipeline(loaded, monkeypatch):
    monkeypatch.setattr(stooq, "fetch_prices", lambda t: make_prices(5))
    with pytest.raises(pipeline.DataQualityError):
        pipeline.run_step("run-bad", "prices", pipeline.step_prices, ["bad.us"], date(2026, 11, 12))
    log = fetch_df("SELECT status FROM etl_run_log WHERE run_id = 'run-bad'")
    assert list(log["status"]) == ["failed"]


def test_fraud_model_metrics(loaded):
    m = loaded["metrics"]
    assert m["selected_model"] in m["comparison"]
    assert m["test"]["roc_auc"] > 0.9
    assert 0 < m["threshold"] < 1


@pytest.fixture(scope="module")
def client(loaded):
    from src.api.main import app, load_model
    load_model.cache_clear()
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["model_loaded"] is True


def test_api_requires_key(client):
    assert client.get("/v1/assets").status_code == 401
    assert client.get("/v1/assets", headers={"X-API-Key": "faux"}).status_code == 401


def test_score_fraud(client):
    legit = {"time_offset_s": 1000, "amount": 50.0, "v": [0.0] * 28}
    fraud = {"time_offset_s": 1000, "amount": 50.0, "v": [3.0] * 4 + [0.0] * 24}
    r1 = client.post("/v1/fraud/score", json=legit, headers=HEADERS).json()
    r2 = client.post("/v1/fraud/score", json=fraud, headers=HEADERS).json()
    assert r1["fraud_probability"] < r2["fraud_probability"]
    assert r2["is_fraud"] is True


def test_score_validation_error(client):
    r = client.post("/v1/fraud/score", json={"time_offset_s": 1, "amount": -5, "v": [0] * 3},
                    headers=HEADERS)
    assert r.status_code == 422


def test_risk_endpoints(client):
    r = client.get("/v1/risk/AAPL.US?days=10", headers=HEADERS)
    assert r.status_code == 200 and len(r.json()) == 10
    assert client.get("/v1/risk/inconnu.us", headers=HEADERS).status_code == 404
    assert client.get("/v1/risk/alerts/latest", headers=HEADERS).status_code == 200
    assert len(client.get("/v1/assets", headers=HEADERS).json()) == 2


def test_news_and_metrics(client):
    news = client.get("/v1/news", headers=HEADERS).json()
    assert news[0]["title"] == "Monetary policy decision" and "body" not in news[0]
    assert "http_requests_total" in client.get("/metrics").text
