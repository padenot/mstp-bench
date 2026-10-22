"""The test signal and processing, mirroring web/signal.js and web/dsp.js."""
import numpy as np
from scipy.signal import fftconvolve


def source(count: int, rate: float) -> np.ndarray:
    """Pseudorandom values every millisecond, linearly interpolated (web/signal.js)."""
    ms = np.arange(count) * 1000 / rate
    knots = np.arange(int(ms[-1]) + 2 if count else 0, dtype=np.uint32)
    knots = (knots ^ (knots >> 16)) * np.uint32(0x45D9F3B)
    knots = (knots ^ (knots >> 16)) * np.uint32(0x45D9F3B)
    knots ^= knots >> 16
    values = knots.astype(np.float64) / 4294967296 * 2 - 1
    return 0.25 * np.interp(ms, np.arange(len(values)), values)


def fir_coefficients(taps: int) -> np.ndarray:
    """0.5 for the current sample, then a decaying tail summing to 0.5 (web/dsp.js)."""
    tail = np.exp(-6 * np.arange(1, taps) / taps)
    return np.r_[0.5, 0.5 * tail / tail.sum()]


def expected(count: int, rate: float, dsp: dict) -> np.ndarray:
    """The processed signal: source samples [0, count) after `dsp`."""
    signal = source(count, rate)
    if dsp["mode"] == "copy":
        return signal
    return fftconvolve(signal, fir_coefficients(dsp["taps"]))[:count] * dsp["gain"]
