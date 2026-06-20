# PRD Quality Review — Domain Watch

## Overall verdict

A well-structured, substantively complete PRD for a hobby/HACS project. The problem framing is honest and specific, features map directly to stated goals, and the developer contract is tight enough to build from without additional elicitation. The main weaknesses are a superficially closed "open questions" section, a thin data-model spec for the persistent store, and one ambiguous FR (F-8.3 un-marking) that could stall a developer mid-story.

---

## 1. Decision-readiness — Strong

The problem statement is specific (brand impersonation, not generic security), the target user is named with enough precision to constrain scope, and counter-metrics honestly disclaim what is not being optimised for. The risk table surfaces real trade-offs (dnstwist dependency conflicts, crt.sh rate limits, RDAP gaps) rather than generic boilerplate. Goals G-1 through G-5 each have a testable success indicator, which is better than most hobby PRDs achieve.

### Findings

- **Minor** — "Open questions resolved" declaration (§8) is furniture. Stating this without showing what was resolved and how removes institutional memory. At hobby stakes this is low risk, but a brief resolved-question log would cost nothing and provide audit value. *Fix:* Replace with a one-line changelog entry or remove the section entirely rather than asserting closure without evidence.
- **Minor** — Counter-metrics are noted in §2 but the PRD has no explicit statement on false-positive policy beyond "acceptable given the small keyword set." A new domain for a major brand like `brandname-shop.com` will always match, and a power user monitoring a common word will be flooded. *Fix:* Add one sentence acknowledging the false-positive exposure for short/common keywords and whether any filtering (e.g. minimum keyword length) is in scope.

---

## 2. Substance over theater — Strong

Each feature section earns its place. FR-2.2 (deduplication/normalisation logic), FR-2.3/2.4 (fail-soft with backoff), FR-3.2 (executor threading), FR-4.3/4.4 (persistence and retention) all represent real engineering decisions documented at the right level for a PRD. NFRs are actionable (`async_get_clientsession`, `hass.async_add_executor_job`) rather than aspirational ("should be fast"). The HACS/hassfest requirements are concrete.

### Findings

- **Minor** — FR-7.2 (binary sensor 24-hour window) is concrete but the reset mechanism is not stated. Does it reset when HA restarts, on the next poll cycle, or strictly 24 hours after last detection? A developer will have to decide this independently. *Fix:* Add one sentence: "The 24-hour window is evaluated at each coordinator update cycle, not at restart."
- **Low** — The `[ASSUMPTION]` in §4 retention note (`ASSUMPTION: no explicit cap in v1`) is buried in an NFR rather than tracked. If the store grows unbounded for high-volume keywords it could impact HA memory. *Fix:* Promote this to a named assumption in §3 or add an explicit "first 500 domains per source per keyword" cap, even a generous one.

---

## 3. Strategic coherence — Strong

The product has a clear thesis: bring enterprise brand-monitoring to HA-native users at zero recurring cost, using public data sources. Every feature serves either detection (F-2, F-3), deduplication/persistence (F-4), enrichment (F-5), or HA integration hygiene (F-6, F-7, F-8, F-9). F-10 (localisation) is a slight outlier — Dutch translations are a personal preference, not a user-need derived from §3 — but this is a hobby project and the scope is a single JSON file.

### Findings

- **Informational** — F-8.3 (un-marking) reads more like a developer hedge than a user story. The primary user need is "mark reviewed"; the un-mark case is edge-case enough that deferring it to v2 would keep the feature surface cleaner. Keeping it here is fine, but it should be marked `[OPTIONAL]` or explicitly scoped to v1.1. *Fix:* Add `[OPTIONAL — v1.1]` label or move to §6 Out of Scope.

---

## 4. Done-ness clarity — Adequate

Most FRs are specific enough to write a passing test against. FR-2.1 ("wildcard match `%keyword%`") even specifies the query syntax. FR-4.1 ("at minimum `first_seen` and `source`") sets a floor without over-specifying the schema. The main gaps are:

### Findings

- **Medium** — FR-4.1 underspecifies the persistent store's implementation contract. "Persistent store" could mean `hass.data`, a custom JSON file via `hass.config.path`, or a `StorageCollection`. The choice affects restart-survival, file path, and atomic-write semantics. A developer picking the wrong mechanism will have to refactor later. *Fix:* Name the storage mechanism explicitly: "Uses `homeassistant.helpers.storage.Store` with key `domain_watch.seen_domains`."
- **Medium** — FR-8.3 un-mark behaviour is ambiguous. "When enabled (via Options), a service becomes available" — does this mean the service is registered dynamically on option change, or gated by a runtime check inside a permanently registered service? Dynamic service registration in HA is uncommon and has edge cases. *Fix:* Specify the mechanism: "The service is registered unconditionally but returns an error if the option is disabled" or "The coordinator re-registers services on options update."
- **Minor** — FR-6.1 event payload lists `cert_id` as "(when available from crt.sh)" but no equivalent field is named for dnstwist-sourced detections. If a dnstwist detection has no cert context, are all cert-related fields absent or present as `null`? *Fix:* Add one line: "Fields absent for a given source are omitted from the payload entirely."

