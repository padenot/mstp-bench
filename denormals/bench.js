// Denormal penalty in typical DSP code. One file, two hosts:
//   node bench.js
//   open denormals.html   (works off file://, no server needed)
//
// Deliberately written as a classic script with no imports, so the browser can
// load it over file:// and node can run it directly. Identical code path in both.
(function () {
  const out = typeof document !== "undefined" ? document.getElementById("out") : null;
  if (out) out.textContent = "";
  function log(s) {
    console.log(s);
    if (out) out.textContent += s + "\n";
  }

  const CHUNK = 65536;         // samples per timing sample
  const CHUNKS = 180;          // long enough for the tail to reach the subnormals
  const POLES = 4;             // one-pole lowpass cascade
  const A = 1e-4;              // small => slow decay => a long subnormal tail
  const WARMUP_MS = 1500;      // per engine, so the timed loop is at top tier
  const MIN_NORMAL = 2.2250738585072014e-308;

  // y += a * (x - y), four times. Textbook DSP, impulse response decays to 0.
  // `offset` is the classic anti-denormal trick: a tiny DC added to the input
  // keeps the state normal forever.
  function jsProcess(y, offset, x0, count) {
    let x = x0, acc = 0;
    for (let i = 0; i < count; i++) {
      let v = x + offset;
      x = 0;
      for (let p = 0; p < POLES; p++) {
        y[p] += A * (v - y[p]);
        v = y[p];
      }
      acc += v;
    }
    return acc;
  }

  function jsEngine() {
    const y = new Float64Array(POLES);
    return {
      name: "js",
      seed: (v) => y.fill(v),
      level: () => Math.abs(y[POLES - 1]),
      process: (offset, x0, count) => jsProcess(y, offset, x0, count),
    };
  }

  // filter.wat compiled with wat2wasm, inlined so no fetch/fs is needed.
  const WASM =
    "AGFzbQEAAAABEANgAXwAYAABfGADfHx/AXwDBAMAAQIGMQR8AUQAAAAAAAAAAAt8AUQAAAAAAAAA" +
    "AAt8AUQAAAAAAAAAAAt8AUQAAAAAAAAAAAsHGgMEc2VlZAAABWxldmVsAAEHcHJvY2VzcwACCrcBAx" +
    "IAIAAkACAAJAEgACQCIAAkAwsFACMDmQubAQIDfAF/IAEhAwJAA0AgBiACTg0BIAMgAKAhBUQAAAAA" +
    "AAAAACEDIwBELUMc6+I2Gj8gBSMAoaKgJAAjACEFIwFELUMc6+I2Gj8gBSMBoaKgJAEjASEFIwJELU" +
    "Mc6+I2Gj8gBSMCoaKgJAIjAiEFIwNELUMc6+I2Gj8gBSMDoaKgJAMjAyEFIAQgBaAhBCAGQQFqIQYM" +
    "AAsLIAQL";

  async function wasmEngine() {
    const bytes = Uint8Array.from(atob(WASM), (c) => c.charCodeAt(0));
    const { instance } = await WebAssembly.instantiate(bytes);
    const { seed, level, process } = instance.exports;
    return { name: "wasm", seed, level, process };
  }

  // Run process() until it is fully optimized, over normal AND subnormal state so
  // that neither phase of the measurement pays for tier-up or a deopt.
  function warmup(e, ms) {
    const t0 = performance.now();
    let acc = 0, passes = 0;
    while (performance.now() - t0 < ms) {
      e.seed(1);      acc += e.process(0, 1, CHUNK);
      e.seed(5e-320); acc += e.process(0, 0, CHUNK);
      e.seed(1);      acc += e.process(1e-18, 1, CHUNK);
      passes++;
    }
    return { acc, passes };
  }

  function run(e, offset) {
    e.seed(0);
    let x0 = 1, acc = 0;       // single impulse, then silence
    const times = [], levels = [];
    for (let c = 0; c < CHUNKS; c++) {
      const t0 = performance.now();
      acc += e.process(offset, x0, CHUNK);
      times.push(performance.now() - t0);
      levels.push(e.level());
      x0 = 0;
    }
    return { times, levels, acc };
  }

  const median = (a) => [...a].sort((x, y) => x - y)[a.length >> 1];

  function measure(e) {
    const w = warmup(e, WARMUP_MS);
    const bare = run(e, 0);
    const fixed = run(e, 1e-18);

    const normal = [], subnormal = [];
    for (let c = 0; c < CHUNKS; c++) {
      (bare.levels[c] < MIN_NORMAL ? subnormal : normal).push(bare.times[c]);
    }
    const n = median(normal), s = median(subnormal), f = median(fixed.times);

    log(`${e.name}: ${(s / n).toFixed(1)}x slower once the filter state goes subnormal`);
    log(`  normal state:    ${n.toFixed(2)} ms/chunk (${normal.length} chunks)`);
    log(`  subnormal state: ${s.toFixed(2)} ms/chunk (${subnormal.length} chunks)`);
    log(`  +1e-18 DC offset:${f.toFixed(2)} ms/chunk (penalty gone)`);
    log(`  (${w.passes} warmup passes, checksum ` +
        `${(bare.acc + fixed.acc).toExponential(6)})`);
  }

  (async () => {
    const engines = [jsEngine(), await wasmEngine()];
    for (const e of engines) measure(e);
    const arch = typeof process !== "undefined" ? process.arch : "browser";
    log(`on ${arch}; x86-64 and old Atom pay for subnormals, arm64 does not`);
  })();
})();
