"""Constants for Domain Watch."""

DOMAIN = "domain_watch"

# Config / options keys
CONF_KEYWORDS = "keywords"
CONF_INTERVAL = "interval"
CONF_NOTIFY = "notify_service"

# Persistent store
STORE_KEY = f"{DOMAIN}.seen"
STORE_VERSION = 1

# HA event
EVENT_DETECTED = f"{DOMAIN}_detected"

# Defaults
DEFAULT_INTERVAL = 6  # hours
MIN_INTERVAL = 1  # hours

# crt.sh
CRTSH_BASE_URL = "https://crt.sh/"
CRTSH_TIMEOUT = 30  # seconds
CRTSH_MAX_RETRIES = 3
