#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.12,<3"]
# ///
"""Local confirmation UI; no freee API calls or automatic confirmations."""
from __future__ import annotations

import argparse
import hmac
import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from freee_deals import confirm, create_export, load_queue, queue_rows, save_queue
from queue_store import queue_lock
from schemas import StrictModel, Text

ASSETS = Path(__file__).resolve().parents[1] / "assets"


class ConfirmationRequest(StrictModel):
    draft_id: Text
    revision: Text


def make_server(queue_path: Path, port: int, token: str) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass  # Do not log receipt data, request bodies, or access tokens.

        def send_content(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status: int, value: object) -> None:
            self.send_content(status, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def allowed(self) -> bool:
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != origin.removeprefix("http://"):
                self.send_json(403, {"error": "起動時の127.0.0.1のURLを使ってください。"})
                return False
            if self.headers.get("Origin", origin) != origin:
                self.send_json(403, {"error": "別のサイトからの操作は受け付けません。"})
                return False
            if not hmac.compare_digest(self.headers.get("X-Kicho-Token", "").encode(), token.encode()):
                self.send_json(401, {"error": "起動時に表示されたURLから開き直してください。"})
                return False
            return True

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            static = {"/": ("freee-review.html", "text/html; charset=utf-8"),
                      "/review.js": ("freee-review.js", "text/javascript; charset=utf-8"),
                      "/review.css": ("freee-review.css", "text/css; charset=utf-8")}
            try:
                if path in static:
                    filename, content_type = static[path]
                    self.send_content(200, (ASSETS / filename).read_bytes(), content_type)
                    return
                if not self.allowed():
                    return
                with queue_lock(queue_path):
                    queue = load_queue(queue_path)
                if path == "/api/queue":
                    self.send_json(200, {"client_id": queue.mapping.client_id, "rows": queue_rows(queue),
                                         "exports": [{"batch_id": batch.batch_id, "created_at": batch.created_at,
                                                      "count": len(batch.draft_ids)} for batch in queue.exports]})
                elif path.startswith("/api/exports/"):
                    batch_id = path.removeprefix("/api/exports/")
                    batch = next((batch for batch in queue.exports if batch.batch_id == batch_id), None)
                    if batch is None:
                        self.send_json(404, {"error": "出力ファイルが見つかりません。"})
                    else:
                        self.send_content(200, batch.csv_text.encode("utf-8-sig"), "text/csv; charset=utf-8",
                                          f"freee-{batch.batch_id}.csv")
                else:
                    self.send_json(404, {"error": "ページが見つかりません。"})
            except (OSError, ValueError):
                self.send_json(400, {"error": "確認キューを読み取れません。ファイルの形式を確認してください。"})

        def do_POST(self) -> None:
            if not self.allowed():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 4096 or self.headers.get_content_type() != "application/json":
                    self.send_json(400, {"error": "操作の形式が正しくありません。"})
                    return
                body = json.loads(self.rfile.read(length))
                path = urlsplit(self.path).path
                with queue_lock(queue_path):
                    queue = load_queue(queue_path)
                    if path in ("/api/confirm", "/api/unconfirm"):
                        request = ConfirmationRequest.model_validate(body)
                        if path == "/api/confirm":
                            confirm(queue, request.draft_id, request.revision)
                        else:
                            row = next((r for r in queue_rows(queue) if r["draft_id"] == request.draft_id), None)
                            if row is None or row["exported"] or row["revision"] != request.revision:
                                raise ValueError("stale confirmation")
                            queue.confirmations.pop(request.draft_id, None)
                        result = {"ok": True}
                    elif path == "/api/export" and body == {}:
                        batch = create_export(queue)
                        result = {"batch_id": batch.batch_id, "count": len(batch.draft_ids)}
                    else:
                        self.send_json(404, {"error": "操作が見つかりません。"})
                        return
                    save_queue(queue_path, queue)
                self.send_json(200, result)
            except (OSError, ValueError):
                self.send_json(400, {"error": "操作できません。対象が更新されたか、出力条件を満たしていません。再読込してください。"})

    return HTTPServer(("127.0.0.1", port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and confirm freee deal drafts locally")
    parser.add_argument("queue", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        load_queue(args.queue)
        token = secrets.token_urlsafe(32)
        server = make_server(args.queue.resolve(), args.port, token)
    except (OSError, ValueError):
        print("確認画面を起動できません。キューの形式とポートの空きを確認してください。", file=sys.stderr)
        return 2
    print(f"確認画面: http://127.0.0.1:{server.server_port}/#{token}", flush=True)
    print("終了: Ctrl+C。確定とCSV出力の履歴は確認キューに保存されます。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
