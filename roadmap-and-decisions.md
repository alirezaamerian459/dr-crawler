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

These phases define planning order only. They do not promise dates or implementation. The release should be broken into smaller implementation milestones after the owner accepts the open decisions below.

## Current planning decisions from the brief

- Product is Persian-first for discovery, with identifiers and source-language titles retained.
- Platforms are PS4 and PS5.
- Default suggested library root is `D:\PlayStation-Library`; users select HDDs/folders explicitly.
- Initial categories are updates, DLC, subtitles, themes, and homebrew.
- Discovery is per game, with a source registry and visible coverage for each game/source/category.
- Local disk scanning is metadata-only and read-only.
- Downloads require approval for each exact candidate and are limited to content the user is authorized to obtain.
- This repository is planning only; no implementation is included.

## Open decisions before implementation

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

## Completion definition

Planning is complete when the owner accepts phase gates, selects initial sources, resolves the open decisions needed to build a first release, and approves a technical design and data migration plan. Code, live crawlers, and download adapters belong to a later, separately authorized implementation phase.
