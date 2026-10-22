## Subnormals

Floating-point numbers very close to zero (subnormals, or denormals) are slow on
most x86 CPUs. Audio DSP produces them all the time: any filter, envelope or
reverb tail decaying towards silence ends up there. Native audio code avoids the
cost by having the CPU flush subnormals to zero. On the Web, this historically
happened on the `AudioWorkletProcessor.process`. More recently, some engines
removed this, which is unfortunately a breaking change. Mitigations can be put
in place, but they aren't satisfactory, and are very invasive.

Firefox, like others, had to do this, but kept flushing to zero WebAssembly
running in `AudioWorkletProcessor.process()`, and only there, as it always has.
Code running anywhere else worker, where MSTP/G processing runs, doesn't get it.

The benchmark is simple, a cascade of four one-pole lowpass filters (`y += a *
(x - y)`) whose impulse response decays into the subnormal range: the most
common DSP code there is, found countless times in any non-trivial
bit of audio code. It runs in JavaScript and in WebAssembly, without flushing. Each
timing sample is a chunk of 65536 samples, 1.365 s of audio at 48 kHz; times are
medians of 109 chunks before the filter state becomes subnormal and 71 after.
Code: [denormals/](https://github.com/padenot/mstp-bench/tree/main/denormals)
(`node bench.js`, or open `denormals.html`).

### Intel: low end 2017, high end 2021, high end 2025

WebAssembly, pinned to one core, time per chunk.

| Machine | Generation | Normal | Subnormal | Slowdown |
|---|---|---|---|---|
| Celeron J4125 | Intel Atom, 2017 | 0.78 ms | 57.17 ms | 73× |
| i9-11900H | Intel Tiger Lake, 2021 | 0.20 ms | 7.65 ms | 38× |
| Core Ultra X9 388H | Intel Panther Lake, 2025 | 0.18 ms | 8.97 ms | 50× |
| EPYC 7713 (reference) | AMD Zen 3, 2021 | 0.41 ms | 1.18 ms | 2.9× |

### All runs

| CPU | Core | Engine | Normal | Subnormal | Slowdown |
|---|---|---|---|---|---|
| Celeron J4125 (Goldmont+, 2017) | — | JS | 1.31 ms | 57.41 ms | 43.8× |
| Celeron J4125 (Goldmont+, 2017) | — | Wasm | 0.78 ms | 57.17 ms | 73.3× |
| i9-11900H (Tiger Lake, 2021) | cpu0 | JS | 0.49 ms | 8.05 ms | 16.4× |
| i9-11900H (Tiger Lake, 2021) | cpu0 | Wasm | 0.20 ms | 7.65 ms | 37.9× |
| Core Ultra X9 388H (Panther Lake, 2025) | cpu0 | JS | 0.36 ms | 9.71 ms | 27.1× |
| Core Ultra X9 388H (Panther Lake, 2025) | cpu0 | Wasm | 0.18 ms | 8.97 ms | 50.4× |
| Core Ultra X9 388H (Panther Lake, 2025) | cpu15 | JS | 0.56 ms | 10.91 ms | 19.4× |
| Core Ultra X9 388H (Panther Lake, 2025) | cpu15 | Wasm | 0.20 ms | 9.89 ms | 48.2× |
| EPYC 7713 (Zen 3, 2021) | — | JS | 0.58 ms | 0.66 ms | 1.1× |
| EPYC 7713 (Zen 3, 2021) | — | Wasm | 0.41 ms | 1.18 ms | 2.9× |
| Apple silicon | — | Both | 0.33 ms | 0.33 ms | 1.0× |

Every Intel CPU tested is slow, including a 2025 high-end part, on both P-cores
and E-cores. AMD Zen 3 has a small penalty: 2.9× in Wasm and 1.1× in JS, 1.18 ms
against 7.65–57 ms on Intel. Apple silicon has none.

- **Slowdowns can't be compared across CPUs.** A slowdown is the subnormal time
  divided by the normal time, so faster code shows a larger one on the same chip
  (73× for Wasm, 44× for JS on the J4125). Compare the subnormal times instead.
- **Times aren't clock-normalized.** Tiger Lake against Panther Lake shows no
  improvement, but can't measure a small regression.

### Who is affected

Firefox users by CPU, from [telemetry](https://sql.telemetry.mozilla.org/queries/121973/source),
grouped by vendor and generation.

| CPU class | Subnormal penalty | Share |
|---|---|---|
| Intel, all generations; measured on Goldmont+, Tiger Lake, Panther Lake | Large penalty | 76.0% |
| AMD Zen 1–5, Hygon; measured on Zen 3 | Small penalty | 17.9% |
| Non-x86 (ARM, Apple, Qualcomm, HiSilicon, …); measured on Apple | No penalty | 0.3% |
| AMD before Zen (Bulldozer, Jaguar/Puma, K10, Bobcat, K8) | Unknown | 1.6% |
| Unknown or other | Unknown | 4.2% |

The Intel row spans Atom, the big cores before Skylake, Skylake to Tiger Lake,
and the hybrids. The three measured parts bracket that range and are all slow,
so the generations in between are assumed slow too. Older Intel parts had
similar or worse penalties.

### Without flushing

DSP in a worker, including MSTP/G processing, has no way to turn flushing on:
WebAssembly and JavaScript can’t change the CPU’s floating-point mode. The code
itself has to keep its state out of the subnormal range, in every site:

- **A noise floor in every recursive stage.** In this benchmark, a 1e-18 DC
  offset on the input removes the penalty on every CPU tested. Real processing
  needs it at each filter, feedback loop, envelope and reverb, not once at the
  input: a DC blocker, a highpass filter or a gain downstream removes or scales
  the offset, and the states after it decay again. Tiny noise or an offset of
  alternating sign survives DC blockers.
- **Explicit flushing.** Compare each state variable to a threshold and set it
  to zero, after every update. Faust’s `-ftz` option generates this. It costs a
  comparison per state per sample, and gets in the way of SIMD.

Native DSP code does neither. It relies on its host setting flush-to-zero on the
audio thread (JUCE’s `ScopedNoDenormals`, for example), so compiled to
WebAssembly it works as written in an `AudioWorkletProcessor`, where Firefox
flushes. In a worker, the same off-the-shelf WebAssembly breaks: it is 38–73×
slower on Intel as soon as a signal decays to silence, until each library is
patched.

### Conclusions

- **76% of Firefox users are on affected hardware.** Intel’s current high-end
  mobile part is 50× slower on subnormals. This won’t age out: newer or more
  expensive hardware doesn’t fix it.
- **The core type doesn’t matter.** Panther Lake’s cpu0 and cpu15 are within 10%
  (8.97 and 9.89 ms), so pinning DSP threads to particular cores doesn’t help.
- **Where the processing runs matters.** DSP in an `AudioWorkletProcessor`
  gets subnormals flushed to zero. The same DSP in a worker, as with MSTP/G,
  pays the full penalty on most users’ machines, unless every recursive stage of
  it is modified to avoid subnormals.
