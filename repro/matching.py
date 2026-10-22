"""Find which source samples an observed window contains.

Each observed 80 ms window is compared with the expected signal by normalized
cross-correlation. Both are band-passed to 200–3000 Hz first, which removes
what the Opus codec changes most, with a zero-phase filter so positions do not
shift. A match needs a high score and a clear margin over the best match more
than 10 ms away; otherwise the window counts as unidentified, never as a
position.
"""
from dataclasses import dataclass
from functools import lru_cache
from math import gcd

import numpy as np
from scipy.signal import butter, correlate, resample_poly, sosfiltfilt

WINDOW_MS = 80
MIN_SCORE = 0.75
MIN_MARGIN = 0.12


def frames(ms: float, rate: float) -> int:
    return int(round(ms * rate / 1000))


@lru_cache
def _bandpass(rate: float):
    return butter(3, [200, 3000], btype="bandpass", fs=rate, output="sos")


def bandpass(signal: np.ndarray, rate: float) -> np.ndarray:
    return sosfiltfilt(_bandpass(rate), signal)


def resample(signal: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return signal
    common = gcd(from_rate, to_rate)
    return resample_poly(signal, to_rate // common, from_rate // common)


@dataclass
class Match:
    accepted: bool
    score: float
    margin: float
    center: float | None  # Source frame at the window's center.


def match(template: np.ndarray, window: np.ndarray, lo: float, hi: float, rate: float) -> Match:
    """Locate `window` in template[lo:hi]. Both must already be band-passed."""
    lo, hi = max(0, int(lo)), min(len(template), int(hi))
    n = len(window)
    if hi - lo < n or np.dot(window, window) < 1e-8:
        return Match(False, 0.0, 0.0, None)
    section = template[lo:hi]
    w = window - window.mean()
    # Energy of every n-sample section of the template, mean removed.
    sums = np.concatenate(([0], np.cumsum(section)))
    squares = np.concatenate(([0], np.cumsum(section * section)))
    energy = squares[n:] - squares[:-n] - (sums[n:] - sums[:-n]) ** 2 / n
    scores = correlate(section, w, mode="valid", method="fft") / np.sqrt(np.maximum(energy * np.dot(w, w), 1e-20))
    best = int(np.argmax(scores))
    others = scores.copy()
    exclusion = frames(10, rate)
    others[max(0, best - exclusion):best + exclusion + 1] = -1
    score, margin = float(scores[best]), float(scores[best] - others.max())
    return Match(score >= MIN_SCORE and margin >= MIN_MARGIN, score, margin, lo + best + n / 2)
