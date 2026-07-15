import numpy as np

from src.services.datasets import downsample


def test_downsample_preserves_extrema() -> None:
    values = np.zeros(10_000)
    values[123] = 50
    values[4567] = -30
    _, sampled = downsample(values, 500)
    assert sampled.max() == 50
    assert sampled.min() == -30
    assert len(sampled) <= 500


def test_downsample_keeps_short_input() -> None:
    values = np.arange(10)
    indices, sampled = downsample(values, 100)
    np.testing.assert_array_equal(indices, np.arange(10))
    np.testing.assert_array_equal(sampled, values)
