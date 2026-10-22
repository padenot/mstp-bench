"""External CPU load with stress-ng, started and stopped at fixed trial times."""
import subprocess
import threading
import time


class CpuLoad:
    """Run `stress-ng --cpu <workers>` from `start_ms` (Unix epoch, ms) for `seconds`."""

    def __init__(self, workers: int, start_ms: float, seconds: float):
        self.command = ["stress-ng", "--cpu", str(workers), "--cpu-method", "int64",
                        "--timeout", f"{seconds}s", "--quiet"]
        self.record = {"command": self.command, "requestedStartMs": start_ms, "requestedSeconds": seconds}
        self.thread = threading.Thread(target=self._run, args=(start_ms,), daemon=True)
        self.thread.start()

    def _run(self, start_ms):
        time.sleep(max(0, start_ms / 1000 - time.time()))
        self.record["startMs"] = time.time() * 1000
        result = subprocess.run(self.command, capture_output=True, text=True)
        self.record.update(endMs=time.time() * 1000, exitCode=result.returncode, stderr=result.stderr[-2000:])

    def wait(self) -> dict:
        self.thread.join()
        if self.record["exitCode"] != 0:
            raise RuntimeError(f"stress-ng failed: {self.record['stderr']}")
        return self.record
