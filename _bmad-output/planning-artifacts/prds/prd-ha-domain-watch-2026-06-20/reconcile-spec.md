# Reconciliation — User Spec vs PRD + Addendum

## Input: User Technical Plan

Dutch-language technical plan covering detection strategy, repo structure, per-file responsibilities, notification paths, constraints, tests, and future scope. Delivered as a structured markdown document with explicit callouts for what is deferred from v1.

---

## Gaps found: 5

- **medium** **crt.sh specific retry cap not stated in PRD.** The original spec says "max retries" (implying a concrete cap, e.g. max 3) and the addendum repeats "max 3 retries per cycle." The PRD's FR-2.4 says "up to a configured max" — implying the retry count is user-configurable — but the spec treats it as a fixed implementation constant, not a user-facing option. If this becomes a config field it needs its own FR and UI; if it remains a constant the PRD wording is misleading.

- **medium** **crt.sh timeout value (~30 s) not captured anywhere in the PRD.** The spec calls out `timeout ~30s` explicitly for crt.sh. The PRD and addendum describe backoff behaviour but contain no mention of a concrete timeout value. This is an implementation constraint that should appear in the NFRs or as a note on FR-2.4, because it affects HA's default `aiohttp` session limits and could surface as a config-flow issue on slow instances.

- **medium** **`issuer_name` and `id` fields from crt.sh response not mapped to a spec requirement.** The original plan documents three fields from the crt.sh response: `name_value`, `not_before`, `issuer_name`, and `id`. The addendum event payload maps `cert_id` (from `id`) correctly but `issuer_name` and `not_before` are silently dropped. There is no FR or NFR that explicitly excludes them, so a developer could reasonably implement without them. If they are intentionally excluded, a brief rationale should be added to FR-2.2 or the addendum.

- **low** **Egress destinations not listed in NFRs.** The original spec has an explicit "Egress" constraint calling out the three outbound targets (`crt.sh`, `rdap.org`, and DNS for dnstwist). The PRD moves this content only to FR-9.3 (README) and the Constraints table. NFR-3 covers "no credentials" but does not enumerate egress endpoints. For an ISO 27001-conscious project, outbound network targets belong in a dedicated NFR or constraint row, not only in the README.

- **low** **`reviewed: bool` field in the store schema not linked to FR-8.2/8.3.** The addendum documents the persistent store schema as `{domain: {first_seen, source, reviewed, ...}}`. FR-8.2 (`mark_reviewed`) and FR-8.3 (`unmark_reviewed`) reference the concept but neither FR cites the store schema nor states that the `reviewed` flag must be persisted across restarts and preserved through retention purges. A reviewed domain being accidentally purged and re-alerting is a real edge case.

---

## Qualitative content not captured

The original plan is written in Dutch and has a noticeably direct, engineering-first tone: it leads with a clear "this is not an add-on" disclaimer, names specific HTTP response fields, and flags the reliability characteristics of crt.sh as a first-class concern ("traag/wisselvallig"). This operational caution — treat crt.sh as an unreliable external dependency, not a stable API — is present in FR-2.3/2.4 but the PRD's risk table rates crt.sh downtime as "Medium likelihood," which understates the spec author's clear concern that it is a routine occurrence. The original framing ("502's, rate limits") implies this is expected normal behaviour, not an occasional risk.

Additionally, the spec's framing of RDAP as "verrijking, geen source" (enrichment, not a source) — a deliberate architectural distinction — is implicit in the addendum's coordinator flow but not explicitly called out in the PRD or as an architectural decision. This distinction matters: it means RDAP failures can never suppress a detection event, which is a correctness guarantee that should be stated as a constraint on FR-5.2 rather than left to convention.

---

## Verdict

The PRD and addendum capture all major functional requirements faithfully; the gaps are implementation-level specifics (timeout value, retry cap status, response field handling) and one architectural clarification (RDAP as enrichment-only, never a gating dependency) that should be tightened before the architecture document is authored.
