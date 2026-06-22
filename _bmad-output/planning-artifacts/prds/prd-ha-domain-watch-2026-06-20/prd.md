---
title: "Domain Watch — Brand Impersonation Domain Monitor for Home Assistant"
status: final
created: 2026-06-20
updated: 2026-06-21
version: 0.2.0
---

# Domain Watch

## 1. Problem

Brand owners — small businesses, independent creators, online shops — routinely have impersonator domains registered against them: lookalike URLs that host fake webshops, phishing pages, or counterfeit product listings. These domains cause direct financial harm (lost sales, customer fraud) and reputational damage that is difficult to reverse.

Enterprise brand-protection tooling targets large organisations with dedicated legal teams and five-figure budgets. Individuals and small businesses have no affordable, automated early-warning system. By the time an impostor domain is discovered — through a customer complaint or an accidental search result — the damage is already done.

Home Assistant users who are also small business owners or brand custodians have no native way to wire brand-protection monitoring into their existing notification stack.

## 2. Goals

| # | Goal | Success indicator |
|---|------|------------------|
| G-1 | Detect newly registered domains that impersonate a monitored brand within one poll cycle | A newly issued TLS certificate for a monitored keyword appears as a detection event within 6 hours (default poll interval) |
| G-2 | Eliminate repeated alerting for already-known impostors | A domain detected in run N does not re-trigger in run N+1 |
| G-3 | Give the owner enough context to act immediately | Every detection includes registrar, registration date, nameservers, and certificate metadata |
| G-4 | Integrate cleanly into any HA notification setup without requiring custom code | Detection fires a standard HA event consumable by any automation; direct notify is available as a zero-automation fallback |
| G-5 | Be installable by a non-technical HA user via HACS | Passes hassfest and HACS Action validation; no manual file placement needed |

**Out of scope for optimisation:** false-positive volume (acceptable given the small keyword set) and detection latency below 1 hour (real-time CT requires a persistent websocket; deferred to v2).

## 3. Target Users

**Primary — Brand-owning HA users.** Small business owners, online shop operators, independent creators, and domain custodians who already run Home Assistant and want to close the gap between "fake domain registered" and "I know about it." They are technically capable of installing HACS integrations and writing basic HA automations; they do not have dedicated security staff.

**Secondary — Security-aware hobbyists.** HA power users who want to monitor their personal domain portfolio, family brand, or community project for typosquatting attacks using their existing HA notification infrastructure.

Users are comfortable with HACS and basic HA concepts (automations, services) but are not expected to understand Certificate Transparency theory.

## 4. Features

### F-1 — Keyword-based configuration

**FR-1.1** The user configures one or more brand keywords (e.g. a brand name, abbreviated name, or distinctive phrase) through the HA config flow UI. No YAML editing required.

**FR-1.2** The user sets the poll interval (default 6 hours, minimum 1 hour).

**FR-1.3** All configuration is editable at runtime via the HA Options flow without restarting HA.

### F-2 — Certificate Transparency monitoring (crt.sh)

**FR-2.1** On each poll, the integration queries crt.sh for every configured keyword using a wildcard match (`%keyword%`), returning all TLS certificates whose Subject Alternative Names contain the keyword.

**FR-2.2** Results are deduplicated: each unique domain name is counted once regardless of how many certificates reference it. Wildcard prefixes (`*.`) are stripped; all domains are normalised to lowercase.

**FR-2.3** crt.sh failures (HTTP 5xx, timeouts, rate limits) do not crash the integration. Errors are logged; the coordinator completes the cycle with whatever data it has.

**FR-2.4** Each request has a fixed timeout of 30 seconds. Failed requests are retried up to 3 times with exponential backoff; after the third failure the source is skipped for the current cycle. The retry limit is a fixed internal constant, not user-configurable.

### F-3 — Deduplication and seen-domain tracking

**FR-3.1** The integration maintains a persistent store (`homeassistant.helpers.storage.Store`, key `domain_watch.seen`) of previously detected domains. The store schema includes a `schema_version` key from the first release to enable future migrations.

**FR-3.2** Only domains absent from the persistent store trigger a detection event and notification. Domains already in the store are silently skipped.

**FR-3.3** The persistent store survives HA restarts. The store grows indefinitely; at the expected data volume (tens of entries) this requires no active management.

**FR-3.4** `domain_watch.mark_reviewed` accepts a `domain` parameter and sets a `reviewed` flag on the store entry. A reviewed domain is permanently suppressed — it never triggers alerts again. This is a one-way operation in v1.

### F-4 — RDAP enrichment

**FR-4.1** For each newly detected domain, the integration attempts to retrieve registrar name, registration date, and nameservers from the RDAP registry.

**FR-4.2** RDAP lookups fail gracefully: if data is unavailable or the request times out, the affected fields are omitted from the payload (not set to null). The detection event is still emitted.

### F-5 — Detection events and notifications

**FR-5.1** For every newly detected domain, the integration fires a Home Assistant event (`domain_watch_detected`) with a payload containing: `domain`, `source`, `first_seen`, `registrar`, `registration_date`, `nameservers`, `cert_id`, `issuer_name`, `not_before`. The last three fields are populated only for crt.sh detections; omitted for other sources.

