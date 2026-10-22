// Records audio gated by timestamped video: each sample is multiplied by the
// gain encoded in the video frame being presented at that sample's
// presentation time. The output is correct only if audio and video timestamps
// are mapped to the same clock, across processing stalls and clock drift.
//
// Audio positions and their clock:
//   worker  context frames from a capture AudioWorklet (SharedArrayBuffer
//           ring); page time from getOutputTimestamp() pairs.
//   mstp    processed frame count; page time from AudioData timestamps.
// Video: VideoFrame timestamps (µs), mapped with the video worker's clock pairs.
import { Ring } from '../ring.js';
import { FrameClock } from '../frame-clock.js';
import { Stalls, wallNow } from '../instrument.js';

let config, audioClock, videoClock, stopped = false, videoEnded = false;
const video = [], blocks = [], transitions = [], chunks = [];
let videoReady = Promise.resolve(), lastTime = -Infinity, current = 0, frames = 0;
const later = () => new Promise(resolve => setTimeout(resolve, 0));
const fatal = error => self.postMessage({ type: 'fatal', message: String(error.stack ?? error) });

self.onmessage = ({ data }) => {
  switch (data.type) {
    case 'start': start(data).catch(fatal); break;
    case 'audio_clock': audioClock.add(data.position, data.timeMs); break;
    case 'video_clock': videoClock.add(data.position, data.timeMs); break;
    case 'video_frame': videoReady = videoReady.then(() => addVideo(data.frame)).catch(fatal); break;
    case 'video_end': videoReady.then(() => { videoEnded = true; }); break;
    case 'stop': stopped = true; break;
  }
};

async function addVideo(frame) {
  try {
    const canvas = new OffscreenCanvas(2, 1), context = canvas.getContext('2d');
    context.drawImage(frame, 0, 0);
    const [level, , , , index] = context.getImageData(0, 0, 2, 1).data;
    if (index !== video.length % 256) throw new Error('Video frame out of order');
    while (!videoClock.ready) await later();
    video.push({ index: video.length, timestamp: frame.timestamp, gain: level / 256,
                 start: videoClock.fit(frame.timestamp).timeMs, end: videoClock.fit(frame.timestamp + frame.duration).timeMs });
  } finally {
    frame.close();
  }
}

async function start(data) {
  config = data;
  audioClock = new FrameClock(1000 / config.rate, 2 * config.rate); // 2 s of observations.
  videoClock = new FrameClock(0.001, 2e6);
  const stalls = new Stalls(config.stalls, config.startWallMs, message => self.postMessage(message));
  if (config.mode === 'worker') {
    const ring = new Ring(config.ring), control = new Int32Array(config.control), block = new Float32Array(4096);
    while (!Atomics.load(control, 1)) await later(); // The first context frame is known.
    const first = Atomics.load(control, 0);
    for (let consumed = 0; ;) {
      const available = Math.min(ring.availableRead(), block.length);
      if (!available) {
        if (stopped) break;
        await later();
        continue;
      }
      const input = block.subarray(0, available);
      ring.pop(input);
      const position = first + consumed;
      consumed += available;
      // Wait for clock observations past this block.
      while (audioClock.latest < position + available && !stopped) await later();
      await process(input, position, stalls);
    }
  } else {
    // Chromium gives AudioData timestamps in the worker's time origin; shift to the page's.
    const offset = performance.timeOrigin - config.pageOrigin;
    const reader = config.readable.getReader();
    for (;;) {
      const { value: audio, done } = await Promise.race([reader.read(), stoppedSoon()]);
      if (done) break;
      const input = new Float32Array(audio.numberOfFrames);
      audio.copyTo(input, { planeIndex: 0, format: 'f32-planar' });
      audioClock.add(frames, audio.timestamp / 1000 + offset);
      audio.close();
      await process(input, frames, stalls);
    }
  }
  while (!videoEnded) await later();
  self.postMessage({ type: 'done', blocks, transitions, video, frames, wav: wav(chunks, config.rate) });
}

async function stoppedSoon() {
  while (!stopped) await new Promise(resolve => setTimeout(resolve, 100));
  return { done: true };
}

async function process(input, position, stalls) {
  const fit = audioClock.fit(position);
  // Wait until video covers this block.
  while (!video.length || video.at(-1).end < fit.timeMs + input.length * fit.msPerUnit) {
    if (videoEnded) throw new Error('Video ended before audio');
    await later();
  }
  stalls.run();
  const output = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) {
    // A refit at a block boundary can move the mapping back by a fraction of
    // a millisecond. Audio is processed in order: its time never decreases.
    const time = lastTime = Math.max(lastTime, fit.timeMs + i * fit.msPerUnit);
    while (current + 1 < video.length && video[current + 1].start <= time) current++;
    if (time < video[current].start) { output[i] = input[i]; continue; } // No frame presented yet.
    if (transitions.at(-1)?.videoIndex !== current) transitions.push({ frame: frames + i, videoIndex: current });
    output[i] = input[i] * video[current].gain;
  }
  blocks.push({ frame: frames, count: input.length, position, timeMs: fit.timeMs, msPerUnit: fit.msPerUnit, wallMs: wallNow() });
  chunks.push(output);
  frames += input.length;
}

// Mono 32-bit float WAV: keeps samples bit-exact for validation.
function wav(chunks, rate) {
  const count = chunks.reduce((n, c) => n + c.length, 0), header = new DataView(new ArrayBuffer(44));
  const text = (offset, value) => [...value].forEach((c, i) => header.setUint8(offset + i, c.charCodeAt(0)));
  text(0, 'RIFF'); header.setUint32(4, 36 + count * 4, true); text(8, 'WAVE');
  text(12, 'fmt '); header.setUint32(16, 16, true); header.setUint16(20, 3, true); header.setUint16(22, 1, true);
  header.setUint32(24, rate, true); header.setUint32(28, rate * 4, true); header.setUint16(32, 4, true); header.setUint16(34, 32, true);
  text(36, 'data'); header.setUint32(40, count * 4, true);
  return new Blob([header, ...chunks], { type: 'audio/wav' });
}
