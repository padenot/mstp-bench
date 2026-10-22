// One side of a call. The harness (repro/trial.py) drives both sides through
// WebDriver: it calls window.sender() / window.receiver() with the trial
// configuration, relays the SDP between them (ICE gathering completes before
// the description is returned, so no signaling server is needed), then calls
// window.finish(), which uploads everything recorded.
//
// Sender:   source ─┬─ muted monitor (device AudioContext output)
//                   └─ processing path (paths.js) ─┬─ MediaRecorder
//                                                  └─ RTCPeerConnection
// Receiver: RTCPeerConnection → device AudioContext → tap → muted output
import * as paths from './paths.js';

const MODULE = new URL('./worklets.js', import.meta.url);
const trial = new URLSearchParams(location.search).get('trial');

// Everything recorded during the trial. Large sample data is kept as typed
// arrays and uploaded as binary files.
const data = { userAgent: navigator.userAgent, events: [], errors: [], rates: {}, clocks: [], stats: [] };
const series = { source_blocks: [], output_blocks: [], playout_blocks: [] };
const samples = { output_blocks: [], playout_blocks: [] };
const owned = { contexts: [], timers: [], stop: [] };

function record(message) {
  if (message.type in series) {
    series[message.type].push(message.blocks);
    if (message.samples) samples[message.type].push(message.samples);
  } else {
    data.events.push(message);
    if (message.type === 'fatal') data.errors.push(message.message);
  }
}
window.onerror = (message, file, line) => record({ type: 'fatal', message: `${message} (${file}:${line})` });
window.onunhandledrejection = ({ reason }) => record({ type: 'fatal', message: String(reason?.stack ?? reason) });

async function deviceContext() {
  const context = new AudioContext({ latencyHint: 'interactive' });
  await context.audioWorklet.addModule(MODULE);
  await context.resume();
  owned.contexts.push(context);
  return context;
}

function peerConnection() {
  const pc = new RTCPeerConnection();
  pc.onconnectionstatechange = () => record({ type: 'connection', state: pc.connectionState, wallMs: Date.now() });
  owned.stop.push(() => pc.close());
  return pc;
}

// Non-trickle ICE: wait for all (host) candidates, then hand back the full SDP.
async function localDescription(pc) {
  await pc.setLocalDescription();
  if (pc.iceGatheringState !== 'complete') {
    await new Promise(resolve => pc.addEventListener('icegatheringstatechange',
      () => pc.iceGatheringState === 'complete' && resolve()));
  }
  return pc.localDescription.toJSON();
}

window.sender = async config => {
  data.role = 'sender'; data.config = config;
  const device = await deviceContext();
  data.rates.source = device.sampleRate;
  const source = new AudioWorkletNode(device, 'source', {
    numberOfInputs: 0, outputChannelCount: [1], processorOptions: { startWallMs: config.startWallMs } });
  source.port.onmessage = ({ data: message }) => record(message);

  // The monitor: unprocessed audio to the output device, muted for automation.
  // This context follows the device clock whatever the processing does.
  const monitor = new GainNode(device, { gain: 0 });
  source.connect(monitor).connect(device.destination);

  const input = device.createMediaStreamDestination();
  input.channelCount = 1;
  source.connect(input);

  const path = await paths[config.path]({ device, source, track: input.stream.getAudioTracks()[0], config, record });
  owned.contexts.push(...path.contexts);
  owned.stop.unshift(path.stop);
  data.rates.processing = path.contexts[0]?.sampleRate ?? device.sampleRate;
  const processed = new MediaStream([path.track]);

  const recorder = new MediaRecorder(processed, { mimeType: 'audio/webm;codecs=opus' });
  const chunks = [];
  recorder.ondataavailable = ({ data: blob }) => blob.size && chunks.push(blob);
  recorder.start(250);
  record({ type: 'recording_start', wallMs: Date.now() });
  owned.recording = async () => {
    await new Promise(resolve => { recorder.onstop = resolve; recorder.stop(); });
    return new Blob(chunks, { type: recorder.mimeType });
  };

  const pc = peerConnection();
  pc.addTransceiver(path.track, { direction: 'sendonly', streams: [processed] });
  preferOpus(pc);
  window.accept = answer => pc.setRemoteDescription(answer);
  return localDescription(pc);
};

window.receiver = async (config, offer) => {
  data.role = 'receiver'; data.config = config;
  const device = await deviceContext();
  data.rates.playout = device.sampleRate;
  const pc = peerConnection();
  pc.ontrack = ({ track }) => {
    const stream = new MediaStream([track]);
    // Chromium only feeds a remote track to Web Audio while a media element
    // plays it (https://crbug.com/933677). Muted; harmless elsewhere.
    const element = new Audio();
    element.srcObject = stream; element.muted = true;
    element.play().catch(error => record({ type: 'fatal', message: `Media element: ${error.message}` }));
    owned.stop.push(() => { element.pause(); element.srcObject = null; });

    const tap = new AudioWorkletNode(device, 'tap', { outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit' });
    tap.port.onmessage = ({ data: message }) => record(message);
    device.createMediaStreamSource(stream).connect(tap).connect(device.destination); // The tap outputs silence.
  };

  // getOutputTimestamp() maps context frames to when they reach the device;
  // getStats() exposes the jitter buffer.
  owned.timers.push(setInterval(async () => {
    const stamp = device.getOutputTimestamp();
    data.clocks.push({ contextTime: stamp.contextTime, performanceTime: stamp.performanceTime });
    const reports = [];
    (await pc.getStats()).forEach(report => report.type === 'inbound-rtp' && reports.push(report));
    data.stats.push({ wallMs: Date.now(), reports });
  }, 250));

  await pc.setRemoteDescription(offer);
  return localDescription(pc);
};

function preferOpus(pc) {
  const opus = RTCRtpSender.getCapabilities('audio').codecs.filter(c => c.mimeType.toLowerCase() === 'audio/opus');
  for (const transceiver of pc.getTransceivers()) transceiver.setCodecPreferences(opus);
}

window.trialErrors = () => data.errors;

window.finish = async () => {
  owned.timers.forEach(clearInterval);
  const recording = await owned.recording?.();
  owned.stop.forEach(stop => stop());
  await Promise.all(owned.contexts.map(context => context.close()));
  data.timeOrigin = performance.timeOrigin;
  // Block metadata arrives as Float64Array batches of [position, frames, wallMs]; store rows.
  for (const [name, blocks] of Object.entries(series)) {
    data[name] = blocks.flatMap(b => Array.from({ length: b.length / 3 }, (_, i) => Array.from(b.subarray(3 * i, 3 * i + 3))));
  }
  const { role } = data;
  await upload(`${role}.json`, JSON.stringify(data));
  for (const [name, chunks] of Object.entries(samples)) {
    if (chunks.length) await upload(`${role}-${name.split('_')[0]}.f32`, new Blob(chunks));
  }
  if (recording) await upload(`${role}.webm`, recording);
  return data.errors;
};

async function upload(name, body) {
  const response = await fetch(`/upload/${trial}/${name}`, { method: 'PUT', body });
  if (!response.ok) throw new Error(`Upload ${name}: HTTP ${response.status}`);
}
