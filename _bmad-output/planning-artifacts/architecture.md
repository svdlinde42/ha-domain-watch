---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - "_bmad-output/planning-artifacts/prds/prd-ha-domain-watch-2026-06-20/prd.md"
  - "_bmad-output/planning-artifacts/prds/prd-ha-domain-watch-2026-06-20/addendum.md"
workflowType: 'architecture'
project_name: 'ha-domain-watch'
user_name: 'Simon'
date: '2026-06-21'
---

# Architecture Decision Document — Domain Watch

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

---

## Step 6 — Project Structure & Boundaries

### Complete Project Tree

```
ha-domain-watch/                          # GitHub repository root
├── custom_components/
│   └── domain_watch/
│       ├── __init__.py                   # async_setup_entry, async_unload_entry,
│       │                                 # service registration (scan_now, mark_reviewed)
│       ├── manifest.json                 # domain, version, iot_class: cloud_polling,
│       │                                 # requirements, min_ha_version: 2024.12.0
│       ├── const.py                      # ALL string literals, keys, defaults, timeouts
│       │                                 # DOMAIN, EVENT_DETECTED, CONF_KEYWORDS,
│       │                                 # CONF_INTERVAL, CONF_NOTIFY, STORE_KEY,
│       │                                 # DEFAULT_INTERVAL, CRTSH_TIMEOUT, CRTSH_MAX_RETRIES
│       ├── config_flow.py                # ConfigFlow (keywords, interval)
│       │                                 # OptionsFlow (interval, notify service)
│       ├── coordinator.py                # DomainWatchCoordinator(DataUpdateCoordinator)
│       │                                 # _async_update_data(), _record_detections(),
│       │                                 # mark_reviewed(), scan_now()
│       ├── store.py                      # DomainWatchStore — wraps helpers.storage.Store,
│       │                                 # schema migration dispatcher (v0→v1 no-op)
│       ├── sources/
│       │   ├── __init__.py               # Source(ABC), Detection(dataclass),
│       │   │                             # SOURCES: dict[str, type[Source]]
│       │   └── crtsh.py                  # CrtShSource — fetch, parse, retry/backoff
│       ├── rdap.py                       # enrich(domain, session) → dict
│       │                                 # fail-graceful, returns {} on any error
│       ├── sensor.py                     # DomainWatchSensor
│       │                                 # state: total detection count
│       │                                 # attrs: last_checked, last_successful_poll, detections[]
│       ├── services.yaml                 # scan_now, mark_reviewed descriptors + schemas
│       ├── strings.json                  # config/options flow UI strings
│       └── translations/
│           ├── en.json
│           └── nl.json
├── tests/
│   ├── conftest.py                       # hass fixture, aioresponses setup,
│   │                                     # DomainWatchStore stub, clock patch
│   ├── test_coordinator.py               # poll cycle, diff/dedup, _record_detections(),
│   │                                     # UpdateFailed on exhaustion, startup hydration
│   ├── test_crtsh.py                     # fetch, parse (multi-SAN, wildcard strip),
│   │                                     # retry/backoff, timeout, HTTP 429/5xx
│   ├── test_rdap.py                      # enrich happy path, timeout, 4xx/5xx, parse error
│   ├── test_store.py                     # load/save, schema_version migration dispatcher,
│   │                                     # inject stub Store
│   ├── test_config_flow.py               # ConfigFlow happy path + empty keyword validation,
│   │                                     # OptionsFlow
│   └── test_sensor.py                    # state, last_checked, last_successful_poll attrs
├── hacs.json                             # content_in_root: false, iot_class: cloud_polling
├── README.md                             # install, config, automation examples (mobile + Telegram),
│                                         # egress requirements, mark_reviewed usage
└── .github/
    └── workflows/
        └── validate.yml                  # hassfest + HACS Action validation
```

### FR → File Mapping

