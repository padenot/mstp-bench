// Single-producer, single-consumer ring of float samples in a SharedArrayBuffer.
//
// Layout: two Int32 indices [read, write], then capacity + 1 samples. One slot
// stays empty to distinguish full from empty. Each side writes only its own
// index, with Atomics.store after touching the samples; the other side reads
// it with Atomics.load before touching them, so data is always complete.
// No allocation: safe on real-time threads.

const READ = 0, WRITE = 1;

export class Ring {
  static bytes(capacity) { return 8 + (capacity + 1) * 4; }

  constructor(buffer) {
    this.indices = new Int32Array(buffer, 0, 2);
    this.data = new Float32Array(buffer, 8);
    this.size = this.data.length;
  }

  availableRead() {
    const read = Atomics.load(this.indices, READ), write = Atomics.load(this.indices, WRITE);
    return (write - read + this.size) % this.size;
  }

  availableWrite() { return this.size - 1 - this.availableRead(); }

  // Callers check availableWrite() first; a short write is a caller bug.
  push(samples) {
    if (samples.length > this.availableWrite()) throw new Error('Ring overflow');
    let write = Atomics.load(this.indices, WRITE);
    for (let i = 0; i < samples.length; i++) {
      this.data[write] = samples[i];
      if (++write === this.size) write = 0;
    }
    Atomics.store(this.indices, WRITE, write);
  }

  // Callers check availableRead() first.
  pop(target) {
    if (target.length > this.availableRead()) throw new Error('Ring underflow');
    let read = Atomics.load(this.indices, READ);
    for (let i = 0; i < target.length; i++) {
      target[i] = this.data[read];
      if (++read === this.size) read = 0;
    }
    Atomics.store(this.indices, READ, read);
  }
}
