# Logical database schema

This is a planning model, not an executable migration. Use normalized identities and append-only observations so new source evidence does not overwrite what the user or another source previously reported. Concrete database engine, types, migrations, and encryption strategy remain design decisions.

## Core entities

| Entity | Important fields | Purpose / key constraints |
| --- | --- | --- |
| `game` | `id`, `canonical_title`, `created_at`, `updated_at` | Stable canonical game identity, independent of a region or platform release |
| `game_name` | `id`, `game_id`, `value`, `normalized_value`, `language`, `name_type`, `provenance` | Localized title, alias, transliteration; retain original text; index normalized form + language |
| `game_release` | `id`, `game_id`, `platform`, `region`, `title_id`, `product_code`, `release_version` | Platform/region-specific identity; unique non-null identifiers in their appropriate namespace |
| `owned_game` | `id`, `release_id` nullable, `game_id`, `ownership_status`, `evidence_note`, `input_source`, `created_at` | User's collection assertion and provenance; does not store account credentials |
| `content_item` | `id`, `release_id`, `category`, `title`, `language`, `version`, `region`, `size_bytes`, `declared_hash`, `compatibility_state` | Normalized candidate or local content identity; category is one of update/DLC/subtitle/theme/homebrew or future extension |
| `source` | `id`, `name`, `source_type`, `base_uri`, `trust_tier`, `enabled`, `policy_json`, `terms_uri`, `reviewed_at`, `health_state` | Registry and per-source request/security policy |
| `source_capability` | `source_id`, `platform`, `category`, `language`, `query_type` | Declared source coverage and supported identifiers |
| `source_observation` | `id`, `source_id`, `content_item_id`, `external_id`, `observed_title`, `observed_uri`, `observed_at`, `payload_digest`, `evidence_json`, `adapter_version`, `result_state` | Immutable or versioned source assertion; unique source + external ID + observation fingerprint where possible |
| `game_source_coverage` | `release_id`, `source_id`, `category`, `state`, `checked_at`, `next_check_at`, `candidate_count`, `reason`, `policy_version` | Latest per-game/release/category/source summary; history remains in source checks |
| `source_check` | `id`, `release_id`, `source_id`, `category`, `started_at`, `completed_at`, `outcome`, `reason`, `query_digest`, `adapter_version` | Auditable individual checks and explicit no-result/error states |
| `local_root` | `id`, `display_path`, `volume_identity`, `volume_label`, `filesystem`, `removable`, `availability`, `last_seen_at`, `user_selected_at` | Explicitly selected local scan root; path identity is not just a drive letter |
| `scan_run` | `id`, `root_id`, `started_at`, `completed_at`, `status`, `scope_json`, `scanner_version`, `items_seen`, `errors_count` | Scan snapshot; only complete runs can reconcile missing items |
| `local_file` | `id`, `root_id`, `relative_path`, `name`, `size_bytes`, `modified_at`, `hash_algorithm`, `hash_value`, `last_seen_run_id`, `presence_state`, `parse_state` | Read-only observation of a local item; unique root + normalized relative path |
| `content_local_match` | `content_item_id`, `local_file_id`, `match_state`, `confidence`, `evidence_json`, `confirmed_by_user_at` | Links discovered content to local file without conflating them |
| `compatibility_assessment` | `id`, `content_item_id`, `release_id`, `state`, `confidence`, `rule_version`, `evidence_json`, `assessed_at` | Explainable, versioned assessment and conflicts |
| `download_job` | `id`, `content_item_id`, `source_observation_id`, `approval_snapshot_json`, `approval_state`, `destination_root_id`, `destination_relative_path`, `status`, `created_at`, `updated_at` | Exact user approval and transfer lifecycle; approval binds to candidate snapshot |
| `download_event` | `id`, `job_id`, `event_type`, `timestamp`, `actor`, `details_json` | Append-only queue/approval/transfer/verification history |
| `user_preference` | `key`, `value_json`, `updated_at` | Locale, root suggestion, categories, freshness, and optional scan/hash preferences |

## Relationships and integrity

- A `game` has many names and releases; an `owned_game` points to a game and optionally a release.
- A `source_check` belongs to one release, category, and source. Its normalized observations link to zero or more content items.
- Coverage is a replaceable summary; check and observation history remains available for audit and freshness.
- A `local_file` belongs to one selected root and is updated only from complete/partial scan observations under the rules in Phase 6.
- A content item can have multiple source observations and local-file matches. Preserve each evidence path rather than choosing a single “truth” field.
- A `download_job` references the source observation and approval snapshot that authorized it. Candidate changes invalidate approval.

## Indexes and privacy notes

Plan indexes for normalized Persian/original names, title IDs/product codes, game + source + category coverage, source external IDs, scan run + root, root + normalized path, content category/language/version, and queue status. Use case-insensitive/Unicode-aware matching deliberately; retain raw values separately.

Keep paths local to the user profile by default and avoid uploading collection, volume identifiers, or firmware details. Do not persist passwords, cookies, or platform account tokens. Define retention and backup behavior before implementation; audit records must not contain secrets.
