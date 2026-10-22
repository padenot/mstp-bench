;; 4-pole one-pole lowpass cascade: y += a * (x - y), state in globals.
;; Regenerate the base64 blob in denormals.html with:
;;   wat2wasm filter.wat -o filter.wasm && base64 -i filter.wasm
(module
  (global $y0 (mut f64) (f64.const 0))
  (global $y1 (mut f64) (f64.const 0))
  (global $y2 (mut f64) (f64.const 0))
  (global $y3 (mut f64) (f64.const 0))

  (func (export "seed") (param $v f64)
    (global.set $y0 (local.get $v))
    (global.set $y1 (local.get $v))
    (global.set $y2 (local.get $v))
    (global.set $y3 (local.get $v)))

  (func (export "level") (result f64)
    (f64.abs (global.get $y3)))

  ;; process(offset, x0, count) -> acc
  (func (export "process")
    (param $offset f64) (param $x0 f64) (param $count i32) (result f64)
    (local $x f64) (local $acc f64) (local $v f64) (local $i i32)
    (local.set $x (local.get $x0))
    (block $done
      (loop $loop
        (br_if $done (i32.ge_s (local.get $i) (local.get $count)))

        (local.set $v (f64.add (local.get $x) (local.get $offset)))
        (local.set $x (f64.const 0))

        (global.set $y0 (f64.add (global.get $y0)
          (f64.mul (f64.const 1e-4) (f64.sub (local.get $v) (global.get $y0)))))
        (local.set $v (global.get $y0))

        (global.set $y1 (f64.add (global.get $y1)
          (f64.mul (f64.const 1e-4) (f64.sub (local.get $v) (global.get $y1)))))
        (local.set $v (global.get $y1))

        (global.set $y2 (f64.add (global.get $y2)
          (f64.mul (f64.const 1e-4) (f64.sub (local.get $v) (global.get $y2)))))
        (local.set $v (global.get $y2))

        (global.set $y3 (f64.add (global.get $y3)
          (f64.mul (f64.const 1e-4) (f64.sub (local.get $v) (global.get $y3)))))
        (local.set $v (global.get $y3))

        (local.set $acc (f64.add (local.get $acc) (local.get $v)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $loop)))
    (local.get $acc))
)
