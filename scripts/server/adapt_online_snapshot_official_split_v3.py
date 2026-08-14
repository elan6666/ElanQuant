#!/usr/bin/env python3
"""Create an immutable column-name adapter view for the locked v3 online runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ALIASES = {"vol": "volume", "amt": "amount"}
FEATURES = ("open", "high", "low", "close", "volume", "amount")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def adapt_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise RuntimeError("online symbol frame must have unique columns")
    for source, target in ALIASES.items():
        if source not in frame.columns or target in frame.columns:
            raise RuntimeError(f"online alias boundary is invalid: {source}->{target}")
    adapted = frame.rename(columns=ALIASES)
    if not adapted.columns.is_unique or any(name not in adapted.columns for name in FEATURES):
        raise RuntimeError("adapted online frame lacks the exact model features")
    values = adapted.loc[:, FEATURES].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise RuntimeError("adapted online model features must be finite")
    if (values[:, :4] <= 0).any() or (values[:, 4:] < 0).any():
        raise RuntimeError("adapted prices must be positive and volume/amount nonnegative")
    for source, target in ALIASES.items():
        if not np.array_equal(
            frame[source].to_numpy(), adapted[target].to_numpy(), equal_nan=True
        ):
            raise RuntimeError(f"online alias changed values: {source}->{target}")
        if frame[source].dtype != adapted[target].dtype:
            raise RuntimeError(f"online alias changed dtype: {source}->{target}")
    return adapted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.out.resolve()
    if output.exists() or source == output or source in output.parents:
        raise RuntimeError("adapted snapshot output must be a new independent directory")
    manifest_path = source / "manifest.json"
    manifest = read_object(manifest_path)
    source_files = manifest.get("files")
    required = {"online_data.pkl", "trade_cal.csv", "execution.json"}
    if manifest.get("status") != "PASS" or not isinstance(source_files, dict):
        raise RuntimeError("source online snapshot is not terminal PASS")
    if set(source_files) != required:
        raise RuntimeError("source online snapshot file set is not exact")
    for name in required:
        if sha256(source / name) != source_files[name]:
            raise RuntimeError(f"source online snapshot file changed: {name}")
    with (source / "online_data.pkl").open("rb") as handle:
        symbols = pickle.load(handle)
    if not isinstance(symbols, dict) or len(symbols) < 250:
        raise RuntimeError("source online snapshot symbol payload is incomplete")
    adapted = {str(code): adapt_frame(frame) for code, frame in sorted(symbols.items())}
    temporary = output.with_name(output.name + f".tmp-{os.getpid()}")
    temporary.mkdir(parents=True)
    data_path = temporary / "online_data.pkl"
    with data_path.open("wb") as handle:
        pickle.dump(adapted, handle, protocol=pickle.HIGHEST_PROTOCOL)
    for name in ("trade_cal.csv", "execution.json"):
        shutil.copyfile(source / name, temporary / name)
    adapted_manifest = {
        "schema_version": "elanquant_online_snapshot_adapter_v1",
        "status": "PASS",
        "resolved_session": manifest.get("resolved_session"),
        "requested_session": manifest.get("requested_session"),
        "source_manifest_sha256": sha256(manifest_path),
        "source_snapshot_logic_sha256": manifest.get("snapshot_logic_sha256"),
        "adapter_sha256": sha256(Path(__file__).resolve()),
        "column_aliases": ALIASES,
        "value_transform": "IDENTITY_NO_SCALE_NO_FILL_NO_REORDER",
        "symbols": len(adapted),
        "source_files": {name: str(source_files[name]) for name in sorted(required)},
        "files": {
            "online_data.pkl": sha256(data_path),
            "trade_cal.csv": sha256(temporary / "trade_cal.csv"),
            "execution.json": sha256(temporary / "execution.json"),
        },
    }
    (temporary / "manifest.json").write_text(
        json.dumps(adapted_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                "status": "PASS",
                "snapshot": output.as_posix(),
                "manifest_sha256": sha256(output / "manifest.json"),
                "source_manifest_sha256": sha256(manifest_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
