## CPU contention

{{ conditions("contention") }}

The processing runs a 16384-tap FIR filter (that's a lot of taps), an eighth to
a third of real time on this machine (Macbook pro M4 Max), while 64 `stress-ng`
workers hammer every core for 20 s. Processing that loses the CPU falls behind:
backlog and latency grow, and audio can be lost. This simulates either a machine
that isn't fast enough (on the older/cheaper side), or a machine that is doing
something heavy at the same time.

{{ results("contention") }}

\* Control, not production code: the test-only environment variable `MOZ_DISABLE_SINKLESS_RT=1` makes Firefox render the sinkless `AudioContext` on a normal-priority thread instead of a real-time one. Compared with the real-time `audioworklet` row, it shows that real-time priority helps keeping processing on time under heavy load.

### Columns

- **Phase.** Before the load, during it (from 1 s after it starts), and after it
  (from 2 s after it ends).
- **Recorded audio intact.** As in [Stalls](#stalls).
- **Backlog p95.** Source audio generated but not yet out of the processing,
  95th percentile per phase.
- **DSP ms per audio s.** Wall-clock time spent in the filter per second of
  audio. Above 1000 would be above our real-time budget. This is wall clock, so
  it ticks while a processing thread is preempted.
- **Source → playback p50.** Median time from generation to the receiver’s
  output device, per phase.
- **Jitter buffer target.** Median `jitterBufferTargetDelay` per phase: the
  delay the receiver aims for.
- **Concealed under load.** Audio the receiver synthesized using its jitter
  buffer during the load because packets arrived too late (`concealedSamples`).

### Failures and likely causes

**Firefox `audioworklet` control\*: 37 ms lost in one trial.** With real-time
promotion disabled, the sinkless graph is starved during the load. Firefox’s
cross-graph drift correction then
[underruns](https://searchfox.org/mozilla-central/source/dom/media/driftcontrol/AudioDriftCorrection.cpp#99)
and, when input catches up, [discards input above its desired
buffering](https://searchfox.org/mozilla-central/source/dom/media/driftcontrol/DynamicResampler.cpp#69):
a 37 ms skip 6.9 s into the load. The real-time configuration shows no such
event.

**Firefox `worker`: preempted under load.** All audio is recorded, but backlog,
latency and concealment grow during the load, and the filter takes longer per
block. Thread priority doesn’t explain it: on macOS 26 both browsers run the
worker at `QOS_CLASS_USER_INITIATED`
([Firefox](https://searchfox.org/mozilla-central/source/xpcom/threads/nsThread.cpp#404),
[Chrome](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/base/threading/platform_thread_apple.mm#288)).
The cause is not identified yet.

### Safari

Needs `AudioContextOptions` `{sinkId: "none"}`. As the control shows, rendering
it on a real-time thread matters under load.
