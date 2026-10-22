// An independent video source: 250 ms frames whose timestamps start at an
// arbitrary 7 s origin and advance `ppm` faster or slower than the page clock.
// Pixel 0 encodes the frame's audio gain (64 → 0.25, 192 → 0.75); pixel 1 the
// frame index. The true page time of each frame (truthMs) goes to the page for
// validation only; the recording worker must derive it from the clock pairs.
const FRAME_US = 250000, ORIGIN_US = 7000000, AHEAD_US = 750000;
let timer, index = 0, config;

self.onmessage = ({ data }) => {
  if (data.stop) { clearInterval(timer); tick(); self.postMessage({ type: 'video_end', count: index }); return; }
  config = data; // { ppm, pageOrigin }
  tick();
  timer = setInterval(tick, 50);
};

function tick() {
  const pageMs = performance.timeOrigin - config.pageOrigin + performance.now();
  const rate = 1 + config.ppm / 1e6;
  const clockUs = ORIGIN_US + pageMs * 1000 * rate;
  self.postMessage({ type: 'video_clock', position: clockUs, timeMs: pageMs });
  while (index * FRAME_US <= clockUs - ORIGIN_US + AHEAD_US) {
    const canvas = new OffscreenCanvas(2, 1), context = canvas.getContext('2d'), pixels = context.createImageData(2, 1);
    pixels.data.set([index % 2 ? 192 : 64, 0, 0, 255, index % 256, 0, 0, 255]);
    context.putImageData(pixels, 0, 0);
    const frame = new VideoFrame(canvas, { timestamp: ORIGIN_US + index * FRAME_US, duration: FRAME_US });
    self.postMessage({ type: 'video_frame', frame, index, truthMs: index * FRAME_US / 1000 / rate }, [frame]);
    index++;
  }
}
