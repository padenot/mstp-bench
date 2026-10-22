"""Backlog recovery and output-clock mapping on synthetic data."""
import numpy as np
import pytest

from repro.analysis import Trial, output_clock, recovery


def points(values, start=650, step=10):
    return [{"wallMs": start + i * step, "unprocessedMs": [v, v]} for i, v in enumerate(values)]


def test_recovery_needs_a_sustained_return():
    flat = points([25] * 65)
    assert recovery(flat, 600, 2000, 30) == {"ceilingMs": 30, "firstMs": 50, "sustainedMs": 50}
    bounce = points([25, 40] + [25] * 63)
    assert recovery(bounce, 600, 2000, 30)["firstMs"] == 50
    assert recovery(bounce, 600, 2000, 30)["sustainedMs"] == 70


def test_recovery_needs_the_full_follow_up():
    assert recovery(points([25] * 45), 600, 2000, 30)["sustainedMs"] is None


def trial_with_source(blocks):
    trial = Trial.__new__(Trial)
    trial.source = np.array(blocks, dtype=float)
    return trial


def test_generated_frames_are_bounded_when_timestamps_tie():
    trial = trial_with_source([[i * 480, 480, i * 10] for i in range(100)])
    assert trial.generated(105) == [5280, 5280]
    # A block stamped exactly now may or may not be generated yet.
    assert trial.generated(100) == [4800, 5280]
    # With 1 ms timestamps, a block within 1 ms is equally uncertain.
    assert trial.generated(109.5, resolution_ms=1) == [5280, 5760]


def test_output_clock_maps_context_frames_to_device_time():
    trial = Trial.__new__(Trial)
    trial.receiver = {"rates": {"playout": 48000}, "timeOrigin": 1_000_000,
                      "clocks": [{"contextTime": t, "performanceTime": t * 1000 + 20} for t in (1, 1.25, 1.5)]}
    device_wall = output_clock(trial)
    assert device_wall(1.1 * 48000) == pytest.approx(1_001_120)
    with pytest.raises(AssertionError):
        device_wall(4 * 48000)