| Feature group | Primary file(s) |
|---------------|----------------|
| F-1 Keyword config | `config_flow.py`, `const.py` |
| F-2 crt.sh monitoring | `sources/crtsh.py`, `coordinator.py`, `const.py` |
| F-3 Dedup & store | `store.py`, `coordinator.py` |
| F-4 RDAP enrichment | `rdap.py`, `coordinator.py` |
| F-5 Events & notify | `coordinator.py`, `const.py` |
| F-6 Sensor | `sensor.py`, `coordinator.py` |
| F-7 Services | `__init__.py`, `services.yaml`, `coordinator.py` |
| F-8 HACS distribution | `manifest.json`, `hacs.json`, `.github/workflows/validate.yml` |
| F-9 Localisation | `strings.json`, `translations/en.json`, `translations/nl.json` |

### Integration Boundaries

**External (egress only, HTTPS 443):**
- `crt.sh` — queried by `sources/crtsh.py` via coordinator-provided `aiohttp` session
- `rdap.org` — queried by `rdap.py` via coordinator-provided `aiohttp` session

**HA internal:**
- **Event bus** — `coordinator.py` fires `domain_watch_detected` via `hass.bus.async_fire()`
- **Config entries** — `__init__.py` manages setup/unload; `config_flow.py` manages UI
- **Storage** — `store.py` wraps `helpers.storage.Store(hass, STORE_VERSION, STORE_KEY)`
- **aiohttp session** — obtained once in coordinator via `async_get_clientsession(hass)`; passed to sources and rdap as a parameter
- **Notify service** — called by `coordinator.py` via `hass.services.async_call()` when configured

### Data Flow

```
coordinator._async_update_data()
  │
  └─ CrtShSource.fetch(session, config)        # sources/crtsh.py
       └─ GET crt.sh/?q=%keyword%...           # external
       └─ parse name_value → list[Detection]
  │
  └─ diff against self._seen → new_domains
  │
  └─ _record_detections(new_domains)           # coordinator.py
       └─ update self._seen
       └─ store.async_save(self._seen)         # store.py → HA storage
       │
       └─ for each domain:
            └─ rdap.enrich(domain, session)    # rdap.py → GET rdap.org
            └─ hass.bus.async_fire(            # HA event bus
                 EVENT_DETECTED, payload)
            └─ [optional] hass.services.       # HA notify
                 async_call("notify", ...)
  │
  └─ set last_checked, last_successful_poll
  └─ sensor reads coordinator.data            # sensor.py
```

---

## Step 5 — Implementation Patterns & Consistency Rules

### Naming Conventions

| Concern | Convention | Example |
|---------|-----------|---------|
| Python identifiers | `snake_case` | `first_seen`, `async_fetch`, `new_domains` |
| Constants | `UPPER_SNAKE_CASE` in `const.py` | `CONF_KEYWORDS`, `STORE_KEY`, `EVENT_DETECTED` |
| HA event name | `{domain}_{event}` | `domain_watch_detected` |
| HA service names | `{domain}.{verb_noun}` | `domain_watch.scan_now`, `domain_watch.mark_reviewed` |
| Store key | `{domain}.{identifier}` | `domain_watch.seen` |
| Files | `snake_case.py` | `config_flow.py`, `crtsh.py` |
| Test files | `test_{module}.py` in `tests/` | `tests/test_coordinator.py` |

`const.py` is the **single source of truth** for all string literals, keys, defaults, and timeouts. No raw string literals in any other module. Lint enforcement: `ruff` rule `WPS226` (or equivalent) flags inline strings in non-const modules.

---

### Structural Rules

- Tests live in `tests/` at repo root, mirroring `custom_components/domain_watch/`.
- `sources/__init__.py` exports `Source` (ABC), `Detection` (dataclass), and the registry dict — nothing else. Registry is a **static module-level dict** populated at import time: `SOURCES: dict[str, type[Source]] = {"crtsh": CrtShSource}`. Coordinator reads this dict; config entry controls which keys are enabled.
- Each source module has **no side effects at import time**. The `Source` subclass is defined; nothing runs until `fetch()` is called.
- `DomainWatchStore` wraps `helpers.storage.Store`. The `Store` instance is injected via constructor — never instantiated inside `DomainWatchStore` itself — so unit tests can inject a stub without a `hass` fixture.

---

### Types

