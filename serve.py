#!/usr/bin/env python3
"""Serve the tool locally (needed so the browser can fetch the JSON dataset).

    python3 serve.py            # http://localhost:8000/web/index.html
    python3 serve.py 9000       # custom port

Three things matter here once the dataset is large:

* **Threaded.** The old single-threaded server handled one request at a time,
  so a multi-MB dataset download blocked every stylesheet and script behind it.
* **Pre-compressed.** The pipeline writes ``graph.json.gz`` next to
  ``graph.json``; this serves that file directly when the client accepts gzip
  (roughly 8x on this JSON). Nothing is compressed per request.
* **Cacheable data.** ``no-store`` is scoped to markup and code so the dataset
  gets normal ``Last-Modified`` / 304 handling instead of a full re-download on
  every navigation between the graph and search pages.
"""
import http.server
import os
import sys
import webbrowser

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

NO_STORE_EXT = (".html", ".js", ".css")


class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        """Transparently serve a pre-built .gz sibling when one exists."""
        path = self.translate_path(self.path)
        if (not path.endswith(".gz")
                and "gzip" in self.headers.get("Accept-Encoding", "")
                and os.path.isfile(path + ".gz")):
            self._gz_for = path
            self.path += ".gz"
        return super().send_head()

    def guess_type(self, path):
        # The .gz sibling must keep the underlying type; the encoding header
        # is what tells the browser to inflate it.
        if getattr(self, "_gz_for", None) and path.endswith(".gz"):
            return super().guess_type(path[:-3])
        return super().guess_type(path)

    def end_headers(self):
        if getattr(self, "_gz_for", None):
            self.send_header("Content-Encoding", "gzip")
            self._gz_for = None
        if self.path.split("?")[0].endswith(NO_STORE_EXT):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):  # quieter console
        pass


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


with Server(("", PORT), Handler) as httpd:
    url = f"http://localhost:{PORT}/web/index.html"
    print(f"Neuro Labs Explorer → {url}\nCtrl-C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
