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
