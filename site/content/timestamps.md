## Timestamp alignment

{{ conditions("timestamps") }}

A worker records audio while an independently clocked video source plays, as a
recorder or a video call would. Each sample is multiplied by the gain of the
video frame shown at its presentation time. The video clock runs 200 ppm fast,
exactly on time, or 200 ppm slow, and the processing stalls three times. Audio
and video stay aligned if every audio frame lands under the right video frame
and the offset between them stays constant.

{{ results("timestamps") }}

### Columns

- **Video clock.** The video source’s clock rate relative to the page.
- **Audio exact.** The recording equals the source times the gain of the true
  frame at each sample’s presentation time, to float precision. Two negative
  controls confirm the check catches timing by processing time, and no gating.
- **Median offset.** At each frame change in the recording: the source sample’s
  generation time minus the frame’s true start, median over the call. A constant
  offset can be calibrated; deviations from it can’t.
- **p95 deviation.** 95th percentile of the distance from the median offset.
- **Max deviation around stalls.** Largest distance from the offset measured
  outside stalls, from each stall’s start to 1 s after its end.

### Failures and likely causes

None: every arm records the audio exactly and stays within about 4 ms of its offset.

**Different median offsets.** Not a failure: each engine puts presentation at a
different point. The patched Firefox’s `getOutputTimestamp()` places a frame
when it reaches the output device, after the [output
latency](https://searchfox.org/mozilla-central/source/third_party/rust/cubeb-coreaudio/src/backend/mod.rs#764)
reported by the audio backend. That latency is read once per stream and includes
a sampled timing gap, so Firefox’s offset varies between runs. WebKit [stamps
frames at render
time](https://searchfox.org/wubkat/source/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#230),
and Chrome’s `mstp` path uses `AudioData` timestamps taken at render time
([Stalls](#stalls)), so both sit near zero.

### Safari

Runs today. WebKit starts an `AudioContext` only with [transient user
activation](https://searchfox.org/wubkat/source/Source/WebCore/Modules/webaudio/AudioContext.cpp#93),
so the harness clicks the page before recording, and this is fine. On this test,
Safari has the best performance of the three, as shown by the tightest
deviation.
