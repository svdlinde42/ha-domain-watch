# Domain Watch

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/svdlinde42/ha-domain-watch/actions/workflows/validate.yml/badge.svg)](https://github.com/svdlinde42/ha-domain-watch/actions/workflows/validate.yml)

Home Assistant integration that monitors [Certificate Transparency](https://certificate.transparency.dev/) logs to detect newly registered domains that impersonate a monitored brand keyword.

When a new impostor domain is found, a `domain_watch_detected` event is fired on the Home Assistant event bus with full detection context (domain, registrar, registration date, nameservers, certificate details). Use a standard HA automation to forward the alert to any notification target — mobile, Telegram, email, etc.

## Requirements

Outbound HTTPS access to:
- `crt.sh` (port 443) — Certificate Transparency log search
- `rdap.org` (port 443) — Domain registration data enrichment

## Installation

1. Open HACS in Home Assistant.
2. Go to **Integrations** → **Custom repositories**.
3. Add `https://github.com/svdlinde42/ha-domain-watch` with category **Integration**.
4. Install **Domain Watch** and restart Home Assistant.

## Configuration

Go to **Settings → Devices & Services → Add Integration → Domain Watch**.

| Field | Description | Default |
|-------|-------------|---------|
| Brand keywords | Comma-separated keywords to monitor (e.g. `mybrand, my-brand`) | — |
| Poll interval | How often to check, in hours | 6 |
| Notification service | HA notify service to call on new detections (e.g. `notify.mobile_app_phone`). Leave empty to use automations only. | — |

Settings can be changed at any time via **Configure** without restarting HA.

## Sensor

`sensor.domain_watch_detections` — total count of known impostor domains detected.

| Attribute | Description |
|-----------|-------------|
| `last_checked` | Timestamp of the most recent poll attempt |
| `last_successful_poll` | Timestamp of the last poll that completed without error |
| `detections` | List of recent detection records with full detail |

## Events

`domain_watch_detected` — fired for every newly detected domain.

```yaml
domain: example-fake-shop.com
source: crtsh
first_seen: "2026-06-20T14:23:00+00:00"
registrar: "Namecheap, Inc."        # omitted if RDAP unavailable
registration_date: "2026-06-19T00:00:00+00:00"  # omitted if RDAP unavailable
nameservers: ["ns1.example.com"]    # omitted if RDAP unavailable
cert_id: 12345678
issuer_name: "C=US, O=Let's Encrypt, CN=R3"
not_before: "2026-06-19T10:00:00+00:00"
```

## Services

| Service | Description |
|---------|-------------|
| `domain_watch.scan_now` | Force an immediate poll outside the regular interval |
| `domain_watch.mark_reviewed` | Mark a detected domain as reviewed (`domain: example.com`) |

## Automation examples

**Mobile push notification:**

```yaml
automation:
  trigger:
    - platform: event
      event_type: domain_watch_detected
  action:
    - action: notify.send_message
      target:
        entity_id: notify.mobile_app_your_phone
      data:
        title: "Impostor domain detected"
        message: >
          {{ trigger.event.data.domain }} —
          registered {{ trigger.event.data.registration_date | default('date unknown') }}
          via {{ trigger.event.data.registrar | default('unknown registrar') }}
```

**Telegram notification:**

```yaml
automation:
  trigger:
    - platform: event
      event_type: domain_watch_detected
  action:
    - action: notify.send_message
      target:
        entity_id: notify.telegram
      data:
        message: >
          *Impostor domain detected*
          Domain: `{{ trigger.event.data.domain }}`
          Registrar: {{ trigger.event.data.registrar | default('unknown') }}
          Registered: {{ trigger.event.data.registration_date | default('unknown') }}
          Cert issued: {{ trigger.event.data.not_before | default('unknown') }}
```

## Known limitations

Detection is based on TLS certificate issuance, not domain registration. A parked domain without a certificate is not visible. For fake webshops this gap is typically hours to a few days, as HTTPS is required for a credible storefront.

Keyword matching is substring-based (`%keyword%`, case-insensitive). Typosquatted variants (`br4nd.com`) are not detected in v1.
