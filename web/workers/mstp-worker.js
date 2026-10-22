// Path "mstp": MediaStreamTrackProcessor → worker DSP → MediaStreamTrackGenerator
// (Chromium). Each AudioData is processed and written with its own timestamp.
import { DSP } from '../dsp.js';
import { Stalls, Observer, DspClock } from '../instrument.js';

self.onmessage = async ({ data }) => {
  const emit = (message, transfer) => self.postMessage(message, transfer);
  const dsp = new DSP(data.dsp), stalls = new Stalls(data.stalls, data.startWallMs, emit);
  const clock = new DspClock(emit), observer = new Observer('output_blocks', emit);
  const reader = data.readable.getReader(), writer = data.writable.getWriter();
  try {
    for (;;) {
      const { value: frame, done } = await reader.read();
      if (done) break;
      if (frame.numberOfChannels !== 1) throw new Error(`Expected mono AudioData, got ${frame.numberOfChannels} channels`);
      const input = new Float32Array(frame.numberOfFrames), output = new Float32Array(frame.numberOfFrames);
      frame.copyTo(input, { planeIndex: 0, format: 'f32-planar' });
      const { sampleRate, timestamp } = frame;
      frame.close();
      stalls.run();
      clock.measure(dsp, input, output);
      observer.push(output);
      const processed = new AudioData({ format: 'f32-planar', sampleRate, numberOfFrames: output.length,
                                        numberOfChannels: 1, timestamp, data: output });
      try { await writer.write(processed); } finally { processed.close(); }
    }
  } catch (error) {
    emit({ type: 'fatal', message: error.stack });
  }
};
