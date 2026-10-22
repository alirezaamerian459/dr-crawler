from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .core import digest_json, json_dump, json_load, new_id, now_iso, validate_source_url
from .database import audit, connect, event


CHUNK_SIZE = 1024 * 1024


class ApprovalExpiredError(ValueError):
    pass


def allowed_hosts(source: Any, policy: dict[str, Any]) -> set[str]:
    values = set(policy.get("allowed_hosts", []))
    if source["base_uri"]:
        hostname = urlparse(source["base_uri"]).hostname
        if hostname:
            values.add(hostname.casefold())
    return {str(host).strip().rstrip(".").casefold() for host in values if str(host).strip()}


def validate_download_url(url: str, host_allowlist: set[str], *, resolve: bool = False) -> tuple[str, str, int, str]:
    url = validate_source_url(url, allow_empty=False) or ""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Downloads require HTTPS.")
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if not hostname or hostname not in host_allowlist:
        raise ValueError("Download host is not approved in this source's access policy.")
    if parsed.port not in (None, 443):
        raise ValueError("Only standard HTTPS port 443 is allowed for transfers.")
    if parsed.fragment:
        raise ValueError("Direct download URLs cannot include a fragment.")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    if resolve:
        resolved = resolve_public(hostname)
        if not resolved:
            raise ValueError("The source host did not resolve to a public address.")
    return url, hostname, 443, path


def resolve_public(hostname: str) -> list[str]:
    try:
        records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Could not resolve the approved source host: {exc}") from exc
    addresses = sorted({record[4][0] for record in records})
    if not addresses:
        raise ValueError("The source host has no network addresses.")
    for value in addresses:
        address = ipaddress.ip_address(value.split("%", 1)[0])
        if not address.is_global:
            raise ValueError("The source host resolves to a private, local, or reserved network address.")
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float = 20):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_address, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def output_filename(url: str, title: str) -> str:
    parsed_name = unquote(Path(urlparse(url).path).name).strip()
    candidate = parsed_name or title.strip()
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", candidate).strip(" .")[:180]
    if not candidate:
        candidate = "content.download"
    if "." not in candidate:
        candidate += ".download"
    return candidate


