"""Nové nastavení se zakládá až v integraci z nokturno-app/nokturno-ha."""
from homeassistant import config_entries

DOMAIN = "nokturno"


class NokturnoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_abort(reason="prestehovano",
                                description_placeholders={"url": "https://github.com/nokturno-app/nokturno-ha"})
