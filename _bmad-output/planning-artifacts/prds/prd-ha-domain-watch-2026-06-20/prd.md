---
title: "Domain Watch — Brand Impersonation Domain Monitor for Home Assistant"
status: final
created: 2026-06-20
updated: 2026-06-20
version: 0.1.0
---

# Domain Watch

## 1. Problem

Brand owners — small businesses, independent creators, online shops — routinely have impersonator domains registered against them: lookalike URLs that host fake webshops, phishing pages, or counterfeit product listings. These domains cause direct financial harm (lost sales, customer fraud) and reputational damage that is difficult to reverse.

Enterprise brand-protection tooling targets large organisations with dedicated legal teams and five-figure budgets. Individuals and small businesses have no affordable, automated early-warning system. By the time an impostor domain is discovered — through a customer complaint or an accidental search result — the damage is already done.

Home Assistant users who are also small business owners or brand custodians have no native way to wire brand-protection monitoring into their existing notification stack.

## 2. Goals

| # | Goal | Success indicator |
|---|------|------------------|
| G-1 | Detect newly registered domains that impersonate a monitored brand within one poll cycle of their appearance in public data sources | A newly issued TLS certificate for a monitored keyword appears as a detection event within 6 hours (default poll interval) |
| G-2 | Eliminate repeated alerting for already-known impostors | A domain detected in run N does not re-trigger in run N+1 |
| G-3 | Give the owner enough context to act immediately | Every detection includes registrar, registration date, nameservers, and certificate metadata |
| G-4 | Integrate cleanly into any HA notification setup without requiring custom code | Detection fires a standard HA event consumable by any automation; direct notify is available as a zero-automation fallback |
| G-5 | Be installable by a non-technical HA user via HACS | Passes hassfest and HACS Action validation; no manual file placement needed |

**Out of scope for optimisation:** false-positive volume (acceptable given the small keyword set) and detection latency below 1 hour (real-time CT requires a persistent websocket; deferred to v2).

## 3. Target Users

**Primary — Brand-owning HA users.** Small business owners, online shop operators, independent creators, and domain custodians who already run Home Assistant and want to close the gap between "fake domain registered" and "I know about it." They are technically capable of installing HACS integrations and writing basic HA automations; they do not have dedicated security staff.

**Secondary — Security-aware hobbyists.** HA power users who want to monitor their personal domain portfolio, family brand, or community project for typosquatting and homoglyph attacks using their existing HA notification infrastructure.

Users are comfortable with HACS and basic HA concepts (automations, services) but are not expected to understand Certificate Transparency or DNS permutation theory.

## 4. Features

### F-1 — Keyword-based configuration

**FR-1.1** The user configures one or more brand keywords (e.g. a brand name, abbreviated name, or distinctive phrase) through the HA config flow UI. No YAML editing required.

**FR-1.2** The user configures one or more base domains for DNS-permutation analysis (used by the dnstwist source).

**FR-1.3** The user sets the poll interval (default 6 hours, minimum 1 hour). All active sources are queried on each interval.

**FR-1.4** Source toggles allow the user to enable or disable crt.sh and dnstwist independently. At least one source must be enabled.

**FR-1.5** All configuration is editable at runtime via the HA Options flow without restarting HA.

### F-2 — Certificate Transparency monitoring (crt.sh)

**FR-2.1** On each poll, the integration queries crt.sh for every configured keyword using a wildcard match (`%keyword%`), returning all TLS certificates whose Subject Alternative Names contain the keyword.

**FR-2.2** Results are deduplicated: each unique domain name is counted once regardless of how many certificates reference it. Wildcard prefixes (`*.`) are stripped; all domains are normalised to lowercase.

**FR-2.3** crt.sh failures (HTTP 5xx, timeouts, rate limits) do not crash the integration or block other sources. Errors are logged; the coordinator proceeds with whatever data it has.

**FR-2.4** Each request has a fixed timeout of 30 seconds. Failed requests are retried up to 3 times with exponential backoff; after the third failure the source is skipped for the current cycle. The retry limit is a fixed internal constant, not user-configurable.

### F-3 — DNS permutation monitoring (dnstwist, optional)

**FR-3.1** When enabled, the integration generates typo, homoglyph, and TLD permutations of each configured base domain and identifies which permutations resolve (are registered).

**FR-3.2** dnstwist processing runs in an executor thread and must not block the HA event loop.

**FR-3.3** dnstwist is declared as a requirement in `manifest.json` so HA installs it automatically at integration setup. The import is lazy (deferred until the source is first used) to avoid slowing HA startup.

### F-4 — Deduplication and seen-domain tracking

**FR-4.1** The integration maintains a persistent store (`homeassistant.helpers.storage.Store`, key `domain_watch.seen`) of previously detected domains, keyed by domain name, containing at minimum a `first_seen` timestamp, originating source, and `reviewed` flag.

**FR-4.2** Only domains absent from the persistent store trigger a detection event and notification. Domains already in the store are silently skipped.

**FR-4.3** The persistent store survives HA restarts.

**FR-4.4** The store has a configurable retention period (default: 6 months). On each poll cycle, entries older than the retention period are purged — unless their `reviewed` flag is set, in which case they are retained indefinitely. A reviewed domain never re-alerts regardless of how much time passes. The retention period is configurable via the Options flow.

### F-5 — RDAP enrichment

