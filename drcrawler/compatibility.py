from __future__ import annotations

import sqlite3
from typing import Any

from .core import json_dump, new_id, normalize_identifier, normalize_text, now_iso


RULE_VERSION = "evidence-v1"


def assess(conn: sqlite3.Connection, content_id: str) -> dict[str, Any]:
    item = conn.execute("SELECT * FROM content_item WHERE id=?", (content_id,)).fetchone()
    if not item:
        raise ValueError("Candidate was not found.")
    release = conn.execute("SELECT r.*,g.canonical_title,g.normalized_title FROM game_release r JOIN game g ON g.id=r.game_id WHERE r.id=?", (item["release_id"],)).fetchone()
    if not release:
        raise ValueError("Game release was not found.")
    evidence: list[dict[str, str]] = []
    state = "unknown"
    confidence = "low"
    confirmed = conn.execute(
        "SELECT 1 FROM content_local_match WHERE content_item_id=? AND match_state='user_confirmed' LIMIT 1", (content_id,)
    ).fetchone()
    if item["platform"] and item["platform"] != release["platform"]:
        state, confidence = "incompatible", "high"
        evidence.append({"kind": "platform_conflict", "detail": f"Candidate declares {item['platform']}; this release is {release['platform']}."})
    else:
        candidate_title_id = item["normalized_title_id"] or normalize_identifier(item["title_id"])
        release_title_id = release["normalized_title_id"] or normalize_identifier(release["title_id"])
        candidate_product = item["normalized_product_code"] or normalize_identifier(item["product_code"])
        release_product = release["normalized_product_code"] or normalize_identifier(release["product_code"])
        exact_identity = bool(candidate_title_id and release_title_id and candidate_title_id == release_title_id)
        exact_identity = exact_identity or bool(candidate_product and release_product and candidate_product == release_product)
        id_conflict = bool(candidate_title_id and release_title_id and candidate_title_id != release_title_id)
        region_conflict = bool(item["region"] and release["region"] and normalize_text(item["region"]) != normalize_text(release["region"]))
        product_conflict = bool(candidate_product and release_product and candidate_product != release_product)
        if id_conflict:
            state, confidence = "incompatible", "high"
            evidence.append({"kind": "title_id_conflict", "detail": f"Candidate title ID {item['title_id']} conflicts with game release ID {release['title_id']}."})
        elif exact_identity and region_conflict:
            state, confidence = "needs_review", "medium"
            evidence.append({"kind": "region_conflict", "detail": f"Candidate region {item['region']} differs from release region {release['region']}."})
            evidence.append({"kind": "identifier_match", "detail": "The declared title or product identifier matches the release."})
        elif exact_identity:
            state, confidence = "exact_match", "high"
            evidence.append({"kind": "identifier_match", "detail": "The candidate declares an exact title ID or product code match."})
        elif item["platform"] == release["platform"] and item["platform"]:
            if region_conflict or product_conflict:
                state, confidence = "needs_review", "low"
                if region_conflict:
                    evidence.append({"kind": "region_conflict", "detail": "Region labels differ; their impact is not inferred."})
                if product_conflict:
                    evidence.append({"kind": "product_code_difference", "detail": "Product codes differ; this can identify a different release or content package."})
            else:
                game_title = release["normalized_title"]
                candidate_title = normalize_text(item["title"])
                if game_title and (game_title in candidate_title or candidate_title in game_title):
                    state, confidence = "likely_match", "medium"
                    evidence.append({"kind": "title_similarity", "detail": "The listing title contains the game title, but no exact identifier was supplied."})
                else:
                    state, confidence = "needs_review", "low"
                    evidence.append({"kind": "identifier_missing", "detail": "Platform matches, but the listing provides no exact game identifier."})
        else:
            if item["platform"]:
                evidence.append({"kind": "platform_match", "detail": "Candidate platform matches the selected release."})
            else:
                evidence.append({"kind": "platform_unknown", "detail": "Candidate platform is not declared."})
            if not candidate_title_id and not candidate_product:
                evidence.append({"kind": "identifier_missing", "detail": "No title ID or product code was reported for this candidate."})
            state, confidence = "unknown", "low"
    if confirmed:
        evidence.append({"kind": "user_confirmed_local_match", "detail": "A local file was explicitly linked to this candidate by the user."})
        if state not in ("incompatible", "needs_review"):
            state, confidence = "already_present", "high"
    stamp = now_iso()
    conn.execute(
        "INSERT INTO compatibility_assessment(id,content_item_id,release_id,state,confidence,rule_version,evidence_json,assessed_at) VALUES(?,?,?,?,?,?,?,?)",
        (new_id(), content_id, item["release_id"], state, confidence, RULE_VERSION, json_dump(evidence), stamp),
    )
    return {"state": state, "confidence": confidence, "rule_version": RULE_VERSION, "evidence": evidence, "assessed_at": stamp}
