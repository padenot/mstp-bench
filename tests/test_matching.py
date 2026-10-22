"""The matcher finds known positions and refuses to identify unrelated audio."""
import numpy as np
import pytest

from repro.matching import WINDOW_MS, bandpass, frames, match, resample
from repro.signal import expected, source

RATES = [44100, 48000]


def test_source_matches_the_javascript_definition():
    # Values computed by web/signal.js sampleAt().
    assert source(1, 48000)[0] == -0.25
    assert abs(source(1001, 48000)[1000] - 0.20549953313699615) < 1e-12


def age_ms(observed, rate):
    """Locate a window 1.8 s into `observed`; return how far behind the source it is."""
    template = bandpass(expected(3 * rate, rate, {"mode": "copy"}), rate)
    start, n = int(1.8 * rate), frames(WINDOW_MS, rate)
    m = match(template, bandpass(observed, rate)[start:start + n], 0, len(template), rate)
    assert m.accepted
    return (start + n / 2 - m.center) * 1000 / rate


@pytest.mark.parametrize("rate", RATES)
def test_delay_loss_and_repetition_are_measured(rate):
    signal = expected(3 * rate, rate, {"mode": "copy"})
    pad, cut = np.zeros(frames(40, rate)), frames(20, rate)
    assert abs(age_ms(np.r_[pad, signal], rate) - 40) < 1000 / rate
    assert abs(age_ms(np.r_[pad, signal[:rate], signal[rate + cut:]], rate) - 20) < 1000 / rate
    assert abs(age_ms(np.r_[pad, signal[:rate], signal[rate - cut:]], rate) - 60) < 1000 / rate


def test_resampled_observation_keeps_its_position():
    observed = resample(np.r_[np.zeros(frames(40, 48000)), expected(3 * 48000, 48000, {"mode": "copy"})], 48000, 44100)
    assert abs(age_ms(observed, 44100) - 40) < 0.1


@pytest.mark.parametrize("rate", RATES)
def test_silence_noise_and_distant_content_are_not_identified(rate):
    template = bandpass(expected(25 * rate, rate, {"mode": "copy"}), rate)
    n = frames(WINDOW_MS, rate)
    noise = np.random.default_rng(1).normal(0, 0.1, n)
    near = template[:3 * rate]
    assert not match(near, np.zeros(n), 0, len(near), rate).accepted
    assert not match(near, bandpass(noise, rate), 0, len(near), rate).accepted
    assert not match(near, template[23 * rate:23 * rate + n], 0, len(near), rate).accepted
