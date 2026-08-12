#!/usr/bin/env python3
"""Bounded two-rank diagnostic for Kronos DDP model synchronization.

This is a server-only admission check.  It deliberately performs no optimizer
step and writes no checkpoint; its only purpose is to distinguish model/DDP
initialization failures from data-loader and training-loop failures.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--backend", choices=("nccl", "gloo"), default="nccl")
    parser.add_argument("--large-collective-mib", type=int, default=64)
    args = parser.parse_args()

    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    dist.init_process_group(backend=args.backend, device_id=torch.device("cuda", local_rank))
    device = torch.device("cuda", local_rank)
    if local_rank == 0:
        print("DIST_READY", flush=True)

    elements = args.large_collective_mib * 1024 * 1024 // 4
    probe = torch.full((elements,), float(local_rank + 1), device=device)
    dist.all_reduce(probe)
    torch.cuda.synchronize(device)
    if not torch.all(probe == 3):
        raise RuntimeError("large all-reduce produced an unexpected value")
    if local_rank == 0:
        print("LARGE_COLLECTIVE_READY", flush=True)

    sys.path.insert(0, str(args.upstream.resolve()))
    from model.kronos import Kronos  # type: ignore[import-not-found]

    model = Kronos.from_pretrained(args.model.resolve()).to(device)
    torch.cuda.synchronize(device)
    if local_rank == 0:
        print("MODEL_LOADED", flush=True)
    wrapped = DistributedDataParallel(model, device_ids=[local_rank], output_device=local_rank)
    torch.cuda.synchronize(device)
    if local_rank == 0:
        print("DDP_READY", flush=True)

    loss = sum(parameter.float().square().mean() for parameter in wrapped.parameters())
    loss.backward()
    torch.cuda.synchronize(device)
    dist.barrier()
    if local_rank == 0:
        print("BACKWARD_READY", flush=True)
    dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
