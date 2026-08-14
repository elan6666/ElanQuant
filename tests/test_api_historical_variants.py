from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import elanquant.api.app as api
from elanquant.settings import Settings

SPLITS = {
    "validation_2025": (
        "official-demo-method-extended-pit-v1",
        "official-demo-top3-drop1-hold5-validation-2025-v2",
        "POST_HOC_HISTORICAL_SENSITIVITY",
    ),
    "test_viewed_2026": (
        "official-demo-method-corrected-opened-2026-v1",
        "official-demo-top3-drop1-hold5-corrected-opened-2026-v2",
        "POST_HOC_OPENED_STRATEGY_DIAGNOSTIC",
    ),
}


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "elanquant.sqlite3",
        artifact_root=tmp_path / "artifacts",
        frontend_dist=tmp_path / "missing-dist",
        historical_backtest_catalog=tmp_path / "releases" / "catalog-v5.json",
    )


def write_series(path: Path, year: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datetime",
                "signal",
                "additive_strategy_with_cost",
                "additive_benchmark",
                "additive_excess_with_cost",
                "compounded_strategy_nav",
                "compounded_benchmark_nav",
            ],
        )
        writer.writeheader()
        for signal in ("last", "max", "mean", "min"):
            writer.writerow(
                {
                    "datetime": f"{year}-01-05",
                    "signal": signal,
                    "additive_strategy_with_cost": "0.01",
                    "additive_benchmark": "0.005",
                    "additive_excess_with_cost": "0.005",
                    "compounded_strategy_nav": "1.01",
                    "compounded_benchmark_nav": "1.005",
                }
            )


def write_holdings(path: Path, year: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "session",
                "signal",
                "instrument",
                "is_empty",
                "amount",
                "weight",
                "value",
            ],
        )
        writer.writeheader()
        for signal in ("last", "max", "mean", "min"):
            writer.writerow(
                {
                    "session": f"{year}-01-05",
                    "signal": signal,
                    "instrument": "600000.SH",
                    "is_empty": "False",
                    "amount": "100",
                    "weight": "0.5",
                    "value": "1000",
                }
            )


def metric() -> dict[str, float]:
    return {
        "total_return_with_cost": 0.01,
        "benchmark_return": 0.005,
        "excess_return_without_cost": 0.006,
        "excess_return_with_cost": 0.005,
        "annualized_return_with_cost": 0.02,
        "annualized_excess_return_with_cost": 0.01,
        "information_ratio_with_cost": 0.2,
        "max_drawdown_with_cost": -0.01,
        "total_cost": 0.001,
        "turnover_mean": 0.1,
    }


