from pathlib import Path

from elanquant.api.app import create_app
from elanquant.orchestration.worker import Worker
from elanquant.settings import Settings
from fastapi.testclient import TestClient


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "elanquant.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "missing-dist",
        initial_cash=100_000,
        top_k=3,
    )


def test_submit_is_202_and_duplicate_clicks_coalesce(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))
    assert client.post("/api/v1/jobs/update-infer").status_code == 422
    first = client.post("/api/v1/jobs/update-infer", json={"target_session": "2026-08-12"})
    second = client.post("/api/v1/jobs/update-infer", json={"target_session": "2026-08-12"})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["job"]["id"] == second.json()["job"]["id"]
    assert first.headers["location"].endswith(first.json()["job"]["id"])
    assert first.headers["content-security-policy"].startswith("default-src 'self'")


def test_mutating_request_rejects_foreign_browser_origin(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))
    response = client.post(
        "/api/v1/jobs/update-infer",
        json={"target_session": "2026-08-12"},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code == 400


def test_job_list_detail_and_retry_contract(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    client = TestClient(app)
    submitted = client.post(
        "/api/v1/jobs/update-infer", json={"target_session": "2026-08-12"}
    ).json()["job"]
    assert client.get(f"/api/v1/jobs/{submitted['id']}").status_code == 200
    listed = client.get("/api/v1/jobs").json()["jobs"]
    assert len(listed) == 1
    assert listed[0]["events"][0]["id"] == "1"
    assert client.post(f"/api/v1/jobs/{submitted['id']}/retry").status_code == 409

    app.state.jobs.fail(submitted["id"], "TEST_FAILURE", "intentional")
    retried = client.post(f"/api/v1/jobs/{submitted['id']}/retry")
    assert retried.status_code == 202
    assert retried.json()["parent_job_id"] == submitted["id"]
    assert retried.json()["attempt"] == 2


def test_status_has_no_broker_or_scheduler(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    assert response.json()["broker_connected"] is False
    assert response.json()["automatic_schedule"] is False


def test_completed_run_matches_dashboard_contract(tmp_path: Path) -> None:
    active = settings(tmp_path)
    app = create_app(active)
    client = TestClient(app)
    submitted = client.post("/api/v1/jobs/update-infer", json={"target_session": "2026-08-12"})
    assert submitted.status_code == 202
    assert Worker(active).run_once() is True

    system = client.get("/api/v1/system/status").json()
    assert system["service_state"] == "ready"
    assert system["inference_as_of"] == "2026-08-12"

    run = client.get("/api/v1/runs/latest").json()
    assert run["status"] == "success"
    assert len(run["experiment_matrix"]) == 3
    assert run["scoreable"] is False
    assert run["provenance"]["data_hash"]

    scores = client.get(f"/api/v1/runs/{run['id']}/scores").json()["scores"]
    assert len(scores) == 5
    assert scores[0]["rank"] == 1
    assert scores[0]["eligible"] is False
    assert len(scores[0]["model_scores"]) == 3

    account = client.get("/api/v1/paper/account").json()
    assert account["initial_cash"] == 100_000
    assert account["equity"] == 100_000
    assert len(client.get("/api/v1/paper/orders").json()["orders"]) == 3
    assert len(client.get("/api/v1/paper/nav").json()["nav"]) == 1

    next_job = client.post(
        "/api/v1/jobs/update-infer", json={"target_session": "2026-08-13"}
    )
    assert next_job.status_code == 202
    assert Worker(active).run_once() is True
    next_account = client.get("/api/v1/paper/account").json()
    assert next_account["positions"]
    assert all(position["last_price"] is not None for position in next_account["positions"])
    assert all(position["market_value"] is not None for position in next_account["positions"])
    assert all(position["unrealized_pnl"] is not None for position in next_account["positions"])
