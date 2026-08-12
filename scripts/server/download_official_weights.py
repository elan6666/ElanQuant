#!/usr/bin/env python3
"""Download pinned public Kronos weights and verify published weight hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

MODELS = {
    "NeoQuasar/Kronos-Tokenizer-base": {
        "revision": "0e0117387f39004a9016484a186a908917e22426",
        "model_sha256": "59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee",
    },
    "NeoQuasar/Kronos-small": {
        "revision": "901c26c1332695a2a8f243eb2f37243a37bea320",
        "model_sha256": "b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020",
    },
    "NeoQuasar/Kronos-base": {
        "revision": "2b554741eca47781b64468546e77fef3e85130e6",
        "model_sha256": "abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    receipt = {"schema_version": "elanquant_official_weights_v1", "models": {}}
    for repo, identity in MODELS.items():
        destination = args.out_root / repo.split("/", 1)[1]
        snapshot_download(repo, revision=identity["revision"], local_dir=destination)
        weight = destination / "model.safetensors"
        actual = sha256(weight)
        if actual != identity["model_sha256"]:
            raise RuntimeError(f"weight hash mismatch for {repo}: {actual}")
        receipt["models"][repo] = {
            **identity,
            "path": destination.as_posix(),
            "bytes": weight.stat().st_size,
        }
    receipt["status"] = "PASS"
    args.out_root.mkdir(parents=True, exist_ok=True)
    (args.out_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