def publish_four(tmp_path: Path) -> tuple[Settings, list[dict[str, object]]]:
    active = settings(tmp_path)
    entries: list[dict[str, object]] = []
    for split, (top50_id, top3_id, top3_role) in SPLITS.items():
        for topk, identifier in ((50, top50_id), (3, top3_id)):
            top50 = topk == 50
            output = tmp_path / "runs" / identifier
            series = output / "daily-series.csv"
            write_series(series, 2025 if split == "validation_2025" else 2026)
            metrics = {signal: metric() for signal in ("mean", "last", "max", "min")}
            receipt: dict[str, object] = {
                "id": identifier,
                "model_cell_id": "small-official-ft",
                "generated_at": "2026-08-13T00:00:00+00:00",
                "evaluation_split": split,
                "result_role": (
                    "TRAINING_VALIDATION_CHECKPOINT_SELECTION"
                    if top50 and split == "validation_2025"
                    else "CORRECTED_OPENED_OOS_DIAGNOSTIC"
                    if top50
                    else top3_role
                ),
                "selection_eligible": top50 and split == "validation_2025",
                "used_for_selection": top50 and split == "validation_2025",
                "test_data_access": (
                    "NOT_APPLICABLE" if split == "validation_2025" else "VIEWED"
                ),
                "primary_signal": "mean",
                "backtest_code_sha256": "3" * 64,
                "strategy": {
                    "topk": topk,
                    "n_drop": 5 if top50 else 1,
                    "hold_thresh": 5,
                },
                "execution": {"benchmark": "SH000300"},
                "support": {"sessions": 1, "signal_rows": 300},
                "metrics": metrics,
                "qlib": {"version": "0.9.7"},
                "observability": (
                    {"turnover_exposed": True, "position_count_exposed": True}
                    if not top50
                    else None
                ),
                "deviations": ["test fixture"],
                "artifacts": {
                    "daily_series": {
                        "path": series.relative_to(tmp_path).as_posix(),
                        "sha256": api.sha256_file(series),
                    }
                },
            }
            if top50:
                receipt.update(
                    {
                        "track_kind": "OFFICIAL_DEMO_METHOD_EXTENDED_PIT",
                        "signal_receipt_sha256": "1" * 64,
                        "provider_receipt_sha256": "2" * 64,
                        "curve_semantics": {
                            "official": "additive",
                            "derived": "compounded",
                        },
                    }
                )
            else:
                receipt["source_backtest_id"] = top50_id
                receipt["source_signal_receipt_sha256"] = "1" * 64
                receipt["source_provider_receipt_sha256"] = "2" * 64
            receipt_path = output / "backtest-receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            holdings_path = output / "daily-holdings.csv"
            write_holdings(holdings_path, 2025 if split == "validation_2025" else 2026)
            receipt_relative = receipt_path.relative_to(tmp_path).as_posix()
            receipt_sha256 = api.sha256_file(receipt_path)
            holdings_receipt: dict[str, object] = {
                "schema_version": "elanquant_historical_holdings_receipt_v1",
                "status": "PASS",
                "id": f"{identifier}-holdings-v1",
                "backtest_id": identifier,
                "generated_at": "2026-08-13T00:00:00+00:00",
                "evaluation_split": split,
                "strategy_variant_id": "official_top50" if top50 else "historical_top3",
                "execution_domain": "HISTORICAL_QLIB_SIMULATION",
                "online_paper_equivalent": False,
                "promotion_eligible": False,
                "backtest_receipt_path": receipt_relative,
                "backtest_receipt_sha256": receipt_sha256,
                "generator_code_sha256": "4" * 64,
                "source_signal_receipt_sha256": "1" * 64,
                "source_provider_receipt_sha256": "2" * 64,
                "metrics_comparison": {
                    "status": "PASS",
                    "absolute_tolerance": 1e-12,
                    "compared_values": 40,
                    "maximum_absolute_difference": 0.0,
                },
                "artifact": {
                    "path": holdings_path.relative_to(tmp_path).as_posix(),
                    "sha256": api.sha256_file(holdings_path),
                    "bytes": holdings_path.stat().st_size,
                    "schema_version": "elanquant_historical_daily_holdings_v1",
                    "columns": [
                        "session",
                        "signal",
                        "instrument",
                        "is_empty",
                        "amount",
                        "weight",
                        "value",
                    ],
                    "rows": 4,
                    "sessions": 1,
                    "session_signal_pairs": 4,
                    "empty_session_signal_pairs": 0,
                },
            }
            holdings_receipt["receipt_hash"] = api.canonical_hash(holdings_receipt)
            holdings_receipt_path = output / "holdings-receipt.json"
            holdings_receipt_path.write_text(json.dumps(holdings_receipt), encoding="utf-8")
            entries.append(
                {
                    "id": identifier,
                    "state": "passed",
                    "model_cell_id": "small-official-ft",
                    "receipt_path": receipt_relative,
                    "receipt_sha256": receipt_sha256,
                    "summary": metrics["mean"],
                    "strategy_variant_id": "official_top50" if top50 else "historical_top3",
                    "strategy_role": (
                        "OFFICIAL_METHOD_BASELINE"
                        if top50
                        else "PORTFOLIO_SENSITIVITY_VARIANT"
                    ),
                    "comparison_group_id": "top50-vs-top3-v1",
                    "evaluation_split": split,
                    "execution_domain": "HISTORICAL_QLIB_SIMULATION",
                    "online_paper_equivalent": False,
                    "promotion_eligible": False,
                    "source_backtest_id": None if top50 else top50_id,
                    "holdings": {
                        "receipt_path": holdings_receipt_path.relative_to(tmp_path).as_posix(),
                        "receipt_sha256": api.sha256_file(holdings_receipt_path),
                    },
                }
            )
    active.historical_backtest_catalog.parent.mkdir(parents=True)
    active.historical_backtest_catalog.write_text(
        json.dumps(
            {
                "schema_version": "elanquant_historical_backtest_catalog_v3",
                "status": "PASS",
                "generated_at": "2026-08-13T00:00:01+00:00",
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return active, entries


def replace_entries(active: Settings, entries: list[dict[str, object]]) -> None:
    catalog = json.loads(active.historical_backtest_catalog.read_text(encoding="utf-8"))
    catalog["entries"] = entries
    active.historical_backtest_catalog.write_text(json.dumps(catalog), encoding="utf-8")


def install_contract_stubs(
    monkeypatch: pytest.MonkeyPatch, expected_entries: int = 4
) -> None:
    def validate_catalog(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict) or len(payload.get("entries", [])) != expected_entries:
            raise RuntimeError("catalog is not exact")
        return payload

    monkeypatch.setattr(api, "validate_historical_catalog", validate_catalog)
    monkeypatch.setattr(
        api,
        "validate_any_backtest_receipt",
        lambda payload: payload if isinstance(payload, dict) else {},
    )


def test_exact_four_variant_catalog_is_get_only_and_does_not_mutate_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active, entries = publish_four(tmp_path)
    install_contract_stubs(monkeypatch)
    client = TestClient(api.create_app(active))
    before = active.database_path.read_bytes()

    response = client.get("/api/v1/research/backtests")
    assert response.status_code == 200
    payload = response.json()["backtests"]
    assert len(payload) == 4
    assert {(item["evaluation_split"], item["strategy_variant_id"]) for item in payload} == {
        ("validation_2025", "official_top50"),
        ("validation_2025", "historical_top3"),
        ("test_viewed_2026", "official_top50"),
        ("test_viewed_2026", "historical_top3"),
    }
    assert {item["comparison_group_id"] for item in payload} == {"top50-vs-top3-v1"}
    assert all(item["execution_domain"] == "HISTORICAL_QLIB_SIMULATION" for item in payload)
    assert all(item["online_paper_equivalent"] is False for item in payload)
    assert all(item["promotion_eligible"] is False for item in payload)
    top3 = [item for item in payload if item["strategy_variant_id"] == "historical_top3"]
    assert all(
        item["observability"]
        == {"turnover_exposed": True, "position_count_exposed": True}
        for item in top3
    )
    assert {item["result_role"] for item in top3} == {
        "POST_HOC_HISTORICAL_SENSITIVITY",
        "POST_HOC_OPENED_STRATEGY_DIAGNOSTIC",
    }
    for entry in entries:
        identifier = str(entry["id"])
        assert client.get(f"/api/v1/research/backtests/{identifier}").status_code == 200
        assert (
            client.get(f"/api/v1/research/backtests/{identifier}/series?signal=mean").status_code
            == 200
        )
        holdings = client.get(f"/api/v1/research/backtests/{identifier}/holdings")
        assert holdings.status_code == 200
        pointer = entry["holdings"]
        assert isinstance(pointer, dict)
        assert holdings.json() == {
            "backtest_id": identifier,
            "available": True,
            "sessions": [
                "2025-01-05"
                if entry["evaluation_split"] == "validation_2025"
                else "2026-01-05"
            ],
            "default_session": (
                "2025-01-05"
                if entry["evaluation_split"] == "validation_2025"
                else "2026-01-05"
            ),
            "selected_session": (
                "2025-01-05"
                if entry["evaluation_split"] == "validation_2025"
                else "2026-01-05"
            ),
            "signal": "mean",
            "empty": False,
            "source": {
                "artifact_sha256": holdings.json()["source"]["artifact_sha256"],
                "receipt_sha256": pointer["receipt_sha256"],
                "backtest_receipt_sha256": entry["receipt_sha256"],
            },
            "holdings": [
                {
                    "instrument": "600000.SH",
                    "amount": 100.0,
                    "weight": 0.5,
                    "value": 1000.0,
                }
            ],
        }
    assert client.post("/api/v1/research/backtests").status_code == 405
    assert active.database_path.read_bytes() == before


def test_variant_catalog_fails_closed_on_missing_entry_or_receipt_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active, entries = publish_four(tmp_path)
    install_contract_stubs(monkeypatch)
    entries.pop()
    replace_entries(active, entries)
    client = TestClient(api.create_app(active))
    assert client.get("/api/v1/research/backtests").status_code == 503

    active, entries = publish_four(tmp_path / "tamper")
    install_contract_stubs(monkeypatch)
    receipt = tmp_path / "tamper" / str(entries[0]["receipt_path"])
    receipt.write_text("tampered", encoding="utf-8")
    client = TestClient(api.create_app(active))
    assert client.get("/api/v1/research/backtests").status_code == 503


def test_variant_public_identity_disagreement_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active, entries = publish_four(tmp_path)
    install_contract_stubs(monkeypatch)
    entries[0]["online_paper_equivalent"] = True
    replace_entries(active, entries)
    response = TestClient(api.create_app(active)).get("/api/v1/research/backtests")
    assert response.status_code == 503

    active, entries = publish_four(tmp_path / "source")
    install_contract_stubs(monkeypatch)
    top3 = next(entry for entry in entries if entry["strategy_variant_id"] == "historical_top3")
    top3["source_backtest_id"] = None
    replace_entries(active, entries)
    response = TestClient(api.create_app(active)).get("/api/v1/research/backtests")
    assert response.status_code == 503


def test_settings_default_to_immutable_v6_catalog() -> None:
    active = Settings(
        database_path=Path("db.sqlite3"),
        artifact_root=Path("artifacts"),
        frontend_dist=Path("dist"),
    )
    assert active.historical_backtest_catalog.name == "historical-backtest-catalog-v6.json"


def test_holdings_missing_sidecar_is_local_404_and_does_not_poison_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active, entries = publish_four(tmp_path)
    install_contract_stubs(monkeypatch)
    unavailable = entries[0]
    unavailable.pop("holdings")
    replace_entries(active, entries)
    client = TestClient(api.create_app(active))

    assert client.get("/api/v1/research/backtests").status_code == 200
    assert client.get(f"/api/v1/research/backtests/{unavailable['id']}").status_code == 200
    response = client.get(f"/api/v1/research/backtests/{unavailable['id']}/holdings")
    assert response.status_code == 404
    assert response.json()["detail"] == "Historical holdings are unavailable for this backtest"
    assert client.get(f"/api/v1/research/backtests/{entries[1]['id']}/holdings").status_code == 200


def test_holdings_session_and_tamper_gates_are_fail_closed_and_get_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active, entries = publish_four(tmp_path)
    install_contract_stubs(monkeypatch)
    client = TestClient(api.create_app(active))
    identifier = str(entries[0]["id"])
    before = active.database_path.read_bytes()

    assert (
        client.get(f"/api/v1/research/backtests/{identifier}/holdings?session=2024-01-01")
        .status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/research/backtests/{identifier}/holdings?session=invalid")
        .status_code
        == 422
    )
    assert client.post(f"/api/v1/research/backtests/{identifier}/holdings").status_code == 405
    pointer = entries[0]["holdings"]
    assert isinstance(pointer, dict)
    sidecar_path = tmp_path / str(pointer["receipt_path"])
    sidecar_path.write_text("tampered", encoding="utf-8")
    assert client.get(f"/api/v1/research/backtests/{identifier}/holdings").status_code == 503
    assert client.get("/api/v1/research/backtests").status_code == 200
    assert active.database_path.read_bytes() == before


def test_holdings_empty_session_and_artifact_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active, entries = publish_four(tmp_path)
    install_contract_stubs(monkeypatch)
    entry = entries[0]
    pointer = entry["holdings"]
    assert isinstance(pointer, dict)
    sidecar_path = tmp_path / str(pointer["receipt_path"])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    artifact_path = tmp_path / sidecar["artifact"]["path"]
    with artifact_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(api.HOLDINGS_COLUMNS))
        writer.writeheader()
        for signal in ("last", "max", "mean", "min"):
            writer.writerow(
                {
                    "session": "2025-01-05",
                    "signal": signal,
                    "instrument": "",
                    "is_empty": "True",
                    "amount": "0",
                    "weight": "0",
                    "value": "0",
                }
            )
    sidecar["artifact"].update(
        {
            "sha256": api.sha256_file(artifact_path),
            "bytes": artifact_path.stat().st_size,
            "empty_session_signal_pairs": 4,
        }
    )
    sidecar.pop("receipt_hash")
    sidecar["receipt_hash"] = api.canonical_hash(sidecar)
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    pointer["receipt_sha256"] = api.sha256_file(sidecar_path)
    replace_entries(active, entries)
    client = TestClient(api.create_app(active))

    response = client.get(f"/api/v1/research/backtests/{entry['id']}/holdings")
    assert response.status_code == 200
    assert response.json()["empty"] is True
    assert response.json()["holdings"] == []

    artifact_path.write_text("tampered", encoding="utf-8")
    assert client.get(f"/api/v1/research/backtests/{entry['id']}/holdings").status_code == 503
    assert client.get("/api/v1/research/backtests").status_code == 200
