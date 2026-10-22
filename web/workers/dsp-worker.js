// Path "worker": processing in a dedicated worker, between two rings shared
// with AudioWorklets (see worklets.js: ring-writer, ring-reader).
//
// control (Int32Array): [0] wake-up counter, bumped by ring-writer;
//                       [1] stop flag, set by the page.
import { DSP } from '../dsp.js';
import { Ring } from '../ring.js';
import { Stalls, DspClock } from '../instrument.js';

self.onmessage = ({ data }) => {
  const emit = message => self.postMessage(message);
  const input = new Ring(data.input), output = new Ring(data.output), control = new Int32Array(data.control);
  const dsp = new DSP(data.dsp), stalls = new Stalls(data.stalls, data.startWallMs, emit), clock = new DspClock(emit);
  const block = new Float32Array(data.blockFrames), processed = new Float32Array(data.blockFrames);
  emit({ type: 'ready' });
  try {
    while (!Atomics.load(control, 1)) {
      const wake = Atomics.load(control, 0);
      if (input.availableRead() < block.length) {
        Atomics.wait(control, 0, wake, 100); // Workers may block.
        continue;
      }
      input.pop(block);
      stalls.run();
      clock.measure(dsp, block, processed);
      if (output.availableWrite() < processed.length) throw new Error('Worker output ring overflow');
      output.push(processed);
    }
  } catch (error) {
    emit({ type: 'fatal', message: error.stack });
  }
};