def create_job(conn: Any, content_id: str, observation_id: str, destination_dir: str) -> dict[str, Any]:
    row = conn.execute(
        """SELECT ci.*,r.platform AS release_platform,r.region AS release_region,r.title_id AS release_title_id,
                  g.canonical_title,COALESCE((SELECT gn.value FROM game_name gn WHERE gn.game_id=g.id AND gn.language IN ('fa-IR','fa') AND gn.name_type IN ('title','alias') ORDER BY CASE gn.language WHEN 'fa-IR' THEN 0 ELSE 1 END,gn.created_at LIMIT 1),g.canonical_title) AS display_title,
                  s.id AS source_id,s.name AS source_name,s.trust_tier,s.base_uri,s.policy_json,s.enabled,
                  so.id AS observation_id,so.observed_uri,so.download_uri,so.original_title,so.observed_at
           FROM content_item ci JOIN game_release r ON r.id=ci.release_id JOIN game g ON g.id=r.game_id
           JOIN source_observation so ON so.content_item_id=ci.id JOIN source s ON s.id=so.source_id
           WHERE ci.id=? AND so.id=?""", (content_id, observation_id)
    ).fetchone()
    if not row:
        raise ValueError("Candidate observation was not found.")
    source = conn.execute("SELECT * FROM source WHERE id=?", (row["source_id"],)).fetchone()
    policy = json_load(source["policy_json"])
    if not source["enabled"] or source["trust_tier"] == "blocked" or policy.get("review_status") == "blocked":
        raise ValueError("This source is disabled or blocked by its access policy.")
    if not policy.get("allow_downloads") or policy.get("review_status") != "reviewed_allowed":
        raise ValueError("Review the source access policy and explicitly allow downloads before creating a queue item.")
    if not row["download_uri"]:
        raise ValueError("This observation has no direct download URL.")
    host_allowlist = allowed_hosts(source, policy)
    url, hostname, _, _ = validate_download_url(row["download_uri"], host_allowlist)
    folder = Path(destination_dir).expanduser()
    if not folder.exists() or not folder.is_dir():
        raise ValueError("Choose an existing destination folder explicitly.")
    folder = folder.resolve(strict=True)
    filename = output_filename(url, row["title"])
    destination = folder / filename
    if destination.exists():
        raise ValueError("A file with this exact destination name already exists; choose another folder or rename the source URL's file.")
    assessment = conn.execute("SELECT * FROM compatibility_assessment WHERE content_item_id=? ORDER BY assessed_at DESC LIMIT 1", (content_id,)).fetchone()
    snapshot = {
        "item": {
            "content_item_id": row["id"], "release_id": row["release_id"], "game_title": row["display_title"],
            "category": row["category"], "title": row["title"], "platform": row["platform"], "title_id": row["title_id"],
            "product_code": row["product_code"], "region": row["region"], "language": row["language"],
            "page_language": row["page_language"], "language_evidence": row["language_evidence"], "version": row["version"], "size_bytes": row["size_bytes"],
            "hash_algorithm": row["hash_algorithm"], "declared_hash": row["declared_hash"],
        },
        "source": {"id": source["id"], "name": source["name"], "trust_tier": source["trust_tier"], "policy_version": policy.get("policy_version", 1)},
        "observation": {"id": row["observation_id"], "observed_uri": row["observed_uri"], "download_uri": url, "observed_at": row["observed_at"]},
        "destination_path": str(destination),
        "compatibility": {"state": assessment["state"]} if assessment else {"state": "unknown"},
    }
    stamp = now_iso()
    job_id = new_id()
    conn.execute(
        """INSERT INTO download_job(id,content_item_id,source_observation_id,approval_snapshot_json,destination_path,
           approval_state,status,total_bytes,created_at,updated_at) VALUES(?,?,?,?,?,'awaiting_approval','awaiting_approval',?,?,?)""",
        (job_id, content_id, observation_id, json_dump(snapshot), str(destination), row["size_bytes"], stamp, stamp),
    )
    event(conn, job_id, "approval_requested", "user", {"snapshot_digest": digest_json(snapshot), "destination_path": str(destination)})
    audit(conn, "download_approval_requested", "download_job", job_id, {"snapshot_digest": digest_json(snapshot), "content_item_id": content_id})
    return {"id": job_id, "status": "awaiting_approval", "snapshot": snapshot, "snapshot_digest": digest_json(snapshot)}


def current_snapshot(conn: Any, job_id: str) -> tuple[dict[str, Any], Any, Any]:
    job = conn.execute("SELECT * FROM download_job WHERE id=?", (job_id,)).fetchone()
    if not job:
        raise ValueError("Queue item was not found.")
    snapshot = json_load(job["approval_snapshot_json"])
    obs = conn.execute(
        """SELECT so.*,ci.*,s.id AS source_id,s.name AS source_name,s.trust_tier,s.enabled,s.policy_json,s.base_uri,
                  r.platform AS release_platform,r.region AS release_region,r.title_id AS release_title_id,g.canonical_title,
                  COALESCE((SELECT gn.value FROM game_name gn WHERE gn.game_id=g.id AND gn.language IN ('fa-IR','fa') AND gn.name_type IN ('title','alias') ORDER BY CASE gn.language WHEN 'fa-IR' THEN 0 ELSE 1 END,gn.created_at LIMIT 1),g.canonical_title) AS display_title
           FROM source_observation so JOIN content_item ci ON ci.id=so.content_item_id
           JOIN source s ON s.id=so.source_id JOIN game_release r ON r.id=ci.release_id JOIN game g ON g.id=r.game_id
           WHERE so.id=?""", (job["source_observation_id"],)
    ).fetchone()
    if not obs:
        raise ValueError("The approved source observation no longer exists.")
    source = conn.execute("SELECT * FROM source WHERE id=?", (obs["source_id"],)).fetchone()
    policy = json_load(source["policy_json"])
    latest_assessment = conn.execute("SELECT state,assessed_at FROM compatibility_assessment WHERE content_item_id=? ORDER BY assessed_at DESC LIMIT 1", (obs["content_item_id"],)).fetchone()
    candidate = {
        "item": {
            "content_item_id": obs["content_item_id"], "release_id": obs["release_id"], "game_title": obs["display_title"],
            "category": obs["category"], "title": obs["title"], "platform": obs["platform"], "title_id": obs["title_id"],
            "product_code": obs["product_code"], "region": obs["region"], "language": obs["language"],
            "page_language": obs["page_language"], "language_evidence": obs["language_evidence"], "version": obs["version"], "size_bytes": obs["size_bytes"],
            "hash_algorithm": obs["hash_algorithm"], "declared_hash": obs["declared_hash"],
        },
        "source": {"id": source["id"], "name": source["name"], "trust_tier": source["trust_tier"], "policy_version": policy.get("policy_version", 1)},
        "observation": {"id": obs["id"], "observed_uri": obs["observed_uri"], "download_uri": obs["download_uri"], "observed_at": obs["observed_at"]},
        "destination_path": job["destination_path"],
        "compatibility": {"state": latest_assessment["state"]} if latest_assessment else {"state": "unknown"},
    }
    return candidate, job, source


