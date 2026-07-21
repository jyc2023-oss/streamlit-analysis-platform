from __future__ import annotations

from typing import Any

import numpy as np

from src.analysis import AnalysisOutput
from src.services.datasets import downsample


def dataset_public(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "id",
            "relative_path",
            "name",
            "extension",
            "size_bytes",
            "modified_at",
            "indexed_at",
            "status",
            "error_message",
            "metadata",
        )
    }


def _series_values(
    x_values: np.ndarray, y_values: np.ndarray, maximum: int = 20_000
) -> tuple[list[float], list[float]]:
    x_values = np.asarray(x_values)
    y_values = np.asarray(y_values)
    if y_values.size > maximum:
        indices, sampled = downsample(y_values, maximum)
        x_values = x_values[indices]
        y_values = sampled
    return x_values.astype(float).tolist(), y_values.astype(float).tolist()


def analysis_output_public(output: AnalysisOutput, include_table: bool = False) -> dict[str, Any]:
    x_values, y_values = _series_values(output.x, output.y)
    series = []
    for label, x_item, y_item in output.series or []:
        series_x, series_y = _series_values(x_item, y_item)
        series.append({"label": label, "x": series_x, "y": series_y})
    result: dict[str, Any] = {
        "title": output.title,
        "x": x_values,
        "y": y_values,
        "xLabel": output.x_label,
        "yLabel": output.y_label,
        "kind": output.kind,
        "series": series,
        "summary": output.summary,
    }
    if include_table:
        table = output.table.replace({np.nan: None})
        result["columns"] = [str(column) for column in table.columns]
        result["rows"] = table.to_dict(orient="records")
    return result
