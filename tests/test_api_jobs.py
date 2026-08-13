import json
import sqlite3
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
    raw_identities: dict[str, dict[str, str]] = {}
    normalized_protocol = {
        "evaluation_mode": "FORMAL",
        "evaluation_batch_size": 50,
        "online_batch_size": 50,
    }
    protocol_sha = canonical_hash(normalized_protocol)
    for size, marker in (("small", "1"), ("base", "2")):
        evaluation_sha = marker * 64
        raw_identities[size] = {
            "evaluation_config_sha256": ("b" if size == "small" else "e") * 64,
            "inference_code_sha256": ("c" if size == "small" else "f") * 64,
        }
        sources[size] = {
            "matrix_sha256": ("3" if size == "small" else "4") * 64,
            "evaluation_sha256": evaluation_sha,
            "upstream_commit": "5" * 40,
            "official_weights_receipt_sha256": "6" * 64,
            "training_data_sha256": "7" * 64,
            "admission_sha256": "8" * 64,
            "split_contract_sha256": "9" * 64,
            "evaluation_data_sha256": "a" * 64,
            **raw_identities[size],
            "evaluation_protocol_sha256": protocol_sha,
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
    compatibility: dict[str, object] = {
        "schema_version": "elanquant_evaluation_compatibility_v1",
        "status": "PASS",
        "decision": "SEMANTICALLY_COMPARABLE",
        "normalized_protocol": normalized_protocol,
        "protocol_sha256": protocol_sha,
        "source_identities": raw_identities,
        "source_revisions": {
            "small": "ec5ccffd1353da792d0dd5274b7a279918a0f1e2",
            "base": "266bab286a03c07a8b186a443c64144bfa35c487",
        },
        "source_path": "scripts/server/evaluate_and_infer.py",
        "source_diff_sha256": "7fff6d49340c5ac08b006cd72f858ba314535a7176da07d97704344648861308",
        "allowed_differences": [
            "MODEL_SIZE_PARAMETERIZATION",
            "MODEL_CELL_ID_PREFIX",
            "BATCH_CONFIG_KEY_RENAMED",
            "ONLINE_BATCH_SIZE_EXPLICIT_50",
            "PRIMARY_STRICT_MODEL_ID_AND_LABEL",
        ],
        "evaluation_receipts": {
            "small": sources["small"]["evaluation_sha256"],
            "base": sources["base"]["evaluation_sha256"],
        },
    }
    compatibility["receipt_hash"] = canonical_hash(compatibility)
    for source in sources.values():
        source["compatibility_receipt_sha256"] = compatibility["receipt_hash"]
    payload: dict[str, object] = {
        "schema_version": "elanquant_research_catalog_v1",
        "status": "PASS",
        "generated_at": "2026-08-13T00:00:00+00:00",
        "experiments": experiments,
        "sources": sources,
        "compatibility": compatibility,
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


def test_research_catalog_rejects_compatibility_tampering(tmp_path: Path) -> None:
    active = settings(tmp_path)
    client = TestClient(create_app(active))
    for field, value in (
        ("source_diff_sha256", "0" * 64),
        ("allowed_differences", ["UNREVIEWED_DIFFERENCE"]),
    ):
        payload = sealed_catalog()
        compatibility = payload["compatibility"]
        assert isinstance(compatibility, dict)
        compatibility[field] = value
        compatibility["receipt_hash"] = canonical_hash(
            {key: item for key, item in compatibility.items() if key != "receipt_hash"}
        )
        sources = payload["sources"]
        assert isinstance(sources, dict)
        for source in sources.values():
            assert isinstance(source, dict)
            source["compatibility_receipt_sha256"] = compatibility["receipt_hash"]
        payload["receipt_hash"] = canonical_hash(
            {key: item for key, item in payload.items() if key != "receipt_hash"}
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

    with sqlite3.connect(active.database_path) as connection:
        connection.execute(
            "DELETE FROM run_model_evaluations WHERE run_id = ?", (next_run["id"],)
        )
        connection.execute(
            """
            UPDATE inference_runs
            SET evaluation_receipt_sha256 = NULL, protocol = 'STRICT_PIT_SMALL'
            WHERE id = ?
            """,
            (next_run["id"],),
        )
    legacy_payload = client.get("/api/v1/runs/latest").json()
    assert legacy_payload["viewed_test"] is False
    assert {cell["state"] for cell in legacy_payload["experiment_matrix"]} == {"blocked"}
    assert all(cell["rank_ic"] is None for cell in legacy_payload["experiment_matrix"])
    assert all(cell["evaluations"] == {} for cell in legacy_payload["experiment_matrix"])
    assert any("双分区正式评估回执" in warning for warning in legacy_payload["warnings"])
