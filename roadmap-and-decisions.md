# Roadmap, decisions, and open questions

## Phase roadmap

| Phase | Planning outcome | Gate before the next phase |
| --- | --- | --- |
| 1. Scope | Goals, user journeys, initial platforms/categories, boundaries | Product scope and forbidden behaviors accepted |
| 2. Architecture | Component/data flow, trust boundaries, privacy and resilience | Local/network boundaries and inert-file rule accepted |
| 3. Catalog and sources | Identity model, Persian-first discovery, source registry and trust | Evidence, source policies, and coverage states accepted |
| 4. Local library | Owned-game import, explicit roots, safe metadata scanner | Import and read-only scan behavior accepted |
| 5. Compatibility and queue | Compatibility evidence and exact approval-bound transfer | Approval snapshot and authorization rules accepted |
| 6. Coverage and synchronization | Matrix, HDD sync/reconnect behavior, freshness and completion rules | No false-complete/no false-deletion behavior accepted |

These phases record the original planning order. They do not promise dates, and their exit criteria have not all been re-certified by the first implementation. The implemented scope and remaining gaps are recorded below.

## Implementation record — first local release

- **Technology:** Python 3.10+ standard library, a browser UI served on loopback, and SQLite. This keeps setup small on Windows and leaves the scanner, source model, and persistence code modular. A browser interface was chosen over a packaged desktop shell because the repository had no stack and no packaging toolchain.
- **Local storage:** SQLite is versioned with `PRAGMA user_version`; migration 1 creates the initial catalog, source, scan, assessment, approval, and audit tables, and migration 2 adds/backfills stable candidate identity for cross-source observation merging. The database stays in the user's local application-data folder by default. No collection data or local paths are uploaded.
- **Localization:** The interface is `fa-IR` and RTL. Recorded Persian titles lead display and source-language ranking; original titles and normalized identifiers remain searchable. Source trust and candidate compatibility are separate evidence.
- **Sources:** No source names or access-policy reviews were provided. The first release starts with an empty registry and supports manual source, candidate, and check records. Repeated same-source observations are idempotent; matching candidate identities from different sources share one candidate with separate observation evidence. It does not fetch or crawl listings. Downloads are available only after a user marks that source's policy as reviewed/allowed, confirms authorization, approves the exact snapshot, and starts the transfer.
- **Local roots:** `D:\PlayStation-Library` is a suggestion only. Roots must be added explicitly. The scanner reads filesystem metadata and filename patterns, skips symlinks/reparse points, does no content hashing, and reconciles missing files only after a complete scan of the selected root. A disconnected root keeps its previous inventory.
- **Compatibility and approval:** Compatibility uses conservative identifier/platform/region rules and appends evidence. A user-confirmed local-file link is required for `already_present`. Approval is per item and exact output path; there is no batch approval. Changed item identity, URL, version, size, hash, source policy, compatibility state, or destination expires approval.
- **Freshness and hashing:** The configurable coverage TTL defaults to 30 days. Scan hashing is off and not implemented; a download digest is checked only when a source has declared SHA-1/SHA-256 evidence. Missing integrity evidence is shown explicitly.
- **Ownership and destinations:** Imports and manual entries preserve a user assertion and optional note, not account data. Download destinations must be existing folders selected or entered by the user; no default staging folder is created.

## Remaining decisions and planned work

The open decisions below remain open. The current defaults make the local collection, import review, metadata scan, manual coverage, compatibility review, and approval queue usable without pretending that source onboarding or policy review has been completed. Future work can add reviewed, policy-compliant adapters; richer documented sidecar parsing; packaging/signing; and backup/retention controls after those decisions are made.

## Current planning decisions from the brief

- Product is Persian-first for discovery, with identifiers and source-language titles retained.
- Platforms are PS4 and PS5.
- Default suggested library root is `D:\PlayStation-Library`; users select HDDs/folders explicitly.
- Initial categories are updates, DLC, subtitles, themes, and homebrew.
- Discovery is per game, with a source registry and visible coverage for each game/source/category.
- Local disk scanning is metadata-only and read-only.
- Downloads require approval for each exact candidate and are limited to content the user is authorized to obtain.
- The phase documents still describe the target product; see the implementation record for the first release's actual scope.

## Open decisions for later milestones

1. **Desktop platform and technology:** Windows-only first (the default root suggests Windows) or cross-platform from the first release?
2. **Source onboarding:** Which specific official and maintained community sources may be included, and who reviews source terms and trust status?
3. **Ownership evidence:** Should the first release accept only a user assertion, or support an optional local evidence note/import field? Do not collect account credentials.
4. **Package metadata:** Which safe, documented filename/sidecar formats should be recognized without reading package payloads?
5. **Hash policy:** Should full-file hashing be opt-in, scheduled, or only on download? Choose a default based on expected HDD size and performance.
6. **Freshness:** What TTLs should apply by source/category, and which refresh operations may run automatically?
7. **Download destinations:** Is a dedicated `Downloads` staging folder under the library preferred? Should approval be per-item only or allow one explicit batch approval after a review summary?
8. **Source verification:** What independent evidence qualifies a source for `official` or `maintained_community` status, and who can change a source to `blocked`?
9. **Localization:** Which locales are required at launch beyond Persian and English? Which Persian regional conventions should UI labels use?
10. **Retention and backup:** How long should source/scan history, failed download details, and audit events be retained?

## Planning completion definition (original)

Planning is complete when the owner accepts phase gates, selects initial sources, resolves the open decisions needed to build a first release, and approves a technical design and data migration plan. Code, live crawlers, and download adapters belong to a later, separately authorized implementation phase.
