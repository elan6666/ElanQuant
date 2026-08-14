"""Author QlibDataset with only the eligible-index enumeration replaced.

The model input, normalization, sampling, feature order and returned tensors are
identical to the pinned Kronos Dataset.  The separate index files ensure each
101-row sample is made of consecutive global exchange sessions and that index
membership is tested at the signal anchor only, never on future rows.
"""

from __future__ import annotations

import pickle
import random

import numpy as np
import torch
from config import Config
from torch.utils.data import Dataset


class QlibDataset(Dataset):
    def __init__(self, data_type: str = "train") -> None:
        self.config = Config()
        if data_type not in {"train", "val"}:
            raise ValueError("data_type must be 'train' or 'val'")
        self.data_type = data_type
        self.py_rng = random.Random(self.config.seed)
        filename = "train" if data_type == "train" else "val"
        self.data_path = f"{self.config.dataset_path}/{filename}_data.pkl"
        self.index_path = f"{self.config.dataset_path}/{filename}_indices.pkl"
        configured = self.config.n_train_iter if data_type == "train" else self.config.n_val_iter
        with open(self.data_path, "rb") as handle:
            self.data = pickle.load(handle)
        with open(self.index_path, "rb") as handle:
            self.indices = pickle.load(handle)
        if not isinstance(self.data, dict) or not isinstance(self.indices, list):
            raise RuntimeError("admitted data/index payload is invalid")
        self.window = self.config.lookback_window + self.config.predict_window + 1
        self.feature_list = self.config.feature_list
        self.time_feature_list = self.config.time_feature_list
        for symbol, frame in list(self.data.items()):
            value = frame.reset_index()
            value["minute"] = value["datetime"].dt.minute
            value["hour"] = value["datetime"].dt.hour
            value["weekday"] = value["datetime"].dt.weekday
            value["day"] = value["datetime"].dt.day
            value["month"] = value["datetime"].dt.month
            self.data[symbol] = value[self.feature_list + self.time_feature_list]
        if not self.indices:
            raise RuntimeError("admitted eligible index is empty")
        self.n_samples = min(configured, len(self.indices))
        print(
            f"[{data_type.upper()}] Loaded {len(self.indices)} admitted consecutive samples. "
            f"Using {self.n_samples} per epoch."
        )

    def set_epoch_seed(self, epoch: int) -> None:
        self.py_rng.seed(self.config.seed + epoch)

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        del idx
        symbol, start_idx = self.indices[self.py_rng.randint(0, len(self.indices) - 1)]
        win_df = self.data[symbol].iloc[start_idx : start_idx + self.window]
        x = win_df[self.feature_list].values.astype(np.float32)
        x_stamp = win_df[self.time_feature_list].values.astype(np.float32)
        past_x = x[: self.config.lookback_window]
        x = (x - np.mean(past_x, axis=0)) / (np.std(past_x, axis=0) + 1e-5)
        x = np.clip(x, -self.config.clip, self.config.clip)
        return torch.from_numpy(x), torch.from_numpy(x_stamp)
