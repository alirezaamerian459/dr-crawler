# Phase 4 — owned games and local HDD scanning

## Owned-game input

The collection is user-curated. A practical import format is UTF-8 CSV for simple use and JSON for richer identity evidence. Import must preview rows, report rejected or ambiguous entries, and require confirmation before merging. A file import does not prove legal ownership; it records the user's assertion or provided evidence.

Suggested CSV headers:

```csv
platform,title,region,title_id,product_code,language,owned_since,source,notes
PS4,Sample Game,EU,CUSA00000,EP0000-CUSA00000_00-SAMPLEGAME000000,en,2025-01-01,manual,
```

Suggested JSON shape:

```json
{
  "schema_version": 1,
  "games": [
    {
      "platform": "PS4",
      "title": "Sample Game",
      "region": "EU",
      "title_id": "CUSA00000",
      "product_code": "EP0000-CUSA00000_00-SAMPLEGAME000000",
      "languages": ["en"],
      "ownership": {"status": "user_asserted", "evidence_note": ""}
    }
  ]
}
```

These are proposed interchange formats. `title_id`, product code, region, and language are optional when unknown; the platform and a title or identifier are required. Treat imported values as untrusted input, preserve original values, and avoid requiring sensitive purchase account data. Duplicate and conflicting records are shown for review rather than silently merged.

## Root selection and scanner behavior

- Initial suggested root is `D:\PlayStation-Library`; it is a suggestion and must be confirmed if it does not exist or is not accessible.
- Users can explicitly add removable HDDs and individual folders. Do not enumerate or scan all drives by default.
- Store a stable volume identity when available, plus the user-facing path/mount point. Drive letters can change, so a missing mount point is not proof that the disk's files were deleted.
- Scan selected roots read-only. Present scope, estimated item count when available, progress, pause/cancel, permission errors, and last-complete time.
- Do not follow symlinks, junctions, or reparse points outside the selected root. Avoid OS/system directories unless the user deliberately selected them.
- Detect likely package and sidecar/manifest files from names and basic filesystem metadata. Do not unpack or execute files. Full-file hashing is optional because it can be expensive; record whether a hash is absent, pending, or computed.
- Retain normalized root-relative paths for matching and display. Keep raw paths only as needed for user access and local operations.

## Metadata and matching

Candidate local items can be identified from filename conventions, sidecar manifests, or user-edited metadata. Every extracted field stores its source and confidence. A filename match does not establish title, region, version, package type, safety, or ownership. Let the user correct a match and remember that correction as a local override.

Store at least: selected root, relative path, file name, extension/category guess, size, modification time, optional hash and algorithm, parsed identifiers/version/language if available, parse outcome, and last-seen scan. Never modify the source file as part of catalog matching.

## Phase 4 exit criteria

- Import format and ambiguity review are agreed.
- A scan is explicit, read-only, scoped, cancellable, and safe when a drive disconnects.
- The app clearly separates observed filesystem facts from inferred game/package metadata.
