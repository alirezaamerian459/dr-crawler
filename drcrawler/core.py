from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .constants import CATEGORIES, PLATFORMS, TRUST_TIERS


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    import uuid

    return str(uuid.uuid4())


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_load(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback if fallback is not None else {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback if fallback is not None else {}


def normalize_text(value: str | None) -> str:
    """Normalize search text without changing the original displayed value."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"}))
    value = value.replace("ـ", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def normalize_identifier(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def normalize_language_tag(value: str | None) -> str | None:
    value = (value or "").strip().replace("_", "-")
    if not value:
        return None
    parts = value.split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(part.upper() if len(part) == 2 else part.title() if len(part) == 4 else part.lower())
    return "-".join(normalized)[:32]


def digest_json(value: Any) -> str:
    return hashlib.sha256(json_dump(value).encode("utf-8")).hexdigest()


def candidate_identity_digest(fields: dict[str, Any]) -> str:
    """Stable cross-source identity; listing language, URL, and trust are evidence, not identity."""
    return digest_json({
        "release_id": fields.get("release_id"),
        "category": fields.get("category"),
        "title": normalize_text(fields.get("title")),
        "platform": fields.get("platform"),
        "title_id": normalize_identifier(fields.get("title_id")),
        "product_code": normalize_identifier(fields.get("product_code")),
        "region": normalize_text(fields.get("region")),
        "language": str(fields.get("language") or "").casefold(),
        "language_evidence": str(fields.get("language_evidence") or "").casefold(),
        "version": str(fields.get("version") or "").casefold(),
        "size_bytes": fields.get("size_bytes"),
        "hash_algorithm": fields.get("hash_algorithm"),
        "declared_hash": str(fields.get("declared_hash") or "").casefold(),
    })


def validate_game_record(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    platform = str(raw.get("platform", "")).strip().upper().replace("PLAYSTATION ", "PS")
    aliases = {"4": "PS4", "5": "PS5", "PS 4": "PS4", "PS 5": "PS5"}
    platform = aliases.get(platform, platform)
    title = str(raw.get("title", raw.get("canonical_title", ""))).strip()
    title_id = str(raw.get("title_id", "")).strip()
    product_code = str(raw.get("product_code", "")).strip()
    if platform not in PLATFORMS:
        return None, "platform must be PS4 or PS5"
    if not title and not title_id and not product_code:
        return None, "title or identifier is required"
    if len(title) > 300 or len(title_id) > 100 or len(product_code) > 160:
        return None, "a field exceeds the supported length"
    if not title:
        title = title_id or product_code
    aliases_raw = raw.get("aliases", [])
    if isinstance(aliases_raw, str):
        aliases_raw = aliases_raw.splitlines()
    aliases: list[dict[str, str | None]] = []
    if isinstance(aliases_raw, list):
        for alias in aliases_raw[:100]:
            if isinstance(alias, dict):
                value = str(alias.get("value", alias.get("title", ""))).strip()
                language = normalize_language_tag(str(alias.get("language", "")))
            else:
                value = str(alias).strip()
                language = None
                if "|" in value:
                    maybe_language, maybe_value = value.split("|", 1)
                    if re.fullmatch(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*", maybe_language.strip()):
                        language = normalize_language_tag(maybe_language)
                        value = maybe_value.strip()
            if value and len(value) <= 300 and normalize_text(value) != normalize_text(title):
                aliases.append({"value": value, "language": language})
    record = {
        "platform": platform,
        "title": title,
        "region": str(raw.get("region", "")).strip()[:80] or None,
        "title_id": title_id or None,
        "product_code": product_code or None,
        "language": normalize_language_tag(str(raw.get("language", ""))) or None,
        "languages": [normalize_language_tag(str(language)) for language in raw.get("languages", []) if normalize_language_tag(str(language))] if isinstance(raw.get("languages", []), list) else [],
        "aliases": aliases,
        "owned_since": str(raw.get("owned_since", "")).strip()[:32] or None,
        "source": str(raw.get("source", "import")).strip()[:120] or "import",
        "notes": str(raw.get("notes", raw.get("evidence_note", (raw.get("ownership") or {}).get("evidence_note", "") if isinstance(raw.get("ownership", {}), dict) else ""))).strip()[:2000],
        "ownership_status": str((raw.get("ownership") or {}).get("status", "user_asserted"))
        if isinstance(raw.get("ownership", {}), dict)
        else "user_asserted",
    }
    return record, None


def validate_source_url(value: str | None, *, allow_empty: bool = True) -> str | None:
    value = (value or "").strip()
    if not value and allow_empty:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a public HTTP or HTTPS URL without embedded credentials.")
    if len(value) > 2048:
        raise ValueError("URL is too long.")
    return value


def validate_category(value: str) -> str:
    if value not in CATEGORIES:
        raise ValueError("Choose a supported content category.")
    return value


def validate_platform(value: str | None) -> str | None:
    value = (value or "").strip().upper() or None
    if value is not None and value not in PLATFORMS:
        raise ValueError("Platform must be PS4 or PS5.")
    return value


def validate_source_fields(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 160:
        raise ValueError("Source name is required and must be under 160 characters.")
    trust = str(data.get("trust_tier", "unverified"))
    if trust not in TRUST_TIERS:
        raise ValueError("Choose a valid trust tier.")
    base_uri = validate_source_url(data.get("base_uri"), allow_empty=True)
    terms_uri = validate_source_url(data.get("terms_uri"), allow_empty=True)
    capabilities = data.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise ValueError("Capabilities must be an object.")
    platforms = [p for p in capabilities.get("platforms", []) if p in PLATFORMS]
    categories = [c for c in capabilities.get("categories", []) if c in CATEGORIES]
    languages = [normalize_language_tag(str(x)) or str(x).strip()[:32] for x in capabilities.get("languages", []) if str(x).strip()]
    query_types = [str(x)[:40] for x in capabilities.get("query_types", []) if str(x).strip()]
    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        raise ValueError("Access policy must be an object.")
    policy = {
        "review_status": policy.get("review_status", "unknown")
        if policy.get("review_status") in ("unknown", "reviewed_allowed", "blocked")
        else "unknown",
        "allow_discovery": bool(policy.get("allow_discovery", False)),
        "allow_downloads": bool(policy.get("allow_downloads", False)),
        "allowed_hosts": sorted({str(h).strip().casefold() for h in policy.get("allowed_hosts", []) if str(h).strip()}),
        "max_download_bytes": max(0, min(int(policy.get("max_download_bytes", 20_000_000_000)), 100_000_000_000)),
        "request_cooldown_seconds": max(1, min(int(policy.get("request_cooldown_seconds", 60)), 86_400)),
        "rate_limit_note": str(policy.get("rate_limit_note", "")).strip()[:500],
        "policy_version": int(policy.get("policy_version", 1)),
    }
    if policy["review_status"] != "reviewed_allowed":
        policy["allow_discovery"] = False
        policy["allow_downloads"] = False
    if policy["review_status"] == "blocked":
        trust = "blocked"
    return {
        "name": name,
        "source_type": str(data.get("source_type", "public_web"))[:40],
        "base_uri": base_uri,
        "trust_tier": trust,
        "enabled": bool(data.get("enabled", True)),
        "attribution": str(data.get("attribution", "")).strip()[:500],
        "maintainer": str(data.get("maintainer", "")).strip()[:200],
        "verification_note": str(data.get("verification_note", "")).strip()[:1000],
        "terms_uri": terms_uri,
        "reviewed_at": str(data.get("reviewed_at", "")).strip()[:40] or (now_iso() if policy["review_status"] == "reviewed_allowed" else None),
        "policy": policy,
        "capabilities": {"platforms": sorted(set(platforms)), "categories": sorted(set(categories)), "languages": sorted(set(languages)), "query_types": sorted(set(query_types))},
        "health_state": str(data.get("health_state", "unknown"))
        if data.get("health_state") in ("unknown", "healthy", "limited", "unavailable", "blocked")
        else "unknown",
    }
