from __future__ import annotations

import copy

import pytest
from elanquant.contracts.unified_comparison import (
    ARTIFACT_ROOT,
    CATALOG_SCHEMA,
    EVIDENCE_SCHEMA,
    MODEL_FAMILIES,
    PORTFOLIOS,
    PROTOCOL_SCHEMA,
    RESULT_SCHEMA,
    result_id,
    validate_catalog,
    validate_model_evidence,
    validate_protocol,
    validate_result_receipt,
)

from elanquant.contracts.official_demo import canonical_hash

SHA = "a" * 64


def sealed(payload: dict[str, object]) -> dict[str, object]:
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


def common() -> dict[str, object]:
    return {
        "evaluation_range": {"start": "2024-07-01", "end": "2026-08-14"},
        "anchor_set_sha256": SHA,
        "label_artifact_sha256": SHA,
        "universe_artifact_sha256": SHA,
        "execution_spec_sha256": SHA,
        "anchor_frequency": "strict_weekly",
        "label_definition": "strict_weekly_open_to_open_log_return",
        "execution_semantics": "next_trading_session_open",
        "delay_sessions": 1,
        "support": {"anchors": 100, "signal_rows": 30000},
    }


def evidence(family: str, lookback: int) -> dict[str, object]:
    return sealed(
        {
            "schema_version": EVIDENCE_SCHEMA,
            "status": "PASS",
            "id": f"weekly-evidence-{family}-v1",
            "model_family_id": family,
            "common_protocol": common(),
            "model_input": {
                "lookback_sessions": lookback,
                "feature_schema": "ohlcv",
                "input_artifact": {
                    "path": f"{ARTIFACT_ROOT}/inputs/{family}.parquet",
                    "sha256": SHA,
                },
            },
            "model_sha256": SHA,
            "runner_code_sha256": SHA,
            "artifacts": {
                "predictions": {
                    "path": f"{ARTIFACT_ROOT}/predictions/{family}.parquet",
                    "sha256": SHA,
                },
                "scores": {"path": f"{ARTIFACT_ROOT}/scores/{family}.json", "sha256": SHA},
            },
            "online_paper_equivalent": False,
            "promotion_eligible": False,
        }
    )


def protocol() -> dict[str, object]:
    return sealed(
        {
            "schema_version": PROTOCOL_SCHEMA,
            "status": "PASS",
            "id": "itransformer-b2-vs-kronos-base-weekly-v1",
            "model_families": list(MODEL_FAMILIES),
            "portfolios": list(PORTFOLIOS),
            "common_protocol": common(),
            "online_paper_equivalent": False,
            "promotion_eligible": False,
            "source_evidence": [
                {
                    "model_family_id": family,
                    "receipt_path": f"{ARTIFACT_ROOT}/evidence/{family}.json",
                    "receipt_sha256": SHA,
                    "common_protocol": common(),
                }
                for family in MODEL_FAMILIES
            ],
        }
    )


def result(family: str, portfolio: str) -> dict[str, object]:
    return sealed(
        {
            "schema_version": RESULT_SCHEMA,
            "status": "PASS",
            "id": result_id(family, portfolio),
            "model_family_id": family,
            "portfolio_id": portfolio,
            "protocol_id": "itransformer-b2-vs-kronos-base-weekly-v1",
            "protocol_receipt_sha256": SHA,
            "source_evidence_receipt_sha256": SHA,
            "prediction_metrics": {
                key: 0.1 for key in ("rank_ic", "pearson_ic", "spearman_ic", "mae", "rmse")
            },
            "portfolio_metrics": {
                key: 0.1
                for key in (
                    "total_return_with_cost",
                    "benchmark_return",
                    "excess_return_with_cost",
                    "information_ratio_with_cost",
                    "max_drawdown_with_cost",
                    "turnover_mean",
                    "total_cost",
                )
            },
            "artifacts": {
                key: {
                    "path": f"{ARTIFACT_ROOT}/results/{family}/{portfolio}/{key}.csv",
                    "sha256": SHA,
                }
                for key in ("daily_series", "holdings", "raw_report")
            },
            "online_paper_equivalent": False,
            "promotion_eligible": False,
        }
    )


def test_b2_and_kronos_evidence_allow_different_windows_but_require_weekly_protocol() -> None:
    assert (
        validate_model_evidence(evidence(MODEL_FAMILIES[0], 80))["model_input"]["lookback_sessions"]
        == 80
    )
    assert (
        validate_model_evidence(evidence(MODEL_FAMILIES[1], 90))["model_family_id"]
        == MODEL_FAMILIES[1]
    )
    bad = evidence(MODEL_FAMILIES[0], 80)
    bad["common_protocol"]["delay_sessions"] = 0
    bad["receipt_hash"] = canonical_hash(
        {key: value for key, value in bad.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="anchor, label or execution"):
        validate_model_evidence(bad)


def test_protocol_rejects_different_anchor_label_or_execution() -> None:
    assert validate_protocol(protocol())["id"]
    bad = copy.deepcopy(protocol())
    bad["source_evidence"][1]["common_protocol"]["label_artifact_sha256"] = "b" * 64
    bad["receipt_hash"] = canonical_hash(
        {key: value for key, value in bad.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="differs"):
        validate_protocol(bad)


def test_results_require_all_metrics_and_keep_paper_separate() -> None:
    assert validate_result_receipt(result(MODEL_FAMILIES[0], "top50"))["id"]
    bad = result(MODEL_FAMILIES[1], "top3")
    bad["online_paper_equivalent"] = True
    bad["receipt_hash"] = canonical_hash(
        {key: value for key, value in bad.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="firewall"):
        validate_result_receipt(bad)


def test_catalog_requires_exact_two_by_three_matrix() -> None:
    entries = [
        {
            "id": result_id(family, portfolio),
            "model_family_id": family,
            "portfolio_id": portfolio,
            "receipt_path": f"{ARTIFACT_ROOT}/results/{family}/{portfolio}/result-receipt.json",
            "receipt_sha256": SHA,
            "online_paper_equivalent": False,
            "promotion_eligible": False,
        }
        for family in MODEL_FAMILIES
        for portfolio in PORTFOLIOS
    ]
    payload = sealed(
        {
            "schema_version": CATALOG_SCHEMA,
            "status": "PASS",
            "protocol_id": "itransformer-b2-vs-kronos-base-weekly-v1",
            "protocol_path": f"{ARTIFACT_ROOT}/protocol/protocol-receipt.json",
            "protocol_receipt_sha256": SHA,
            "entries": entries,
        }
    )
    assert len(validate_catalog(payload)["entries"]) == 6
    payload["entries"].pop()
    payload["receipt_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        validate_catalog(payload)
