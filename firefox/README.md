# Firefox build

The Firefox results need a build with patches that are not all in Nightly yet.

**Builds:** optimized with profile-guided optimization (shippable), from [this try push](https://treeherder.mozilla.org/jobs?repo=try&revision=3d54c42567d6c54f3a8738d0617912ba648253fc). The downloads expire on 2026-11-20.

| Platform | Download |
|---|---|
| Linux x86-64 | [target.tar.xz](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/ISuns0oyQ8Cjk63rYiDE2g/artifacts/public/build/target.tar.xz) |
| Windows x86-64 | [target.zip](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/flWJKG3yR5OiVYr1Ler3rQ/artifacts/public/build/target.zip) |
| macOS, Apple silicon | [target.dmg](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/CqMRZ9csR8CZcz_MPkXTww/artifacts/public/build/target.dmg) |
| macOS, Intel | [target.dmg](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/FGsgPddmQtq39qyo5Fv98w/artifacts/public/build/target.dmg) |

Try builds aren't notarized: on macOS, run `xattr -r -d com.apple.quarantine` on the app after copying it out of the disk image.

## What the patches add

All web-facing changes implement the Web Audio API and Media Capture specifications.

- `AudioContext` options `renderSizeHint` / `renderQuantumSize` (non-128-frame render quanta) and `latencyHint`.
- `AudioContext.setSinkId()` and `sinkId: { type: "none" }`: sinkless contexts render on a dedicated graph that catches up after a stall, with bounded cross-graph buffering.
- `getOutputTimestamp()` returns the current time as `performanceTime`.
- `Atomics.wait` throws in worklets.
- Microphone tracks are created in the graph of their first consumer.
- A pending worker idle GC is cancelled when the worker resumes work.
- `MOZ_DISABLE_SINKLESS_RT=1`, an environment variable used only by the contention experiment: render sinkless contexts on a normal-priority thread.

## Building

`./mach build` with this mozconfig (optimized, not debug):

```
ac_add_options --enable-optimize
ac_add_options --disable-debug
```

Pass the resulting executable to the harness, for example on macOS:

```
uv run repro --firefox obj-…/dist/Nightly.app/Contents/MacOS/firefox run stalls
```