**`DetectionRecord`** is a `TypedDict`:
```python
class DetectionRecord(TypedDict, total=False):
    first_seen: str        # ISO 8601, required
    source: str            # required
    reviewed: bool         # required
    registrar: str         # omitted when RDAP unavailable
    registration_date: str # omitted when RDAP unavailable
    nameservers: list[str] # omitted when RDAP unavailable
    cert_id: int           # omitted for non-crt.sh sources
    issuer_name: str       # omitted for non-crt.sh sources
    not_before: str        # omitted for non-crt.sh sources
```

`Detection` (the transient fetch result) is a `dataclass`:
```python
@dataclass
class Detection:
    domain: str
    source: str
    evidence: dict   # cert fields for crtsh; empty for future sources
```

---

### Event Payload Contract

The `domain_watch_detected` payload is a **plain `dict`** — no dataclass instances, no custom objects in event data.

**Always present:** `domain`, `source`, `first_seen`.

**Omitted when RDAP unavailable** (not `None`, not empty string, not `[]`): `registrar`, `registration_date`, `nameservers`.

**Omitted for non-crt.sh sources:** `cert_id`, `issuer_name`, `not_before`.

All timestamp values are **ISO 8601 strings** via `dt_util.utcnow().isoformat()` (`homeassistant.util.dt`). Never `datetime.utcnow()`. Test patch target: `homeassistant.util.dt.utcnow`.

README automation examples **must** use `| default('unknown')` filters on all optional fields.

---

### State Mutation Pattern

All writes to `self._seen: dict[str, DetectionRecord]` go through `_record_detections()`:

```python
async def _record_detections(self, detections: list[Detection], enriched: dict) -> None:
    for d in detections:
        self._seen[d.domain] = build_record(d, enriched.get(d.domain, {}))
    try:
        await self._store.async_save(self._seen)
    except Exception:
        _LOGGER.warning("Store flush failed; in-memory state is authoritative")
```

**Failure contract:** dict is updated first; store flush is best-effort. In-memory state is always authoritative. A flush failure is logged at `WARNING` and does not roll back the dict. On the next successful flush the state is recovered.

`mark_reviewed` service handler calls this method — no direct mutations to `self._seen` anywhere else.

---

### HA API Usage Rules

| Rule | Correct | Wrong |
|------|---------|-------|
| HTTP session | `async_get_clientsession(hass)` | `aiohttp.ClientSession()` |
| Fire-and-forget tasks | `hass.async_create_task(...)` | `asyncio.create_task(...)` |
| Timestamps | `dt_util.utcnow().isoformat()` | `datetime.utcnow().isoformat()` |
| Timeouts | `async with asyncio.timeout(30):` | `async_timeout.timeout(30)` |
| Event bus | `hass.bus.async_fire(...)` **in an `async def`** | calling from a sync callback or executor |

`hass.bus.async_fire()` must only appear inside `async def` methods. Structurally: it is called only within `_record_detections()`, which is `async def`. No other code path fires the event.

---

### Error Handling

**Intentional asymmetry:** crt.sh is the **detection source** — its failure degrades the integration's core function and must be visible. RDAP is **best-effort enrichment** — its failure enriches nothing and must not block detection.

| Failure | Action | Log level |
|---------|--------|-----------|
| crt.sh timeout (within retries) | retry with backoff | `DEBUG` |
| crt.sh HTTP 429 / 5xx | retry with backoff | `WARNING` |
| crt.sh JSON decode error | retry with backoff | `WARNING` |
| crt.sh retries exhausted | raise `UpdateFailed` → sensor `unavailable` | `ERROR` |
| RDAP any error (timeout, 4xx, 5xx, parse) | return `{}`, continue | `DEBUG` |
| Store flush failure | log and continue | `WARNING` |

`UpdateFailed` is raised only after all retries are exhausted on crt.sh. HTTP 429 and 5xx are both retried (same backoff policy). A JSON decode error on crt.sh is treated as a transient failure and retried.

---

### Sensor Attributes

`sensor.domain_watch_detections` exposes:

| Attribute | Type | When set |
|-----------|------|----------|
| `last_checked` | ISO 8601 string | Every poll attempt, success or failure |
| `last_successful_poll` | ISO 8601 string | Every poll that completes without crt.sh exhaustion |
| `detections` | list of recent `DetectionRecord` dicts | Always |

