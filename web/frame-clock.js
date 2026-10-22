// Maps a stream position (audio frames, or video timestamp microseconds) to
// page time in milliseconds, from (position, time) observations.
//
// A least-squares line over the observations from the last `windowUnits`
// absorbs jitter in when observations were taken. Only observations at or
// before the requested position are used: processing an old block after a
// stall must not borrow timing from later observations.
export class FrameClock {
  constructor(nominalMsPerUnit, windowUnits) {
    this.nominal = nominalMsPerUnit; this.window = windowUnits; this.points = [];
  }

  add(position, timeMs) {
    if (this.points.length && position <= this.points.at(-1).position) return;
    this.points.push({ position, timeMs });
  }

  get ready() { return this.points.length >= 2; }
  get latest() { return this.points.at(-1)?.position ?? -Infinity; }

  // Returns { timeMs, msPerUnit } at `position`.
  fit(position) {
    let end = this.points.findIndex(p => p.position > position);
    if (end < 0) end = this.points.length;
    end = Math.max(end, Math.min(2, this.points.length)); // At startup, extrapolate from the first pair.
    let start = end - 1;
    while (start > 0 && this.points[start - 1].position >= this.points[end - 1].position - this.window) start--;
    const origin = this.points[start];
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (let i = start; i < end; i++) {
      const x = this.points[i].position - origin.position, y = this.points[i].timeMs - origin.timeMs;
      sx += x; sy += y; sxx += x * x; sxy += x * y;
    }
    const n = end - start, denominator = n * sxx - sx * sx;
    const slope = denominator > 0 ? (n * sxy - sx * sy) / denominator : this.nominal;
    return { timeMs: origin.timeMs + (sy - slope * sx) / n + (position - origin.position) * slope, msPerUnit: slope };
  }
}
