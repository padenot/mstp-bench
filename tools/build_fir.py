"""Compile web/fir.wat into web/fir-wasm.js. Requires wat2wasm (WABT).

Worklet scopes have neither fetch() nor atob(), so the module bytes are
embedded as an array literal.
"""
import hashlib
import subprocess
from pathlib import Path

web = Path(__file__).resolve().parent.parent / "web"
source = web / "fir.wat"
wasm = subprocess.run(["wat2wasm", str(source), "--output=-"], check=True, capture_output=True).stdout
(web / "fir-wasm.js").write_text(
    "// Generated from fir.wat by tools/build_fir.py; do not edit.\n"
    f"// fir.wat SHA-256: {hashlib.sha256(source.read_bytes()).hexdigest()}\n"
    f"export const FIR_WASM = new Uint8Array([{','.join(map(str, wasm))}]);\n")