`last_checked` being set even on failure gives the user confidence the integration is alive before any detection fires. Sensor state flipping to `unavailable` (on `UpdateFailed`) is the failure signal; `last_checked` confirms liveness.

---

### Enforcement Summary — All Agents Must

1. Import string literals only from `const.py`.
2. Write `self._seen` only via `_record_detections()`.
3. Use `async_get_clientsession(hass)` — never instantiate `aiohttp.ClientSession`.
4. Use `dt_util.utcnow().isoformat()` for all timestamps.
5. Call `hass.bus.async_fire()` only from `async def` methods (structurally: only from `_record_detections()`).
6. Omit RDAP and non-crt.sh fields from event payload — never set them to `None` or `[]`.

---

## Step 4 — Core Architectural Decisions

### Observability

**`last_successful_poll` sensor attribute — added.** The `sensor.domain_watch_detections` entity exposes a `last_successful_poll` attribute (ISO 8601 timestamp, set by the coordinator after each cycle that completes without exhausting retries on all sources). Persisted in the coordinator's in-memory state; survives HA reload because the sensor is re-created from coordinator state on setup. Makes silent failure observable directly from the HA dashboard without log inspection.

### RDAP Payload Contract

**Option A — omit absent fields.** When RDAP is unavailable or returns an error, `registrar`, `registration_date`, and `nameservers` are simply not present in the `domain_watch_detected` event payload dict. They are never set to `null`. Automations that reference `{{ trigger.event.data.registrar | default('unknown') }}` work correctly; automations that don't guard the field get an empty string from Jinja2's default behaviour — acceptable given the README automation examples will use `default()` filters.

### Unload Ordering (Implementation Constraint)

`async_unload_entry` must fully await the coordinator's in-flight poll before flushing the store. If a poll is mid-execution when unload fires, `self._seen` may be partially mutated. The correct sequence:

```python
async def async_unload_entry(hass, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()   # cancels and awaits any in-flight refresh
    await coordinator.store.async_save(coordinator._seen)  # flush clean state
    ...
```

`DataUpdateCoordinator.async_shutdown()` is the HA-provided method that handles cancellation and awaits the current refresh task — do not cancel the task manually.

### Logging Levels

| Level | When |
|-------|------|
| `DEBUG` | Normal cycle events: fetched N certs, found M new domains, RDAP enriched |
| `WARNING` | Transient errors: crt.sh timeout, RDAP failure, retry N of 3 |
| `ERROR` | Retry exhaustion: source skipped for this cycle after 3 failed attempts |

### Integration Domain

`domain_watch` — used for `custom_components/domain_watch/`, `manifest.json` domain field, service names (`domain_watch.scan_now`, `domain_watch.mark_reviewed`), event name (`domain_watch_detected`), and store key (`domain_watch.seen`). GitHub repository name is `ha-domain-watch` (the `ha-` prefix is a repo naming convention only).

---

## Step 3 — Starter Template

**Selected:** `ludeeus/integration_blueprint` (GitHub template — "Use this template" → new repository)

**Rationale:** Provides correctly wired CI (hassfest + HACS Action in `.github/workflows/validate.yml`), correct `manifest.json` structure, `ConfigFlow`/`OptionsFlow` skeleton, and `DataUpdateCoordinator` scaffold — all the non-obvious HA-specific plumbing. Single-file platform structure matches our module design. Rename domain from `integration_blueprint` to `domain_watch`; strip example API/entity files; add `store.py`, `sources/`, `rdap.py`.

**HA integration domain:** `domain_watch` (Python identifier — underscores, no hyphens). The GitHub repo is named `ha-domain-watch`; the `custom_components/` folder, `manifest.json` domain, service names (`domain_watch.scan_now`), event name (`domain_watch_detected`), and store key (`domain_watch.seen`) all use `domain_watch`.

**Decisions inherited from blueprint:**

| Concern | Decision |
|---------|----------|
| Language | Python 3.12+ |
| HTTP client | `aiohttp` via `async_get_clientsession(hass)` |
| Testing | `pytest` + `pytest-homeassistant-custom-component` |
| CI | GitHub Actions — hassfest + HACS Action |
| Config management | HA `ConfigEntry` — no external config files |

