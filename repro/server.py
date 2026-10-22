"""Local HTTP server: serves web/ and receives the files each page uploads."""
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

# SharedArrayBuffer (the worker path) requires cross-origin isolation:
# COOP/COEP for the whole browsing context group, or Document Isolation Policy
# for a single document.
ISOLATION = {
    "coop-coep": {"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp"},
    "dip": {"Document-Isolation-Policy": "isolate-and-credentialless"},
}
UPLOAD = re.compile(r"^/upload/(?P<trial>[\w-]+)/(?P<name>[\w.-]+)$")


class Server:
    """Serve one trial: `PUT /upload/<trial>/<name>` writes `<directory>/<name>`."""

    def __init__(self, trial: str, directory: Path, isolation: str):
        headers = {"Cache-Control": "no-store", **ISOLATION[isolation]}

        class Handler(SimpleHTTPRequestHandler):
            extensions_map = {".js": "text/javascript", ".html": "text/html", ".wasm": "application/wasm"}

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(WEB), **kwargs)

            def end_headers(self):
                for key, value in headers.items():
                    self.send_header(key, value)
                super().end_headers()

            def do_PUT(self):
                match = UPLOAD.match(self.path)
                if not match or match["trial"] != trial:
                    self.send_error(404)
                    return
                body = self.rfile.read(int(self.headers["Content-Length"]))
                (directory / match["name"]).write_bytes(body)
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
