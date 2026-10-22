;; FIR filter in WebAssembly SIMD. Every processing path runs this same loop,
;; so CPU cost does not depend on a JavaScript engine's JIT.
;; Rebuild web/fir-wasm.js after editing: uv run tools/build_fir.py
;;
;; Memory layout, set up by web/dsp.js (byte offsets are passed in):
;;   coef    taps f32, reversed: coef[m] multiplies the m-th oldest sample.
;;   hist    2 * taps f32. Each sample is stored at pos and pos + taps, so
;;           the window hist[pos + 1 .. pos + taps] is contiguous, oldest first.
;;   in/out  count f32.
;; Returns the history position to pass to the next call.
(module
  (memory (export "memory") 1)
  (func (export "process")
    (param $coef i32) (param $hist i32) (param $taps i32) (param $pos i32)
    (param $in i32) (param $out i32) (param $count i32) (param $gain f32)
    (result i32)
    (local $i i32) (local $k i32) (local $vend i32) (local $window i32)
    (local $x f32) (local $sum f32) (local $acc v128)
    ;; Taps handled four at a time; the remainder is scalar.
    (local.set $vend (i32.and (local.get $taps) (i32.const -4)))
    (block $done
      (loop $samples
        (br_if $done (i32.ge_u (local.get $i) (local.get $count)))
        (local.set $x (f32.load (i32.add (local.get $in) (i32.shl (local.get $i) (i32.const 2)))))
        (f32.store (i32.add (local.get $hist) (i32.shl (local.get $pos) (i32.const 2))) (local.get $x))
        (f32.store (i32.add (local.get $hist) (i32.shl (i32.add (local.get $pos) (local.get $taps)) (i32.const 2)))
                   (local.get $x))
        (local.set $window (i32.add (local.get $hist) (i32.shl (i32.add (local.get $pos) (i32.const 1)) (i32.const 2))))
        (local.set $acc (v128.const f32x4 0 0 0 0))
        (local.set $k (i32.const 0))
        (block $vectors_done
          (loop $vectors
            (br_if $vectors_done (i32.ge_u (local.get $k) (local.get $vend)))
            (local.set $acc (f32x4.add (local.get $acc) (f32x4.mul
              (v128.load (i32.add (local.get $coef) (i32.shl (local.get $k) (i32.const 2))))
              (v128.load (i32.add (local.get $window) (i32.shl (local.get $k) (i32.const 2)))))))
            (local.set $k (i32.add (local.get $k) (i32.const 4)))
            (br $vectors)))
        (local.set $sum (f32.add
          (f32.add (f32x4.extract_lane 0 (local.get $acc)) (f32x4.extract_lane 1 (local.get $acc)))
          (f32.add (f32x4.extract_lane 2 (local.get $acc)) (f32x4.extract_lane 3 (local.get $acc)))))
        (block $tail_done
          (loop $tail
            (br_if $tail_done (i32.ge_u (local.get $k) (local.get $taps)))
            (local.set $sum (f32.add (local.get $sum) (f32.mul
              (f32.load (i32.add (local.get $coef) (i32.shl (local.get $k) (i32.const 2))))
              (f32.load (i32.add (local.get $window) (i32.shl (local.get $k) (i32.const 2)))))))
            (local.set $k (i32.add (local.get $k) (i32.const 1)))
            (br $tail)))
        (f32.store (i32.add (local.get $out) (i32.shl (local.get $i) (i32.const 2)))
                   (f32.mul (local.get $sum) (local.get $gain)))
        (local.set $pos (i32.add (local.get $pos) (i32.const 1)))
        (if (i32.eq (local.get $pos) (local.get $taps)) (then (local.set $pos (i32.const 0))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $samples)))
    (local.get $pos)))
