"""Check a MediaRecorder recording of the processed track.

Content: every 10 ms of the expected processed signal must be present, in
order, at the right level, through Opus. Missing, repeated, unprocessed or
wrongly timed audio fails.

Timeline: container packet timestamps must be contiguous and match the
decoded duration. A recording can contain the right samples and still have a
broken timeline.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

from .matching import WINDOW_MS, bandpass, frames, match
from .signal import expected

# Tolerances for lossy audio, per 10 ms section, after up to ±0.25 ms of
# realignment: normalized squared error, and RMS level relative to expected.
MAX_ERROR = 0.12
LEVEL = (0.65, 1.35)
# The recording's clock may drift from the source's (resamplers, drift
# correction), but only slowly and without jumps.
MAX_STEP_MS = 1
MAX_LOCAL_PPM = 2500
MAX_PPM = 2000


def decode(path: Path, rate: int) -> np.ndarray:
    channels = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels", "-of", "json",
         str(path)], check=True, capture_output=True, text=True).stdout)["streams"][0]["channels"]
    # Downmix as Web Audio does, (L + R) / 2. FFmpeg's default mono mix scales
    # by 1/sqrt(2) per channel, which would fail the level check on dual mono.
    mix = "pan=mono|c0=c0" if channels == 1 else "pan=mono|c0=0.5*c0+0.5*c1"
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-af", mix, "-ar", str(rate),
                          "-f", "f32le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(pcm, dtype="<f4").astype(np.float64)


def timeline(path: Path, decoded_seconds: float) -> dict:
    packets = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "packet=pts_time,duration_time",
         "-of", "json", str(path)], check=True, capture_output=True, text=True).stdout).get("packets", [])
    if not packets or any("pts_time" not in p or "duration_time" not in p for p in packets):
        return {"passed": False, "violations": ["Missing packet timestamps or durations"]}
    pts = np.array([float(p["pts_time"]) for p in packets])
    durations = np.array([float(p["duration_time"]) for p in packets])
    gaps = np.diff(pts) - durations[:-1]
    span = pts[-1] + durations[-1] - pts[0]
    violations = []
    # WebM timestamps have 1 ms precision: allow two ticks.
    if np.any(np.abs(gaps) > 0.0021):
        violations.append("Packet gap or overlap above 2.1 ms")
    # Opus pre-skip and end trimming account for less than two 20 ms packets.
    if abs(span - decoded_seconds) > 0.04:
        violations.append("Container duration and decoded duration differ by more than 40 ms")
    return {"passed": not violations, "violations": violations, "packets": len(packets),
            "maxGapMs": float(max(0, gaps.max(initial=0)) * 1000),
            "maxOverlapMs": float(max(0, -gaps.min(initial=0)) * 1000),
            "durationDifferenceMs": float(abs(span - decoded_seconds) * 1000)}


def content(pcm: np.ndarray, rate: int, duration: float, dsp: dict, prefix: float) -> dict:
    """`prefix`: approximate decoded frame of source frame 0 (recording started earlier)."""
    reference = expected(int((duration + 3) * rate), rate, dsp)
    template, received = bandpass(reference, rate), bandpass(pcm, rate)
    n = frames(WINDOW_MS, rate)

    # 1. Anchors: where source positions are, every 200 ms and near both ends.
    anchors = []
    for center in np.unique(np.r_[0.15, np.arange(0.5, duration - 0.2, 0.2), duration - 0.15]) * rate:
        offset = int(prefix + center - n // 2)
        if 0 <= offset and offset + n <= len(received):
            m = match(template, received[offset:offset + n], center - 2 * rate, center + 2 * rate, rate)
            if m.accepted:
                anchors.append((m.center, offset + n // 2))
    if len(anchors) < 10:
        return {"passed": False, "violations": ["Insufficient identifiable content"], "anchors": len(anchors)}

    # 2. The recording's clock relative to the source: no jumps, bounded drift.
    x, y = np.array(anchors).T
    slope, intercept = np.polyfit(x, y, 1)
    steps_ms = (np.diff(x) - np.diff(y) / slope) * 1000 / rate
    local_ppm = (np.diff(y) / np.diff(x) - 1) * 1e6
    violations = []
    if np.max(np.abs(steps_ms)) > MAX_STEP_MS:
        violations.append(f"Source position jumps by more than {MAX_STEP_MS} ms")
    if np.any(np.diff(x) <= 0) or np.max(np.abs(local_ppm)) > MAX_LOCAL_PPM:
        violations.append(f"Local clock rate differs by more than {MAX_LOCAL_PPM} ppm")
    if abs(slope - 1) * 1e6 > MAX_PPM:
        violations.append(f"Clock rate differs by more than {MAX_PPM} ppm")

    # 3. Every 10 ms section, every 5 ms, at the mapped position. Beyond the
    #    first and last anchors, extrapolate at the local rate.
    rates = np.diff(y) / np.diff(x)
    def position(source_frames):
        source_frames = np.asarray(source_frames, dtype=np.float64)
        mapped = np.interp(source_frames, x, y)
        mapped = np.where(source_frames < x[0], y[0] + (source_frames - x[0]) * rates[0], mapped)
        return np.where(source_frames > x[-1], y[-1] + (source_frames - x[-1]) * rates[-1], mapped)
    start, end = int(0.1 * rate), int((duration - 0.1) * rate)
    first, last = position([start, end])
    if first < 0 or last > len(received):
        violations.append("Recording does not cover the whole source interval")
    section, hop = frames(10, rate), frames(5, rate)
    grid = np.arange(len(received), dtype=np.float64)
    failed, checked = [], 0
    for frame in range(start, end - section + 1, hop):
        mapped = position(frame + np.arange(section))
        target = template[frame:frame + section]
        energy = float(np.dot(target, target))
        if energy < 1e-9:
            continue
        checked += 1
        if mapped[0] < 0 or mapped[-1] >= len(received):
            failed.append({"sourceMs": frame * 1000 / rate, "reason": "missing"})
            continue
        # Up to ±10 frames (about 0.25 ms) of realignment for codec phase.
        error, level = min(
            (float(np.dot(a - target, a - target) / energy), float(np.sqrt(np.dot(a, a) / energy)))
            for a in (np.interp(mapped + shift, grid, received) for shift in range(-10, 11, 2)))
        if error > MAX_ERROR or not LEVEL[0] <= level <= LEVEL[1]:
            failed.append({"sourceMs": frame * 1000 / rate, "error": error, "level": level})
    if failed:
        violations.append(f"{len(failed)} of {checked} 10 ms sections differ from the expected audio")
    return {"passed": not violations, "violations": violations, "anchors": len(anchors), "sections": checked,
            "clockPpm": float((slope - 1) * 1e6), "maxLocalPpm": float(np.max(np.abs(local_ppm))),
            "maxStepMs": float(np.max(np.abs(steps_ms))), "failedSections": failed[:50]}


def check(path: Path, rate: int, duration: float, dsp: dict, prefix: float) -> dict:
    pcm = decode(path, rate)
    result = {"content": content(pcm, rate, duration, dsp, prefix), "timeline": timeline(path, len(pcm) / rate)}
    result["passed"] = result["content"]["passed"] and result["timeline"]["passed"]
    return result
