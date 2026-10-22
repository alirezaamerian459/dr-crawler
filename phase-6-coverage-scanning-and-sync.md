# Phase 6 — coverage matrix, HDD metadata scanning, and synchronization

## Per-game coverage matrix

The matrix answers “what has been checked for this game, category, and source?” It is keyed by canonical game/release × content category × source. Its row should show:

- Source name and trust tier.
- Category (update, DLC, subtitles, theme, homebrew) and platform/release scope.
- Coverage state and last attempt/completion time.
- Number of candidate observations and whether any are local matches.
- Languages found, strongest identity/compatibility confidence, and stale/health indicator.
- Reason for no result, source unavailability, unsupported capability, or policy block.

Coverage states: `not_checked`, `checked_found`, `checked_no_result`, `unavailable`, `blocked_by_policy`, `unsupported`, `stale`, and `error`. A local file can coexist with each state; it is shown as a separate local-presence signal. A matrix summary should say “N configured sources checked” and list skipped/unavailable sources. It must never claim “all sources” or “complete” without a defined registry snapshot and time.

For prioritization, use Persian-language availability and user category preferences only after safety and source policy. A discovery job can be started for one game, a selected group, or the collection; bulk jobs remain bounded and cancellable.

## HDD metadata scanner

The scanner operates only on roots selected by the user. The initial suggested root is `D:\PlayStation-Library`; additional disks/folders are explicit. Each root stores its display path and, when possible, volume identity, filesystem type, label, removable status, and last availability. This metadata helps identify a drive after its mount letter changes; it must not be used to scan other volumes automatically.

For each selected root, the metadata pass records directories/files in scope and likely package/sidecar candidates. It reads names, relative paths, sizes, timestamps, and optional manifests; hash computation is configurable. It does not inspect protected package payloads, extract archives, launch content, or write metadata into the scanned tree. User-facing labels should say `detected`, `inferred`, or `user-confirmed` so confidence is visible.

Safety constraints: canonicalize root and candidate paths; reject path traversal; do not follow reparse points across the root boundary; detect loops; limit path depth, item count, and file size for parsers; isolate parse errors per file; and never report a partial/cancelled scan as a complete inventory.

## Synchronization rules

1. **Start snapshot.** A scan run records selected root identity, start time, scanner version, scope, and status `running`.
2. **Incremental reconciliation.** Match observations by stable root identity + normalized relative path; use file metadata and an optional content hash to detect change or duplicates. A move is a new path plus a prior-path candidate, not an automatic destructive rename.
3. **Commit only complete scope.** Mark unseen items missing only after a successful, complete scan of the same root and scope. A cancellation, permission error, disconnected disk, or partial traversal cannot mark files missing.
4. **Offline disks.** Mark root `unavailable`/`last_seen_at`; preserve last known files and their previous scan time. Do not equate offline with empty or remove local matches.
5. **Reappearance.** When the same volume identity returns, reconcile and restore present state. If identity cannot be verified, ask the user whether the path represents a known root before merging.
6. **Deletion and retention.** Missing observations are soft-state with `last_seen_at` and reason. Retain history and allow correction; do not delete catalog data automatically. Any cleanup policy is a user-visible setting.
7. **Idempotency.** Repeating a scan or source check without changed evidence should update last-checked data without duplicating the canonical game or candidate. Preserve source observations and scan history for provenance.

Source synchronization and disk synchronization are independent. A changed source candidate cannot alter local files, and a scan cannot claim that remote content is available. The per-game view joins these records only for comparison and coverage.

## Freshness and scheduling

Freshness is per source and category, using a configurable TTL plus source-specific policy. Store `checked_at`, `next_check_at`, and source/adapter policy version. A failed check does not replace a prior successful result; mark that result stale and show the failure separately. Automatic refresh, if enabled later, must respect user-selected scope, source limits, quiet-hours preferences if any, and cancellation.

## Phase 6 exit criteria

- Matrix states distinguish no result, not checked, stale, unavailable, blocked, and local presence.
- An HDD disconnect/reconnect cannot create false deletion or duplicate catalogs.
- A complete scan is auditable and reproducible from its recorded scope and version.
