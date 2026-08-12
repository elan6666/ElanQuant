import json
from pathlib import Path

from elanquant.api.app import canonical_hash, create_app
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
        research_catalog=tmp_path / "research-catalog.json",
    )


def sealed_catalog() -> dict[str, object]:
    support = {
        "validation_2025": (18_000, 60, "a" * 64),
        "test_viewed_2026": (10_500, 35, "b" * 64),
    }
    sources: dict[str, dict[str, object]] = {}
    experiments: list[dict[str, object]] = []
    for size, marker in (("small", "1"), ("base", "2")):
        evaluation_sha = marker * 64
        sources[size] = {
            "matrix_sha256": ("3" if size == "small" else "4") * 64,
            "evaluation_sha256": evaluation_sha,
            "upstream_commit": "5" * 40,
            "official_weights_receipt_sha256": "6" * 64,
            "training_data_sha256": "7" * 64,
            "admission_sha256": "8" * 64,
            "split_contract_sha256": "9" * 64,
            "evaluation_data_sha256": "a" * 64,
            "evaluation_config_sha256": "b" * 64,
            "inference_code_sha256": "c" * 64,
            "as_of_session": "2026-08-12",
            "support": {
                split: {
                    "eligible_rows": rows,
                    "evaluated_rows": rows,
                    "evaluated_cross_sections": sections,
                    "anchor_set_sha256": anchor,
                }
                for split, (rows, sections, anchor) in support.items()
            },
        }
        for identity, track in (
            ("zero-shot", "zero_shot"),
            ("official-ft", "official_style"),
            ("strict-pit", "strict_pit"),
        ):
            experiments.append(
                {
                    "id": f"{size}-{identity}",
                    "model_size": size,
                    "track": track,
                    "state": "passed",
                    "rank_ic": 0.01,
                    "pearson_ic": 0.02,
                    "top10_mean_return": 0.03,
                    "model_hash": "d" * 64,
                    "receipt": evaluation_sha,
                    "note": "sealed",
                    "evaluations": {
                        split: {
                            "rank_ic": 0.01,
                            "pearson_ic": 0.02,
                            "top10_mean_return": 0.03,
                            "rows": rows,
                            "cross_sections": sections,
                            "anchor_set_sha256": anchor,
                        }
                        for split, (rows, sections, anchor) in support.items()
                    },
                }
            )
    payload: dict[str, object] = {
        "schema_version": "elanquant_research_catalog_v1",
        "status": "PASS",
        "generated_at": "2026-08-13T00:00:00+00:00",
        "experiments": experiments,
        "sources": sources,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


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
    assert client.get("/api/v1/research/experiments").json()["experiments"] == []


def test_research_catalog_fails_closed_on_unsealed_payload(tmp_path: Path) -> None:
    active = settings(tmp_path)
    active.research_catalog.write_text('{"schema_version":"wrong"}', encoding="utf-8")
    response = TestClient(create_app(active)).get("/api/v1/research/experiments")
    assert response.status_code == 503


def test_research_catalog_accepts_only_canonical_six_cell_receipt(tmp_path: Path) -> None:
    active = settings(tmp_path)
    payload = sealed_catalog()
    active.research_catalog.write_text(json.dumps(payload), encoding="utf-8")
    client = TestClient(create_app(active))
    response = client.get("/api/v1/research/experiments")
    assert response.status_code == 200
    assert len(response.json()["experiments"]) == 6

    payload["experiments"][0]["track"] = "strict_pit"  # type: ignore[index]
    payload["receipt_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )
    active.research_catalog.write_text(json.dumps(payload), encoding="utf-8")
    assert client.get("/api/v1/research/experiments").status_code == 503


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
    assert system["primary_model"] == "small-strict-pit"

    run = client.get("/api/v1/runs/latest").json()
    assert run["status"] == "success"
    assert len(run["experiment_matrix"]) == 3
    assert run["scoreable"] is False
    assert run["provenance"]["data_hash"]
    assert run["paper_publication"]["state"] == "FROZEN"
    run_detail = client.get(f"/api/v1/runs/{run['id']}").json()["run"]
    assert "artifact_path" not in run_detail

    listed_runs = client.get("/api/v1/runs").json()["runs"]
    assert listed_runs[0]["id"] == run["id"]
    assert client.get(f"/api/v1/runs/{run['id']}/diff").json()["comparable"] is False
    health = client.get(f"/api/v1/runs/{run['id']}/data-health").json()
    assert health["summary"]["eligible_symbols"] == 5

    scores = client.get(f"/api/v1/runs/{run['id']}/scores").json()["scores"]
    assert len(scores) == 5
    assert scores[0]["rank"] == 1
    assert scores[0]["eligible"] is False
    assert len(scores[0]["model_scores"]) == 3
    assert scores[0]["model_spread"] == (
        max(scores[0]["model_scores"].values()) - min(scores[0]["model_scores"].values())
    )

    account = client.get("/api/v1/paper/account").json()
    assert account["initial_cash"] == 100_000
    assert account["equity"] == 100_000
    orders = client.get("/api/v1/paper/orders").json()["orders"]
    assert len(orders) == 3
    assert {order["run_id"] for order in orders} == {run["id"]}
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
    assert next_account["market_value"] == sum(
        position["market_value"] for position in next_account["positions"]
    )
    assert next_account["equity"] == next_account["cash"] + next_account["market_value"]
    next_run = client.get("/api/v1/runs/latest").json()
    diff = client.get(f"/api/v1/runs/{next_run['id']}/diff").json()
    assert diff["comparable"] is False
    assert diff["reason"] == "STRICT_RANK_COVERAGE_INCOMPLETE"
    assert diff["against_run_id"] == run["id"]
    summary = client.get("/api/v1/paper/summary").json()
    assert summary["sample_sessions"] == 2
    assert summary["evidence_state"] == "available"
