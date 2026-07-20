import numpy as np
import pandas as pd

from src.analysis import AnalysisOutput
from src.components.plots import build_analysis_figure
from src.services.jobs import render_figure_bytes


def test_multi_series_output_renders_each_channel() -> None:
    frequencies = np.asarray([0.0, 50.0, 100.0])
    output = AnalysisOutput(
        "5 周波多通道 FFT 幅值谱",
        frequencies,
        np.asarray([0.0, 1.0, 0.0]),
        "频率 (Hz)",
        "幅值",
        "line",
        pd.DataFrame(),
        [
            ("CH01", frequencies, np.asarray([0.0, 1.0, 0.0])),
            ("CH02", frequencies, np.asarray([0.0, 0.5, 0.0])),
        ],
    )

    figure = build_analysis_figure(output)

    assert [trace.name for trace in figure.data] == ["CH01", "CH02"]
    assert render_figure_bytes(output, "png").startswith(b"\x89PNG")


def test_bar_output_with_text_labels_renders_png() -> None:
    output = AnalysisOutput(
        "电弧识别",
        np.asarray(["特征一", "特征二"]),
        np.asarray([0.25, 0.75]),
        "特征",
        "平均特征值",
        "bar",
        pd.DataFrame(),
    )

    assert render_figure_bytes(output, "png").startswith(b"\x89PNG")


def test_arc_detection_timeline_renders_png() -> None:
    output = AnalysisOutput(
        "文件夹判定：有弧",
        np.asarray([0.005, 0.015, 0.025]),
        np.asarray([0.2, 0.9, 0.7]),
        "时间 (s)",
        "有弧概率",
        "arc_detection",
        pd.DataFrame(),
        summary={"probability_threshold": 0.5},
    )

    assert render_figure_bytes(output, "png").startswith(b"\x89PNG")
