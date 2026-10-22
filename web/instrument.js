// Instrumentation shared by worklets and workers. Every timestamp is wall-clock
// milliseconds (Unix epoch), comparable across browser processes on one machine.

// AudioWorkletGlobalScope has no `performance` in some engines; Date.now()
// then limits worklet timestamps to 1 ms resolution.
const precise = typeof globalThis.performance?.now === 'function';
export const wallNow = () => precise ? performance.timeOrigin + performance.now() : Date.now();

// Deliberate processing stalls: busy-wait on the processing thread at fixed
// times, as an expensive or descheduled callback would.
export class Stalls {
  // schedule: [{ atSeconds, durationMs }], relative to startWallMs.
  constructor(schedule, startWallMs, emit) {
    this.pending = schedule.map(s => ({ wallMs: startWallMs + s.atSeconds * 1000, durationMs: s.durationMs }));
    this.emit = emit;
  }

  run() {
    if (!this.pending.length || wallNow() < this.pending[0].wallMs) return;
    const { durationMs } = this.pending.shift();
    const start = wallNow();
    this.emit({ type: 'stall_start', wallMs: start, durationMs });
    while (wallNow() < start + durationMs) { /* spin */ }
    this.emit({ type: 'stall_end', wallMs: wallNow(), durationMs });
  }
}

// Records samples at a point in the graph, with the wall time of each block.
// Batches are copied out and sent to the page; push() itself does not
// allocate, so it is safe on real-time threads.
export class Observer {
  constructor(type, emit, batchFrames = 4800, maxBlockFrames = 4096) {
    this.type = type; this.emit = emit; this.batchFrames = batchFrames;
    this.samples = new Float32Array(batchFrames + maxBlockFrames);
    this.blocks = new Float64Array(3 * (batchFrames + maxBlockFrames)); // [position, frames, wallMs]...
    this.used = 0; this.count = 0; this.total = 0;
  }

  // position: the block's frame position in its own stream (for example a
  // context's currentFrame); defaults to the running count of observed frames.
  push(samples, position = this.total) {
    this.samples.set(samples, this.used);
    const b = 3 * this.count;
    this.blocks[b] = position; this.blocks[b + 1] = samples.length; this.blocks[b + 2] = wallNow();
    this.used += samples.length; this.total += samples.length; this.count++;
    if (this.used >= this.batchFrames) this.flush();
  }

  flush() {
    if (!this.count) return;
    const samples = this.samples.slice(0, this.used), blocks = this.blocks.slice(0, 3 * this.count);
    this.emit({ type: this.type, blocks, samples }, [samples.buffer, blocks.buffer]);
    this.used = 0; this.count = 0;
  }
}

// Time spent inside DSP.process(), reported every `everyFrames` frames.
export class DspClock {
  constructor(emit, everyFrames = 4096) {
    this.emit = emit; this.everyFrames = everyFrames;
    this.frames = 0; this.dspMs = 0; this.calls = 0; this.next = everyFrames;
  }

  measure(dsp, input, output) {
    const start = wallNow();
    dsp.process(input, output);
    this.dspMs += wallNow() - start; this.calls++; this.frames += input.length;
    if (this.frames >= this.next) {
      this.emit({ type: 'progress', wallMs: wallNow(), processedFrames: this.frames, dspMs: this.dspMs, calls: this.calls });
      this.next = this.frames + this.everyFrames;
    }
  }
}
