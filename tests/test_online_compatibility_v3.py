from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from scripts.research.online_compatibility_v3 import (
    ALIAS_MAPPING,
    COMPATIBILITY_MODE,
    COMPATIBILITY_SCHEMA,
    OnlineCompatibilityError,
    canonical_hash,
    validate_compatibility_receipt,
)
from scripts.server.adapt_online_snapshot_official_split_v3 import adapt_frame


def compatibility_receipt() -> dict[str, object]:
    artifacts = {
        name: {"sha256": character * 64, "bytes": index + 1}
        for index, (name, character) in enumerate(
            (
                ("training-matrix.json", "a"),
                ("analysis-lock.json", "b"),
                ("online-method-lock.json", "c"),
                ("rolling-evaluation.json", "d"),
                ("historical-catalog.json", "e"),
                ("manifest.json", "f"),
            )
        )
    }
    value: dict[str, object] = {
        "schema_version": COMPATIBILITY_SCHEMA,
        "status": "PASS",
        "source_release_id": "official-v3-source",
        "target_release_id": "official-v3-compat-v1",
        "compatibility_mode": COMPATIBILITY_MODE,
        "source_manifest_sha256": "1" * 64,
        "source_manifest_receipt_hash": "2" * 64,
        "source_artifacts": artifacts,
        "source_artifact_set_sha256": canonical_hash(artifacts),
        "online_snapshot_adapter_sha256": "3" * 64,
        "online_fetcher_sha256": "4" * 64,
        "compatibility_contract_sha256": "7" * 64,
        "original_online_runner_sha256": "5" * 64,
        "original_online_contract_sha256": "6" * 64,
        "column_aliases": ALIAS_MAPPING,
        "value_transform": "IDENTITY_NO_SCALE_NO_FILL_NO_REORDER",
        "formal_evaluation_alias": {
            "source": "rolling-evaluation.json",
            "alias": "formal-evaluation.json",
            "semantics": "BYTE_IDENTICAL_INDEPENDENT_COPY",
        },
        "source_preserved": True,
        "method_identity_unchanged": True,
        "applied_after_viewed_results": True,
        "test_metrics_used_for_selection": False,
        "training_evaluation_backtest_rerun": False,
        "used_for_selection": False,
        "promotion_eligible": False,
    }
    value["receipt_hash"] = canonical_hash(value)
    return value


def test_online_alias_adapter_preserves_values_dtype_index_and_order() -> None:
    frame = pd.DataFrame(
        {
            "open": [1.0, 2.0],
            "high": [2.0, 3.0],
            "low": [0.5, 1.5],
            "close": [1.5, 2.5],
            "vol": [100, 200],
            "amt": [1000.0, 2000.0],
            "name": ["A", "A"],
        },
        index=pd.to_datetime(["2026-08-12", "2026-08-13"]),
    )
    frame["vol"] = frame["vol"].astype("int64")
    adapted = adapt_frame(frame)
    assert list(adapted.columns) == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "name",
    ]
    assert adapted.index.equals(frame.index)
    np.testing.assert_array_equal(adapted["volume"], frame["vol"])
    np.testing.assert_array_equal(adapted["amount"], frame["amt"])
    assert adapted["volume"].dtype == frame["vol"].dtype


@pytest.mark.parametrize(
    "mutation",
    (
        lambda frame: frame.drop(columns="amt"),
        lambda frame: frame.assign(volume=frame["vol"]),
        lambda frame: frame.assign(close=np.inf),
        lambda frame: frame.assign(amt=-1.0),
    ),
)
def test_online_alias_adapter_rejects_missing_collision_and_nonfinite(mutation) -> None:
    frame = pd.DataFrame(
        {
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "vol": [100.0],
            "amt": [1000.0],
        }
    )
    with pytest.raises(RuntimeError):
        adapt_frame(mutation(frame))


def test_compatibility_receipt_is_post_viewed_non_selection_and_tamper_closed() -> None:
    receipt = compatibility_receipt()
    assert validate_compatibility_receipt(receipt)["promotion_eligible"] is False
    altered = copy.deepcopy(receipt)
    altered["method_identity_unchanged"] = False
    altered["receipt_hash"] = canonical_hash(
        {key: value for key, value in altered.items() if key != "receipt_hash"}
    )
    with pytest.raises(OnlineCompatibilityError, match="firewall"):
        validate_compatibility_receipt(altered)
