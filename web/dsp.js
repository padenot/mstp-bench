// The processing under test, identical in every path: either a block copy, or
// a long FIR filter compiled to WebAssembly SIMD (fir.wat). The filter is
// reproduced in repro/signal.py to compute the expected output.
import { FIR_WASM } from './fir-wasm.js';

const CHUNK = 4096; // Frames per call into WebAssembly.
let module;

// Coefficients: 0.5 for the current sample, then an exponentially decaying
// tail that sums to 0.5.
export function firCoefficients(taps) {
  const coefficients = new Float64Array(taps);
  let sum = 0;
  for (let i = 1; i < taps; i++) sum += coefficients[i] = Math.exp(-6 * i / taps);
  for (let i = 1; i < taps; i++) coefficients[i] *= 0.5 / sum;
  coefficients[0] = 0.5;
  return coefficients;
}

export class DSP {
  // options: { mode: 'copy' } or { mode: 'fir', taps, gain }
  constructor(options) {
    this.copy = options.mode === 'copy';
    if (this.copy) return;
    const { taps, gain } = options;
    const { exports } = new WebAssembly.Instance(module ??= new WebAssembly.Module(FIR_WASM));
    const history = taps * 4, input = history + taps * 8, output = input + CHUNK * 4;
    exports.memory.grow(Math.ceil((output + CHUNK * 4) / 65536) - 1);
    new Float32Array(exports.memory.buffer, 0, taps).set(firCoefficients(taps).reverse());
    this.fir = exports.process;
    this.taps = taps; this.gain = gain; this.position = 0;
    this.offsets = { history, input, output };
    this.input = new Float32Array(exports.memory.buffer, input, CHUNK);
    this.output = new Float32Array(exports.memory.buffer, output, CHUNK);
  }

  // Element-wise copies keep this allocation-free on real-time threads.
  process(input, output) {
    if (this.copy) {
      for (let i = 0; i < input.length; i++) output[i] = input[i];
      return;
    }
    const { history, input: wasmIn, output: wasmOut } = this.offsets;
    for (let offset = 0; offset < input.length; offset += CHUNK) {
      const count = Math.min(CHUNK, input.length - offset);
      for (let i = 0; i < count; i++) this.input[i] = input[offset + i];
      this.position = this.fir(0, history, this.taps, this.position, wasmIn, wasmOut, count, this.gain);
      for (let i = 0; i < count; i++) output[offset + i] = this.output[i];
    }
  }
}
