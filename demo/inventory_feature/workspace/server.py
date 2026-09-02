from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from inventory.domain import load_inventory


ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "demo_inventory.json"


class InventoryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "static"), **kwargs)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/inventory":
            self.send_json(200, {"products": load_inventory(DATA_PATH)})
            return
        super().do_GET()

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), InventoryHandler)
    print("Stockroom running at http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
