"""Environment-bound official hyperparameters for isolated Kronos workspaces."""

from __future__ import annotations

import os


class Config:
    def __init__(self):
        root = os.environ["ELANQUANT_ROOT"]
        track = os.environ["ELANQUANT_TRACK"]
        size = os.environ.get("ELANQUANT_MODEL_SIZE", "small")
        self.qlib_data_path = "UNUSED_ELANQUANT_IMMUTABLE_DATASET"
        self.instrument = "csi300"
        self.dataset_begin_time = "2011-01-01"
        self.dataset_end_time = "LATEST_CLOSED_SESSION"
        self.lookback_window = 90
        self.predict_window = 10
        self.max_context = 512
        self.feature_list = ["open", "high", "low", "close", "vol", "amt"]
        self.time_feature_list = ["minute", "hour", "weekday", "day", "month"]
        self.train_time_range = ["2011-01-01", "2024-12-31"]
        self.val_time_range = ["2025-01-01", "2025-12-31"]
        self.test_time_range = ["2026-01-01", "LATEST_CLOSED_SESSION"]
        self.backtest_time_range = self.test_time_range
        self.dataset_path = f"{root}/data/processed/extended-v2/{track}"
        self.clip = 5.0
        self.epochs = int(os.environ.get("ELANQUANT_EPOCHS", "30"))
        self.log_interval = 100
        self.batch_size = int(os.environ.get("ELANQUANT_BATCH_SIZE", "50"))
        self.n_train_iter = int(
            os.environ.get("ELANQUANT_TRAIN_SAMPLES", str(2000 * self.batch_size))
        )
        self.n_val_iter = int(os.environ.get("ELANQUANT_VAL_SAMPLES", str(400 * self.batch_size)))
        self.tokenizer_learning_rate = 2e-4
        self.predictor_learning_rate = 4e-5
        self.accumulation_steps = 1
        self.adam_beta1 = 0.9
        self.adam_beta2 = 0.95
        self.adam_weight_decay = 0.1
        self.seed = 100
        self.use_comet = False
        self.comet_config = {"api_key": "", "project_name": "", "workspace": ""}
        self.comet_tag = f"elanquant-{track}-{size}"
        self.comet_name = self.comet_tag
        save_root = os.environ.get("ELANQUANT_SAVE_ROOT", f"{root}/models/finetuned")
        self.save_path = f"{save_root}/{track}"
        self.tokenizer_save_folder_name = "tokenizer"
        self.predictor_save_folder_name = f"predictor-{size}"
        self.backtest_save_folder_name = f"backtest-{size}"
        self.backtest_result_path = f"{root}/reports/generated/{track}-{size}"
        self.pretrained_tokenizer_path = f"{root}/models/pretrained/Kronos-Tokenizer-base"
        self.pretrained_predictor_path = f"{root}/models/pretrained/Kronos-{size}"
        self.finetuned_tokenizer_path = (
            f"{self.save_path}/{self.tokenizer_save_folder_name}/checkpoints/best_model"
        )
        self.finetuned_predictor_path = (
            f"{self.save_path}/{self.predictor_save_folder_name}/checkpoints/best_model"
        )
        self.backtest_n_symbol_hold = 50
        self.backtest_n_symbol_drop = 5
        self.backtest_hold_thresh = 5
        self.inference_T = 0.6
        self.inference_top_p = 0.9
        self.inference_top_k = 0
        self.inference_sample_count = 10
        self.backtest_batch_size = 1000
        self.backtest_benchmark = "SH000300"
