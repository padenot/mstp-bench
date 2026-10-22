// The three processing paths under test. Each takes the device-clocked context
// and its source node, and returns the processed MediaStreamTrack plus a stop
// function. `record(message)` stores instrumentation; see call.js.
//
//   audioworklet  sinkless AudioContext running the DSP in an AudioWorklet.
//   worker        DSP in a dedicated worker; AudioWorklets move audio in and
//                 out through SharedArrayBuffer rings (needs cross-origin
//                 isolation).
//   mstp          MediaStreamTrackProcessor → worker → MediaStreamTrackGenerator
//                 (Chromium only).
import { Ring } from './ring.js';

const MODULE = new URL('./worklets.js', import.meta.url);

// A sinkless context has no device rate. Use the source's rate so that no
// resampler is inserted (Chromium otherwise defaults to 48 kHz), and so that
// the worker rings connect two clocks running at the same nominal rate.
async function sinklessContext(device, quantum) {
  const context = new AudioContext({ sinkId: { type: 'none' }, renderSizeHint: quantum, sampleRate: device.sampleRate });
  if (context.sinkId?.type !== 'none') throw new Error('AudioContext sinkId { type: "none" } is not supported');
  if (context.renderQuantumSize !== quantum) throw new Error(`renderSizeHint ${quantum} gave ${context.renderQuantumSize}`);
  await context.audioWorklet.addModule(MODULE);
  await context.resume();
  return context;
}

function worklet(context, name, record, options = {}) {
  const node = new AudioWorkletNode(context, name, { outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit', ...options });
  node.port.onmessage = ({ data }) => record(data);
  node.onprocessorerror = () => record({ type: 'fatal', message: `AudioWorklet "${name}" failed` });
  return node;
}

function trackOf(context, node) {
  const destination = context.createMediaStreamDestination();
  destination.channelCount = 1;
  node.connect(destination);
  return destination.stream.getAudioTracks()[0];
}

export async function audioworklet({ device, track, config, record }) {
  const context = await sinklessContext(device, config.quantum);
  const input = context.createMediaStreamSource(new MediaStream([track]));
  const dsp = worklet(context, 'dsp', record, {
    processorOptions: { dsp: config.dsp, stalls: config.stalls, startWallMs: config.startWallMs } });
  input.connect(dsp);
  return { track: trackOf(context, dsp), contexts: [context], stop() {} };
}

export async function worker({ device, source, config, record }) {
  if (!crossOriginIsolated) throw new Error('The worker path needs SharedArrayBuffer: serve with cross-origin isolation');
  // Rings hold 2 s; overflowing them fails the run.
  const capacity = 2 * device.sampleRate;
  const shared = {
    input: new SharedArrayBuffer(Ring.bytes(capacity)),
    output: new SharedArrayBuffer(Ring.bytes(capacity)),
    control: new SharedArrayBuffer(8),
  };
  const thread = new Worker(new URL('./workers/dsp-worker.js', import.meta.url), { type: 'module' });
  const ready = new Promise((resolve, reject) => {
    thread.onmessage = ({ data }) => data.type === 'ready' ? resolve() : record(data);
    thread.onerror = event => reject(new Error(event.message));
  });
  thread.postMessage({ ...shared, dsp: config.dsp, stalls: config.stalls, startWallMs: config.startWallMs, blockFrames: config.quantum });
  await ready;
  thread.onmessage = ({ data }) => record(data);

  // Output: four processing blocks of allowance before output starts.
  const context = await sinklessContext(device, config.quantum);
  const reader = worklet(context, 'ring-reader', record, {
    numberOfInputs: 0, processorOptions: { ring: shared.output, control: shared.control, startFrames: 4 * config.quantum } });
  const track = trackOf(context, reader);

  // Input, connected last: whatever the device context renders before the
  // output side runs would otherwise stay queued as permanent latency.
  const writer = worklet(device, 'ring-writer', record, { processorOptions: { ring: shared.input, control: shared.control } });
  source.connect(writer).connect(device.destination); // Connected so it is pulled; outputs silence.

  const control = new Int32Array(shared.control);
  return {
    track, contexts: [context],
    stop() { Atomics.store(control, 1, 1); Atomics.notify(control, 0); thread.terminate(); },
  };
}

export async function mstp({ track, config, record }) {
  if (typeof MediaStreamTrackProcessor !== 'function' || typeof MediaStreamTrackGenerator !== 'function') {
    throw new Error('Audio MediaStreamTrackProcessor/Generator are not supported');
  }
  // 100 queued AudioData (about 1 s) lets the 500 ms stall complete without
  // the processor dropping input.
  const processor = new MediaStreamTrackProcessor({ track, maxBufferSize: 100 });
  const generator = new MediaStreamTrackGenerator({ kind: 'audio' });
  const thread = new Worker(new URL('./workers/mstp-worker.js', import.meta.url), { type: 'module' });
  thread.onmessage = ({ data }) => record(data);
  thread.onerror = event => record({ type: 'fatal', message: event.message });
  thread.postMessage({ readable: processor.readable, writable: generator.writable, dsp: config.dsp,
                       stalls: config.stalls, startWallMs: config.startWallMs },
                     [processor.readable, generator.writable]);
  return { track: generator, contexts: [], stop() { thread.terminate(); } };
}
