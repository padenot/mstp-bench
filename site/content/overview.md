## Architecture

The source can be any MediaStream, such as a microphone, a media element playing, a remote track, etc.. Here it is a generated test signal.

### Web standards

AudioWorklet, sinkless `AudioContext` (`sinkId: { type: "none" }`), `SharedArrayBuffer`. This can run in Firefox and Chrome (but not Safari just yet, see the [Safari](#safari) section for a complete list of missing APIs).

Variant 1: `audioworklet`: the processing runs in an `AudioWorkletProcessor`, not associated with an audio device (`{sinkID: "none"}`).

{{ diagram("audioworklet") }}

Variant 2: `worker`: the processing runs in a dedicated worker: `AudioWorkletProcessor`
moves the audio through a `SharedArrayBuffer` buffer (classical SPSC design,
ubiquitous: [Chrome's
solution](https://developer.chrome.com/blog/audio-worklet-design-pattern),
[Firefox's solution](https://github.com/padenot/ringbuf.js/)). This is useful
when using APIs that are best used on a Web Worker. Note that DIP is going to
ship very soon, so `SharedArrayBuffer` is fine again (finally after 8 years!)

{{ diagram("worker") }}

Variant 3, the classic with a twist: the same sinkless `AudioContext` as variant 1,
whose `AudioWorkletProcessor`s move audio to a dedicated worker and back, with
`postMessage` or a ring buffer. The processing can use any worker API.
`postMessage` needs no `SharedArrayBuffer`, but Shared memory is back on the
menu, and might be preferable.

{{ diagram("message") }}

### MSTP/G

`mstp`: MediaStreamTrackProcessor and MediaStreamTrackGenerator, with the
processing in a dedicated worker. Chrome only.

{{ diagram("mstp") }}

## Scenario

Two browsers on the same machine (to easily reproduce) are in a WebRTC
call (or at least, one sends and one receive, it doesn't have to be duplex). The
sender monitors its input (sends it to an audio output device). It also
processes it using a type of processing that is **not** real-time safe: running
this in the `AudioWorkletProcessor` on the `AudioContext` that is used for
monitoring would glitch. The processed audio is then sent it to the receiver,
which plays it (or does something e.g. mixes it, saves it, whatever). The sender
also records the processed audio locally, as apps sometimes do for safety
(sometimes called "local record" in podcasting apps).

Any 80 ms of the test signal tells _where_ in the signal it comes from
(see [signal.js](https://github.com/padenot/mstp-bench/blob/main/web/signal.js)).

At each measurement point, we cross-correlate the audio with the signal to find
how old it is
([matching.py](https://github.com/padenot/mstp-bench/blob/main/repro/matching.py)).
Audio that doesn't match is counted as unmatched.

Various measurements happen:

- [Stalls](#stalls): end to end latency (source on one machine to the other
  machine playback), in the presence of repeated 500ms stalls
- [Receiver playback](#playout): delay building up at the receiver's end: this
  let us determine if there's delay building up at the sending side or receiving
  side, to absorb the stalls
- [CPU contention](#contention): same deal, but with heavy audio processing, and
  the machine hammered by external load (64 `stress-ng` processes).
- [Timestamp alignments](#timestamps):  same setup, with a sibling video stream,
  checking if A/V sync is satisfactory in those scenario. This test case can run
  well in Safari (that shows excellent results).

The processing is either a plain memory copy or a massive WebAssembly SIMD FIR
filter ([fir.wat](https://github.com/padenot/mstp-bench/blob/main/web/fir.wat)),
that has been measured as being roughly as fast to compute on all three
browsers. Stalls are just busy-wait where they are to happen
(`AudioWorkletProcessor.process`, etc.).

{{ diagram("call") }}

Measurement points:

1. Source generated.
2. Processing output.
3. Local recording.
4. Playback, `getOutputTimestamp()`.
5. Jitter buffer, `getStats()`.

Every `AudioContext` runs at the device’s sample rate (on this machine,
44.1kHz). Again, we're using a single machine to repro easily, that means
loopback network and no network latency.

In the tests, the browsers are headless, the sources are synthetic
(`AudioWorkletProcessor`), to not depend on external stimuli on a microphone or
complexify the setup using virtual audio driver. That means audio device
latencies are mostly irrelevant.
