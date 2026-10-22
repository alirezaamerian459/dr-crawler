# DR Crawler planning

Planning documents for a Persian-first PS4/PS5 library catalog and source-discovery tool. This repository currently defines the product and its data flows; it contains no implementation.

The product helps a user understand what content exists for each game they own, where that content was observed, whether it appears compatible with their title and system, and whether a copy is already present in a folder or HDD they selected. Persian (`fa-IR`) is the preferred discovery language, while original-language names and identifiers remain searchable.

## Product defaults

- Platforms: PlayStation 4 and PlayStation 5.
- Library root default: `D:\PlayStation-Library`; the user can choose other folders or HDDs.
- Initial content categories: updates, DLC, subtitles, themes, and homebrew.
- Discovery is per game and records all configured source checks, including no-result and unavailable outcomes.
- Local scanning is read-only and limited to roots the user explicitly selected.
- A download is never started until the user approves that exact item and destination. Downloads are for content the user is authorized to obtain; no installation, account bypass, DRM circumvention, or unattended acquisition is in scope.

## Planning index

1. [Phase 1 — product scope and user journeys](phase-1-product-scope.md)
2. [Phase 2 — architecture and system boundaries](phase-2-architecture.md)
3. [Phase 3 — game catalog, Persian discovery, and source registry](phase-3-catalog-and-source-registry.md)
4. [Phase 4 — owned games and local HDD scanning](phase-4-local-library-and-owned-games.md)
5. [Phase 5 — compatibility and approval-based downloads](phase-5-compatibility-and-authorized-downloads.md)
6. [Phase 6 — coverage matrix and synchronization](phase-6-coverage-scanning-and-sync.md)
7. [Logical database schema](database-schema.md)
8. [Roadmap, decisions, and open questions](roadmap-and-decisions.md)

## Planning status

The selected product constraints above come from the planning brief. Details marked as proposed or open in the documents still need owner review before implementation. No crawler, database, downloader, or scanner has been implemented here.
