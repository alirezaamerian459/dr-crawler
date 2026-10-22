# Phase 5 — compatibility and approval-based downloads

## Compatibility model

Compatibility is an evidence-backed assessment, not a guarantee. Compare a candidate with the selected game release and any system details the user chooses to provide. Relevant dimensions include:

- Platform (PS4/PS5) and package/content type.
- Exact title/product ID and region where the candidate declares them.
- Base-game association for an update or DLC.
- Update version, base-version range, dependency, and required system firmware when stated.
- Language/subtitle availability and locale evidence.
- Source's own compatibility claim, evidence date, and confidence.

Use clear states: `exact_match`, `likely_match`, `needs_review`, `incompatible`, `unknown`, and `already_present`. Explain the evidence and conflicts behind every state. Exact ID + compatible platform can support an exact identity match, but cannot establish licensing or safety. Unknown requirements remain unknown; never invent them. If versions or IDs conflict, downgrade to review or incompatible based on an explicit rule and preserve the reason.

An optional user-supplied console firmware value may be used for comparison, but it is sensitive local preference data and not required. Do not probe a console or upload this information.

## Trust and candidate review

The result view should show source tier, source attribution, original listing, candidate identifiers, language, size, version, known hash, compatibility state, source-check time, and missing/conflicting evidence. Source trust never automatically converts a candidate into a safe or authorized download.

## Approval-bound download queue

Default policy is `approval_required` for every item. Before starting, show the exact content item and category, game/release association, source and final URL/host, version, size, destination, available hash/signature evidence, trust tier, compatibility result, and rights/authorization reminder. The user approves that exact snapshot; if URL, item identity, version, size, hash, or destination changes, pause and request new approval.

Planned states: `awaiting_approval`, `approved`, `queued`, `downloading`, `paused`, `completed`, `failed`, `cancelled`, `rejected`, `approval_expired`, and `verification_failed`. Each transition is timestamped and attributable to a user action or system event. Approval can be revoked before completion; cancel/delete behavior must be clear and must not erase audit history.

Transfer safeguards:

- Fetch only from an allowed source URL over HTTPS by default; re-check every redirect and reject unsafe schemes and local/private-network destinations.
- Honor source terms, robots/access rules, rate limits, and size caps. Stop rather than retrying an access block.
- Use the chosen staging destination, free-space check, bounded retries, resumable transfer where safe, and cancellation.
- Verify a declared digest only against a recorded source of that digest. Report absent integrity evidence honestly; do not imply that transport security proves package safety.
- Store the downloaded file inertly. Do not install, mount, unpack, execute, or redistribute it.

The policy permits only downloads that the user is authorized to obtain. No account credential collection, paywall bypass, DRM/console-security circumvention, or automated sourcing of unauthorized copies is in scope. The user is responsible for confirming rights; the application must not present ownership of a game as blanket permission for every candidate.

## Phase 5 exit criteria

- Compatibility states and evidence requirements are understood as guidance, not guarantees.
- Every transfer is tied to an explicit, auditable approval for one unchanged candidate.
- Transfer completion is separate from verification, installation, and use.
