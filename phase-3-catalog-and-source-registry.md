# Phase 3 — game catalog, Persian discovery, and source registry

## Game identity and search

Represent a game independently from a particular release or package. A game may have PS4 and PS5 releases, multiple regions, title IDs/product codes, localized titles, alternate spellings, and transliterations. Store each name with its language and provenance. Preserve identifiers exactly as observed, plus a normalized search form.

Search order should favor Persian (`fa-IR`) names and source results, then use the user's configured fallback languages and original names. Search must also match title/product IDs and known aliases, because transliteration alone is ambiguous. Normalize Unicode consistently (including Persian/Arabic character variants and zero-width characters) for matching while retaining the original display text. Do not rewrite the canonical title based only on fuzzy matching.

Persian discovery is a ranking and interface preference, not a trust exception: a Persian-language result from an untrusted source remains untrusted. Show language as `fa-IR`, `fa`, or an explicit unknown value; do not infer Persian language solely from script. Preserve separate subtitle-language evidence from the language of a page or listing.

## Source registry

Each source record describes a source endpoint or local manifest. A source has:

- Stable internal ID, display name, source type, base URL/manifest location, and enabled/disabled state.
- Declared platform and content-category coverage, search/discovery capabilities, supported query identifiers, and known language coverage.
- Trust tier, verification notes, ownership/maintainer, attribution, terms/robots/access policy reference, and date last reviewed.
- Request policy: allowed schemes/hosts, rate and concurrency caps, timeout, maximum response size, cache age, and redirect rules.
- Health state and last successful/failed check, with machine outcome and user-readable reason.
- Adapter/version and source-policy version used to interpret observations.

Planned trust tiers:

| Tier | Meaning | Default behavior |
| --- | --- | --- |
| `official` | Publisher or platform-controlled source, verified against an independent official identity | Eligible for discovery; still validate the specific item and any download rights |
| `maintained_community` | Identifiable project/maintainer with documented provenance and a review history | Eligible for discovery with visible attribution and evidence |
| `unverified` | Unknown ownership or weak provenance | Manual review; never silently recommended or auto-downloaded |
| `blocked` | Unsafe, deceptive, policy-violating, or explicitly disallowed | No fetch; retained only as a block record if needed for explanation |

Trust applies to a source, while authenticity and compatibility apply to each candidate. A good source tier is not a cryptographic guarantee. HTTPS protects transport, not content provenance. A hash is useful only when its trusted origin is clear.

## Discovery workflow

For each selected game/release and enabled source capable of the requested category:

1. Build a bounded query from exact IDs, Persian title/aliases, and configured fallback names.
2. Check the source policy and capabilities before sending requests.
3. Fetch within declared limits; treat returned content as untrusted data.
4. Normalize each candidate into a source observation without discarding the original title, URL, language evidence, or source identifiers.
5. Link candidates to games only by scored evidence. Exact ID matches rank above title-only fuzzy matches; conflicting IDs require review.
6. Record an explicit result for found, no result, unavailable, blocked by policy, unsupported query, or failed check.

Source adapters should be read-only by default and should not require user credentials. A source requiring login, private cookies, or bypass behavior is not part of the initial automated discovery set.

## Per-game source coverage

Coverage is keyed by game/release, category, and source. Store the last attempt, result state, number of observations, matching confidence, languages represented, source-policy version, and next-check time.

States include `not_checked`, `checked_found`, `checked_no_result`, `unavailable`, `blocked_by_policy`, `unsupported`, `stale`, and `error`. `checked_no_result` is a valid observation at a particular time, not proof no content exists anywhere. Coverage is never represented as globally complete.

## Phase 3 exit criteria

- Source fields, trust tiers, Persian language behavior, identifier matching, and no-result semantics are agreed.
- A human can see why a candidate was linked to a game and which source supplied each claim.
- Source policy and rate limits are designed before enabling any live adapter.
