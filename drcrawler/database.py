from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from .core import candidate_identity_digest, json_dump, json_load, new_id, normalize_identifier, normalize_text, now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS game (
  id TEXT PRIMARY KEY,
  canonical_title TEXT NOT NULL,
  normalized_title TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  provenance TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS game_name (
  id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  language TEXT,
  name_type TEXT NOT NULL DEFAULT 'title',
  provenance TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_game_name_search ON game_name(normalized_value, language);
CREATE TABLE IF NOT EXISTS game_release (
  id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  platform TEXT NOT NULL CHECK(platform IN ('PS4','PS5')),
  region TEXT,
  title_id TEXT,
  normalized_title_id TEXT,
  product_code TEXT,
  normalized_product_code TEXT,
  release_version TEXT,
  provenance TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_release_ids ON game_release(platform, normalized_title_id, normalized_product_code);
CREATE TABLE IF NOT EXISTS owned_game (
  id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  release_id TEXT REFERENCES game_release(id) ON DELETE SET NULL,
  ownership_status TEXT NOT NULL DEFAULT 'user_asserted',
  evidence_note TEXT NOT NULL DEFAULT '',
  input_source TEXT NOT NULL,
  owned_since TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  base_uri TEXT,
  trust_tier TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  attribution TEXT NOT NULL DEFAULT '',
  maintainer TEXT NOT NULL DEFAULT '',
  verification_note TEXT NOT NULL DEFAULT '',
  terms_uri TEXT,
  reviewed_at TEXT,
  policy_json TEXT NOT NULL DEFAULT '{}',
  capabilities_json TEXT NOT NULL DEFAULT '{}',
  health_state TEXT NOT NULL DEFAULT 'unknown',
  last_request_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_check (
  id TEXT PRIMARY KEY,
  release_id TEXT NOT NULL REFERENCES game_release(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  query_digest TEXT,
  adapter_version TEXT NOT NULL DEFAULT 'manual-v1',
  provenance TEXT NOT NULL DEFAULT 'user_confirmed'
);
CREATE INDEX IF NOT EXISTS ix_source_check_coverage ON source_check(release_id, source_id, category, completed_at DESC);
CREATE TABLE IF NOT EXISTS content_item (
  id TEXT PRIMARY KEY,
  release_id TEXT NOT NULL REFERENCES game_release(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  normalized_title TEXT NOT NULL,
  identity_digest TEXT NOT NULL DEFAULT '',
  platform TEXT,
  title_id TEXT,
  normalized_title_id TEXT,
  product_code TEXT,
  normalized_product_code TEXT,
  region TEXT,
  language TEXT,
  page_language TEXT,
  language_evidence TEXT,
  version TEXT,
  size_bytes INTEGER,
  hash_algorithm TEXT,
  declared_hash TEXT,
  notes TEXT NOT NULL DEFAULT '',
  provenance TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_content_game_category ON content_item(release_id, category, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_content_identity ON content_item(release_id, category, identity_digest);
CREATE TABLE IF NOT EXISTS source_observation (
  id TEXT PRIMARY KEY,
  content_item_id TEXT NOT NULL REFERENCES content_item(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES source(id) ON DELETE RESTRICT,
  external_id TEXT,
  observed_uri TEXT,
  download_uri TEXT,
  observed_at TEXT NOT NULL,
  original_title TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  result_state TEXT NOT NULL DEFAULT 'found'
);
CREATE INDEX IF NOT EXISTS ix_observation_item ON source_observation(content_item_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS local_root (
  id TEXT PRIMARY KEY,
  display_path TEXT NOT NULL,
  normalized_path TEXT NOT NULL UNIQUE,
  volume_identity TEXT,
  volume_label TEXT,
  filesystem TEXT,
  removable INTEGER,
  availability TEXT NOT NULL DEFAULT 'unknown',
  last_seen_at TEXT,
  user_selected_at TEXT NOT NULL,
  selected_scope TEXT NOT NULL DEFAULT 'recursive'
);
CREATE TABLE IF NOT EXISTS scan_run (
  id TEXT PRIMARY KEY,
  root_id TEXT NOT NULL REFERENCES local_root(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  scanner_version TEXT NOT NULL,
  items_seen INTEGER NOT NULL DEFAULT 0,
  errors_count INTEGER NOT NULL DEFAULT 0,
  progress_path TEXT,
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_scan_root_time ON scan_run(root_id, started_at DESC);
CREATE TABLE IF NOT EXISTS local_file (
  id TEXT PRIMARY KEY,
  root_id TEXT NOT NULL REFERENCES local_root(id) ON DELETE CASCADE,
  relative_path TEXT NOT NULL,
  normalized_path TEXT NOT NULL,
  name TEXT NOT NULL,
  extension TEXT NOT NULL DEFAULT '',
  size_bytes INTEGER NOT NULL DEFAULT 0,
  modified_at TEXT,
  package_guess TEXT,
  parsed_title_id TEXT,
  parsed_version TEXT,
  hash_algorithm TEXT,
  hash_value TEXT,
  last_observed_run_id TEXT REFERENCES scan_run(id) ON DELETE SET NULL,
  last_seen_run_id TEXT REFERENCES scan_run(id) ON DELETE SET NULL,
  presence_state TEXT NOT NULL DEFAULT 'present',
  parse_state TEXT NOT NULL DEFAULT 'filename_only',
  provenance TEXT NOT NULL DEFAULT 'inferred',
  evidence_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(root_id, normalized_path)
);
CREATE INDEX IF NOT EXISTS ix_local_file_root ON local_file(root_id, presence_state, name);
CREATE TABLE IF NOT EXISTS content_local_match (
  id TEXT PRIMARY KEY,
  content_item_id TEXT NOT NULL REFERENCES content_item(id) ON DELETE CASCADE,
  local_file_id TEXT NOT NULL REFERENCES local_file(id) ON DELETE CASCADE,
  match_state TEXT NOT NULL,
  confidence TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  confirmed_by_user_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(content_item_id, local_file_id)
);
CREATE TABLE IF NOT EXISTS compatibility_assessment (
  id TEXT PRIMARY KEY,
  content_item_id TEXT NOT NULL REFERENCES content_item(id) ON DELETE CASCADE,
  release_id TEXT NOT NULL REFERENCES game_release(id) ON DELETE CASCADE,
  state TEXT NOT NULL,
  confidence TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  assessed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assessment_latest ON compatibility_assessment(content_item_id, assessed_at DESC);
CREATE TABLE IF NOT EXISTS download_job (
  id TEXT PRIMARY KEY,
  content_item_id TEXT NOT NULL REFERENCES content_item(id) ON DELETE RESTRICT,
  source_observation_id TEXT NOT NULL REFERENCES source_observation(id) ON DELETE RESTRICT,
  approval_snapshot_json TEXT NOT NULL,
  destination_path TEXT NOT NULL,
  approval_state TEXT NOT NULL DEFAULT 'awaiting_approval',
  status TEXT NOT NULL DEFAULT 'awaiting_approval',
  authorization_ack INTEGER NOT NULL DEFAULT 0,
  progress_bytes INTEGER NOT NULL DEFAULT 0,
  total_bytes INTEGER,
  sha256_actual TEXT,
  integrity_state TEXT NOT NULL DEFAULT 'not_checked',
  error_reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  approved_at TEXT,
  completed_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_job_status ON download_job(status, created_at DESC);
CREATE TABLE IF NOT EXISTS download_event (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES download_job(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  actor TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS audit_event (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  timestamp TEXT NOT NULL,
  provenance TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_audit_time ON audit_event(timestamp DESC);
CREATE TABLE IF NOT EXISTS user_preference (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
PRAGMA user_version = 2;
"""


def get_data_dir() -> Path:
    override = os.environ.get("DRCRAWLER_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "DRCrawler"


def get_db_path() -> Path:
    return get_data_dir() / "dr-crawler.sqlite3"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        with conn:
            conn.executescript(SCHEMA)
            defaults = {
                "locale": "fa-IR",
                "fallback_languages": ["en"],
                "suggested_library_root": r"D:\PlayStation-Library",
                "coverage_ttl_days": 30,
                "scan_hashing": False,
            }
            for key, value in defaults.items():
                conn.execute(
                    "INSERT OR IGNORE INTO user_preference(key,value_json,updated_at) VALUES(?,?,?)",
                    (key, json_dump(value), now_iso()),
                )
    elif version == 1:
        with conn:
            conn.execute("ALTER TABLE content_item ADD COLUMN identity_digest TEXT NOT NULL DEFAULT ''")
            rows = conn.execute("SELECT * FROM content_item").fetchall()
            for row in rows:
                fields = dict(row)
                fields["release_id"] = row["release_id"]
                conn.execute("UPDATE content_item SET identity_digest=? WHERE id=?", (candidate_identity_digest(fields), row["id"]))
            conn.execute("CREATE INDEX IF NOT EXISTS ix_content_identity ON content_item(release_id,category,identity_digest)")
            conn.execute("PRAGMA user_version = 2")
    return conn


def rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def audit(conn: sqlite3.Connection, event_type: str, entity_type: str, entity_id: str | None, details: Any, provenance: str = "user_confirmed") -> None:
    conn.execute(
        "INSERT INTO audit_event(id,event_type,entity_type,entity_id,timestamp,provenance,details_json) VALUES(?,?,?,?,?,?,?)",
        (new_id(), event_type, entity_type, entity_id, now_iso(), provenance, json_dump(details)),
    )


def event(conn: sqlite3.Connection, job_id: str, event_type: str, actor: str, details: Any) -> None:
    conn.execute(
        "INSERT INTO download_event(id,job_id,event_type,timestamp,actor,details_json) VALUES(?,?,?,?,?,?)",
        (new_id(), job_id, event_type, now_iso(), actor, json_dump(details)),
    )


def insert_game(conn: sqlite3.Connection, record: dict[str, Any], *, game_id: str | None = None, provenance: str = "imported") -> tuple[str, str]:
    selected_game_id = game_id
    game_id = game_id or new_id()
    stamp = now_iso()
    game = conn.execute("SELECT id, canonical_title FROM game WHERE id=?", (game_id,)).fetchone()
    if game is None:
        conn.execute(
            "INSERT INTO game(id,canonical_title,normalized_title,note,provenance,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (game_id, record["title"], normalize_text(record["title"]), record.get("notes", ""), provenance, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO game_name(id,game_id,value,normalized_value,language,name_type,provenance,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (new_id(), game_id, record["title"], normalize_text(record["title"]), record.get("language"), "title", provenance, json_dump({"input_source": record.get("source", provenance)}), stamp),
        )
    else:
        conn.execute("UPDATE game SET updated_at=? WHERE id=?", (stamp, game_id))
        if record["title"] and normalize_text(record["title"]) != normalize_text(game["canonical_title"]):
            exists = conn.execute("SELECT 1 FROM game_name WHERE game_id=? AND normalized_value=?", (game_id, normalize_text(record["title"]))).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO game_name(id,game_id,value,normalized_value,language,name_type,provenance,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (new_id(), game_id, record["title"], normalize_text(record["title"]), record.get("language"), "alias", provenance, json_dump({"input_source": record.get("source", provenance)}), stamp),
                )
    for alias in record.get("aliases", []):
        value = str(alias.get("value", "")).strip()
        normalized_alias = normalize_text(value)
        if not value or not normalized_alias or normalized_alias == normalize_text(record["title"]):
            continue
        exists = conn.execute("SELECT 1 FROM game_name WHERE game_id=? AND normalized_value=?", (game_id, normalized_alias)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO game_name(id,game_id,value,normalized_value,language,name_type,provenance,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (new_id(), game_id, value, normalized_alias, alias.get("language"), "alias", provenance, json_dump({"input_source": record.get("source", provenance), "entry_method": "alternate_title"}), stamp),
            )
    title_id_norm = normalize_identifier(record.get("title_id")) if record.get("title_id") else None
    product_norm = normalize_identifier(record.get("product_code")) if record.get("product_code") else None
    existing_release = None
    if title_id_norm:
        existing_release = conn.execute("SELECT id,game_id FROM game_release WHERE platform=? AND normalized_title_id=? ORDER BY created_at LIMIT 1", (record["platform"], title_id_norm)).fetchone()
    if existing_release is None and product_norm:
        existing_release = conn.execute("SELECT id,game_id FROM game_release WHERE platform=? AND normalized_product_code=? ORDER BY created_at LIMIT 1", (record["platform"], product_norm)).fetchone()
    if existing_release is not None and selected_game_id and existing_release["game_id"] != game_id:
        raise ValueError("That identifier already belongs to another game. Choose that game as the merge target or review the row again.")
    if existing_release is None or existing_release["game_id"] != game_id:
        release_id = new_id()
        conn.execute(
            "INSERT INTO game_release(id,game_id,platform,region,title_id,normalized_title_id,product_code,normalized_product_code,release_version,provenance,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (release_id, game_id, record["platform"], record.get("region"), record.get("title_id"), title_id_norm, record.get("product_code"), product_norm, None, provenance, stamp),
        )
    else:
        release_id = existing_release["id"]
    if record.get("languages"):
        for language in record["languages"]:
            language = str(language).strip()[:32]
            if not language:
                continue
            exists = conn.execute("SELECT 1 FROM game_name WHERE game_id=? AND language=? AND name_type='language_evidence'", (game_id, language)).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO game_name(id,game_id,value,normalized_value,language,name_type,provenance,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (new_id(), game_id, record["title"], normalize_text(record["title"]), language, "language_evidence", provenance, json_dump({"meaning": "owned-game import language claim"}), stamp),
                )
    owned = conn.execute("SELECT id FROM owned_game WHERE game_id=? AND release_id IS ? AND input_source=?", (game_id, release_id, record.get("source", provenance))).fetchone()
    if owned is None:
        conn.execute(
            "INSERT INTO owned_game(id,game_id,release_id,ownership_status,evidence_note,input_source,owned_since,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (new_id(), game_id, release_id, record.get("ownership_status", "user_asserted"), record.get("notes", ""), record.get("source", provenance), record.get("owned_since"), stamp),
        )
    return game_id, release_id


def all_games(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT g.id,g.canonical_title,g.normalized_title,g.note,g.created_at,g.updated_at,
                  COUNT(DISTINCT o.id) AS owned_count,
                  GROUP_CONCAT(DISTINCT r.platform) AS platforms,
                  GROUP_CONCAT(DISTINCT r.region) AS regions,
                  GROUP_CONCAT(DISTINCT r.title_id) AS title_ids,
                  GROUP_CONCAT(DISTINCT r.product_code) AS product_codes,
                  GROUP_CONCAT(DISTINCT r.id) AS release_ids
           FROM game g LEFT JOIN owned_game o ON o.game_id=g.id
           LEFT JOIN game_release r ON r.game_id=g.id
           GROUP BY g.id ORDER BY g.normalized_title,g.created_at"""
    ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        for key in ("platforms", "regions", "title_ids", "product_codes", "release_ids"):
            item[key] = [x for x in (item.get(key) or "").split(",") if x]
        names = conn.execute("SELECT value,language,name_type,provenance FROM game_name WHERE game_id=? ORDER BY CASE WHEN language='fa-IR' THEN 0 WHEN language='fa' THEN 1 ELSE 2 END,created_at", (item["id"],)).fetchall()
        item["names"] = [dict(n) for n in names]
        item["display_title"] = next((n["value"] for n in item["names"] if n["language"] in ("fa-IR", "fa") and n["name_type"] in ("title", "alias")), item["canonical_title"])
        output.append(item)
    return output


def game_detail(conn: sqlite3.Connection, game_id: str) -> dict[str, Any] | None:
    game = conn.execute("SELECT * FROM game WHERE id=?", (game_id,)).fetchone()
    if not game:
        return None
    result: dict[str, Any] = dict(game)
    result["names"] = [dict(r) for r in conn.execute("SELECT * FROM game_name WHERE game_id=? ORDER BY CASE WHEN language='fa-IR' THEN 0 WHEN language='fa' THEN 1 ELSE 2 END,created_at", (game_id,))]
    result["display_title"] = next((n["value"] for n in result["names"] if n["language"] in ("fa-IR", "fa") and n["name_type"] in ("title", "alias")), result["canonical_title"])
    result["owned"] = [dict(r) for r in conn.execute("SELECT o.*,r.platform,r.region,r.title_id,r.product_code FROM owned_game o LEFT JOIN game_release r ON r.id=o.release_id WHERE o.game_id=? ORDER BY o.created_at DESC", (game_id,))]
    fallback_pref = conn.execute("SELECT value_json FROM user_preference WHERE key='fallback_languages'").fetchone()
    fallback_languages = json_load(fallback_pref[0], ["en"]) if fallback_pref else ["en"]
    if not isinstance(fallback_languages, list):
        fallback_languages = ["en"]

    def language_rank(value: str | None) -> int:
        normalized = (value or "").replace("_", "-").casefold()
        if normalized == "fa-ir":
            return 0
        if normalized == "fa":
            return 1
        for index, fallback in enumerate(fallback_languages):
            if normalized == str(fallback).replace("_", "-").casefold():
                return index + 2
        return len(fallback_languages) + 2 if normalized else len(fallback_languages) + 3

    releases = [dict(r) for r in conn.execute("SELECT * FROM game_release WHERE game_id=? ORDER BY platform,region,title_id", (game_id,))]
    for release in releases:
        release_id = release["id"]
        release["local_files"] = [dict(r) for r in conn.execute(
            """SELECT lf.*,lr.display_path,lr.availability AS root_availability,sr.completed_at AS last_complete_at,
                      cm.match_state,cm.confidence,cm.confirmed_by_user_at,cm.content_item_id
               FROM local_file lf JOIN local_root lr ON lr.id=lf.root_id
               JOIN scan_run sr ON sr.id=lf.last_seen_run_id
               LEFT JOIN content_local_match cm ON cm.local_file_id=lf.id
               WHERE sr.status='complete' AND lf.presence_state='present'
                 AND (lf.parsed_title_id=? OR EXISTS(
                   SELECT 1 FROM content_local_match cm2 JOIN content_item ci ON ci.id=cm2.content_item_id
                   WHERE cm2.local_file_id=lf.id AND ci.release_id=?
                 ))
               ORDER BY lf.name LIMIT 500""", (release.get("normalized_title_id"), release_id)
        )]
        release["candidates"] = []
        contents = conn.execute("SELECT * FROM content_item WHERE release_id=? ORDER BY created_at DESC", (release_id,)).fetchall()
        contents = sorted(contents, key=lambda row: row["created_at"] or "", reverse=True)
        for content in contents:
            item = dict(content)
            obs = conn.execute(
                """SELECT so.*,s.name AS source_name,s.trust_tier,s.health_state,s.enabled,s.policy_json,s.capabilities_json,
                          s.attribution,s.base_uri,s.terms_uri,s.reviewed_at
                   FROM source_observation so JOIN source s ON s.id=so.source_id WHERE so.content_item_id=?
                   ORDER BY so.observed_at DESC""", (item["id"],)
            ).fetchall()
            item["observations"] = []
            for o in obs:
                od = dict(o)
                od["evidence"] = json_load(od.pop("evidence_json", "{}"))
                od["policy"] = json_load(od.pop("policy_json", "{}"))
                od["capabilities"] = json_load(od.pop("capabilities_json", "{}"))
                item["observations"].append(od)
            page_languages = [o["evidence"].get("page_language") for o in item["observations"] if o["evidence"].get("page_language")]
            item["page_languages"] = sorted(set(page_languages), key=lambda value: (language_rank(value), value.casefold()))
            item["page_language"] = item["page_languages"][0] if item["page_languages"] else item.get("page_language")
            assessment = conn.execute("SELECT * FROM compatibility_assessment WHERE content_item_id=? ORDER BY assessed_at DESC LIMIT 1", (item["id"],)).fetchone()
            item["assessment"] = dict(assessment) if assessment else None
            if item["assessment"]:
                item["assessment"]["evidence"] = json_load(item["assessment"].pop("evidence_json", "[]"), [])
            item["local_matches"] = [dict(r) for r in conn.execute(
                """SELECT cm.*,lf.name,lf.relative_path,lf.size_bytes,lf.presence_state,lr.display_path
                   FROM content_local_match cm JOIN local_file lf ON lf.id=cm.local_file_id
                   JOIN local_root lr ON lr.id=lf.root_id WHERE cm.content_item_id=? ORDER BY cm.created_at DESC""", (item["id"],)
            )]
            release["candidates"].append(item)
        release["candidates"].sort(key=lambda item: item["created_at"] or "", reverse=True)
        release["candidates"].sort(key=lambda item: min((language_rank(value) for value in item["page_languages"]), default=len(fallback_languages) + 3))
        result.setdefault("releases", []).append(release)
    result["local_files"] = [dict(r) for r in conn.execute(
        """SELECT lf.*,lr.display_path,lr.availability AS root_availability,sr.completed_at AS last_complete_at,
                  cm.match_state,cm.confidence,cm.confirmed_by_user_at,cm.content_item_id
           FROM local_file lf JOIN local_root lr ON lr.id=lf.root_id
           JOIN scan_run sr ON sr.id=lf.last_seen_run_id
           LEFT JOIN content_local_match cm ON cm.local_file_id=lf.id
           WHERE sr.status='complete' AND lf.presence_state='present' AND (
             lf.parsed_title_id IN (SELECT normalized_title_id FROM game_release WHERE game_id=? AND normalized_title_id IS NOT NULL)
             OR EXISTS(SELECT 1 FROM content_local_match cm2 JOIN content_item ci ON ci.id=cm2.content_item_id
                       JOIN game_release gr ON gr.id=ci.release_id WHERE cm2.local_file_id=lf.id AND gr.game_id=?)
           ) ORDER BY lf.name LIMIT 1000""", (game_id, game_id)
    )]
    result["coverage"] = coverage_for_game(conn, game_id)
    result["checks"] = [dict(r) for r in conn.execute(
        """SELECT sc.*,s.name AS source_name,s.trust_tier FROM source_check sc JOIN source s ON s.id=sc.source_id
           JOIN game_release r ON r.id=sc.release_id WHERE r.game_id=? ORDER BY sc.completed_at DESC LIMIT 200""", (game_id,)
    )]
    return result


def source_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM source ORDER BY name COLLATE NOCASE").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["policy"] = json_load(item.pop("policy_json", "{}"))
        item["capabilities"] = json_load(item.pop("capabilities_json", "{}"))
        item["check_count"] = conn.execute("SELECT COUNT(*) FROM source_check WHERE source_id=?", (item["id"],)).fetchone()[0]
        item["last_check"] = rowdict(conn.execute("SELECT * FROM source_check WHERE source_id=? ORDER BY completed_at DESC LIMIT 1", (item["id"],)).fetchone())
        result.append(item)
    return result


def all_roots(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    roots = []
    for row in conn.execute("SELECT * FROM local_root ORDER BY user_selected_at DESC"):
        item = dict(row)
        item["last_scan"] = rowdict(conn.execute("SELECT * FROM scan_run WHERE root_id=? ORDER BY started_at DESC LIMIT 1", (item["id"],)).fetchone())
        item["file_count"] = conn.execute("SELECT COUNT(*) FROM local_file WHERE root_id=? AND presence_state='present'", (item["id"],)).fetchone()[0]
        roots.append(item)
    return roots


def all_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    jobs = []
    for row in conn.execute(
        """SELECT j.*,c.title,c.category,c.language,c.version,c.size_bytes,c.declared_hash,
                  s.name AS source_name,s.trust_tier
           FROM download_job j JOIN content_item c ON c.id=j.content_item_id
           JOIN source_observation so ON so.id=j.source_observation_id JOIN source s ON s.id=so.source_id
           ORDER BY j.created_at DESC"""
    ):
        item = dict(row)
        item["snapshot"] = json_load(item.pop("approval_snapshot_json", "{}"))
        item["events"] = [dict(e) for e in conn.execute("SELECT * FROM download_event WHERE job_id=? ORDER BY timestamp", (item["id"],))]
        for e in item["events"]:
            e["details"] = json_load(e.pop("details_json", "{}"))
        jobs.append(item)
    return jobs


def coverage_for_game(conn: sqlite3.Connection, game_id: str) -> list[dict[str, Any]]:
    ttl = 30
    pref = conn.execute("SELECT value_json FROM user_preference WHERE key='coverage_ttl_days'").fetchone()
    if pref:
        ttl = max(1, min(int(json_load(pref[0], 30)), 365))
    output: list[dict[str, Any]] = []
    releases = conn.execute("SELECT * FROM game_release WHERE game_id=? ORDER BY platform,region", (game_id,)).fetchall()
    sources = conn.execute("SELECT * FROM source ORDER BY name COLLATE NOCASE").fetchall()
    for release in releases:
        for source in sources:
            capabilities = json_load(source["capabilities_json"])
            policy = json_load(source["policy_json"])
            for category in ("updates", "DLC", "subtitles", "themes", "homebrew"):
                supports = release["platform"] in capabilities.get("platforms", []) and category in capabilities.get("categories", [])
                latest = conn.execute(
                    "SELECT * FROM source_check WHERE release_id=? AND source_id=? AND category=? ORDER BY completed_at DESC LIMIT 1",
                    (release["id"], source["id"], category),
                ).fetchone()
                state = "not_checked"
                reason = "No check has been recorded."
                checked_at = None
                previous_state = None
                if source["trust_tier"] == "blocked" or policy.get("review_status") == "blocked":
                    state, reason = "blocked_by_policy", "This source is marked blocked in its access policy."
                elif not source["enabled"]:
                    state, reason = "not_checked", "Source is disabled."
                elif not supports:
                    state, reason = "unsupported", "The source does not declare this platform and category."
                # A currently blocked access policy takes precedence over an
                # older successful result. Keep that historical check in the
                # history view, but do not present it as usable coverage.
                currently_blocked = source["trust_tier"] == "blocked" or policy.get("review_status") == "blocked"
                if latest:
                    checked_at = latest["completed_at"]
                if latest and not currently_blocked:
                    reason = latest["reason"] or "Manual check result recorded."
                    if latest["outcome"] in ("checked_found", "checked_no_result") and age_days(checked_at) > ttl:
                        state, previous_state = "stale", latest["outcome"]
                        reason = f"Last result is older than the {ttl}-day freshness window."
                    elif latest["outcome"] in ("error", "unavailable"):
                        prior = conn.execute(
                            """SELECT outcome,completed_at FROM source_check WHERE release_id=? AND source_id=? AND category=?
                               AND outcome IN ('checked_found','checked_no_result') ORDER BY completed_at DESC LIMIT 1""",
                            (release["id"], source["id"], category),
                        ).fetchone()
                        if prior:
                            state, previous_state = "stale", prior["outcome"]
                            reason = f"Latest check {latest['outcome']}; prior result retained from {prior['completed_at']}."
                        else:
                            state = latest["outcome"]
                    else:
                        state = latest["outcome"]
                counts = conn.execute(
                    """SELECT COUNT(DISTINCT ci.id) AS candidates,COUNT(DISTINCT so.id) AS observations
                       FROM content_item ci JOIN source_observation so ON so.content_item_id=ci.id
                       WHERE ci.release_id=? AND ci.category=? AND so.source_id=?""", (release["id"], category, source["id"])
                ).fetchone()
                langs = [r[0] for r in conn.execute(
                    """SELECT DISTINCT COALESCE(ci.language_evidence,ci.language) FROM content_item ci JOIN source_observation so ON so.content_item_id=ci.id
                       WHERE ci.release_id=? AND ci.category=? AND so.source_id=? AND COALESCE(ci.language_evidence,ci.language) IS NOT NULL""",
                    (release["id"], category, source["id"]),
                )]
                output.append({
                    "release_id": release["id"], "platform": release["platform"], "region": release["region"],
                    "source_id": source["id"], "source_name": source["name"], "trust_tier": source["trust_tier"],
                    "category": category, "state": state, "previous_state": previous_state,
                    "checked_at": checked_at, "candidate_count": counts["candidates"], "observation_count": counts["observations"], "languages": langs,
                    "reason": reason, "supported": supports, "source_health": source["health_state"],
                    "source_enabled": bool(source["enabled"]),
                    "policy_status": policy.get("review_status", "unknown"),
                })
    return output


def age_days(stamp: str | None) -> float:
    if not stamp:
        return 10**9
    from datetime import datetime, timezone

    try:
        value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - value).total_seconds() / 86400
    except ValueError:
        return 10**9
