"""Run one call: a sender and a receiver browser process on this machine.

Files written to the trial directory:
  trial.json           configuration, browser versions, CPU load, outcome
  sender.json          events, source blocks, processed-output block index
  sender-output.f32    processed samples, as they left the DSP
  sender.webm          MediaRecorder recording of the processed track
  receiver.json        playout block index, output clock, getStats() samples
  receiver-playout.f32 samples received and rendered by the receiver
"""
import json
import time
from pathlib import Path

from . import browsers
from .load import CpuLoad
from .server import Server

LEAD_SECONDS = 5  # Setup time before the source starts.

# Which processing paths each browser runs, and how it is isolated.
PATHS = {"chrome": ("audioworklet", "worker", "mstp"), "firefox": ("audioworklet", "worker")}
ISOLATION = {"chrome": "dip", "firefox": "coop-coep", "safari": "coop-coep"}


def run(directory: Path, *, browser: str, path: str, duration: float, stalls: list[dict],
        dsp: dict, quantum: int = 128, load: dict | None = None, realtime: bool = True,
        firefox: str | None = None, chrome: str | None = None) -> dict:
    """Run a trial and return trial.json's content. Raises if the trial is invalid.

    stalls  [{"atSeconds": 5, "durationMs": 500}, ...], after the source starts.
    dsp     {"mode": "copy"} or {"mode": "fir", "taps": 16384, "gain": 0.5}.
    load    {"workers": 64, "atSeconds": 10, "seconds": 20} for stress-ng.
    """
    if path not in PATHS[browser]:
        raise ValueError(f"{browser} does not run the {path} path")
    directory.mkdir(parents=True, exist_ok=False)
    binary = firefox if browser == "firefox" else chrome
    config = {"browser": browser, "path": path, "durationSeconds": duration, "stalls": stalls, "dsp": dsp,
              "quantum": quantum, "realtime": realtime, "isolation": ISOLATION[browser], "load": load}
    trial = {"config": config, "errors": []}
    drivers = {}
    with Server(directory.name, directory, ISOLATION[browser]) as server:
        try:
            # Sender and receiver: same browser, separate processes.
            drivers["sender"] = browsers.launch(browser, binary, realtime)
            drivers["receiver"] = browsers.launch(browser, binary)
            trial["browser"] = browsers.describe(drivers["sender"])
            for driver in drivers.values():
                driver.get(f"{server.url}/call.html?trial={directory.name}")

            config["startWallMs"] = time.time() * 1000 + LEAD_SECONDS * 1000
            offer = call(drivers["sender"], "sender", config)
            answer = call(drivers["receiver"], "receiver", config, offer)
            call(drivers["sender"], "accept", answer)
            cpu = load and CpuLoad(load["workers"], config["startWallMs"] + load["atSeconds"] * 1000, load["seconds"])

            end = config["startWallMs"] / 1000 + duration + 1
            while time.time() < end and not trial["errors"]:
                time.sleep(0.5)
                for role, driver in drivers.items():
                    trial["errors"] += [f"{role}: {e}" for e in driver.execute_script("return trialErrors()")]
            if cpu:
                trial["load"] = cpu.wait()
            # The sender stops first, so the receiver records the end of the stream.
            for role in ("sender", "receiver"):
                trial["errors"] += [f"{role}: {e}" for e in call(drivers[role], "finish")]
        finally:
            for driver in drivers.values():
                driver.quit()
            (directory / "trial.json").write_text(json.dumps(trial, indent=2))
    if trial["errors"]:
        raise RuntimeError(f"{directory}: {trial['errors']}")
    return trial


def call(driver, function: str, *args):
    """Await `window[function](...args)` in the page; page exceptions are raised here."""
    result = driver.execute_async_script("""
        const done = arguments[arguments.length - 1];
        window[arguments[0]](...Array.from(arguments).slice(1, -1))
          .then(value => done({ value }), error => done({ error: String(error.stack ?? error) }));
    """, function, *args)
    if "error" in result:
        raise RuntimeError(f"{function}: {result['error']}")
    return result.get("value")
