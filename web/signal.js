// The test signal: pseudorandom values every millisecond, linearly
// interpolated. It is defined in time, so any sample rate can generate it, and
// any 80 ms window identifies its position. repro/signal.py is the same
// definition; the analysis relies on both producing identical samples.

function knot(index) {
  let x = index | 0;
  x = Math.imul(x ^ (x >>> 16), 0x45d9f3b);
  x = Math.imul(x ^ (x >>> 16), 0x45d9f3b);
  x ^= x >>> 16;
  return (x >>> 0) / 4294967296 * 2 - 1;
}

export function sampleAt(frame, rate) {
  const ms = frame * 1000 / rate, whole = Math.floor(ms), fraction = ms - whole;
  return 0.25 * (knot(whole) * (1 - fraction) + knot(whole + 1) * fraction);
}