def ensure_snapshot_current(conn: Any, job_id: str) -> tuple[dict[str, Any], Any, Any, dict[str, Any]]:
    current, job, source = current_snapshot(conn, job_id)
    approved = json_load(job["approval_snapshot_json"])
    if current != approved or job["destination_path"] != approved.get("destination_path"):
        stamp = now_iso()
        conn.execute("UPDATE download_job SET status='approval_expired',approval_state='approval_expired',updated_at=?,error_reason=? WHERE id=?", (stamp, "The candidate, source policy, compatibility evidence, or destination changed after approval. Request approval again.", job_id))
        event(conn, job_id, "approval_expired", "system", {"reason": "approval snapshot changed"})
        audit(conn, "download_approval_expired", "download_job", job_id, {"reason": "approval snapshot changed"})
        # Callers may be inside a transaction context that rolls back when this
        # exception is raised. Persist the invalidation before reporting it.
        conn.commit()
        raise ValueError("Approval expired because the item, source policy, evidence, or destination changed. Request approval again.")
    policy = json_load(source["policy_json"])
    if not source["enabled"] or source["trust_tier"] == "blocked" or policy.get("review_status") != "reviewed_allowed" or not policy.get("allow_downloads"):
        raise ValueError("The source no longer permits this download; approval must be renewed after review.")
    if not job["authorization_ack"]:
        raise ValueError("The authorization confirmation is missing.")
    if job["status"] in ("incompatible", "verification_failed", "completed", "cancelled", "rejected"):
        raise ValueError(f"Queue item cannot start from state {job['status']}.")
    return current, job, source, policy