**FR-5.2** The event is fired unconditionally; it is always available for user-defined automations regardless of whether a direct notify service is configured.

**FR-5.3** The user may optionally configure a notification entity ID (e.g. `notify.mobile_app_phone`). When set, the coordinator calls the `notify.send_message` action with that entity ID for each new detection, providing a human-readable summary (domain name, registrar, registration date, and cert issuance date when available). This uses the HA notification entity API introduced in HA 2024.12.0.

**FR-5.4** The README documents at least two ready-to-use automation examples (mobile push and Telegram).

### F-6 — Sensor entities

**FR-6.1** A sensor entity (`sensor.domain_watch_detections`) exposes the total count of known impostor domains as its state. Its attributes include the most recent detections with full detail.

### F-7 — Services

**FR-7.1** `domain_watch.scan_now` forces an immediate poll cycle outside the regular interval.

**FR-7.2** `domain_watch.mark_reviewed` accepts a `domain` parameter and permanently suppresses alerts for that domain. See FR-3.4.

### F-8 — HACS distribution

**FR-8.1** The integration ships with a `hacs.json` declaring minimum HA version `2024.12.0`.

**FR-8.2** The integration passes hassfest and HACS Action validation in CI (`validate.yml`), including dependency version-pin validation.

**FR-8.3** The README covers installation via HACS, initial configuration, example automations, and egress requirements.

### F-9 — Localisation

**FR-9.1** All user-facing strings in the config flow, options flow, and entity names are defined in `strings.json` with English and Dutch translations provided.

## 5. Non-Functional Requirements

**NFR-1 — Async discipline.** No blocking I/O on the HA event loop. All HTTP uses `async_get_clientsession(hass)`.

**NFR-2 — Fault isolation.** A crt.sh failure must not prevent the coordinator from completing its cycle. RDAP failures must not block detection event emission.

**NFR-3 — No credentials.** The integration uses only publicly accessible endpoints (crt.sh, rdap.org). No API keys or authentication are required or stored.

**NFR-4 — Minimal footprint.** The poll cycle must complete within the configured interval. Store growth is unbounded but negligible at expected data volumes.

**NFR-5 — HA coding standards.** Config entries are managed via ConfigFlow; no YAML-only setup. `iot_class` is `cloud_polling`. The integration registers and unloads cleanly.

**NFR-6 — Egress requirements.** The integration requires outbound access to `crt.sh` (HTTPS, port 443) and `rdap.org` (HTTPS, port 443). These must be documented in the README for users with restrictive firewall policies.

## 6. Out of Scope — v1

- Binary sensor entity (redundant given `domain_watch_detected` event as primary notification path; the count sensor covers dashboard visibility).
- DNS permutation monitoring via dnstwist (deferred to v2; adds executor complexity and a heavy dependency for marginal gain over crt.sh alone).
- Store retention / purge policy (deferred to v2; unnecessary at expected data volumes).
- Reversible mark_reviewed / unmark_reviewed (deferred to v2).
- Real-time Certificate Transparency via certstream (persistent websocket; deferred to a standalone add-on).
- Newly Registered Domains (NRD) zone-file downloads.
- Automated takedown reporting (Google Safe Browsing, SmartScreen).
- Multi-brand / multi-tenant profiles within a single config entry.
- Historical reporting or trend dashboards.

## 7. Constraints and Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| crt.sh rate-limiting or downtime | Medium | Exponential backoff + fail-soft per FR-2.3/2.4 |
| RDAP data unavailable for some registrars | High | Graceful degradation per FR-4.2 |
| HA breaking changes in future versions | Low | Pin minimum HA version; CI validates on current release |
| Impostor uses a CDN with no direct TLS cert (rare) | Low | Accepted gap; CT remains the primary and most reliable signal |

## 8. Resolved Decisions

- **dnstwist deferred to v2** — crt.sh covers the core detection need; dnstwist adds executor/threading complexity and a heavy dependency that outweighs its value for v1.
- **Store retention removed from v1** — data volume is too small to warrant a purge policy. Revisit if user-reported store size becomes an issue.
- **mark_reviewed is one-way in v1** — plain suppress flag; reversibility deferred.
- **Binary sensor dropped** — `domain_watch_detected` event + user automation is the primary notification path; binary sensor is redundant. Count sensor covers dashboard visibility.
- **Event as primary notification path** — event fires unconditionally with full payload; direct notify (FR-5.3) retained as a zero-config convenience for HACS users.
- **Event payload cert fields** (`cert_id`, `issuer_name`, `not_before`) — included; omitted (not null) for non-crt.sh sources.
- **In-memory dict + Store flush** — coordinator owns live state in memory; Store is persistence layer flushed after mutations; eliminates coroutine interleave risk.
- **schema_version from day one** — top-level key in store dict; absent key treated as v0 with no-op migration.
- **Clean unload** — coordinator cancelled and Store flushed inside `async_unload_entry` via `entry.async_on_unload`.
