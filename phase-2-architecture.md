# Phase 2 — architecture and system boundaries

## Proposed logical components

1. **Desktop UI and application service.** Owns user preferences, explicit confirmations, game collection workflows, source review, scan controls, and queue review. UI labels and accessible reading order are designed for Persian right-to-left (RTL), with per-field language metadata.
2. **Catalog service.** Maintains canonical games, aliases, platform/region identifiers, owned-game records, content categories, and localized labels.
3. **Source registry and discovery coordinator.** Stores source configuration, policy, capabilities, health, attribution, and terms notes. Runs bounded checks only for enabled sources and emits normalized observations.
4. **Compatibility evaluator.** Compares a candidate's stated platform/title/version/region/language requirements with game and user-provided system context. It returns a reasoned state and evidence; it does not install or modify packages.
5. **Local library scanner.** Reads metadata from selected roots and reports scan results. It does not traverse outside a selected root, follow reparse points by default, or write to scanned locations.
6. **Download queue.** Persists the exact approval decision, fetches only approved candidates from permitted source URLs to an approved destination, records outcomes, and stops before install or execution.
7. **Persistence and audit.** Stores normalized data, source/scan history, user decisions, and an append-only record of security-relevant actions.

These are planning boundaries, not a decision to use separate processes or services. A first release may implement them as modules in one desktop process.

## Data flow

```text
Owned-game input ──> Catalog / identity review ──> Per-game view
                                            ├──> Source coordinator ──> Observations
Selected HDD roots ──> Read-only scanner ───┤                         └──> Coverage matrix
                                            ├──> Compatibility evaluator
                                            └──> Approval UI ──> Download queue ──> User-selected destination
```

Source observations and local-file observations are separate records. A source result never overwrites local scan state, and an offline disk never overwrites source coverage.

## Trust boundaries

- **Untrusted source input:** names, HTML, manifests, metadata, URLs, hashes, and compatibility claims are data, not executable instructions. Parse with resource limits; sanitize displayed text; reject unsafe URL schemes and local-network destinations.
- **Local filesystem:** access only explicitly selected roots; canonicalize paths; prevent traversal and reparse-point escape; avoid writing to scanned roots.
- **Network transfer:** allow HTTPS by default, apply per-source host/rate/size limits, revalidate redirects, and record final URL and evidence. Do not send account cookies or credentials to third-party sources.
- **Approval boundary:** approval binds to a specific source observation, candidate identity/version, URL or source item identifier, expected size/hash if known, and destination. A material change requires renewed approval.
- **Package boundary:** downloaded files remain inert data. No auto-open, install, extraction, script, or executable behavior is planned.

## Operational behavior

- Network discovery and local scans are independently scheduled and cancellable.
- Every operation has an operation ID, start/end time, outcome, and concise user-facing reason.
- Retry only transient errors with bounded backoff; respect source-specific limits and stop when a source signals that automated access is disallowed.
- Maintain a source/scan snapshot so interrupted operations can resume without claiming completion.
- Keep logs useful for diagnosis while avoiding credentials and unnecessary personal paths.

## Non-functional requirements to validate

- Large HDDs: incremental traversal, bounded memory, visible progress, pause/cancel, and no content hashing unless configured or requested.
- Persian/RTL: correct shaping and bidirectional rendering, Unicode normalization, keyboard navigation, readable mixed-script IDs and paths.
- Reliability: transactionally persist scan/queue state; recover from app restart; idempotently merge repeat observations.
- Privacy: collection and paths remain local unless the user explicitly enables a network source or export.

## Phase 2 exit criteria

- Component boundaries, trust boundaries, offline behavior, and the no-install rule are accepted.
- Data flow is agreed before choosing a concrete framework, database engine, or source-adapter API.
