from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .compatibility import assess
from .core import candidate_identity_digest, digest_json, json_dump, json_load, new_id, normalize_identifier, normalize_language_tag, normalize_text, now_iso, validate_category, validate_game_record, validate_platform, validate_source_fields, validate_source_url
from .database import audit, connect, coverage_for_game, game_detail, get_data_dir, insert_game, rowdict, source_list
from .downloads import DownloadManager, allowed_hosts, create_job, validate_download_url
from .importer import preview_import
from .scanner import ScanManager


class Application:
    def __init__(self) -> None:
        self.scans = ScanManager()
        self.downloads = DownloadManager()
        self._imports: dict[str, dict[str, Any]] = {}
        self._import_lock = threading.Lock()

    def bootstrap(self) -> dict[str, Any]:
        conn = connect()
        try:
            games = __import__("drcrawler.database", fromlist=["all_games"]).all_games(conn)
            sources = source_list(conn)
            roots = self._roots(conn)
            jobs = self._jobs(conn)
            counts = {
                "games": len(games),
                "sources": len(sources),
                "local_roots": len(roots),
                "local_files": conn.execute("SELECT COUNT(*) FROM local_file WHERE presence_state='present'").fetchone()[0],
                "pending_approvals": conn.execute("SELECT COUNT(*) FROM download_job WHERE status='awaiting_approval'").fetchone()[0],
                "active_downloads": conn.execute("SELECT COUNT(*) FROM download_job WHERE status IN ('queued','downloading')").fetchone()[0],
                "stale_coverage": self._stale_count(conn, games),
            }
            preferences = {r["key"]: json_load(r["value_json"]) for r in conn.execute("SELECT key,value_json FROM user_preference")}
            recent = [dict(row) for row in conn.execute("SELECT * FROM audit_event ORDER BY timestamp DESC LIMIT 12")]
            for row in recent:
                row["details"] = json_load(row.pop("details_json", "{}"))
            return {"games": games, "sources": sources, "roots": roots, "jobs": jobs, "counts": counts, "preferences": preferences, "recent_activity": recent, "data_dir": str(get_data_dir())}
        finally:
            conn.close()

    def _stale_count(self, conn: Any, games: list[dict[str, Any]]) -> int:
        return sum(1 for game in games for item in coverage_for_game(conn, game["id"]) if item["state"] == "stale")

    @staticmethod
    def _roots(conn: Any) -> list[dict[str, Any]]:
        from .database import all_roots

        return all_roots(conn)

    @staticmethod
    def _jobs(conn: Any) -> list[dict[str, Any]]:
        from .database import all_jobs

        return all_jobs(conn)

    def create_game(self, data: dict[str, Any]) -> dict[str, Any]:
        record, error = validate_game_record(data)
        if error:
            raise ValueError(error)
        record["source"] = "manual"
        conn = connect()
        try:
            with conn:
                title_id = normalize_identifier(record.get("title_id"))
                product_code = normalize_identifier(record.get("product_code"))
                duplicate = None
                if title_id:
                    duplicate = conn.execute("SELECT g.canonical_title FROM game_release r JOIN game g ON g.id=r.game_id WHERE r.platform=? AND r.normalized_title_id=? LIMIT 1", (record["platform"], title_id)).fetchone()
                if duplicate is None and product_code:
                    duplicate = conn.execute("SELECT g.canonical_title FROM game_release r JOIN game g ON g.id=r.game_id WHERE r.platform=? AND r.normalized_product_code=? LIMIT 1", (record["platform"], product_code)).fetchone()
                if duplicate is None:
                    duplicate = conn.execute("SELECT g.canonical_title FROM game g JOIN game_release r ON r.game_id=g.id WHERE g.normalized_title=? AND r.platform=? LIMIT 1", (normalize_text(record["title"]), record["platform"])).fetchone()
                if duplicate:
                    raise ValueError(f"A possible duplicate already exists: {duplicate['canonical_title']}. Use import preview to review a merge.")
                game_id, release_id = insert_game(conn, record, provenance="user_confirmed")
                audit(conn, "game_added", "game", game_id, {"release_id": release_id, "platform": record["platform"], "title": record["title"], "source": "manual"})
            return game_detail(conn, game_id) or {}
        finally:
            conn.close()

    def prepare_import(self, filename: str, contents: str) -> dict[str, Any]:
        conn = connect()
        try:
            preview = preview_import(conn, filename, contents)
        finally:
            conn.close()
        token = new_id()
        with self._import_lock:
            self._imports[token] = preview
        return {"token": token, **preview}

    def commit_import(self, token: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        with self._import_lock:
            preview = self._imports.get(token)
        if not preview:
            raise ValueError("Import preview expired. Preview the file again before importing.")
        decision_map = {int(item.get("index", -1)): item for item in decisions if isinstance(item, dict)}
        conn = connect()
        added = 0
        skipped = 0
        merged = 0
        outcomes = []
        try:
            with conn:
                for row in preview["rows"]:
                    decision = decision_map.get(row["index"], {})
                    action = str(decision.get("action", row["default_action"]))
                    if row["status"] == "invalid" or action == "skip" or action == "review":
                        skipped += 1
                        outcomes.append({"index": row["index"], "action": "skip", "status": row["status"]})
                        continue
                    if action not in ("new", "merge"):
                        raise ValueError("Each reviewed row must be imported as new, merged with a selected game, or skipped.")
                    record = row["record"]
                    target_id = None
                    if action == "merge":
                        target_id = str(decision.get("target_game_id", ""))
                        if not target_id or not conn.execute("SELECT 1 FROM game WHERE id=?", (target_id,)).fetchone():
                            raise ValueError("Choose an existing game for every merge action.")
                    game_id, release_id = insert_game(conn, record, game_id=target_id, provenance="imported")
                    outcome = "merged" if target_id else "added"
                    merged += bool(target_id)
                    added += not bool(target_id)
                    audit(conn, "game_imported", "game", game_id, {"release_id": release_id, "filename": preview["filename"], "row": row["line"], "action": action, "record": record}, provenance="imported")
                    outcomes.append({"index": row["index"], "action": outcome, "game_id": game_id})
            with self._import_lock:
                self._imports.pop(token, None)
            return {"added": added, "merged": merged, "skipped": skipped, "outcomes": outcomes}
        finally:
            conn.close()

    def save_source(self, data: dict[str, Any], source_id: str | None = None) -> dict[str, Any]:
        fields = validate_source_fields(data)
        conn = connect()
        try:
            with conn:
                stamp = now_iso()
                if source_id:
                    old = conn.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
                    if not old:
                        raise ValueError("Source was not found.")
                    old_policy = json_load(old["policy_json"])
                    new_policy = fields["policy"]
                    if ({k: v for k, v in old_policy.items() if k != "policy_version"} != {k: v for k, v in new_policy.items() if k != "policy_version"}
                            or old["base_uri"] != fields["base_uri"]
                            or old["terms_uri"] != fields["terms_uri"]
                            or old["verification_note"] != fields["verification_note"]
                            or old["attribution"] != fields["attribution"]
                            or old["maintainer"] != fields["maintainer"]
                            or old["trust_tier"] != fields["trust_tier"]
                            or bool(old["enabled"]) != fields["enabled"]):
                        new_policy["policy_version"] = max(int(old_policy.get("policy_version", 1)) + 1, int(new_policy.get("policy_version", 1)))
                    else:
                        new_policy["policy_version"] = int(old_policy.get("policy_version", 1))
                    conn.execute(
                        """UPDATE source SET name=?,source_type=?,base_uri=?,trust_tier=?,enabled=?,attribution=?,maintainer=?,
                           verification_note=?,terms_uri=?,reviewed_at=?,policy_json=?,capabilities_json=?,health_state=?,updated_at=? WHERE id=?""",
                        (fields["name"], fields["source_type"], fields["base_uri"], fields["trust_tier"], int(fields["enabled"]), fields["attribution"], fields["maintainer"], fields["verification_note"], fields["terms_uri"], fields["reviewed_at"], json_dump(new_policy), json_dump(fields["capabilities"]), fields["health_state"], stamp, source_id),
                    )
                    audit(conn, "source_updated", "source", source_id, {"name": fields["name"], "policy_version": new_policy["policy_version"]})
                else:
                    source_id = new_id()
                    conn.execute(
                        """INSERT INTO source(id,name,source_type,base_uri,trust_tier,enabled,attribution,maintainer,terms_uri,
                           verification_note,reviewed_at,policy_json,capabilities_json,health_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (source_id, fields["name"], fields["source_type"], fields["base_uri"], fields["trust_tier"], int(fields["enabled"]), fields["attribution"], fields["maintainer"], fields["terms_uri"], fields["verification_note"], fields["reviewed_at"], json_dump(fields["policy"]), json_dump(fields["capabilities"]), fields["health_state"], stamp, stamp),
                    )
                    audit(conn, "source_added", "source", source_id, {"name": fields["name"], "trust_tier": fields["trust_tier"], "policy_status": fields["policy"]["review_status"]})
            return next(x for x in __import__("drcrawler.database", fromlist=["source_list"]).source_list(conn) if x["id"] == source_id)
        finally:
            conn.close()

    def record_source_check(self, source_id: str, data: dict[str, Any]) -> dict[str, Any]:
        release_id = str(data.get("release_id", ""))
        category = validate_category(str(data.get("category", "")))
        outcome = str(data.get("outcome", ""))
        if outcome not in ("checked_found", "checked_no_result", "unavailable", "blocked_by_policy", "unsupported", "error"):
            raise ValueError("Choose a valid source check result.")
        reason = str(data.get("reason", "")).strip()[:1000]
        conn = connect()
        try:
            with conn:
                source = conn.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
                release = conn.execute("SELECT * FROM game_release WHERE id=?", (release_id,)).fetchone()
                if not source or not release:
                    raise ValueError("Choose an existing source and game release.")
                policy = json_load(source["policy_json"])
                caps = json_load(source["capabilities_json"])
                supports = release["platform"] in caps.get("platforms", []) and category in caps.get("categories", [])
                if outcome in ("checked_found", "checked_no_result") and not supports:
                    raise ValueError("The source does not declare this platform and category. Record unsupported or update its capabilities after review.")
                if outcome == "checked_found":
                    count = conn.execute("SELECT COUNT(*) FROM source_observation so JOIN content_item ci ON ci.id=so.content_item_id WHERE so.source_id=? AND ci.release_id=? AND ci.category=?", (source_id, release_id, category)).fetchone()[0]
                    if count == 0:
                        raise ValueError("Add at least one source candidate before recording a found result.")
                if outcome == "blocked_by_policy":
                    reason = reason or "Automated access was blocked by source policy."
                stamp = now_iso()
                check_id = new_id()
                conn.execute(
                    "INSERT INTO source_check(id,release_id,source_id,category,started_at,completed_at,outcome,reason,query_digest,adapter_version,provenance) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (check_id, release_id, source_id, category, stamp, stamp, outcome, reason, digest_json({"source_id": source_id, "release_id": release_id, "category": category}), "manual-v1", "user_confirmed"),
                )
                health = {"checked_found": "healthy", "checked_no_result": "healthy", "unavailable": "unavailable", "blocked_by_policy": "blocked", "unsupported": source["health_state"], "error": "limited"}[outcome]
                conn.execute("UPDATE source SET health_state=?,updated_at=? WHERE id=?", (health, stamp, source_id))
                audit(conn, "source_check_recorded", "source_check", check_id, {"source_id": source_id, "release_id": release_id, "category": category, "outcome": outcome, "reason": reason, "source_policy_status": policy.get("review_status")})
            return {"id": check_id, "outcome": outcome, "completed_at": stamp}
        finally:
            conn.close()

    def add_candidate(self, data: dict[str, Any]) -> dict[str, Any]:
        release_id = str(data.get("release_id", ""))
        source_id = str(data.get("source_id", ""))
        category = validate_category(str(data.get("category", "")))
        title = str(data.get("title", "")).strip()
        if not title or len(title) > 300:
            raise ValueError("Candidate title is required and must be under 300 characters.")
        platform = validate_platform(data.get("platform"))
        title_id = str(data.get("title_id", "")).strip() or None
        product_code = str(data.get("product_code", "")).strip() or None
        region = str(data.get("region", "")).strip()[:80] or None
        page_language = normalize_language_tag(str(data.get("page_language", data.get("language", ""))))
        language_evidence = normalize_language_tag(str(data.get("language_evidence", "")))
        language = normalize_language_tag(str(data.get("content_language", language_evidence or "")))
        version = str(data.get("version", "")).strip()[:100] or None
        notes = str(data.get("notes", "")).strip()[:2000]
        observed_uri = validate_source_url(data.get("observed_uri"), allow_empty=True)
        download_uri = validate_source_url(data.get("download_uri"), allow_empty=True)
        size = data.get("size_bytes")
        if size in (None, ""):
            size = None
        else:
            try:
                size = int(size)
            except (ValueError, TypeError) as exc:
                raise ValueError("Size must be a whole number of bytes.") from exc
            if size < 0 or size > 100_000_000_000:
                raise ValueError("Size must be between 0 and 100 GB.")
        hash_algorithm = str(data.get("hash_algorithm", "")).casefold().strip() or None
        declared_hash = str(data.get("declared_hash", "")).strip().casefold() or None
        if hash_algorithm not in (None, "sha256", "sha1"):
            raise ValueError("Only SHA-256 and SHA-1 digests are supported.")
        if declared_hash and not hash_algorithm:
            raise ValueError("Select the digest algorithm before entering a hash.")
        expected_hex = {"sha256": 64, "sha1": 40}.get(hash_algorithm)
        if declared_hash and (len(declared_hash) != expected_hex or any(ch not in "0123456789abcdef" for ch in declared_hash)):
            raise ValueError(f"{hash_algorithm.upper()} must be {expected_hex} hexadecimal characters.")
        conn = connect()
        try:
            with conn:
                # Serialize lookup-then-insert so repeated manual observations
                # cannot race into duplicate candidate identities.
                conn.execute("BEGIN IMMEDIATE")
                release = conn.execute("SELECT * FROM game_release WHERE id=?", (release_id,)).fetchone()
                source = conn.execute("SELECT * FROM source WHERE id=?", (source_id,)).fetchone()
                if not release or not source:
                    raise ValueError("Choose an existing game release and source.")
                if source["trust_tier"] == "blocked" or json_load(source["policy_json"]).get("review_status") == "blocked":
                    raise ValueError("Blocked sources cannot provide active content candidates.")
                policy = json_load(source["policy_json"])
                if download_uri:
                    validate_download_url(download_uri, allowed_hosts(source, policy))
                external_id = str(data.get("external_id", "")).strip()[:160] or None
                observed = {
                    "external_id": external_id,
                    "title": title, "category": category, "title_id": title_id, "product_code": product_code, "region": region,
                    "language": language, "page_language": page_language, "language_evidence": language_evidence, "version": version, "size_bytes": size,
                    "hash_algorithm": hash_algorithm, "declared_hash": declared_hash, "observed_uri": observed_uri, "download_uri": download_uri,
                }
                payload_digest = digest_json(observed)
                repeated = conn.execute(
                    """SELECT so.id AS observation_id,so.content_item_id
                       FROM source_observation so JOIN content_item ci ON ci.id=so.content_item_id
                       WHERE so.source_id=? AND ci.release_id=? AND ci.category=? AND so.payload_digest=?
                       ORDER BY so.observed_at DESC LIMIT 1""",
                    (source_id, release_id, category, payload_digest),
                ).fetchone()
                if repeated:
                    assessment = assess(conn, repeated["content_item_id"])
                    audit(conn, "candidate_repeat_seen", "content_item", repeated["content_item_id"], {
                        "release_id": release_id, "source_id": source_id, "observation_id": repeated["observation_id"],
                        "payload_digest": payload_digest,
                    }, provenance="source_reported")
                    return {"id": repeated["content_item_id"], "observation_id": repeated["observation_id"], "assessment": assessment, "reused": True}

                identity_digest = candidate_identity_digest({
                    "release_id": release_id, "category": category, "title": title, "platform": platform,
                    "title_id": title_id, "product_code": product_code, "region": region, "language": language,
                    "language_evidence": language_evidence, "version": version, "size_bytes": size,
                    "hash_algorithm": hash_algorithm, "declared_hash": declared_hash,
                })
                canonical = conn.execute(
                    "SELECT id FROM content_item WHERE release_id=? AND category=? AND identity_digest=? ORDER BY created_at LIMIT 1",
                    (release_id, category, identity_digest),
                ).fetchone()
                item_id = canonical["id"] if canonical else new_id()
                stamp = now_iso()
                evidence = {
                    "source_claim": data.get("source_claim", "user entered listing details"),
                    "page_language": page_language,
                    "language_separation": "page_language and content_language are recorded independently",
                    "download_rights": "not inferred from game ownership or source trust",
                }
                if not canonical:
                    conn.execute(
                        """INSERT INTO content_item(id,release_id,category,title,normalized_title,identity_digest,platform,title_id,normalized_title_id,
                           product_code,normalized_product_code,region,language,page_language,language_evidence,version,size_bytes,hash_algorithm,
                           declared_hash,notes,provenance,evidence_json,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (item_id, release_id, category, title, normalize_text(title), identity_digest, platform, title_id, normalize_identifier(title_id) if title_id else None,
                         product_code, normalize_identifier(product_code) if product_code else None, region, language, None, language_evidence, version, size,
                         hash_algorithm, declared_hash, notes, "source_reported", json_dump(evidence), stamp),
                    )
                observation_id = new_id()
                conn.execute(
                    """INSERT INTO source_observation(id,content_item_id,source_id,external_id,observed_uri,download_uri,observed_at,
                       original_title,payload_digest,evidence_json,result_state) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (observation_id, item_id, source_id, external_id, observed_uri, download_uri, stamp, title, payload_digest, json_dump({"entered_by_user": True, "page_language": page_language, "source_attribution": source["attribution"], "trust_tier": source["trust_tier"]}), "found"),
                )
                assessment = assess(conn, item_id)
                audit(conn, "candidate_observation_added" if canonical else "candidate_recorded", "content_item", item_id, {"release_id": release_id, "source_id": source_id, "observation_id": observation_id, "category": category, "language": language, "compatibility_state": assessment["state"], "merged_into_existing_candidate": bool(canonical)}, provenance="source_reported")
            return {"id": item_id, "observation_id": observation_id, "assessment": assessment, "merged": bool(canonical)}
        finally:
            conn.close()

    def assess_candidate(self, content_id: str) -> dict[str, Any]:
        conn = connect()
        try:
            with conn:
                result = assess(conn, content_id)
                audit(conn, "compatibility_assessed", "content_item", content_id, result)
            return result
        finally:
            conn.close()

    def link_local_file(self, content_id: str, file_id: str) -> dict[str, Any]:
        conn = connect()
        try:
            with conn:
                item = conn.execute("SELECT * FROM content_item WHERE id=?", (content_id,)).fetchone()
                local = conn.execute("SELECT lf.*,lr.availability FROM local_file lf JOIN local_root lr ON lr.id=lf.root_id WHERE lf.id=?", (file_id,)).fetchone()
                if not item or not local:
                    raise ValueError("Choose an existing candidate and local file.")
                if local["presence_state"] != "present" or local["availability"] == "unavailable":
                    raise ValueError("The local file is not present on an available selected root.")
                stamp = now_iso()
                match_id = new_id()
                conn.execute(
                    """INSERT INTO content_local_match(id,content_item_id,local_file_id,match_state,confidence,evidence_json,confirmed_by_user_at,created_at)
                       VALUES(?,?,?,'user_confirmed','high',?,?,?) ON CONFLICT(content_item_id,local_file_id) DO UPDATE SET
                       match_state='user_confirmed',confidence='high',evidence_json=excluded.evidence_json,confirmed_by_user_at=excluded.confirmed_by_user_at""",
                    (match_id, content_id, file_id, json_dump({"method": "explicit user confirmation", "relative_path": local["relative_path"]}), stamp, stamp),
                )
                result = assess(conn, content_id)
                audit(conn, "local_match_confirmed", "content_local_match", match_id, {"content_item_id": content_id, "local_file_id": file_id, "compatibility_state": result["state"]})
            return {"id": match_id, "assessment": result}
        finally:
            conn.close()

    def add_root(self, path_value: str) -> dict[str, Any]:
        raw = str(path_value).strip()
        if not raw or len(raw) > 2048:
            raise ValueError("Enter a selected folder path.")
        path = Path(raw).expanduser()
        if not path.exists() or not path.is_dir():
            raise ValueError("Folder does not exist or is not accessible. The suggested D:\\PlayStation-Library path is not created or scanned automatically.")
        try:
            canonical = path.resolve(strict=True)
            info = canonical.stat()
        except OSError as exc:
            raise ValueError(f"Could not inspect selected folder: {exc}") from exc
        normalized = os.path.normcase(str(canonical)).casefold()
        volume_identity = f"{canonical.anchor.casefold()}:{info.st_dev}"
        conn = connect()
        try:
            with conn:
                existing = conn.execute("SELECT * FROM local_root WHERE normalized_path=?", (normalized,)).fetchone()
                if existing:
                    conn.execute("UPDATE local_root SET availability='available',last_seen_at=? WHERE id=?", (now_iso(), existing["id"]))
                    return dict(conn.execute("SELECT * FROM local_root WHERE id=?", (existing["id"],)).fetchone())
                root_id = new_id()
                conn.execute(
                    "INSERT INTO local_root(id,display_path,normalized_path,volume_identity,availability,user_selected_at) VALUES(?,?,?,?,?,?)",
                    (root_id, str(canonical), normalized, volume_identity, "available", now_iso()),
                )
                audit(conn, "local_root_selected", "local_root", root_id, {"volume_identity": volume_identity, "display_path": str(canonical)})
            return dict(conn.execute("SELECT * FROM local_root WHERE id=?", (root_id,)).fetchone())
        finally:
            conn.close()

    def choose_folder(self, initial_dir: str = "") -> dict[str, str]:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError as exc:
            raise ValueError("Native folder picker is unavailable; enter an existing folder path manually.") from exc
        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            initial = Path(initial_dir).expanduser() if initial_dir else None
            selected = filedialog.askdirectory(title="Choose a folder for DR Crawler", initialdir=str(initial) if initial and initial.is_dir() else None, mustexist=True, parent=root)
            return {"path": selected or ""}
        except Exception as exc:
            raise ValueError(f"Could not open the native folder picker: {exc}") from exc
        finally:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

    def record_check(self, source_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self.record_source_check(source_id, data)

    def start_scan(self, root_id: str) -> dict[str, Any]:
        return self.scans.start(root_id)

    def cancel_scan(self, run_id: str) -> bool:
        return self.scans.cancel(run_id)

    def get_scan(self, run_id: str) -> dict[str, Any] | None:
        conn = connect()
        try:
            row = conn.execute("SELECT sr.*,lr.display_path FROM scan_run sr JOIN local_root lr ON lr.id=sr.root_id WHERE sr.id=?", (run_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def root_files(self, root_id: str) -> list[dict[str, Any]]:
        conn = connect()
        try:
            root = conn.execute("SELECT 1 FROM local_root WHERE id=?", (root_id,)).fetchone()
            if not root:
                raise ValueError("Selected folder was not found.")
            return [dict(row) for row in conn.execute(
                """SELECT lf.id,lf.relative_path,lf.name,lf.extension,lf.size_bytes,lf.modified_at,lf.package_guess,
                          lf.parsed_title_id,lf.parsed_version,lf.presence_state,lf.parse_state,lf.provenance,lf.last_seen_run_id
                   FROM local_file lf WHERE lf.root_id=? ORDER BY CASE lf.presence_state WHEN 'present' THEN 0 WHEN 'observed_partial' THEN 1 ELSE 2 END,lf.name LIMIT 2000""", (root_id,)
            )]
        finally:
            conn.close()

    def source_checks(self, source_id: str) -> list[dict[str, Any]]:
        conn = connect()
        try:
            source = conn.execute("SELECT 1 FROM source WHERE id=?", (source_id,)).fetchone()
            if not source:
                raise ValueError("Source was not found.")
            return [dict(row) for row in conn.execute(
                """SELECT sc.*,g.canonical_title,r.platform,r.region FROM source_check sc
                   JOIN game_release r ON r.id=sc.release_id JOIN game g ON g.id=r.game_id
                   WHERE sc.source_id=? ORDER BY sc.completed_at DESC LIMIT 100""", (source_id,)
            )]
        finally:
            conn.close()

    def update_preferences(self, data: dict[str, Any]) -> dict[str, Any]:
        ttl = data.get("coverage_ttl_days", 30)
        try:
            ttl = max(1, min(int(ttl), 365))
        except (TypeError, ValueError) as exc:
            raise ValueError("Freshness window must be a whole number from 1 to 365 days.") from exc
        fallback = data.get("fallback_languages", ["en"])
        if not isinstance(fallback, list):
            raise ValueError("Fallback languages must be a list.")
        ordered_fallbacks = []
        seen_fallbacks = set()
        for value in fallback:
            tag = normalize_language_tag(str(value))
            if tag and tag.casefold() not in ("fa", "fa-ir") and tag.casefold() not in seen_fallbacks:
                ordered_fallbacks.append(tag)
                seen_fallbacks.add(tag.casefold())
        fallback = ordered_fallbacks
        conn = connect()
        try:
            stamp = now_iso()
            with conn:
                conn.execute("INSERT INTO user_preference(key,value_json,updated_at) VALUES('coverage_ttl_days',?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at", (json_dump(ttl), stamp))
                conn.execute("INSERT INTO user_preference(key,value_json,updated_at) VALUES('fallback_languages',?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at", (json_dump(fallback), stamp))
                audit(conn, "preferences_updated", "user_preference", None, {"coverage_ttl_days": ttl, "fallback_languages": fallback})
            return {"locale": "fa-IR", "coverage_ttl_days": ttl, "fallback_languages": fallback, "suggested_library_root": r"D:\PlayStation-Library"}
        finally:
            conn.close()

    def find_local_files(self, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        conn = connect()
        try:
            clauses = ["lf.presence_state='present'", "lr.availability='available'"]
            args: list[Any] = []
            q = str(query).strip()
            if q:
                ident = normalize_identifier(q)
                text_like = "(LOWER(lf.name) LIKE ? OR LOWER(lf.relative_path) LIKE ?"
                args += [f"%{q.casefold()}%", f"%{q.casefold()}%"]
                if ident:
                    text_like += " OR lf.parsed_title_id LIKE ?"
                    args.append(f"%{ident}%")
                clauses.append(text_like + ")")
            args.append(max(1, min(int(limit), 200)))
            return [dict(row) for row in conn.execute(
                f"""SELECT lf.id,lf.name,lf.relative_path,lf.extension,lf.size_bytes,lf.package_guess,lf.parsed_title_id,
                           lf.parsed_version,lr.display_path FROM local_file lf JOIN local_root lr ON lr.id=lf.root_id
                    WHERE {' AND '.join(clauses)} ORDER BY lf.name LIMIT ?""", args
            )]
        finally:
            conn.close()

    def create_download_job(self, content_id: str, observation_id: str, destination_dir: str) -> dict[str, Any]:
        conn = connect()
        try:
            with conn:
                return create_job(conn, content_id, observation_id, destination_dir)
        finally:
            conn.close()

    def approve_job(self, job_id: str, rights_confirmed: bool, uncertainty_ack: bool) -> dict[str, Any]:
        if not rights_confirmed:
            raise ValueError("Confirm that you are authorized to obtain this exact item before approval.")
        conn = connect()
        try:
            with conn:
                snapshot, job, source = __import__("drcrawler.downloads", fromlist=["current_snapshot"]).current_snapshot(conn, job_id)
                approved = json_load(job["approval_snapshot_json"])
                if snapshot != approved or job["destination_path"] != approved.get("destination_path"):
                    conn.execute("UPDATE download_job SET approval_state='approval_expired',status='approval_expired',updated_at=?,error_reason=? WHERE id=?", (now_iso(), "Candidate or approval details changed.", job_id))
                    event(conn, job_id, "approval_expired", "system", {"reason": "snapshot changed before approval"})
                    audit(conn, "download_approval_expired", "download_job", job_id, {"reason": "snapshot changed before approval"})
                    conn.commit()
                    raise ValueError("Approval details changed. Create a new approval request.")
                if snapshot["compatibility"]["state"] == "incompatible":
                    raise ValueError("This candidate conflicts with the selected game release and cannot be queued.")
                if snapshot["compatibility"]["state"] in ("unknown", "needs_review") and not uncertainty_ack:
                    raise ValueError("Review the compatibility evidence and acknowledge its uncertainty before approval.")
                policy = json_load(source["policy_json"])
                if not source["enabled"] or source["trust_tier"] == "blocked" or policy.get("review_status") != "reviewed_allowed" or not policy.get("allow_downloads"):
                    raise ValueError("This source's reviewed access policy does not permit downloads.")
                if job["status"] != "awaiting_approval":
                    raise ValueError(f"Queue item is {job['status']} and cannot be approved again.")
                stamp = now_iso()
                conn.execute("UPDATE download_job SET approval_state='approved',status='approved',authorization_ack=1,approved_at=?,updated_at=? WHERE id=?", (stamp, stamp, job_id))
                event(conn, job_id, "approved", "user", {"rights_confirmed": True, "uncertainty_acknowledged": bool(uncertainty_ack), "snapshot_digest": digest_json(snapshot)})
                audit(conn, "download_approved", "download_job", job_id, {"rights_confirmed": True, "uncertainty_acknowledged": bool(uncertainty_ack), "snapshot_digest": digest_json(snapshot)})
            return {"id": job_id, "status": "approved", "snapshot": snapshot}
        finally:
            conn.close()

    def start_download(self, job_id: str) -> dict[str, Any]:
        conn = connect()
        try:
            with conn:
                snapshot, job, source, policy = __import__("drcrawler.downloads", fromlist=["ensure_snapshot_current"]).ensure_snapshot_current(conn, job_id)
                if job["status"] not in ("approved", "queued"):
                    raise ValueError("Approve the exact candidate before starting the download.")
            self.downloads.start(job_id)
            return {"id": job_id, "status": "starting"}
        finally:
            conn.close()

    def cancel_download(self, job_id: str) -> dict[str, Any]:
        conn = connect()
        try:
            with conn:
                job = conn.execute("SELECT * FROM download_job WHERE id=?", (job_id,)).fetchone()
                if not job:
                    raise ValueError("Queue item was not found.")
                if job["status"] == "downloading":
                    if not self.downloads.cancel(job_id):
                        raise ValueError("Download is finishing; refresh its status before trying again.")
                    return {"id": job_id, "status": "cancelling"}
                if job["status"] in ("awaiting_approval", "approved", "queued"):
                    stamp = now_iso()
                    conn.execute("UPDATE download_job SET status='cancelled',approval_state='cancelled',updated_at=? WHERE id=?", (stamp, job_id))
                    event(conn, job_id, "download_cancelled", "user", {"reason": "cancelled before transfer"})
                    audit(conn, "download_cancelled", "download_job", job_id, {"reason": "cancelled before transfer"})
                    return {"id": job_id, "status": "cancelled"}
                raise ValueError(f"Queue item is {job['status']} and cannot be cancelled.")
        finally:
            conn.close()

    def reject_job(self, job_id: str) -> dict[str, Any]:
        conn = connect()
        try:
            with conn:
                job = conn.execute("SELECT * FROM download_job WHERE id=?", (job_id,)).fetchone()
                if not job or job["status"] != "awaiting_approval":
                    raise ValueError("Only a waiting approval can be rejected.")
                stamp = now_iso()
                conn.execute("UPDATE download_job SET status='rejected',approval_state='rejected',updated_at=? WHERE id=?", (stamp, job_id))
                event(conn, job_id, "rejected", "user", {})
                audit(conn, "download_rejected", "download_job", job_id, {})
                return {"id": job_id, "status": "rejected"}
        finally:
            conn.close()


def list_games() -> list[dict[str, Any]]:
    from .database import all_games

    conn = connect()
    try:
        return all_games(conn)
    finally:
        conn.close()


def get_game(game_id: str) -> dict[str, Any] | None:
    conn = connect()
    try:
        return game_detail(conn, game_id)
    finally:
        conn.close()


def get_sources() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return source_list(conn)
    finally:
        conn.close()


def get_roots() -> list[dict[str, Any]]:
    conn = connect()
    try:
        from .database import all_roots

        return all_roots(conn)
    finally:
        conn.close()


def get_jobs() -> list[dict[str, Any]]:
    conn = connect()
    try:
        from .database import all_jobs

        return all_jobs(conn)
    finally:
        conn.close()


def get_preferences() -> dict[str, Any]:
    conn = connect()
    try:
        return {r["key"]: json_load(r["value_json"]) for r in conn.execute("SELECT key,value_json FROM user_preference")}
    finally:
        conn.close()


def get_coverage(game_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        return coverage_for_game(conn, game_id)
    finally:
        conn.close()


def local_path_identity(path: str) -> str:
    return os.path.normcase(str(Path(path).resolve())).casefold()
