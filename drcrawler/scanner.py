from __future__ import annotations

import os
import re
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import json_dump, new_id, now_iso, normalize_identifier
from .database import connect


SCANNER_VERSION = "metadata-v1"
MAX_DEPTH = 64
MAX_ITEMS = 2_000_000
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
TITLE_ID_RE = re.compile(r"\b(?:CUSA|PPSA|PCAS|PLAS)\d{5}\b", re.IGNORECASE)
VERSION_RE = re.compile(r"(?:\b(?:update|patch|version|ver|v)[ _.-]*)(\d+(?:[._-]\d+){0,3})", re.IGNORECASE)


class ScanManager:
    def __init__(self) -> None:
        self._cancel: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._active_roots: set[str] = set()
        self._lock = threading.Lock()

    def start(self, root_id: str) -> dict[str, Any]:
        with self._lock:
            if root_id in self._active_roots:
                raise ValueError("A scan is already running for this selected folder.")
            self._active_roots.add(root_id)
        worker_started = False
        conn = connect()
        try:
            root = conn.execute("SELECT * FROM local_root WHERE id=?", (root_id,)).fetchone()
            if not root:
                raise ValueError("Selected folder was not found in the local root list.")
            root_path = Path(root["display_path"])
            run_id = new_id()
            started = now_iso()
            if not root_path.exists() or not root_path.is_dir():
                with conn:
                    conn.execute("UPDATE local_root SET availability='unavailable' WHERE id=?", (root_id,))
                    conn.execute(
                        "INSERT INTO scan_run(id,root_id,started_at,completed_at,status,scope_json,scanner_version,reason) VALUES(?,?,?,?,?,?,?,?)",
                        (run_id, root_id, started, now_iso(), "unavailable", json_dump({"selected_path": str(root_path), "recursive": True}), SCANNER_VERSION, "Selected volume or folder is unavailable; the last inventory was preserved."),
                    )
                return {"id": run_id, "status": "unavailable", "reason": "Selected volume or folder is unavailable; the last inventory was preserved."}
            try:
                canonical = root_path.resolve(strict=True)
            except OSError as exc:
                with conn:
                    conn.execute("UPDATE local_root SET availability='unavailable' WHERE id=?", (root_id,))
                    conn.execute(
                        "INSERT INTO scan_run(id,root_id,started_at,completed_at,status,scope_json,scanner_version,reason) VALUES(?,?,?,?,?,?,?,?)",
                        (run_id, root_id, started, now_iso(), "unavailable", json_dump({"selected_path": str(root_path), "recursive": True}), SCANNER_VERSION, str(exc)[:500]),
                    )
                return {"id": run_id, "status": "unavailable", "reason": "Selected volume or folder is unavailable; the last inventory was preserved."}
            with conn:
                conn.execute("UPDATE local_root SET availability='scanning' WHERE id=?", (root_id,))
                conn.execute(
                    "INSERT INTO scan_run(id,root_id,started_at,status,scope_json,scanner_version) VALUES(?,?,?,?,?,?)",
                    (run_id, root_id, started, "running", json_dump({"selected_path": str(canonical), "recursive": True, "hashing": False}), SCANNER_VERSION),
                )
            cancel = threading.Event()
            thread = threading.Thread(target=self._run, args=(root_id, run_id, canonical, cancel), name=f"drc-scan-{run_id[:8]}", daemon=True)
            with self._lock:
                self._cancel[run_id] = cancel
                self._threads[run_id] = thread
            thread.start()
            worker_started = True
            return {"id": run_id, "status": "running"}
        finally:
            conn.close()
            if not worker_started:
                with self._lock:
                    self._active_roots.discard(root_id)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            signal = self._cancel.get(run_id)
        if signal:
            signal.set()
            return True
        return False

    def _run(self, root_id: str, run_id: str, root: Path, cancel: threading.Event) -> None:
        conn = connect()
        seen = 0
        errors = 0
        item_cap = False
        stack: list[tuple[Path, int]] = [(root, 0)]
        try:
            while stack:
                if cancel.is_set():
                    break
                folder, depth = stack.pop()
                if depth > MAX_DEPTH:
                    errors += 1
                    continue
                try:
                    folder_real = folder.resolve(strict=True)
                    if not is_within(folder_real, root) or folder_real != folder.absolute():
                        errors += 1
                        continue
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            if cancel.is_set():
                                break
                            try:
                                info = entry.stat(follow_symlinks=False)
                            except OSError:
                                errors += 1
                                continue
                            if getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
                                continue
                            if entry.is_symlink():
                                continue
                            entry_path = Path(entry.path)
                            if not is_within(entry_path.absolute(), root):
                                errors += 1
                                continue
                            if stat.S_ISDIR(info.st_mode):
                                if depth < MAX_DEPTH:
                                    stack.append((entry_path, depth + 1))
                                else:
                                    errors += 1
                                continue
                            if not stat.S_ISREG(info.st_mode):
                                continue
                            if seen >= MAX_ITEMS:
                                item_cap = True
                                break
                            relative = entry_path.relative_to(root).as_posix()
                            parsed = parse_filename(entry.name)
                            self._record_file(conn, root_id, run_id, entry_path, relative, info, parsed)
                            seen += 1
                            if seen % 200 == 0:
                                conn.commit()
                                conn.execute("UPDATE scan_run SET items_seen=?,errors_count=?,progress_path=? WHERE id=?", (seen, errors, relative[:1000], run_id))
                                conn.commit()
                        if item_cap:
                            break
                except OSError:
                    errors += 1
            cancelled = cancel.is_set()
            unavailable = not root.exists()
            complete = not cancelled and not unavailable and not errors and not item_cap
            status = "complete" if complete else "unavailable" if unavailable else "cancelled" if cancelled else "partial"
            reason = "" if complete else "Selected volume disconnected during the scan; the prior completed inventory was preserved." if unavailable else "Scan was cancelled; prior completed inventory remains in place." if cancelled else "Some folders could not be read or a safety limit was reached; unseen files were not marked missing."
            finished = now_iso()
            if complete:
                with conn:
                    conn.execute(
                        "UPDATE local_file SET presence_state='missing' WHERE root_id=? AND COALESCE(last_observed_run_id,last_seen_run_id)<>? AND presence_state IN ('present','observed_partial')",
                        (root_id, run_id),
                    )
                    conn.execute(
                        "UPDATE local_file SET presence_state='present',last_seen_run_id=? WHERE root_id=? AND last_observed_run_id=?",
                        (run_id, root_id, run_id),
                    )
                    conn.execute("UPDATE scan_run SET completed_at=?,status=?,items_seen=?,errors_count=?,reason=? WHERE id=?", (finished, status, seen, errors, reason, run_id))
                    conn.execute("UPDATE local_root SET availability='available',last_seen_at=? WHERE id=?", (finished, root_id))
            else:
                with conn:
                    conn.execute("UPDATE scan_run SET completed_at=?,status=?,items_seen=?,errors_count=?,reason=? WHERE id=?", (finished, status, seen, errors, reason, run_id))
                    conn.execute("UPDATE local_root SET availability=? WHERE id=?", ("unavailable" if unavailable else "available", root_id))
        except Exception as exc:
            missing_root = not root.exists()
            with conn:
                status = "unavailable" if missing_root else "partial"
                reason = "Selected volume disconnected during the scan; the prior completed inventory was preserved." if missing_root else f"Scan stopped after an unexpected metadata error: {str(exc)[:300]}"
                conn.execute("UPDATE scan_run SET completed_at=?,status=?,reason=? WHERE id=?", (now_iso(), status, reason, run_id))
                conn.execute("UPDATE local_root SET availability=? WHERE id=?", ("unavailable" if missing_root else "available", root_id))
        finally:
            conn.close()
            with self._lock:
                self._cancel.pop(run_id, None)
                self._threads.pop(run_id, None)
                self._active_roots.discard(root_id)

    @staticmethod
    def _record_file(conn: Any, root_id: str, run_id: str, path: Path, relative: str, info: os.stat_result, parsed: dict[str, Any]) -> None:
        stamp = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(timespec="seconds")
        normalized = relative.casefold()
        row = conn.execute("SELECT id,presence_state FROM local_file WHERE root_id=? AND normalized_path=?", (root_id, normalized)).fetchone()
        if row:
            presence = row["presence_state"] if row["presence_state"] == "present" else "observed_partial"
            conn.execute(
                """UPDATE local_file SET relative_path=?,name=?,extension=?,size_bytes=?,modified_at=?,package_guess=?,
                   parsed_title_id=?,parsed_version=?,last_observed_run_id=?,presence_state=?,parse_state='filename_only',
                   provenance='inferred',evidence_json=? WHERE id=?""",
                (relative, path.name, path.suffix.casefold(), info.st_size, stamp, parsed["guess"], parsed["title_id"], parsed["version"], run_id, presence, json_dump({"method": "filename and filesystem metadata only", "scanner_version": SCANNER_VERSION}), row["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO local_file(id,root_id,relative_path,normalized_path,name,extension,size_bytes,modified_at,
                   package_guess,parsed_title_id,parsed_version,last_observed_run_id,last_seen_run_id,presence_state,parse_state,
                   provenance,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,'observed_partial','filename_only','inferred',?)""",
                (new_id(), root_id, relative, normalized, path.name, path.suffix.casefold(), info.st_size, stamp, parsed["guess"], parsed["title_id"], parsed["version"], run_id, json_dump({"method": "filename and filesystem metadata only", "scanner_version": SCANNER_VERSION})),
            )


def is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root)))) == os.path.normcase(str(root))
    except (ValueError, OSError):
        return False


def parse_filename(name: str) -> dict[str, Any]:
    ext = Path(name).suffix.casefold()
    title_id_match = TITLE_ID_RE.search(name)
    version_match = VERSION_RE.search(name)
    guess = {
        ".pkg": "package_candidate",
        ".srt": "subtitle_candidate",
        ".ass": "subtitle_candidate",
        ".ssa": "subtitle_candidate",
        ".vtt": "subtitle_candidate",
        ".json": "sidecar_candidate",
        ".zip": "archive_candidate",
        ".png": "image_candidate",
        ".jpg": "image_candidate",
        ".jpeg": "image_candidate",
    }.get(ext, "file")
    return {
        "guess": guess,
        "title_id": normalize_identifier(title_id_match.group(0)) if title_id_match else None,
        "version": version_match.group(1).replace("_", ".").replace("-", ".") if version_match else None,
    }
