## Running

Requirements:

- `uv` for python
- Chrome 
- An `ffmpeg` binary
- A `stress-ng` binary for contention
- A [patched Firefox](https://github.com/padenot/mstp-bench/blob/main/firefox/README.md), and soon a Nightly/Release Firefox, patches are being reviewed. Optimized builds: [Linux](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/ISuns0oyQ8Cjk63rYiDE2g/artifacts/public/build/target.tar.xz), [Windows](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/flWJKG3yR5OiVYr1Ler3rQ/artifacts/public/build/target.zip), [macOS, Apple silicon](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/CqMRZ9csR8CZcz_MPkXTww/artifacts/public/build/target.dmg), [macOS, Intel](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/FGsgPddmQtq39qyo5Fv98w/artifacts/public/build/target.dmg), until 2026-11-20.
- Safari for `timestamps` only

For Safari, running `sudo safaridriver --enable` and `Develop -> Allow Remote
Automation` in the Preferences are necessary to enable remote control and remove
human errors from the equation.

This framework uses browser automation to be able to reliably reproduces
results.

Comments after the command show rough durations to run all tests a few times and
regenerated the data (e.g. after patching or another machine). Running in
parallel probably degrades the data quality in some cases, and we've preferred
running everything linearly.

```
uv run repro trial --browser chrome --path mstp --out results/first   # One call, analyzed.
uv run repro --firefox /path/to/firefox run stalls                     # 18 min
uv run repro --firefox /path/to/firefox run playout                    # 65 min
uv run repro --firefox /path/to/firefox run contention                 # 30 min
uv run repro --firefox /path/to/firefox run timestamps --browsers chrome,firefox,safari
uv run --group dev pytest                                              # Analysis tests.
uv run python tools/build_site.py                                      # This page.
```

Output: `results/<experiment>-<time>/`. `uv run repro summarize <directory>`
re-analyzes.
