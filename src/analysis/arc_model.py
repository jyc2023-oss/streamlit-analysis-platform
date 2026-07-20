from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "arc_recognition"


@lru_cache(maxsize=1)
def _load_assets() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    weights_path = MODEL_DIR / "mlp_weights_numpy.npz"
    norm_path = MODEL_DIR / "norm_params.npz"
    if not weights_path.is_file() or not norm_path.is_file():
        raise FileNotFoundError("电弧识别模型文件尚未部署。")
    with np.load(weights_path) as content:
        weights = {name: np.asarray(content[name]) for name in content.files}
    with np.load(norm_path) as content:
        feature_mean = np.asarray(content["feature_mean"], dtype=np.float64)
        feature_std = np.asarray(content["feature_std"], dtype=np.float64)
    if feature_mean.shape != (24,) or feature_std.shape != (24,):
        raise ValueError("电弧识别归一化参数必须为24维。")
    return weights, feature_mean, feature_std


def _batch_norm(values: np.ndarray, weights: dict[str, np.ndarray], name: str) -> np.ndarray:
    normalized = (values - weights[f"{name}.running_mean"]) / np.sqrt(
        weights[f"{name}.running_var"] + 1e-5
    )
    return normalized * weights[f"{name}.weight"] + weights[f"{name}.bias"]


def predict_arc(features: np.ndarray) -> np.ndarray:
    """Return the trained MLP arc probability for each 24-dimensional half-wave."""
    weights, feature_mean, feature_std = _load_assets()
    values = np.asarray(features, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 24:
        raise ValueError("电弧识别模型输入必须是 N×24 特征矩阵。")
    values = (values - feature_mean) / (feature_std + 1e-12)
    values = (values - values.mean(axis=1, keepdims=True)) / (
        values.std(axis=1, keepdims=True) + 1e-12
    )
    for index in range(1, 5):
        values = values @ weights[f"fc{index}.weight"].T + weights[f"fc{index}.bias"]
        values = _batch_norm(values, weights, f"bn{index}")
        values = np.maximum(values, 0.0)
    logits = values @ weights["fc5.weight"].T + weights["fc5.bias"]
    logits = np.clip(logits.reshape(-1), -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-logits))
