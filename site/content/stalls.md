## Stalls

{{ conditions("stalls") }}

The processing stalls three times by busy-waiting where the processing runs
(`MediaStreamTrackProcessor`, `AudioWorkletProcessor`, etc.). This simulates a
slow plugin / processing pass, garbage collection pauses, heavy GPU processing
would. During this time the source keeps producing audio. Real-time processing
has to keep every sample, and to keep the recording’s timeline intact. It needs
to catch up once it resumes, so that latency returns to where it was.

{{ results("stalls") }}

### Columns

- **Render quantum.** Frames per AudioWorklet `process()` call in the processing
  context.
- **Recorded audio intact.** Trials whose MediaRecorder file (point 3) contains
  every 10 ms of the expected processed signal, in order and at the right level,
  after Opus.
- **Recording timeline intact.** Trials whose WebM packet timestamps are
  contiguous within 2.1 ms, and whose container duration is within 40 ms of the
  decoded audio. Samples can be intact while their timestamps are not; players
  and editors then place them at the wrong time.
- **Catch-up after 500 ms stall.** Per trial: time from the end of the 500 ms
  stall until the backlog is back under its pre-stall p95 plus one source batch,
  and stays there for 500 ms. “never”: not within the call.
- **Backlog before stalls.** Source audio generated (point 1) but not yet out of
  the processing (point 2), 95th percentile before the first stall: the path’s
  steady-state buffering.
- **Source → playback before stalls.** Median time from generation (point 1) to
  the receiver’s output device (point 4), before the first stall. Includes
  WebRTC and the receiver’s jitter buffer.

### Failures and likely causes

From Chrome 156.0.8078.47 source.

**Chrome `audioworklet`, 128 and 512 frames: audio lost, no catch-up.** Chrome
renders a sinkless `AudioContext` into a
[`NullAudioSink`](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/content/renderer/media/renderer_webaudiodevice_impl.cc#114),
clocked in [10 ms
steps](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/content/renderer/media/renderer_webaudiodevice_impl.cc#81).
The stall blocks that render callback. The track feeding the context waits in a
FIFO [sized for six
reads](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/third_party/blink/renderer/modules/mediastream/webaudio_media_stream_audio_sink.cc#101),
about 60 ms here, and audio arriving once it is full is
[dropped](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/third_party/blink/renderer/modules/mediastream/webaudio_media_stream_audio_sink.cc#151).
When the callback returns, the clock [skips to the next on-time
interval](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/media/base/fake_audio_worker.cc#184)
instead of rendering the time it missed, so the context never runs faster than
real time and the backlog never drains. The render quantum doesn’t change this.

**Chrome `worker`: no catch-up, timeline broken.** The ring reader waits for the
worker inside the sinkless context’s render callback, which blocks it for the
stall. No audio is lost: the 2 s SharedArrayBuffer rings hold it. The clock then
[skips the intervals it
missed](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/media/base/fake_audio_worker.cc#184),
so the backlog stays in the output ring for the rest of the call. The processed
track is stamped with [the current time at each
render](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/third_party/blink/renderer/platform/mediastream/webaudio_media_stream_source.cc#89),
so after each stall its timestamps jump ahead while the samples continue: 78,
103 and 293 ms in the first trial, for the 100, 200 and 500 ms stalls.

**Every Chrome path, including `mstp`: timeline jitter.**
`MediaStreamAudioDestinationNode` stamps audio with [`base::TimeTicks::Now()` at
render
time](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/third_party/blink/renderer/platform/mediastream/webaudio_media_stream_source.cc#89),
with a TODO to use the playout time. MediaRecorder’s Opus encoder derives packet
timestamps [from those capture times, not from a sample
count](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/third_party/blink/renderer/modules/mediarecorder/audio_track_opus_encoder.cc#205).
Render callbacks aren’t evenly spaced, so packet timestamps jitter by ±3 ms
throughout every Chrome recording, against a 2.1 ms limit. MSTG passes the
source’s `AudioData` timestamps through [as capture
times](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/third_party/blink/renderer/modules/breakout_box/media_stream_audio_track_underlying_sink.cc#121),
so `mstp` inherits the source track’s jitter. In one trial the first packet is
also stamped about 640 ms ahead of the next ones; the muxer [forces later
packets up to
it](https://chromium.googlesource.com/chromium/src/+/refs/tags/156.0.8078.47/media/muxers/muxer_timestamp_adapter.cc#170),
so 11 packets share timestamp 0.

### Safari

Needs a sinkless `AudioContext` for both web standards paths, and
`renderSizeHint` for the 512-frame variant (See [Safari](#safari)).
