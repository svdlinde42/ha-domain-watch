# Addendum — Domain Watch

_Companion to prd.md. Contains implementation-level detail, technical decisions, and content that belongs in downstream architecture/engineering documents._

---

## Repository Structure

```
.
├── custom_components/
│   └── domain_watch/
│       ├── __init__.py            # setup/unload entry, register services
│       ├── manifest.json
│       ├── const.py               # DOMAIN, defaults, conf-keys, event name
│       ├── config_flow.py         # ConfigFlow + OptionsFlow
│       ├── coordinator.py         # DataUpdateCoordinator + diff/dedup + event/notify
│       ├── store.py               # wrapper around helpers.storage.Store
│       ├── sources/
│       │   ├── __init__.py        # Source ABC + registry
│       │   └── crtsh.py
│       ├── rdap.py                # enrichment helper
│       ├── sensor.py              # detection counter + attributes
│       ├── services.yaml          # scan_now, mark_reviewed
│       ├── strings.json           # config-flow strings
│       └── translations/
│           ├── en.json
│           └── nl.json
├── hacs.json
├── README.md
└── .github/workflows/validate.yml # hassfest + HACS Action
```

---

## Key Technical Decisions

### Source interface

```python
class Source(ABC):
    name: str
    async def fetch(self, session, config) -> list[Detection]

@dataclass
class Detection:
    domain: str
    source: str
    evidence: dict
```

Registry dict keyed by source identifier enables toggle-by-key from config.

### crt.sh query

- Endpoint: `https://crt.sh/?q=%25{keyword}%25&output=json&exclude=expired&deduplicate=Y`
- `exclude=expired` drops expired certs server-side; `deduplicate=Y` collapses duplicate SANs server-side.
- Response field `name_value` contains newline-separated SANs; split, strip `*.`, lowercase.
- Match type: ILIKE substring (case-insensitive `%keyword%`). Catches keyword-containing domains; does not catch typosquats — that is the v2 dnstwist gap.
- Timeout: 30s; exponential backoff; max 3 retries per cycle.

### Persistent store

`homeassistant.helpers.storage.Store`, key `domain_watch.seen`.
Schema: `{domain: {first_seen: ISO8601, source: str, reviewed: bool, ...}}`

### RDAP enrichment

- Endpoint: `https://rdap.org/domain/{domain}`
- Fields extracted: `registrar`, `registration_date`, `nameservers`
- Any failure → fields set to `None`; detection still proceeds.

### Coordinator flow (per cycle)

1. For each enabled source: `await source.fetch(session, config)`
2. Merge + normalise results.
3. Diff against persistent store → `new_domains`.
4. Write `new_domains` to store (raw, before enrichment — ensures detections are persisted even if RDAP times out).
5. For each new domain: RDAP enrich → fire `domain_watch_detected` event → optional notify call.

### Event payload

```json
{
  "domain": "example-fake-shop.com",
  "source": "crtsh",
  "first_seen": "2026-06-20T14:23:00Z",
  "registrar": "Namecheap, Inc.",
  "registration_date": "2026-06-19T00:00:00Z",
  "nameservers": ["ns1.example.com"],
  "cert_id": 12345678,
  "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
  "not_before": "2026-06-19T10:00:00Z"
}
```

`cert_id`, `issuer_name`, and `not_before` are populated only for crt.sh detections; omitted entirely (not set to null) for other sources.

---

## Phased Delivery

| Phase | Scope | Acceptance |
|-------|-------|------------|
| 1 — Skeleton | Repo structure, manifest, hacs.json, const.py, empty config_flow (keywords + interval), validate.yml green | Integration loads; config flow shows keyword/interval step |
| 2 — crt.sh + coordinator + store | crt.sh source, coordinator, dedup, sensor with count + attributes | Known keyword returns hit; repeated runs do not re-trigger |
| 3 — Events + notifications | `domain_watch_detected` event + optional notify in OptionsFlow + README automations | New (mocked) detection fires event and, with service set, a notify call |
| 4 — RDAP + services | RDAP enrichment, `scan_now`, `mark_reviewed` | Event payload contains registrar/date/NS; services work; mark_reviewed suppresses repeat |
| 5 — Translations + README | nl/en translations, README finalised (installation, config, automation examples, egress requirements) | Strings localised; README covers all user-facing steps |

---

## Test Strategy

- **Unit:** crt.sh parser (multi-SAN, wildcard strip, dedup); diff/dedup logic with mocked Store; RDAP parser with fixture JSON.
- **Config flow:** happy path + validation error on empty keyword.
- **HTTP mocking:** `aioresponses` for all external calls; no real network calls in tests.

---

## Future Scope (post-v1)

- Real-time CT via certstream as a separate HA add-on that pushes events to this integration via webhook.
- NRD keyword feed as an additional Source.
- Auto-reporting to Google Safe Browsing / SmartScreen on detection.
- Multi-profile support (multiple brands per config entry or multiple entries).
