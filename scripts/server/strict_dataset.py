"""Strict target-bounded, epoch-deterministic Kronos dataset adapter."""

from __future__ import annotations

import pickle
import random

import numpy as np
import torch
from config import Config
from torch.utils.data import Dataset


class QlibDataset(Dataset):
    def __init__(self, data_type: str = "train"):
        if data_type not in {"train", "val"}:
            raise ValueError("data_type must be train or val")
        self.config = Config()
        self.data_type = data_type
        with open(f"{self.config.dataset_path}/full_data.pkl", "rb") as handle:
            self.data = pickle.load(handle)
        with open(f"{self.config.dataset_path}/{data_type}_anchors.pkl", "rb") as handle:
            self.all_indices = list(pickle.load(handle))
        configured = self.config.n_train_iter if data_type == "train" else self.config.n_val_iter
        self.n_samples = min(configured, len(self.all_indices))
        self.indices: list[tuple[str, int]] = []
        self.window = self.config.lookback_window + self.config.predict_window + 1
        self.feature_list = self.config.feature_list
        self.time_feature_list = self.config.time_feature_list
        self.set_epoch_seed(0)

    def set_epoch_seed(self, epoch: int) -> None:
        # The pinned author loop passes ``epoch_idx * 10000 + rank``.  A strict
        # DDP dataset must expose the same sampled index list on every rank so
        # DistributedSampler can partition it without cross-rank overlap.
        logical_epoch = epoch // 10000
        rng = random.Random(self.config.seed + logical_epoch)
        self.indices = rng.sample(self.all_indices, self.n_samples)

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        symbol, start = self.indices[idx]
        frame = self.data[symbol].iloc[start : start + self.window].copy()
        if len(frame) != self.window:
            raise RuntimeError("strict anchor does not materialize a complete window")
        signal_index = self.config.lookback_window - 1
        signal_factor = float(frame.iloc[signal_index]["adj_factor"])
        factor = frame["adj_factor"].to_numpy(dtype=np.float64) / signal_factor
        price_columns = ["open", "high", "low", "close"]
        adjusted_prices = frame[price_columns].to_numpy(dtype=np.float64) * factor[:, None]
        frame.loc[:, price_columns] = adjusted_prices
        x = frame[self.feature_list].to_numpy(dtype=np.float32)
        dates = frame.index
        stamps = np.column_stack(
            [
                dates.minute,
                dates.hour,
                dates.weekday,
                dates.day,
                dates.month,
            ]
        ).astype(np.float32)
        past = x[: self.config.lookback_window]
        mean = past.mean(axis=0)
        std = past.std(axis=0)
        normalized = np.clip((x - mean) / (std + 1e-5), -self.config.clip, self.config.clip)
        return torch.from_numpy(normalized), torch.from_numpy(stamps)