---

## Step 2 — Project Context Analysis

### What We Are Building

**ha-domain-watch** is a Home Assistant HACS custom integration (`cloud_polling`) that monitors Certificate Transparency logs to detect newly registered domains that impersonate a configured brand keyword. It persists detections across restarts, suppresses re-alerting on known domains, enriches detections with RDAP registration data, and delivers detections via the HA event bus so users can wire any notification target (mobile, Telegram, etc.) via standard HA automations.

**Target environment:** HA instance running as a long-lived process; daily detection latency is acceptable; personal-scale data volume (tens of detected domains total).

---

### Core Constraints

**1. Strict async discipline (NFR-1)**
All I/O runs on the HA event loop via `aiohttp`. No blocking calls on the loop. The only executor boundary removed for v1: dnstwist (deferred to v2). This eliminates the main threading complexity risk.

**2. Fault isolation (NFR-2)**
- crt.sh failure (5xx, timeout, rate-limit) must not crash the coordinator. It skips the cycle with a logged warning.
- RDAP failure must not block detection event emission. RDAP runs after raw detections are already persisted.

**3. HA integration contract (NFR-5)**
- `ConfigFlow` + `OptionsFlow` for all config; no YAML-only setup.
- `iot_class: cloud_polling` in manifest.
- Clean registration and unload: all entities, services, listeners de-registered without leaving dangling state.
- Minimum HA version: 2024.12.0.

**4. HACS compliance (FR-8)**
- Passes `hassfest` and HACS Action validation in CI.
- `hacs.json` declares minimum HA version and content type.

---

### Module Inventory (v1)

```
custom_components/domain_watch/
├── __init__.py          # async_setup_entry, async_unload_entry, service registration
├── manifest.json        # domain, version, iot_class, requirements, min_ha_version
├── const.py             # DOMAIN, EVENT_DETECTED, CONF_*, STORE_KEY, defaults
├── config_flow.py       # ConfigFlow (keywords, interval) + OptionsFlow (interval, notify service)
├── coordinator.py       # DomainWatchCoordinator(DataUpdateCoordinator)
├── store.py             # DomainWatchStore — thin wrapper on helpers.storage.Store
├── sources/
│   ├── __init__.py      # Source(ABC) + Detection dataclass + registry dict
│   └── crtsh.py         # CrtShSource — fetch, parse, deduplicate, retry
├── rdap.py              # enrich(domain, session) → dict — fail-graceful
├── sensor.py            # DomainWatchSensor — count + full attribute list
├── services.yaml        # scan_now, mark_reviewed descriptors
├── strings.json
└── translations/
    ├── en.json
    └── nl.json
```

**Not present in v1:** `binary_sensor.py` (dropped), `dnstwist_source.py` (v2).

---

### State Management Architecture

**Pattern: in-memory dict + Store flush**

The coordinator owns the authoritative live state as a Python dict keyed by domain. `DomainWatchStore` is a persistence layer that wraps `homeassistant.helpers.storage.Store`; it is only written after mutations to the in-memory dict.

This prevents asyncio coroutine interleave: there is no window where a second coroutine reads an inconsistent state from the store because the store is only flushed after the in-memory dict is already updated.

```python
# coordinator holds:
self._seen: dict[str, DetectionRecord]  # authoritative live state

# store is flushed after every mutation:
self._seen[domain] = record
await self._store.async_save(self._seen)
```

**Schema versioning from day one**

The store JSON root always carries `schema_version: 1`. A store file without this key is treated as v0 with a no-op migration path. This costs nothing now and makes future migrations cheap.

```json
{
  "schema_version": 1,
  "domains": {
    "fake-brand.com": {
      "first_seen": "2026-06-20T14:23:00Z",
      "source": "crtsh",
      "reviewed": false
    }
  }
}
```

---

### Coordinator Lifecycle

**Poll cycle (per interval):**

