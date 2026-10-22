from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .database import connect, get_data_dir
from .services import Application, get_game, get_jobs, get_preferences, get_roots, get_sources, list_games


STATIC_DIR = Path(__file__).parent / "static"
MAX_REQUEST_BYTES = 3_000_000


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(app: Application, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"DRCrawler/{__version__}"
        sys_version = ""

        def log_message(self, fmt: str, *args: object) -> None:
            # Keep local collection data and paths out of routine terminal logs.
            return

        def _host_ok(self) -> bool:
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            return self.headers.get("Host", "").casefold() in allowed

        def _api_guard(self, write: bool = False) -> bool:
            if not self._host_ok():
                self._send_json({"error": "Host is not allowed."}, 403)
                return False
            if self.headers.get("X-DRC-Token") != token:
                self._send_json({"error": "Local session token is missing."}, 403)
                return False
            origin = self.headers.get("Origin")
            if write and origin:
                expected = f"http://{self.headers.get('Host')}"
                if origin != expected:
                    self._send_json({"error": "Cross-origin requests are not allowed."}, 403)
                    return False
            return True

        def _send_json(self, value: object, status: int = 200) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json({"error": "Invalid request length."}, 400)
                raise StopIteration
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._send_json({"error": "Request body is empty or exceeds the 3 MB limit."}, 413)
                raise StopIteration
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json({"error": "Request body must be UTF-8 JSON."}, 400)
                raise StopIteration
            if not isinstance(value, dict):
                self._send_json({"error": "Request body must be a JSON object."}, 400)
                raise StopIteration
            return value

        def _api(self, method: str, body: dict | None = None) -> None:
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            parts = [part for part in path.split("/") if part]
            try:
                if method == "GET" and path == "/api/bootstrap":
                    self._send_json(app.bootstrap())
                    return
                if method == "GET" and path == "/api/games":
                    self._send_json(list_games())
                    return
                if method == "POST" and path == "/api/games":
                    self._send_json(app.create_game(body or {}), 201)
                    return
                if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "games"]:
                    result = get_game(parts[2])
                    self._send_json(result or {"error": "Game not found."}, 200 if result else 404)
                    return
                if method == "POST" and path == "/api/import/preview":
                    result = app.prepare_import(str((body or {}).get("filename", "import.csv")), str((body or {}).get("contents", "")))
                    self._send_json(result, 201)
                    return
                if method == "POST" and path == "/api/import/commit":
                    result = app.commit_import(str((body or {}).get("token", "")), (body or {}).get("decisions", []))
                    self._send_json(result)
                    return
                if method == "GET" and path == "/api/sources":
                    self._send_json(get_sources())
                    return
                if method == "GET" and len(parts) == 4 and parts[:2] == ["api", "sources"] and parts[3] == "checks":
                    self._send_json(app.source_checks(parts[2]))
                    return
                if method == "POST" and path == "/api/sources":
                    self._send_json(app.save_source(body or {}), 201)
                    return
                if method == "PUT" and len(parts) == 3 and parts[:2] == ["api", "sources"]:
                    self._send_json(app.save_source(body or {}, parts[2]))
                    return
                if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "sources"] and parts[3] == "checks":
                    self._send_json(app.record_source_check(parts[2], body or {}), 201)
                    return
                if method == "POST" and path == "/api/candidates":
                    self._send_json(app.add_candidate(body or {}), 201)
                    return
                if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "candidates"] and parts[3] == "assess":
                    self._send_json(app.assess_candidate(parts[2]))
                    return
                if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "candidates"] and parts[3] == "link-local":
                    self._send_json(app.link_local_file(parts[2], str((body or {}).get("file_id", ""))))
                    return
                if method == "GET" and path == "/api/local-files":
                    query = parse_qs(parsed.query).get("q", [""])[0]
                    self._send_json(app.find_local_files(query))
                    return
                if method == "GET" and path == "/api/roots":
                    self._send_json(get_roots())
                    return
                if method == "POST" and path == "/api/pick-folder":
                    self._send_json(app.choose_folder(str((body or {}).get("initial_dir", ""))))
                    return
                if method == "GET" and len(parts) == 4 and parts[:2] == ["api", "roots"] and parts[3] == "files":
                    self._send_json(app.root_files(parts[2]))
                    return
                if method == "POST" and path == "/api/roots":
                    self._send_json(app.add_root(str((body or {}).get("path", ""))), 201)
                    return
                if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "roots"] and parts[3] == "scan":
                    self._send_json(app.start_scan(parts[2]), 202)
                    return
                if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "scans"]:
                    result = app.get_scan(parts[2])
                    self._send_json(result or {"error": "Scan run not found."}, 200 if result else 404)
                    return
                if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "scans"] and parts[3] == "cancel":
                    ok = app.cancel_scan(parts[2])
                    self._send_json({"cancel_requested": ok}, 200 if ok else 409)
                    return
                if method == "GET" and path == "/api/jobs":
                    self._send_json(get_jobs())
                    return
                if method == "POST" and path == "/api/jobs":
                    self._send_json(app.create_download_job(str((body or {}).get("content_item_id", "")), str((body or {}).get("observation_id", "")), str((body or {}).get("destination_dir", ""))), 201)
                    return
                if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "jobs"]:
                    job_id, action = parts[2], parts[3]
                    if action == "approve":
                        self._send_json(app.approve_job(job_id, bool((body or {}).get("rights_confirmed")), bool((body or {}).get("uncertainty_ack"))))
                        return
                    if action == "start":
                        self._send_json(app.start_download(job_id), 202)
                        return
                    if action == "cancel":
                        self._send_json(app.cancel_download(job_id))
                        return
                    if action == "reject":
                        self._send_json(app.reject_job(job_id))
                        return
                if method == "GET" and path == "/api/preferences":
                    self._send_json(get_preferences())
                    return
                if method == "POST" and path == "/api/preferences":
                    self._send_json(app.update_preferences(body or {}))
                    return
                self._send_json({"error": "Route not found."}, 404)
            except StopIteration:
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception:
                self._send_json({"error": "The operation could not be completed. No source content was executed."}, 500)

        def do_GET(self) -> None:
            if self.path.startswith("/api/"):
                if self._api_guard():
                    self._api("GET")
                return
            if not self._host_ok():
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            if path == "/":
                file_path = STATIC_DIR / "index.html"
                content_type = "text/html; charset=utf-8"
            elif path in ("/styles.css", "/app.js"):
                file_path = STATIC_DIR / path.lstrip("/")
                content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                if path.endswith(".js"):
                    content_type += "; charset=utf-8"
            else:
                self.send_error(404)
                return
            try:
                content = file_path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            if path == "/":
                content = content.replace(b"__DRC_TOKEN__", token.encode("ascii"))
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self) -> None:
            if not self._api_guard(write=True):
                return
            try:
                body = self._read_json()
            except StopIteration:
                return
            self._api("POST", body)

        def do_PUT(self) -> None:
            if not self._api_guard(write=True):
                return
            try:
                body = self._read_json()
            except StopIteration:
                return
            self._api("PUT", body)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local DR Crawler library manager.")
    parser.add_argument("--port", type=int, default=0, help="Local port (default: choose an available port).")
    parser.add_argument("--no-browser", action="store_true", help="Print the local URL without opening a browser tab.")
    args = parser.parse_args()
    connect().close()
    token = secrets.token_urlsafe(32)
    server = LocalServer(("127.0.0.1", args.port), make_handler(Application(), token))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"DR Crawler {__version__} is running locally at {url}")
    print(f"Local database folder: {get_data_dir()}")
    print("Keep this terminal open while using the app. Press Ctrl+C to stop it.")
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("Stopping DR Crawler.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
