import numpy as np

from src.analysis.registry import bandpass_filter, fft_spectrum, waveform, wavelet_energy


def test_waveform_metrics() -> None:
    output = waveform(np.array([1.0, -1.0, 1.0, -1.0]), 4.0, {})
    assert output.kind == "line"
    assert len(output.x) == 4
    assert "均方根" in output.table["指标"].tolist()


def test_fft_finds_tone() -> None:
    sample_rate = 4096.0
    time = np.arange(4096) / sample_rate
    values = np.sin(2 * np.pi * 256 * time)
    output = fft_spectrum(values, sample_rate, {"min_frequency": 0, "max_frequency": 1000})
    peak_frequency = output.x[int(np.argmax(output.y))]
    assert abs(peak_frequency - 256) <= 1


def test_bandpass_reduces_out_of_band_tone() -> None:
    sample_rate = 4000.0
    time = np.arange(8000) / sample_rate
    values = np.sin(2 * np.pi * 100 * time) + np.sin(2 * np.pi * 1000 * time)
    output = bandpass_filter(
        values,
        sample_rate,
        {"low_frequency": 80, "high_frequency": 120, "order": 4},
    )
    assert np.sqrt(np.mean(output.y**2)) < np.sqrt(np.mean(values**2))
    assert np.sqrt(np.mean(output.y**2)) > 0.5


def test_wavelet_energy_ratios_sum_to_one() -> None:
    values = np.sin(np.linspace(0, 20 * np.pi, 4096))
    output = wavelet_energy(values, 4096.0, {"wavelet": "db3", "level": 4})
    assert output.kind == "bar"
    assert np.isclose(output.y.sum(), 1.0)
