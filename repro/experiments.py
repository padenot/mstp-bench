"""The experiments: which trials to run, and how to summarize them.

  stalls      22 s calls; 100, 200 and 500 ms processing stalls at 5, 10 and
              15 s; block copy. Does processed audio survive, and how fast
              does processing catch up?
  playout     60 s calls; one 500 ms stall at 5 s. How long until the
              listener's delay returns to normal?
  contention  40 s calls; 16384-tap FIR; 64 stress-ng workers from 10 to 30 s.
              Does processing keep up when the machine is overloaded?

Trials run in a random order within each round, each in fresh browser processes.
"""
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

from . import analysis, trial

COPY = {"mode": "copy"}
FIR = {"mode": "fir", "taps": 16384, "gain": 0.5}


@dataclass(frozen=True)
class Arm:
    browser: str
    path: str
    quantum: int = 128
    realtime: bool = True  # Firefox sinkless rendering on a real-time thread.

    @property
    def label(self):
        return f"{self.browser}-{self.path}-{self.quantum}" + ("" if self.realtime else "-no-rt")


ARMS = [Arm("firefox", "audioworklet"), Arm("firefox", "audioworklet", 512), Arm("firefox", "worker"),
        Arm("chrome", "audioworklet"), Arm("chrome", "audioworklet", 512), Arm("chrome", "worker"), Arm("chrome", "mstp")]

EXPERIMENTS = {
    "stalls": {"arms": ARMS, "duration": 22, "dsp": COPY, "load": None,
               "stalls": [{"atSeconds": 5, "durationMs": 100}, {"atSeconds": 10, "durationMs": 200},
                          {"atSeconds": 15, "durationMs": 500}]},
    "playout": {"arms": ARMS, "duration": 60, "dsp": COPY, "load": None,
                "stalls": [{"atSeconds": 5, "durationMs": 500}]},
    "contention": {"arms": [a for a in ARMS if a.quantum == 128] + [Arm("firefox", "audioworklet", realtime=False)],
                   "duration": 40, "dsp": FIR, "stalls": [], "load": {"workers": 64, "atSeconds": 10, "seconds": 20}},
}


def run(name: str, out: Path, browsers: list[str], rounds: int, firefox: str | None, chrome: str | None) -> dict:
    spec = EXPERIMENTS[name]
    arms = [a for a in spec["arms"] if a.browser in browsers]
    out.mkdir(parents=True)
    plan = {"experiment": name, "rounds": rounds, "arms": [asdict(a) for a in arms],
            **{k: v for k, v in spec.items() if k != "arms"}}
    (out / "plan.json").write_text(json.dumps(plan, indent=2))
    order = random.Random(20261022)
    for round_ in range(1, rounds + 1):
        for arm in order.sample(arms, len(arms)):
            directory = out / f"r{round_}-{arm.label}"
            print(f"{directory.name} ...", flush=True)
            try:
                trial.run(directory, browser=arm.browser, path=arm.path, quantum=arm.quantum, realtime=arm.realtime,
                          duration=spec["duration"], stalls=spec["stalls"], dsp=spec["dsp"], load=spec["load"],
                          firefox=firefox, chrome=chrome)
            except Exception as error:  # Keep going; the failure is reported in the summary.
                print(f"  failed: {error}", flush=True)
            time.sleep(2)  # Let the previous processes exit.
    return summarize(out)


def summarize(out: Path) -> dict:
    """Analyze every trial in `out` and write summary.json and summary.md."""
    plan = json.loads((out / "plan.json").read_text())
    groups: dict[str, list] = {Arm(**a).label: [] for a in plan["arms"]}
    for directory in sorted(p for p in out.iterdir() if p.is_dir()):
        label = directory.name.split("-", 1)[1]
        try:
            groups[label].append(analysis.analyze(directory))
        except Exception as error:
            groups[label].append({"failed": f"{type(error).__name__}: {error}", "directory": directory.name})
    table = SUMMARIES[plan["experiment"]](groups)
    (out / "summary.json").write_text(json.dumps({"plan": plan, "rows": table}, indent=2))
    markdown = to_markdown(table)
    (out / "summary.md").write_text(markdown)
    if plan["experiment"] == "playout":
        plot_playout(groups, out / "playout.svg")
    print(markdown)
    return table


# --- Per-experiment summaries. Each returns {arm label: {column: value}}. ---

def _span(values, digits=0):
    values = [v for v in values if v is not None]
    if not values:
        return "–"
    lo, hi = round(min(values), digits), round(max(values), digits)
    return f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"


def _count(trials, test):
    return f"{sum(1 for t in trials if 'failed' not in t and test(t))}/{len(trials)}"


def _failed(trials):
    return [t for t in trials if "failed" in t]


def _ok(trials):
    return [t for t in trials if "failed" not in t]


def _playout_before(t):
    """Median source → playback delay before the first stall."""
    stalls = t["config"]["stalls"]
    until = t["config"]["startWallMs"] + stalls[0]["atSeconds"] * 1000 if stalls else float("inf")
    ages = [w["sourceAgeMs"] for w in t["playout"] if w["accepted"] and w["wallMs"] < until]
    return median(ages) if ages else None


