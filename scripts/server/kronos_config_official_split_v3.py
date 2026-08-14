"""Pinned author-compatible runtime config for Plan011 official raw slices."""

from __future__ import annotations

import os


class Config:
    def __init__(self) -> None:
        root = os.environ["ELANQUANT_ROOT"]
        size = os.environ["ELANQUANT_MODEL_SIZE"]
        run_id = os.environ["ELANQUANT_RUN_ID"]
        self.qlib_data_path = "UNUSED_ELANQUANT_IMMUTABLE_DATASET"
        self.instrument = "csi300"
        self.dataset_begin_time = "2011-01-01"
        self.dataset_end_time = os.environ["ELANQUANT_FROZEN_LATEST"]
        self.lookback_window = 90
        self.predict_window = 10
        self.max_context = 512
        self.feature_list = ["open", "high", "low", "close", "vol", "amt"]
        self.time_feature_list = ["minute", "hour", "weekday", "day", "month"]
        self.train_time_range = ["2011-01-01", "2022-12-31"]
        self.val_time_range = ["2022-09-01", "2024-06-30"]
        self.test_time_range = ["2024-04-01", self.dataset_end_time]
        self.backtest_time_range = ["2024-07-01", self.dataset_end_time]
        self.dataset_path = os.environ.get(
            "ELANQUANT_DATASET_PATH",
            f"{root}/data/processed/official-split-v3/official",
        )
        self.clip = 5.0
        self.epochs = 30
        self.log_interval = 100
        self.batch_size = 50
        self.n_train_iter = 2000 * self.batch_size
        self.n_val_iter = 400 * self.batch_size
        self.tokenizer_learning_rate = 2e-4
        self.predictor_learning_rate = 4e-5
        self.accumulation_steps = 1
        self.adam_beta1 = 0.9
        self.adam_beta2 = 0.95
        self.adam_weight_decay = 0.1
        self.seed = 100
        self.use_comet = False
        self.comet_config = {"api_key": "", "project_name": "", "workspace": ""}
        self.comet_tag = f"elanquant-official-split-v3-{size}"
        self.comet_name = self.comet_tag
        self.save_path = f"{root}/models/training/{run_id}/official"
        self.tokenizer_save_folder_name = "tokenizer"
        self.predictor_save_folder_name = f"predictor-{size}"
        self.backtest_save_folder_name = f"backtest-{size}"
        self.backtest_result_path = f"{root}/reports/generated/{run_id}"
        self.pretrained_tokenizer_path = f"{root}/models/pretrained/Kronos-Tokenizer-base"
        self.pretrained_predictor_path = f"{root}/models/pretrained/Kronos-{size}"
        self.finetuned_tokenizer_path = (
            f"{self.save_path}/tokenizer/checkpoints/best_model"
        )
        self.finetuned_predictor_path = (
            f"{self.save_path}/predictor-{size}/checkpoints/best_model"
        )
        self.backtest_n_symbol_hold = 50
        self.backtest_n_symbol_drop = 5
        self.backtest_hold_thresh = 5
        self.inference_T = 0.6
        self.inference_top_p = 0.9
        self.inference_top_k = 0
        self.inference_sample_count = 5
        self.backtest_batch_size = 1000
        self.backtest_benchmark = "SH000300"
