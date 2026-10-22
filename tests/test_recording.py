"""Recording checks accept faithful Opus recordings and reject every defect."""
import subprocess

import numpy as np
import pytest

from repro.recording import check, content, decode, timeline
from repro.signal import expected

RATE, SECONDS = 44100, 4
FIR = {"mode": "fir", "taps": 4096, "gain": 0.5}


def encode(pcm, path, channels=1):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(RATE), "-ac", str(channels), "-i", "-",
                    "-c:a", "libopus", "-b:a", "128k", str(path)], input=pcm.astype("<f4").tobytes(), check=True)
    return path


@pytest.fixture(scope="module")
def pcm():
    return expected(SECONDS * RATE, RATE, FIR)


@pytest.fixture(scope="module")
def webm(pcm, tmp_path_factory):
    return encode(pcm, tmp_path_factory.mktemp("rec") / "clean.webm")


def passes(pcm, dsp=FIR):
    return content(pcm, RATE, SECONDS, dsp, 0)["passed"]


def test_faithful_recording_passes(webm):
    result = check(webm, RATE, SECONDS, FIR, 0)
    assert result["passed"], result


def test_dual_mono_stereo_keeps_its_level(pcm, tmp_path):
    assert check(encode(np.column_stack([pcm, pcm]), tmp_path / "stereo.webm", 2), RATE, SECONDS, FIR, 0)["passed"]


def test_slow_clock_drift_passes(pcm):
    drifted = np.interp(np.arange(int(len(pcm) * 1.0001)) / 1.0001, np.arange(len(pcm)), pcm)
    result = content(drifted, RATE, SECONDS, FIR, 0)
    assert result["passed"] and abs(result["clockPpm"] - 100) < 20


@pytest.mark.parametrize("defect", ["removed", "inserted silence", "silenced", "truncated", "quiet", "unprocessed"])
def test_defects_fail(pcm, defect):
    cut, n = 2 * RATE, RATE // 10
    damaged = {
        "removed": lambda: np.r_[pcm[:cut], pcm[cut + n:]],
        "inserted silence": lambda: np.r_[pcm[:cut], np.zeros(n), pcm[cut:]],
        "silenced": lambda: np.r_[pcm[:cut], np.zeros(RATE // 50), pcm[cut + RATE // 50:]],
        "truncated": lambda: pcm[:-RATE],
        "quiet": lambda: pcm * 0.1,
        "unprocessed": lambda: expected(SECONDS * RATE, RATE, {"mode": "copy"}),
    }[defect]()
    assert not passes(damaged)


@pytest.mark.parametrize("shift", [0.5, -0.01])
def test_timeline_gap_or_overlap_fails_with_identical_samples(webm, tmp_path, shift):
    shifted = tmp_path / "shifted.webm"
    expression = f"setts=pts='PTS+gte(PTS*TB,2)*({shift})/TB':dts='DTS+gte(DTS*TB,2)*({shift})/TB'"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(webm), "-c:a", "copy", "-bsf:a", expression, str(shifted)],
                   check=True)
    assert np.array_equal(decode(shifted, RATE), decode(webm, RATE))
    assert not timeline(shifted, len(decode(shifted, RATE)) / RATE)["passed"]