---

## 5. Scope honesty — Strong

Section 6 (Out of Scope) is specific and technically justified. Deferring certstream to a standalone add-on is the right call for v1 (persistent websocket requires an add-on lifecycle, not an integration). NRD zone-file downloads, automated takedown, multi-brand, and dashboards are all plausible future asks that are correctly excluded. The implied scope of "one config entry per brand" is never stated positively but is deducible from the out-of-scope note on multi-tenant profiles.

### Findings

- **Minor** — The integration's egress surface (crt.sh, rdap.org, public DNS) is mentioned in FR-9.3 (README) but not formally listed as a constraint. HA users on restricted networks may need this up front. *Fix:* Add a one-line constraint to §5 or §7: "Requires outbound HTTPS to `crt.sh`, `rdap.org`, and recursive DNS."
- **Informational** — It is not stated whether the integration supports multiple config entries (one entry per brand). The out-of-scope note rules out multi-brand within a single entry, but a power user may add two entries. This is probably fine to leave implicit at hobby stakes but worth one sentence if the storage key (FR-4.1 recommendation) is shared across entries.

---

## 6. Downstream usability — Adequate

UX/architecture/story agents can extract cleanly from this PRD. The config-flow scope (FR-1.1 through 1.5) is well-defined. Entity contract (FR-7.1, 7.2) and service signatures (FR-8.1 through 8.3) are named. The HACS packaging requirements (FR-9.1, 9.2) are precise.

### Findings

- **Medium** — There is no data model section or HA integration structure diagram. A developer starting fresh will need to infer the coordinator structure, entity registration pattern, and config-entry layout from the FRs. For a hobby project this is workable, but an architect agent will produce a better output with an explicit component inventory. *Fix:* Add a brief §9 "Integration structure" listing the expected modules: `__init__.py`, `coordinator.py`, `sensor.py`, `binary_sensor.py`, `config_flow.py`, `services.py`, `sources/crt_sh.py`, `sources/dnstwist.py`, `storage.py`. This is two sentences of effort and saves significant downstream ambiguity.
- **Minor** — The notify service (FR-6.3) is described as a "notify service name" string, but HA has deprecated the notify domain in favour of `notify.send_message` action on notify entities in recent releases (2024.x). This could cause confusion for users on current HA. *Fix:* Clarify which notification mechanism targets: the legacy `notify.*` service or the current `notify.send_message` action. If targeting 2024.12+, prefer the entity-based action.

---

## 7. Shape fit — Strong

The PRD is correctly shaped for a HACS integration: it specifies a config flow (no YAML-only setup), names `iot_class`, addresses hassfest/HACS CI, includes localisation, and calls out the HA async contract explicitly in NFRs. The level of detail is appropriate — more granular than a product brief, less granular than a technical spec. At ~1,800 words of requirement content it is not over-engineered for a hobby project.

### Findings

- **Informational** — Version `0.1.0` in frontmatter suggests initial release. Consider whether HACS requires a corresponding GitHub release tag before discovery works. This is an operational note, not a PRD gap, but worth confirming during release planning.

---

## Mechanical notes

**Glossary drift.** "Impostor" and "impersonator" are used interchangeably (§1, §4, §7). The event name uses `domain_watch_detected` (FR-6.1) while the service uses `domain_watch.scan_now` (FR-8.1) — the dot-vs-underscore distinction is correct for HA (events use underscores, services use dots) but worth a glossary note to prevent copy-paste errors in automation examples.

**ID continuity.** Feature IDs F-1 through F-10 and FR-x.x are continuous and consistent throughout. No gaps detected.

**Broken cross-refs.** FR-2.3 and FR-2.4 are referenced in the risk table (§7) correctly. FR-5.2 is referenced in the risk table correctly. No broken internal references found.

**Assumption roundtrip.** Three assumptions are present:
- §3 (user comfort with HACS/automations) — tagged `[ASSUMPTION]`, appropriate.
- §4 FR-4.4 / NFR-4 (no explicit store cap) — tagged `[ASSUMPTION]` in NFR-4 only; the corresponding FR-4.4 does not flag the gap. These should be cross-linked.
- Implicit assumption that one config entry = one brand — untagged; see §5 findings.

**Minor wording.** §2 counter-metrics: "false-positive volume (acceptable given the small keyword set)" conflates false-positive rate with user tolerance. A one-word keyword like "shop" is both small and high-volume. The parenthetical should say "acceptable provided keywords are sufficiently specific" to avoid implying any keyword set is safe.