**FR-5.1** For each newly detected domain, the integration attempts to retrieve registrar name, registration date, and nameservers from the RDAP registry.

**FR-5.2** RDAP lookups fail gracefully: if data is unavailable or the request times out, the affected fields are omitted from the payload rather than surfaced as errors. The detection event is still emitted.

### F-6 — Detection events and notifications

**FR-6.1** For every newly detected domain, the integration fires a Home Assistant event (`domain_watch_detected`) with a payload containing: `domain`, `source`, `first_seen`, `registrar`, `registration_date`, `nameservers`, `cert_id`, `issuer_name`, `not_before`. The last four fields are populated only when the detection originates from crt.sh; they are omitted (not null) for other sources.

**FR-6.2** The event is fired regardless of whether a direct notify service is configured; it is always available for user-defined automations.

**FR-6.3** The user may optionally configure a notify service name. When set, the coordinator calls that service directly for each new detection with a human-readable summary. The implementation must target the current notify API for the declared minimum HA version (2024.12.0), which uses `notify.send_message` on notification entities.

**FR-6.4** The README documents at least two ready-to-use automation examples (mobile push and Telegram).

### F-7 — Sensor entities

**FR-7.1** A sensor entity (`sensor.domain_watch_detections`) exposes the total count of known impostor domains as its state. Its attributes include the most recent detections with full detail.

**FR-7.2** A binary sensor entity (`binary_sensor.domain_watch_new_detection`) is `on` when a new detection occurred within the last 24 hours, `off` otherwise.

### F-8 — Services

**FR-8.1** `domain_watch.scan_now` forces an immediate poll cycle outside the regular interval.

**FR-8.2** `domain_watch.mark_reviewed` accepts a `domain` parameter and marks the domain as reviewed in the persistent store. A reviewed domain does not trigger further alerts but remains in the store for audit purposes.

**FR-8.3** Both `domain_watch.mark_reviewed` and `domain_watch.unmark_reviewed` are registered unconditionally on integration load. The `unmark_reviewed` service raises a service-call error if invoked while the option is disabled. Un-marking is off by default; it can be enabled via the Options flow, at which point a previously reviewed domain re-enters active monitoring.

### F-9 — HACS distribution

**FR-9.1** The integration ships with a `hacs.json` declaring minimum HA version `2024.12.0`.

**FR-9.2** The integration passes hassfest and HACS Action validation in CI (`validate.yml`).

**FR-9.3** The README covers installation via HACS, initial configuration, example automations, and egress requirements (outbound to `crt.sh`, `rdap.org`, DNS).

### F-10 — Localisation

**FR-10.1** All user-facing strings in the config flow, options flow, and entity names are defined in `strings.json` with English and Dutch translations provided.

## 5. Non-Functional Requirements

**NFR-1 — Async discipline.** No blocking I/O on the HA event loop. All HTTP uses `async_get_clientsession(hass)`. dnstwist and any blocking DNS calls run in `hass.async_add_executor_job`.

**NFR-2 — Fault isolation.** A failure in any single source must not prevent the coordinator from completing a cycle using data from other sources.

**NFR-3 — No credentials.** The integration uses only publicly accessible endpoints (crt.sh, rdap.org, public DNS). No API keys or authentication are required or stored.

**NFR-4 — Minimal footprint.** The poll cycle must complete within the configured interval without significant memory growth over time. Store size is bounded by the configurable retention period (FR-4.4); reviewed entries are exempt from purge but expected to remain small in practice.

**NFR-5 — HA coding standards.** Config entries are managed via ConfigFlow; no YAML-only setup. `iot_class` is `cloud_polling`. The integration registers and unloads cleanly.

**NFR-6 — Egress requirements.** The integration requires outbound access to `crt.sh` (HTTPS, port 443), `rdap.org` (HTTPS, port 443), and public DNS resolvers (UDP/TCP port 53, used by dnstwist). No other external endpoints are contacted. These must be documented in the README for users with restrictive firewall policies.

## 6. Out of Scope — v1

- Real-time Certificate Transparency via certstream (persistent websocket; deferred to a standalone add-on).
- Newly Registered Domains (NRD) zone-file downloads.
- Automated takedown reporting (Google Safe Browsing, SmartScreen, registrar abuse channels).
- Multi-brand / multi-tenant profiles within a single config entry.
- Historical reporting or trend dashboards.

## 7. Constraints and Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| crt.sh rate-limiting or downtime | Medium | Exponential backoff + fail-soft per FR-2.3/2.4 |
| dnstwist dependency conflicts with other HA integrations | Low-Medium | Lazy import; document the dependency explicitly |
| RDAP data unavailable for some registrars | High | Graceful degradation per FR-5.2 |
| HA breaking changes in future versions | Low | Pin minimum HA version; CI validates on current release |
| Impostor uses a CDN with no direct cert (rare) | Low | Accepted gap; CT remains primary signal |

## 8. Resolved Decisions

All open questions were resolved during Discovery and review:

- **Store retention** — configurable, default 6 months; reviewed domains exempt from purge (permanent).
- **mark_reviewed reversibility** — off by default; opt-in via Options enables `unmark_reviewed`.
- **dnstwist dependency** — declared in `manifest.json`; HA installs it at setup. Lazy import preserves startup performance.
- **Binary sensor window** — 24 hours.
- **Event payload cert fields** (`cert_id`, `issuer_name`, `not_before`) — included; omitted (not null) for non-crt.sh sources.
