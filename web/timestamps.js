// Timestamp alignment: record audio gated by an independently clocked video
// source, with processing stalls. Driven by repro/timestamps.py.
//
//   source ─┬─ muted monitor
//           └─ worker: capture AudioWorklet → ring ─┐
//              mstp:   MediaStreamTrackProcessor ───┴→ recording worker ← video worker
import { Ring } from './ring.js';

const trial = new URLSearchParams(location.search).get('trial');
const data = { userAgent: navigator.userAgent, events: [], errors: [], source_blocks: [], videoTruth: [], audioClocks: [] };
let context, recorder, video, done, clock, clockTimer;

function record(message) {
  if (message.type === 'source_blocks') {
    for (let i = 0; i < message.blocks.length; i += 3) data.source_blocks.push(Array.from(message.blocks.subarray(i, i + 3)));
  } else {
    data.events.push(message);
    if (message.type === 'fatal') data.errors.push(message.message);
  }
}
window.onunhandledrejection = ({ reason }) => record({ type: 'fatal', message: String(reason?.stack ?? reason) });

window.record = async config => {
  data.config = config;
  context = new AudioContext({ latencyHint: 'interactive' });
  await context.audioWorklet.addModule(new URL('./worklets.js', import.meta.url));
  await context.resume();
  data.rate = context.sampleRate;
  data.pageOrigin = performance.timeOrigin;

  const source = new AudioWorkletNode(context, 'source', {
    numberOfInputs: 0, outputChannelCount: [1], processorOptions: { startWallMs: config.startWallMs } });
  source.port.onmessage = ({ data: message }) => record(message);
  source.connect(new GainNode(context, { gain: 0 })).connect(context.destination);

  recorder = new Worker(new URL('./workers/recording-worker.js', import.meta.url), { type: 'module' });
  done = new Promise(resolve => {
    recorder.onmessage = ({ data: message }) => message.type === 'done' ? resolve(message) : record(message);
  });
  recorder.onerror = event => record({ type: 'fatal', message: event.message });
  const start = { type: 'start', mode: config.path, rate: context.sampleRate, stalls: config.stalls,
                  startWallMs: config.startWallMs, pageOrigin: performance.timeOrigin };

  if (config.path === 'worker') {
    const ring = new SharedArrayBuffer(Ring.bytes(2 * context.sampleRate)), control = new SharedArrayBuffer(8);
    const capture = new AudioWorkletNode(context, 'capture', {
      outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit', processorOptions: { ring, control } });
    capture.port.onmessage = ({ data: message }) => record(message);
    source.connect(capture).connect(context.destination);
    recorder.postMessage({ ...start, ring, control });
    // Audio clock: when context frames reach the output device, in page time.
    clock = () => {
      const { contextTime, performanceTime } = context.getOutputTimestamp();
      if (contextTime > 0 && performanceTime > 0) {
        const point = { position: contextTime * context.sampleRate, timeMs: performanceTime };
        data.audioClocks.push(point);
        recorder.postMessage({ type: 'audio_clock', ...point });
      }
    };
    clock();
    clockTimer = setInterval(clock, 50);
  } else {
    const destination = context.createMediaStreamDestination();
    destination.channelCount = 1;
    source.connect(destination);
    const processor = new MediaStreamTrackProcessor({ track: destination.stream.getAudioTracks()[0], maxBufferSize: 200 });
    recorder.postMessage({ ...start, readable: processor.readable }, [processor.readable]);
  }

  video = new Worker(new URL('./workers/video-worker.js', import.meta.url), { type: 'module' });
  video.onmessage = ({ data: message }) => {
    if (message.type === 'video_frame') {
      data.videoTruth.push({ index: message.index, timestamp: message.frame.timestamp, pageMs: message.truthMs });
      recorder.postMessage({ type: 'video_frame', frame: message.frame }, [message.frame]);
    } else {
      recorder.postMessage(message);
    }
  };
  video.postMessage({ ppm: config.videoPpm, pageOrigin: performance.timeOrigin });
};

window.trialErrors = () => data.errors;

window.finish = async () => {
  await context.suspend();
  clearInterval(clockTimer);
  clock?.();
  video.postMessage({ stop: true });
  recorder.postMessage({ type: 'stop' });
  const result = await done;
  video.terminate(); recorder.terminate();
  await context.close();
  const { wav, ...worker } = result;
  await upload('page.json', JSON.stringify(data));
  await upload('worker.json', JSON.stringify(worker));
  await upload('recording.wav', wav);
  return data.errors;
};

async function upload(name, body) {
  const response = await fetch(`/upload/${trial}/${name}`, { method: 'PUT', body });
  if (!response.ok) throw new Error(`Upload ${name}: HTTP ${response.status}`);
}
