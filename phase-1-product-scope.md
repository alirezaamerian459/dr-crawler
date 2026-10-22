# Phase 1 — product scope and user journeys

## Product goal

Create a desktop-first catalog and discovery workflow for a user's PS4/PS5 game collection. For every owned game, show candidate updates, DLC, subtitles, themes, and homebrew references found in the user's configured source registry, alongside content already present in user-selected local library folders.

The central view is per game: identity and ownership evidence, local files, compatible and uncertain content candidates, source provenance and trust, and the latest source-check status. The tool must distinguish “checked and found nothing” from “not checked” and “source unavailable.”

## Users and primary journeys

1. **Set up a collection.** Choose a library root (initial suggestion `D:\PlayStation-Library`), add any other HDDs/folders explicitly, and import owned games from a documented CSV/JSON file or add them manually.
2. **Resolve game identity.** Match names, platform, region, title/product identifiers, and aliases. Review ambiguous matches before they become canonical collection entries.
3. **Discover per-game content.** Search the registered sources using Persian first, then configured fallback languages. Inspect each result's evidence, language, compatibility confidence, trust, and last-checked time.
4. **Review local coverage.** See local items and scan status for each selected root. An offline HDD is shown as unavailable, never treated as an empty library.
5. **Approve an authorized download.** Review one exact candidate, source, version, size, destination, and available integrity evidence; approve or reject it. The queue cannot silently expand a prior approval to a different candidate.

## In scope

- PS4 and PS5 game identity, user-owned-game input, and aliases.
- Source registry and per-game source-check results.
- Persian-first discovery with multilingual title matching and identifier search.
- User-selected, read-only local HDD/folder metadata scans.
- Candidate compatibility assessment with evidence and uncertainty.
- User-reviewed queue for downloads the user is authorized to obtain.
- Local catalog, provenance, scan history, and synchronization rules.

## Out of scope

- Installing, mounting, unpacking, signing, patching, or executing packages.
- Circumventing console security, DRM, region/licensing checks, paywalls, or access controls.
- Automatically scraping sources that prohibit automated access, using private credentials/cookies, or bypassing rate limits.
- Automatically selecting all disks or scanning arbitrary machine paths.
- Treating a filename or a community assertion as proof that a package is safe or compatible.
- A game launcher, console-management utility, or an assumption that ownership implies a right to redistribute content.

## Product principles

- **Persian first, identifiers always.** Persian titles and language variants lead search and display, but original names, product IDs, and transliterations remain first-class.
- **Evidence over guesses.** Every match, compatibility result, and source claim carries provenance and confidence.
- **Read-only local discovery.** Scanning records metadata and does not alter local files.
- **User intent at the boundary.** Root selection, ambiguous identity resolution, and every download are explicit user actions.
- **Graceful uncertainty.** Unknown, stale, blocked, and unavailable are distinct states rather than hidden as “missing.”

## Phase 1 exit criteria

- The scope and prohibited behaviors are accepted.
- The initial content categories, default root, platforms, and Persian-first preference are recorded as defaults, not hard-coded limits.
- A game detail view and its source/local/compatibility concepts are agreed at a product level.
- Open policy questions in the roadmap have owners before implementation planning is treated as final.