class DownloadManager:
    def __init__(self) -> None:
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def start(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._cancel:
                return
            if self._cancel:
                raise ValueError("A transfer is already active. The queue starts one download at a time.")
            signal = threading.Event()
            self._cancel[job_id] = signal
        thread = threading.Thread(target=self._run, args=(job_id, signal), name=f"drc-download-{job_id[:8]}", daemon=True)
        thread.start()

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            signal = self._cancel.get(job_id)
        if signal:
            signal.set()
            return True
        return False

    def _run(self, job_id: str, cancel: threading.Event) -> None:
        conn = connect()
        part_path: Path | None = None
        created_destination: Path | None = None
        try:
            with conn:
                snapshot, job, source, policy = ensure_snapshot_current(conn, job_id)
                if job["status"] not in ("approved", "queued"):
                    raise ValueError("Approve this exact candidate before starting the transfer.")
                cooldown = int(policy.get("request_cooldown_seconds", 60))
                if source["last_request_at"]:
                    try:
                        last_request = datetime.fromisoformat(source["last_request_at"].replace("Z", "+00:00"))
                        if last_request.tzinfo is None:
                            last_request = last_request.replace(tzinfo=timezone.utc)
                        remaining = cooldown - (datetime.now(timezone.utc) - last_request).total_seconds()
                    except ValueError:
                        remaining = 0
                    if remaining > 0:
                        raise ValueError(f"This source's configured rate limit requires waiting {int(remaining)+1} more seconds before a new download request.")
                request_stamp = now_iso()
                conn.execute("UPDATE source SET last_request_at=?,updated_at=? WHERE id=?", (request_stamp, request_stamp, source["id"]))
                conn.execute("UPDATE download_job SET status='downloading',updated_at=?,error_reason='' WHERE id=?", (now_iso(), job_id))
                event(conn, job_id, "download_started", "user", {"destination_path": job["destination_path"]})
            destination = Path(snapshot["destination_path"])
            parent = destination.parent.resolve(strict=True)
            if str(parent / destination.name) != str(destination) or not parent.is_dir():
                raise ValueError("Approved destination is no longer an existing folder path.")
            if destination.exists():
                raise ValueError("The approved destination file already exists; no file was overwritten.")
            uri = snapshot["observation"]["download_uri"]
            hosts = allowed_hosts(source, policy)
            connection = None
            response = None
            _, hostname, port, request_path = validate_download_url(uri, hosts, resolve=True)
            addresses = resolve_public(hostname)
            last_error = None
            for address in addresses:
                try:
                    connection = PinnedHTTPSConnection(hostname, port, address, timeout=20)
                    connection.request("GET", request_path, headers={"User-Agent": "DR-Crawler/0.1", "Accept-Encoding": "identity", "Connection": "close"})
                    response = connection.getresponse()
                    last_error = None
                    break
                except OSError as exc:
                    last_error = exc
                    if connection:
                        connection.close()
            if last_error:
                raise ValueError(f"Could not connect to the approved source host: {last_error}")
            if response.status in (301, 302, 303, 307, 308):
                connection.close()
                raise ApprovalExpiredError("Source redirected; the new URL was not followed. Review the source listing and record its current direct URL as a candidate before requesting approval again.")
            if response.status != 200:
                raise ValueError(f"Source returned HTTP {response.status}; no retry was attempted.")
            content_length = response.getheader("Content-Length")
            expected = snapshot["item"].get("size_bytes")
            declared_size = int(content_length) if content_length and content_length.isdigit() else None
            max_bytes = int(policy.get("max_download_bytes", 20_000_000_000))
            if declared_size is not None and declared_size > max_bytes:
                raise ValueError("Response exceeds this source's configured transfer size limit.")
            if expected is not None and declared_size is not None and int(expected) != declared_size:
                raise ApprovalExpiredError("Response size differs from the approved size. Review the updated candidate and request approval again.")
            if expected is not None and int(expected) > max_bytes:
                raise ValueError("Approved item exceeds this source's configured transfer size limit.")
            part_path = destination.with_name(f".{destination.name}.drcrawler-{job_id[:8]}.part")
            if part_path.exists():
                raise ValueError("A partial file from an earlier run already exists at the approved destination.")
            digest_name = snapshot["item"].get("hash_algorithm")
            hasher = hashlib.sha256()
            declared_hasher = hashlib.new(digest_name) if digest_name in ("sha256", "sha1") else None
            downloaded = 0
            last_update = time.monotonic()
            with part_path.open("xb") as output:
                while True:
                    if cancel.is_set():
                        raise InterruptedError("Transfer cancelled by the user.")
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if expected is not None and downloaded > int(expected):
                        raise ApprovalExpiredError("Response exceeded the approved size. Request new approval after reviewing the updated size.")
                    if downloaded > max_bytes:
                        raise ValueError("Transfer exceeded the approved or source-configured size limit.")
                    output.write(chunk)
                    hasher.update(chunk)
                    if declared_hasher:
                        declared_hasher.update(chunk)
                    if time.monotonic() - last_update > 0.75:
                        with conn:
                            conn.execute("UPDATE download_job SET progress_bytes=?,total_bytes=?,updated_at=? WHERE id=?", (downloaded, declared_size or expected, now_iso(), job_id))
                        last_update = time.monotonic()
                output.flush()
                os.fsync(output.fileno())
            if cancel.is_set():
                raise InterruptedError("Transfer cancelled by the user.")
            if expected is not None and downloaded != int(expected):
                raise ApprovalExpiredError("Response size differs from the approved size. Review the updated candidate and request approval again.")
            actual_hash = hasher.hexdigest()
            if declared_hasher and snapshot["item"].get("declared_hash"):
                if declared_hasher.hexdigest().casefold() != str(snapshot["item"]["declared_hash"]).strip().casefold():
                    part_path.unlink(missing_ok=True)
                    part_path = None
                    with conn:
                        conn.execute("UPDATE download_job SET status='verification_failed',integrity_state='mismatch',sha256_actual=?,progress_bytes=?,completed_at=?,updated_at=?,error_reason=? WHERE id=?", (actual_hash, downloaded, now_iso(), now_iso(), "Declared digest did not match the downloaded bytes.", job_id))
                        event(conn, job_id, "verification_failed", "system", {"algorithm": digest_name, "sha256_actual": actual_hash})
                        audit(conn, "download_verification_failed", "download_job", job_id, {"algorithm": digest_name, "sha256_actual": actual_hash})
                    return
            if destination.exists():
                raise ValueError("Approved destination became occupied; no file was overwritten.")
            try:
                os.link(part_path, destination)
                created_destination = destination
                part_path.unlink()
            except FileExistsError as exc:
                raise ValueError("Approved destination became occupied; no file was overwritten.") from exc
            except OSError:
                with destination.open("xb") as final_file:
                    created_destination = destination
                    with part_path.open("rb") as input_file:
                        while True:
                            block = input_file.read(CHUNK_SIZE)
                            if not block:
                                break
                            final_file.write(block)
                    final_file.flush()
                    os.fsync(final_file.fileno())
                part_path.unlink()
            part_path = None
            created_destination = None
            integrity = "verified" if declared_hasher and snapshot["item"].get("declared_hash") else "no_declared_hash"
            with conn:
                conn.execute("UPDATE download_job SET status='completed',integrity_state=?,sha256_actual=?,progress_bytes=?,total_bytes=?,completed_at=?,updated_at=? WHERE id=?", (integrity, actual_hash, downloaded, downloaded, now_iso(), now_iso(), job_id))
                event(conn, job_id, "download_completed", "system", {"bytes": downloaded, "sha256": actual_hash, "integrity_state": integrity, "destination_path": str(destination)})
                audit(conn, "download_completed", "download_job", job_id, {"bytes": downloaded, "sha256": actual_hash, "destination_path": str(destination)})
        except InterruptedError as exc:
            if part_path:
                part_path.unlink(missing_ok=True)
            if created_destination:
                created_destination.unlink(missing_ok=True)
            with conn:
                conn.execute("UPDATE download_job SET status='cancelled',updated_at=?,error_reason=? WHERE id=?", (now_iso(), str(exc), job_id))
                event(conn, job_id, "download_cancelled", "user", {"reason": str(exc)})
                audit(conn, "download_cancelled", "download_job", job_id, {"reason": str(exc)})
        except ApprovalExpiredError as exc:
            if part_path:
                part_path.unlink(missing_ok=True)
            if created_destination:
                created_destination.unlink(missing_ok=True)
            with conn:
                conn.execute("UPDATE download_job SET status='approval_expired',approval_state='approval_expired',updated_at=?,error_reason=? WHERE id=?", (now_iso(), str(exc)[:800], job_id))
                event(conn, job_id, "approval_expired", "system", {"reason": str(exc)[:800]})
                audit(conn, "download_approval_expired", "download_job", job_id, {"reason": str(exc)[:800]})
        except Exception as exc:
            if part_path:
                part_path.unlink(missing_ok=True)
            if created_destination:
                created_destination.unlink(missing_ok=True)
            with conn:
                current = conn.execute("SELECT status FROM download_job WHERE id=?", (job_id,)).fetchone()
                if current and current["status"] not in ("approval_expired", "verification_failed", "cancelled"):
                    conn.execute("UPDATE download_job SET status='failed',updated_at=?,error_reason=? WHERE id=?", (now_iso(), str(exc)[:800], job_id))
                    event(conn, job_id, "download_failed", "system", {"reason": str(exc)[:800]})
                    audit(conn, "download_failed", "download_job", job_id, {"reason": str(exc)[:800]})
        finally:
            try:
                if "response" in locals() and response:
                    response.close()
                if "connection" in locals() and connection:
                    connection.close()
            except Exception:
                pass
            conn.close()
            with self._lock:
                self._cancel.pop(job_id, None)
