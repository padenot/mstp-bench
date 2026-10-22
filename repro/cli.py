"""Command line: `uv run repro --help`."""
import argparse
import time
from pathlib import Path

from . import analysis, experiments, timestamps, trial


def stalls(text: str) -> list[dict]:
    """"5:100,10:500" → stalls of 100 ms at 5 s and 500 ms at 10 s."""
    if text == "none":
        return []
    return [{"atSeconds": float(at), "durationMs": float(ms)} for at, ms in (s.split(":") for s in text.split(","))]


def main():
    parser = argparse.ArgumentParser(prog="repro", description=__doc__)
    parser.add_argument("--firefox", help="patched Firefox executable (see firefox/README.md)")
    parser.add_argument("--chrome", help="Chrome executable; default: the installed Chrome")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run an experiment and summarize it")
    run.add_argument("experiment", choices=[*experiments.EXPERIMENTS, "timestamps"])
    run.add_argument("--rounds", type=int, default=3)
    run.add_argument("--browsers", default=None, help="comma-separated; default: chrome, plus firefox if --firefox")
    run.add_argument("--out", type=Path)

    summarize = commands.add_parser("summarize", help="re-analyze an experiment directory")
    summarize.add_argument("directory", type=Path)

    one = commands.add_parser("trial", help="run and analyze a single call")
    one.add_argument("--browser", choices=["chrome", "firefox"], required=True)
    one.add_argument("--path", choices=["audioworklet", "worker", "mstp"], required=True)
    one.add_argument("--duration", type=float, default=22)
    one.add_argument("--stalls", type=stalls, default="5:100,10:200,15:500", help='"at:ms,…" or "none"')
    one.add_argument("--fir", type=int, metavar="TAPS", help="FIR filter instead of block copy")
    one.add_argument("--quantum", type=int, default=128)
    one.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "run":
        browsers = args.browsers.split(",") if args.browsers else ["chrome"] + (["firefox"] if args.firefox else [])
        out = args.out or Path("results") / f"{args.experiment}-{time.strftime('%Y%m%d-%H%M%S')}"
        if args.experiment == "timestamps":
            timestamps.run(out, browsers, args.firefox, args.chrome)
        else:
            experiments.run(args.experiment, out, browsers, args.rounds, args.firefox, args.chrome)
    elif args.command == "summarize":
        plan = (args.directory / "plan.json").read_text()
        (timestamps if '"timestamps"' in plan else experiments).summarize(args.directory)
    else:
        dsp = {"mode": "fir", "taps": args.fir, "gain": 0.5} if args.fir else experiments.COPY
        trial.run(args.out, browser=args.browser, path=args.path, duration=args.duration, stalls=args.stalls,
                  dsp=dsp, quantum=args.quantum, firefox=args.firefox, chrome=args.chrome)
        result = analysis.analyze(args.out)
        print(experiments.to_markdown(experiments.summarize_stalls({args.out.name: [result]})))
