## Receiver playback

{{ conditions("playout") }}

One 500 ms stall in a 60 s call. Its backlog manifests on the other end as extra
delay. We follow that delay at the receiver's output for the rest of the call,
and split it between the sender's processing and the receiver's jitter buffer,
to see where the audio waits and whether it drains, with things like a jitter
buffer's compression strategy.

{{ results("playout") }}

### Columns

- **Source → playback before stall.** Median time from generation (point 1) to
  the receiver’s output device (point 4), before the stall.
- **Peak after stall.** Largest source → playback delay after the stall.
- **Added delay, last 5 s.** Median source → playback delay over the last 5 s of
  the call, minus its value before the stall: the delay the call keeps.
- **Jitter buffer, last 5 s.** Median receiver jitter buffer delay over the last
  5 s (point 5): `jitterBufferDelay` per emitted sample, from `getStats()`.
- **Recorded audio intact.** As in [Stalls](#stalls).

### Failures and likely causes

**Chrome `worker`: delay kept at the sender.** Its added delay is not in the
jitter buffer. The backlog stays in the sender’s output ring for the rest of the
call, because Chrome’s sinkless context doesn’t render the time it missed
([Stalls](#stalls)).

**Chrome `audioworklet`, 128 and 512 frames: audio lost.** Less delay is added
because the stall’s audio is dropped at the sender instead of delivered late
([Stalls](#stalls)).

**Every other path: delay kept at the receiver.** The stall’s audio reaches the
receiver as a burst, about 500 ms late, and its jitter buffer keeps it.
libwebrtc’s NetEq, in both browsers, accelerates only when playout delay exceeds
its target plus [the largest packet arrival
delay](https://searchfox.org/mozilla-central/source/third_party/libwebrtc/modules/audio_coding/neteq/decision_logic.cc#271)
of the [last 2
s](https://searchfox.org/mozilla-central/source/third_party/libwebrtc/modules/audio_coding/neteq/decision_logic.cc#38),
so it plays normally until the burst ages out of that window. After that, each
accelerate removes one pitch period, and only when the cut [passes a 0.9
correlation
test](https://searchfox.org/mozilla-central/source/third_party/libwebrtc/modules/audio_coding/neteq/accelerate.cc#60).
Fast accelerate is [off by
default](https://searchfox.org/mozilla-central/source/third_party/libwebrtc/api/neteq/neteq.h#138).
The delay drains slowly, at a rate that depends on the signal.

### Safari

Needs a sinkless `AudioContext` (`sinkId: "none"`) for both web standards paths.

The other bits needed for this tests are already implemented in WebKit:
`getOutputTimestamp()` and the jitter buffer counters (see
[Safari](#safari)).
