// AudioWorklet processors. All are mono. Messages to the page go through
// this.port; see call.js for how they are recorded.
import { sampleAt } from './signal.js';
import { DSP } from './dsp.js';
import { Ring } from './ring.js';
import { wallNow, Stalls, Observer, DspClock } from './instrument.js';

// The test source. Runs in the device-clocked AudioContext, so it advances at
// the audio device's pace regardless of what processing does. Reports when
// each block was generated: the reference for every latency measurement.
registerProcessor('source', class extends AudioWorkletProcessor {
  constructor({ processorOptions: { startWallMs } }) {
    super();
    this.startWallMs = startWallMs; this.frame = 0;
    this.blocks = new Float64Array(3 * 32); this.count = 0; // [frame, frames, wallMs]...
  }

  process(_, [[output]]) {
    const wallMs = wallNow();
    if (wallMs < this.startWallMs) return true; // Outputs are zero-filled.
    for (let i = 0; i < output.length; i++) output[i] = sampleAt(this.frame + i, sampleRate);
    this.blocks[3 * this.count] = this.frame;
    this.blocks[3 * this.count + 1] = output.length;
    this.blocks[3 * this.count + 2] = wallMs;
    this.frame += output.length;
    if (++this.count === 32) {
      this.port.postMessage({ type: 'source_blocks', blocks: this.blocks.slice() });
      this.count = 0;
    }
    return true;
  }
});

// Records its input with the context frame of each block, so the samples can
// be mapped to the output device clock (getOutputTimestamp). Outputs silence.
registerProcessor('tap', class extends AudioWorkletProcessor {
  constructor() {
    super();
    this.observer = new Observer('playout_blocks', (m, t) => this.port.postMessage(m, t));
    this.silence = new Float32Array(4096);
  }

  process([[input]], [[output]]) {
    this.observer.push(input ?? this.silence.subarray(0, output.length), currentFrame);
    return true;
  }
});

// Path "audioworklet": processing in a sinkless AudioContext.
registerProcessor('dsp', class extends AudioWorkletProcessor {
  constructor({ processorOptions: { dsp, stalls, startWallMs } }) {
    super();
    const emit = (m, t) => this.port.postMessage(m, t);
    this.dsp = new DSP(dsp);
    this.stalls = new Stalls(stalls, startWallMs, emit);
    this.clock = new DspClock(emit);
    this.observer = new Observer('output_blocks', emit);
  }

  process([[input]], [[output]]) {
    if (!input) return true; // No input connected yet.
    this.stalls.run();
    this.clock.measure(this.dsp, input, output);
    this.observer.push(output);
    return true;
  }
});

// Path "worker", input side. Runs in the device-clocked context: copies each
// input block into a ring and wakes the worker. Never blocks. Overflowing the
// ring is a test failure, not a reason to drop audio.
registerProcessor('ring-writer', class extends AudioWorkletProcessor {
  constructor({ processorOptions: { ring, control } }) {
    super();
    this.ring = new Ring(ring); this.control = new Int32Array(control);
  }

  process([[input]]) {
    if (!input) return true;
    if (this.ring.availableWrite() < input.length) {
      this.port.postMessage({ type: 'fatal', message: 'Worker input ring overflow' });
      return false;
    }
    this.ring.push(input);
    Atomics.add(this.control, 0, 1);
    Atomics.notify(this.control, 0);
    return true;
  }
});

// Path "worker", output side. Runs in the sinkless context, whose render
// thread is not tied to a device deadline, and outputs processed audio as the
// worker produces it.
//
// Worklets may not block (Atomics.wait throws there), so a missing block is
// awaited by spinning. Spinning delays only this sinkless context, the same
// way a late MediaStreamTrackGenerator write delays its track.
//
// Output starts after `startFrames` processed frames are available, a small
// allowance for worker wake-up jitter.
registerProcessor('ring-reader', class extends AudioWorkletProcessor {
  constructor({ processorOptions: { ring, control, startFrames } }) {
    super();
    this.ring = new Ring(ring); this.control = new Int32Array(control);
    this.startFrames = startFrames; this.started = false;
    this.observer = new Observer('output_blocks', (m, t) => this.port.postMessage(m, t));
  }

  process(_, [[output]]) {
    if (!this.started) {
      if (this.ring.availableRead() < this.startFrames) return true;
      this.started = true;
    }
    while (this.ring.availableRead() < output.length) {
      if (Atomics.load(this.control, 1)) return false; // Stopping.
    }
    this.ring.pop(output);
    this.observer.push(output);
    return true;
  }
});

// Timestamp experiment, worker path: copies input into a ring for the
// recording worker, after publishing the context frame of the first sample.
// control (Int32Array): [0] first context frame, [1] set once [0] is valid.
registerProcessor('capture', class extends AudioWorkletProcessor {
  constructor({ processorOptions: { ring, control } }) {
    super();
    this.ring = new Ring(ring); this.control = new Int32Array(control);
  }

  process([[input]]) {
    if (!input) return true;
    if (!Atomics.load(this.control, 1)) {
      Atomics.store(this.control, 0, currentFrame);
      Atomics.store(this.control, 1, 1);
    }
    if (this.ring.availableWrite() < input.length) {
      this.port.postMessage({ type: 'fatal', message: 'Capture ring overflow' });
      return false;
    }
    this.ring.push(input);
    return true;
  }
});
