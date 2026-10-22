from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Any

from .core import normalize_identifier, normalize_text, validate_game_record


MAX_IMPORT_BYTES = 2_000_000
MAX_IMPORT_ROWS = 2_000


def parse_import(filename: str, contents: str) -> list[dict[str, Any]]:
    if len(contents.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise ValueError("Import is larger than 2 MB.")
    suffix = filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
    if suffix == "json" or contents.lstrip().startswith("{"):
        try:
            payload = json.loads(contents)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parse error on line {exc.lineno}: {exc.msg}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("games"), list):
            raise ValueError("JSON must contain schema_version: 1 and a games array.")
        raw_rows = payload["games"]
        if len(raw_rows) > MAX_IMPORT_ROWS:
            raise ValueError(f"Import is limited to {MAX_IMPORT_ROWS} games at a time.")
        return [row if isinstance(row, dict) else {"_invalid": row} for row in raw_rows]
    reader = csv.DictReader(io.StringIO(contents, newline=""))
    if not reader.fieldnames:
        raise ValueError("CSV needs a header row.")
    fields = {str(x).strip().lstrip("\ufeff").casefold() for x in reader.fieldnames if x is not None}
    if "platform" not in fields or not ({"title", "title_id", "product_code"} & fields):
        raise ValueError("CSV needs platform and at least one of title, title_id, or product_code columns.")
    raw_rows = list(reader)
    if len(raw_rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"Import is limited to {MAX_IMPORT_ROWS} games at a time.")
    cleaned = []
    for row in raw_rows:
        cleaned.append({(key or "").strip().lstrip("\ufeff").casefold(): value for key, value in row.items()})
    return cleaned


def preview_import(conn: sqlite3.Connection, filename: str, contents: str) -> dict[str, Any]:
    raw_rows = parse_import(filename, contents)
    all_existing = conn.execute(
        """SELECT g.id,g.canonical_title,g.normalized_title,r.platform,r.title_id,r.normalized_title_id,
                  r.product_code,r.normalized_product_code,r.region
           FROM game g JOIN game_release r ON r.game_id=g.id ORDER BY g.canonical_title"""
    ).fetchall()
    seen: dict[tuple[str, str], int] = {}
    seen_titles: dict[tuple[str, str], int] = {}
    preview = []
    for index, raw in enumerate(raw_rows):
        record, error = validate_game_record(raw) if "_invalid" not in raw else (None, "row must be an object")
        line = index + (2 if filename.casefold().endswith(".csv") else 1)
        if error:
            preview.append({"index": index, "line": line, "status": "invalid", "error": error, "record": raw, "matches": [], "default_action": "skip"})
            continue
        title_key = normalize_text(record["title"])
        title_id = normalize_identifier(record.get("title_id"))
        product = normalize_identifier(record.get("product_code"))
        matches = []
        for old in all_existing:
            if old["platform"] != record["platform"]:
                continue
            exact_id = bool(title_id and title_id == (old["normalized_title_id"] or ""))
            exact_product = bool(product and product == (old["normalized_product_code"] or ""))
            same_title = bool(title_key and title_key == old["normalized_title"])
            if exact_id or exact_product:
                matches.append({"game_id": old["id"], "title": old["canonical_title"], "kind": "exact_identifier"})
            elif same_title:
                matches.append({"game_id": old["id"], "title": old["canonical_title"], "kind": "same_title"})
        identity_key = (record["platform"], f"id:{title_id}" if title_id else f"product:{product}" if product else f"title:{title_key}")
        duplicate_in_batch = seen.get(identity_key)
        seen.setdefault(identity_key, index)
        title_in_batch = seen_titles.get((record["platform"], title_key)) if title_key else None
        if title_in_batch is not None and title_in_batch != duplicate_in_batch:
            matches.append({"game_id": None, "title": f"Import row {title_in_batch + 1}", "kind": "same_title_in_file", "row_index": title_in_batch})
        if title_key:
            seen_titles.setdefault((record["platform"], title_key), index)
        if duplicate_in_batch is not None:
            matches.append({"game_id": None, "title": f"Import row {duplicate_in_batch + 1}", "kind": "duplicate_in_file", "row_index": duplicate_in_batch})
        if duplicate_in_batch is not None or any(m["kind"] == "exact_identifier" for m in matches):
            status, default_action = "duplicate", "skip"
        elif matches:
            status, default_action = "ambiguous", "review"
        else:
            status, default_action = "ready", "new"
        preview.append({
            "index": index,
            "line": line,
            "status": status,
            "error": None,
            "record": record,
            "matches": matches,
            "default_action": default_action,
        })
    return {"filename": filename[:256], "rows": preview}