1. For each enabled source: `await source.fetch(session, config)` → `list[Detection]`
2. Merge results; normalise domains (strip `*.`, lowercase).
3. Diff against `self._seen` → `new_domains`.
4. Write `new_domains` to `self._seen` and flush store **before RDAP** — detections are persisted even if RDAP times out.
5. For each new domain:
   a. `await rdap.enrich(domain, session)` — fail-graceful, returns partial dict on any error.
   b. `hass.bus.async_fire(EVENT_DETECTED, payload)` — unconditional.
   c. If notify service configured: call `notify.send_message` with human-readable summary.
6. Update sensor state.

**Clean unload (NFR-5):**

Registered via `entry.async_on_unload` so it runs inside `async_unload_entry`:
- Cancel coordinator update loop.
- Flush store one final time.
- De-register services.

---

### Notification Architecture

**Primary path:** `domain_watch_detected` HA event with full payload. Users write standard HA automations triggered by this event. The event fires unconditionally on every new detection regardless of whether a notify service is configured.

**Event payload:**
```json
{
  "domain": "example-fake-shop.com",
  "source": "crtsh",
  "first_seen": "2026-06-20T14:23:00Z",
  "registrar": "Namecheap, Inc.",
  "registration_date": "2026-06-19T00:00:00Z",
  "nameservers": ["ns1.example.com"],
  "cert_id": 12345678,
  "issuer_name": "Let's Encrypt",
  "not_before": "2026-06-19T10:00:00Z"
}
```
`cert_id`, `issuer_name`, `not_before` are omitted (not null) for non-crt.sh sources.

**Secondary path:** optional direct notify service (FR-5.3). User configures a notify service name via OptionsFlow. When set, the coordinator calls it directly as a zero-automation convenience. This is secondary — the event is always fired regardless.

**Binary sensor: not implemented.** Dropped as redundant: the event IS the trigger, and the count sensor covers dashboard visibility.

---

### Source Architecture

```python
class Source(ABC):
    name: str

    @abstractmethod
    async def fetch(self, session: aiohttp.ClientSession, config: dict) -> list[Detection]:
        ...

@dataclass
class Detection:
    domain: str
    source: str
    evidence: dict  # cert fields for crtsh; empty for future sources
```

Registry: `dict[str, type[Source]]` keyed by source identifier. In v1 this contains only `"crtsh"`. The coordinator iterates enabled sources from config against the registry — this pattern supports v2 sources without touching the coordinator.

**crt.sh specifics:**
- Endpoint: `https://crt.sh/?q=%25{keyword}%25&output=json&exclude=expired&deduplicate=Y`
- `&exclude=expired` drops certs that are no longer valid; `&deduplicate=Y` lets the server collapse duplicate SANs, reducing payload size.
- `name_value` field contains newline-separated SANs; split, strip `*.`, lowercase, deduplicate any remaining.
- Match semantics: ILIKE substring — case-insensitive, `%keyword%` catches `fake-brand.com` and `brand-fakestore.eu` but not typosquats (`br4nd.com`). Typosquat coverage is the gap dnstwist fills in v2.
- Detection boundary: crt.sh sees a domain when a TLS cert is issued, not when the domain is registered. A parked domain with no cert is invisible. For fake webshops this gap is typically hours to days (HTTPS is required for a credible storefront). This limitation is documented in the README.
- 30s timeout per request; exponential backoff; max 3 retries; skip source on exhaustion.

---

### Key Decisions Locked in Step 2

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| State management | In-memory dict + Store flush | Prevents coroutine interleave; Store is persistence only |
| Schema versioning | `schema_version: 1` from day one | Zero-cost now; enables cheap future migrations |
| Unload pattern | `entry.async_on_unload` callback | Guarantees clean state on HA reload/restart |
| RDAP ordering | Persist raw → then enrich | RDAP timeout never blocks detection persistence |
| Notification primary path | `domain_watch_detected` event | Flexible: any notify target, any message template via automation |
| Notification secondary path | Optional direct notify service | Zero-automation convenience for HACS users |
| Binary sensor | Dropped (v1) | Redundant given event as primary notification path |
| dnstwist | Deferred to v2 | Eliminates executor boundary complexity for v1 |
| Retention/purge | Deferred to v2 | Unnecessary at expected data volume |
| unmark_reviewed | Deferred to v2 | One-way suppress flag sufficient for v1 |

---
