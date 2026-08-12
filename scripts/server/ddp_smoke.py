#!/usr/bin/env python3
"""Minimal two-GPU collective gate for the server research runtime."""

from __future__ import annotations

import os

import torch
import torch.distributed as dist


def main() -> int:
    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    device = torch.device(f"cuda:{local_rank}")
    dist.init_process_group(backend="nccl", device_id=device)
    value = torch.tensor([float(dist.get_rank() + 1)], device=device)
    dist.all_reduce(value)
    torch.cuda.synchronize(device)
    if dist.get_rank() == 0:
        print(
            {
                "status": "PASS",
                "world_size": dist.get_world_size(),
                "all_reduce": value.item(),
                "cuda": torch.version.cuda,
                "nccl": torch.cuda.nccl.version(),
            },
            flush=True,
        )
    dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
