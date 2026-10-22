"""Timestamp alignment: audio recorded in a worker, gated by timestamped video.

The video worker's clock starts at an arbitrary origin and runs at −200, 0 or
+200 ppm relative to the page. Each audio sample is multiplied by the gain of
the video frame presented at that sample's time (web/workers/recording-worker.js).

Checks:
  content  The recording equals the source × the gain of the true video frame
           at each sample's presentation time, to float precision. Two
           negative controls confirm the check would catch timing by
           processing time, or no gating.
  timing   At every video frame change in the recording, the source sample's
           generation time minus the frame's true start: constant if audio
           and video stay aligned through stalls and drift.
"""
import json
import time
from pathlib import Path
from statistics import median

import numpy as np
from scipy.io import wavfile

from . import browsers
from .experiments import to_markdown
from .server import Server
from .signal import source
from .trial import ISOLATION, LEAD_SECONDS, call

DURATION = 22
STALLS = [{"atSeconds": 5, "durationMs": 100}, {"atSeconds": 10, "durationMs": 200}, {"atSeconds": 15, "durationMs": 500}]
PATH = {"chrome": "mstp", "firefox": "worker", "safari": "worker"}
PPM = (200, 0, -200)


def run(out: Path, browser_names: list[str], firefox: str | None, chrome: str | None):
    out.mkdir(parents=True)
    plan = {"experiment": "timestamps", "durationSeconds": DURATION, "stalls": STALLS,
            "trials": [{"browser": b, "path": PATH[b], "videoPpm": ppm} for ppm in PPM for b in browser_names]}
    (out / "plan.json").write_text(json.dumps(plan, indent=2))
    for spec in plan["trials"]:
        directory = out / trial_name(spec)
        print(f"{directory.name} ...", flush=True)
        try:
            record(directory, spec, {"firefox": firefox, "chrome": chrome}.get(spec["browser"]))
        except Exception as error:
            print(f"  failed: {error}", flush=True)
    return summarize(out)


def trial_name(spec: dict) -> str:
    return f"{spec['browser']}-{spec['path']}-{spec['videoPpm']}ppm"


def record(directory: Path, spec: dict, binary: str | None):
    directory.mkdir()
    config = {**spec, "durationSeconds": DURATION, "stalls": STALLS}
    meta = {"config": config, "errors": []}
    with Server(directory.name, directory, ISOLATION[spec["browser"]]) as server:
        driver = browsers.launch(spec["browser"], binary)
        try:
            meta["browser"] = browsers.describe(driver)
            driver.get(f"{server.url}/timestamps.html?trial={directory.name}")
            if spec["browser"] == "safari":
                # WebKit starts an AudioContext only with transient user activation;
                # safaridriver clicks are trusted input.
                driver.find_element("css selector", "html").click()
            config["startWallMs"] = time.time() * 1000 + LEAD_SECONDS * 1000
            call(driver, "record", config)
            while time.time() < config["startWallMs"] / 1000 + DURATION and not meta["errors"]:
                time.sleep(0.5)
                meta["errors"] = driver.execute_script("return trialErrors()")
            meta["errors"] += call(driver, "finish")
        finally:
            driver.quit()
            (directory / "trial.json").write_text(json.dumps(meta, indent=2))
    if meta["errors"]:
        raise RuntimeError(meta["errors"])


def validate(directory: Path) -> dict:
    page = json.loads((directory / "page.json").read_text())
    worker = json.loads((directory / "worker.json").read_text())
    rate, pcm = wavfile.read(directory / "recording.wav")
    config, origin = page["config"], page["pageOrigin"]
    assert rate == page["rate"] and pcm.dtype == np.float32 and pcm.ndim == 1 and len(pcm) == worker["frames"]

    # The source starts with a nonzero sample; silence before it is setup.
    prefix = int(np.flatnonzero(pcm)[0])
    assert len(pcm) - prefix >= (DURATION - 0.15) * rate, "Recording is shorter than the source"
    ungated = np.zeros(len(pcm))
    ungated[prefix:] = source(len(pcm) - prefix, rate)

    truth = np.array([v["pageMs"] for v in page["videoTruth"]])
    assert len(worker["video"]) <= len(truth)
    video_clock_error = max(abs(v["start"] - truth[v["index"]]) for v in worker["video"])

    def gated(times):
        frame = np.searchsorted(truth, times, side="right") - 1
        return ungated * np.where(frame < 0, 1, np.where(frame % 2, 0.75, 0.25))

    # Presentation time of every sample, as the worker computed it (never decreasing).
    times = np.maximum.accumulate(np.concatenate(
        [b["timeMs"] + np.arange(b["count"]) * b["msPerUnit"] for b in worker["blocks"]]))
    expected = gated(times)
    error = float(np.max(np.abs(pcm - expected)))
    # Negative controls: gating by when a block was processed, or not at all.
    arrival = np.concatenate([b["wallMs"] - origin + np.arange(b["count"]) * 1000 / rate for b in worker["blocks"]])
    assert np.max(np.abs(gated(arrival) - expected)) > 1e-3, "Processing-time control ineffective"
    assert np.max(np.abs(ungated - expected)) > 1e-3, "Ungated control ineffective"

    # Timing at each frame change: source generation time minus true frame start.
    blocks = np.array(page["source_blocks"])
    offsets = []
    for change in worker["transitions"]:
        frame = change["frame"] - prefix
        if frame < rate:  # Skip the first second.
            continue
        i = np.searchsorted(blocks[:, 0], frame, side="right") - 1
        generated = blocks[i, 2] - origin + (frame - blocks[i, 0]) * 1000 / rate
        offsets.append((generated, generated - truth[change["videoIndex"]]))
    stalls = [e for e in page["events"] if e["type"] == "stall_start"]
    windows = [(s["wallMs"] - origin, s["wallMs"] - origin + s["durationMs"] + 1000) for s in stalls]
    baseline = median(o for t, o in offsets if not any(a <= t <= b for a, b in windows))
    values = np.array([o for _, o in offsets])
    result = {
        "config": config, "rate": rate, "samples": len(pcm),
        "contentPassed": error <= 2e-7, "maxSampleError": error, "videoClockMaxErrorMs": video_clock_error,
        "medianOffsetMs": float(np.median(values)),
        "p95DeviationMs": float(np.percentile(np.abs(values - np.median(values)), 95)),
        "maxStallDeviationMs": max(abs(o - baseline) for t, o in offsets if any(a <= t <= b for a, b in windows)),
        "frameChanges": len(offsets),
    }
    (directory / "analysis.json").write_text(json.dumps(result, indent=2, default=lambda v: v.item()))
    return result


def summarize(out: Path) -> dict:
    rows = {}
    for directory in sorted(p for p in out.iterdir() if p.is_dir()):
        try:
            r = validate(directory)
            rows[directory.name] = {
                "Audio exact": "yes" if r["contentPassed"] else f"no ({r['maxSampleError']:.2g})",
                "Median offset, ms": f"{r['medianOffsetMs']:.1f}",
                "p95 deviation, ms": f"{r['p95DeviationMs']:.1f}",
                "Max deviation around stalls, ms": f"{r['maxStallDeviationMs']:.1f}",
            }
        except Exception as error:
            rows[directory.name] = {"Audio exact": f"failed: {error}", "Median offset, ms": "–",
                                    "p95 deviation, ms": "–", "Max deviation around stalls, ms": "–"}
    markdown = to_markdown(rows)
    (out / "summary.json").write_text(json.dumps(rows, indent=2))
    (out / "summary.md").write_text(markdown)
    print(markdown)
    return rows