def summarize_stalls(groups):
    rows = {}
    for label, trials in groups.items():
        ok = _ok(trials)
        def catch_up(t):
            """Sustained return to normal backlog after the last (longest) stall."""
            if not t["backlog"]["stalls"]:
                return "–"
            ms = t["backlog"]["stalls"][-1]["recovery"]["1Batches"]["sustainedMs"]
            return "never" if ms is None else f"{ms:.0f}"
        rows[label] = {
            "Recorded audio intact": _count(trials, lambda t: t["recording"]["content"]["passed"]),
            "Recording timeline intact": _count(trials, lambda t: t["recording"]["timeline"]["passed"]),
            "Catch-up after 500 ms stall, ms": ", ".join(catch_up(t) for t in ok),
            "Backlog before stalls (p95), ms": _span([t["backlog"]["baselineP95Ms"] for t in ok]),
            "Source → playback before stalls, ms": _span([_playout_before(t) for t in ok]),
            "Failed trials": len(_failed(trials)),
        }
    return rows


def summarize_playout(groups):
    rows = {}
    for label, trials in groups.items():
        ok = _ok(trials)

        def final(t, values):
            end = t["config"]["startWallMs"] + (t["config"]["durationSeconds"] - 5) * 1000
            values = [v for wall, v in values if wall >= end and v is not None]
            return median(values) if values else None
        rows[label] = {
            "Source → playback before stall, ms": _span([_playout_before(t) for t in ok]),
            "Peak after stall, ms": _span([max(w["sourceAgeMs"] for w in t["playout"] if w["accepted"]) for t in ok]),
            "Added delay, last 5 s, ms": _span([final(t, [(w["wallMs"], w["sourceAgeMs"]) for w in t["playout"] if w["accepted"]])
                                                - _playout_before(t) for t in ok]),
            "Jitter buffer, last 5 s, ms": _span([final(t, [(i["wallMs"], i["delayMs"]) for i in t["jitterBuffer"]]) for t in ok]),
            "Recorded audio intact": _count(trials, lambda t: t["recording"]["content"]["passed"]),
            "Failed trials": len(_failed(trials)),
        }
    return rows


PHASES = ("before", "load", "after")  # Contention columns: "before / load / after".


def summarize_contention(groups):
    rows = {}
    for label, trials in groups.items():
        ok = _ok(trials)

        def per_phase(metric):
            return " / ".join(_span([metric(t, phase) for t in ok]) for phase in PHASES)

        def in_phase(t, phase, wall):
            lo, hi = t["phases"][phase]["seconds"]
            return t["config"]["startWallMs"] + lo * 1000 <= wall < t["config"]["startWallMs"] + hi * 1000

        def backlog(t, phase):
            values = sorted(p["unprocessedMs"][1] for p in t["backlog"]["points"] if in_phase(t, phase, p["wallMs"]))
            return values[int(0.95 * (len(values) - 1))] if values else None

        def playout(t, phase):
            values = [w["sourceAgeMs"] for w in t["playout"] if w["accepted"] and in_phase(t, phase, w["wallMs"])]
            return median(values) if values else None

        def target(t, phase):
            values = [i["targetMs"] for i in t["jitterBuffer"] if i["targetMs"] is not None and in_phase(t, phase, i["wallMs"])]
            return median(values) if values else None
        rows[label] = {
            "Recorded audio intact": _count(trials, lambda t: t["recording"]["content"]["passed"]),
            "Backlog p95, ms (before / load / after)": per_phase(backlog),
            "DSP ms per audio s": per_phase(lambda t, phase: t["phases"][phase]["dspMsPerSecond"]),
            "Source → playback p50, ms": per_phase(playout),
            "Jitter buffer target, ms": per_phase(target),
            "Concealed under load, ms": _span([sum(i["concealedMs"] or 0 for i in t["jitterBuffer"] if in_phase(t, "load", i["wallMs"]))
                                               for t in ok]),
            "Failed trials": len(_failed(trials)),
        }
    return rows


SUMMARIES = {"stalls": summarize_stalls, "playout": summarize_playout, "contention": summarize_contention}


def to_markdown(rows: dict) -> str:
    columns = list(next(iter(rows.values())))
    lines = ["| Arm | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns)]
    lines += [f"| {label} | " + " | ".join(str(row[c]) for c in columns) + " |" for label, row in rows.items()]
    return "\n".join(lines) + "\n"


def plot_playout(groups, path: Path):
    """Source → playback delay over time, one line per trial, zero at the stall's end."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = list(groups)
    fig, axes = plt.subplots(len(labels), 1, figsize=(9, 1.9 * len(labels)), sharex=True, sharey=True,
                             constrained_layout=True)
    for ax, label in zip(axes, labels):
        for t in _ok(groups[label]):
            end = t["backlog"]["stalls"][0]["endWallMs"]
            points = [w for w in t["playout"] if w["accepted"]]
            ax.plot([(w["wallMs"] - end) / 1000 for w in points], [w["sourceAgeMs"] for w in points],
                    color="#222222", linewidth=0.9, alpha=0.8)
        ax.set_title(label, loc="left", fontsize=10)
        ax.set_ylim(bottom=0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#eeeeee")
    axes[len(labels) // 2].set_ylabel("Source → playback (ms)")
    axes[-1].set_xlabel("Seconds after the 500 ms stall ends")
    fig.savefig(path)
    plt.close(fig)
