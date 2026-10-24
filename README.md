# DR Crawler

DR Crawler is a local-first PS4/PS5 collection manager with a Persian (`fa-IR`) right-to-left interface. It records game identities, source candidates, compatibility evidence, selected-folder metadata, source coverage, and exact download approvals.

The first release runs as a small Python application and opens its interface in the desktop browser. The local HTTP server listens on `127.0.0.1` only. The catalog and paths remain on this computer; the app does not sync or upload them.

## Run on Windows

Use Python 3.10 or newer. No Python packages are required.

```powershell
cd path\to\dr-crawler
python -m drcrawler
```

The app opens a browser tab and prints its local address and database folder in the terminal. Keep the terminal open while using it; press `Ctrl+C` to stop. To print the address without opening a tab:

```powershell
python -m drcrawler --no-browser
```

The native folder picker uses Python's optional `tkinter` module. If it is unavailable, enter an existing folder path in the app instead.

The database is stored under `%LOCALAPPDATA%\DRCrawler\dr-crawler.sqlite3` on Windows. On other platforms it uses `$XDG_DATA_HOME/DRCrawler` or `~/.local/share/DRCrawler`. Set `DRCRAWLER_DATA_DIR` before launch to choose a different local data folder. The SQLite `user_version` migration 1 creates the catalog and workflow tables; migration 2 adds stable cross-source candidate identity and backfills existing candidates.

## Build a standalone Windows executable

On a Windows build computer with Python 3.10 or newer, run:

```powershell
python -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build-windows.ps1
```

The result is `dist\DRCrawler.exe`. It includes the Python runtime and the web interface, so the other Windows PC does not need Python installed. Copy the executable there and double-click it; the browser opens the local app. Keep its console window open while using it. The other PC keeps its own database under its local application-data folder; this executable does not copy your current catalog. The binary is unsigned, so Windows may show its normal publisher warning.

## First-release workflows

- Add games manually or import the documented UTF-8 CSV and JSON formats after reviewing every duplicate, ambiguous, and invalid row.
- Search Persian names, original titles, aliases, transliterations, and title/product identifiers. Add alternate titles in the game form or import them as aliases. A Persian title is displayed first when one has been recorded; the original title remains searchable.
- Register sources with declared platforms/categories/languages, attribution, maintainer, trust tier, health, terms/access reference, allowed hosts, and a user-reviewed access policy. Persian language ranking is independent of source trust.
- Record source candidates and manual check outcomes per game, release, source, and category. Coverage differentiates `not_checked`, `checked_found`, `checked_no_result`, `unavailable`, `blocked_by_policy`, `unsupported`, `stale`, and `error`.
- Add only folders you explicitly select. `D:\PlayStation-Library` is suggested, but the app does not create it, enumerate drives, or scan it automatically. Scans read names, paths, sizes, timestamps, and limited filename patterns; they do not follow links/reparse points, read package payloads, calculate hashes, or write to selected roots. Windows-visible game folders on exFAT are scanned the same way as other selected folders. `.pkg`, `.fpkg`, and numbered split names such as `.pkg.0` are indexed as package candidates, and title IDs in folder paths are used as identity evidence. Package contents are not inspected or reassembled. PlayStation-formatted storage that Windows does not expose as ordinary browsable files is not interpreted.
- Review compatibility evidence and conflicts per candidate. Only an explicit user-confirmed file link produces `already_present`; a filename match alone remains a weaker inference.
- Create an approval request for one exact candidate and existing destination folder. Approval records the item, source observation, URL, version, size, hash, compatibility state, source policy version, and output path. Confirm authorization before approving. Transfers require HTTPS, an explicitly allowed public host, public DNS addresses, a size cap, and no redirects. Any change to the item, URL, version, size, hash, compatibility state, source policy, or destination expires the approval; a redirect or response-size mismatch also requires review. A declared SHA-1/SHA-256 digest is checked after transfer; missing hash evidence stays visible. Downloaded files are left inert and are not installed, opened, mounted, extracted, or executed.

The app starts with an empty catalog and no seeded sources. The source registry does not trigger automated crawling in this release. The user records candidate listings and check results manually after reviewing the source's terms and access policy. This keeps the app useful without guessing which sources permit automated access or are trustworthy.

## Import formats

CSV uses the headers shown in [Phase 4 — owned games and local HDD scanning](phase-4-local-library-and-owned-games.md). The optional `aliases` cell accepts one title per line, with an optional language prefix such as `en|Original title`:

```csv
platform,title,region,title_id,product_code,language,owned_since,source,notes
PS4,Sample Game,EU,CUSA00000,EP0000-CUSA00000_00-SAMPLEGAME000000,en,2025-01-01,manual,
```

JSON requires `schema_version: 1` and a `games` array. `platform` and at least one of `title`, `title_id`, or `product_code` are required.

```json
{
  "schema_version": 1,
  "games": [
    {
      "platform": "PS5",
      "title": "نام بازی",
      "aliases": [
        {"value": "Original title", "language": "en"},
        {"value": "نام فارسی", "language": "fa-IR"}
      ],
      "region": "EU",
      "title_id": "PPSA00000",
      "languages": ["fa", "en"],
      "ownership": {"status": "user_asserted", "evidence_note": ""}
    }
  ]
}
```

Imports are limited to 2 MB and 2,000 rows per preview. A file records the user's assertion; it does not verify legal ownership.

## Boundaries and known gaps

The app does not bypass logins, paywalls, DRM, console security, rate limits, or source policies. It stores no credentials or browser cookies. It includes no preselected mirrors, built-in network crawler, sidecar parser, package payload inspection, installer, extraction flow, or cross-device sync. Source trust labels are user-maintained evidence, not proof of authenticity, safety, compatibility, or download rights.

Open technical/product decisions and the implementation choices made for this release are recorded in [Roadmap, decisions, and open questions](roadmap-and-decisions.md). The original phase documents remain the planning reference and are not rewritten to imply that every planned exit criterion is complete.

## Planning index

1. [Phase 1 — product scope and user journeys](phase-1-product-scope.md)
2. [Phase 2 — architecture and system boundaries](phase-2-architecture.md)
3. [Phase 3 — game catalog, Persian discovery, and source registry](phase-3-catalog-and-source-registry.md)
4. [Phase 4 — owned games and local HDD scanning](phase-4-local-library-and-owned-games.md)
5. [Phase 5 — compatibility and approval-based downloads](phase-5-compatibility-and-authorized-downloads.md)
6. [Phase 6 — coverage matrix and synchronization](phase-6-coverage-scanning-and-sync.md)
7. [Logical database schema](database-schema.md)
8. [Roadmap, decisions, and open questions](roadmap-and-decisions.md)
