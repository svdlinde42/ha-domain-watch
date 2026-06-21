"""Config flow for Domain Watch."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_INTERVAL, CONF_KEYWORDS, CONF_NOTIFY, DEFAULT_INTERVAL, DOMAIN, MIN_INTERVAL


class DomainWatchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Domain Watch."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            keywords = [k.strip() for k in user_input[CONF_KEYWORDS].split(",") if k.strip()]
            if not keywords:
                errors[CONF_KEYWORDS] = "no_keywords"
            else:
                return self.async_create_entry(
                    title=", ".join(keywords),
                    data={
                        CONF_KEYWORDS: keywords,
                        CONF_INTERVAL: user_input[CONF_INTERVAL],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_KEYWORDS): str,
                    vol.Optional(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
                        int, vol.Range(min=MIN_INTERVAL)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DomainWatchOptionsFlow:
        return DomainWatchOptionsFlow()


class DomainWatchOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Domain Watch."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_INTERVAL,
            self.config_entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL),
        )
        current_notify = self.config_entry.options.get(CONF_NOTIFY, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_INTERVAL, default=current_interval): vol.All(
                        int, vol.Range(min=MIN_INTERVAL)
                    ),
                    vol.Optional(CONF_NOTIFY, default=current_notify): str,
                }
            ),
        )
