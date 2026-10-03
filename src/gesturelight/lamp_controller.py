"""Local-Wi-Fi HTTP control for the ESP32 lamp-button relay board."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Self
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_HTTP_TIMEOUT_SECONDS = 1.0
COMMAND_PATH = "/command"
HEALTH_PATH = "/health"
POWER_COMMAND = "p"
BRIGHTNESS_DOWN_COMMAND = "d"
BRIGHTNESS_UP_COMMAND = "u"


class LampControllerError(RuntimeError):
    """Raised when the ESP32 Wi-Fi connection cannot be used safely."""


@dataclass(frozen=True, slots=True)
class LampControllerConfig:
    """HTTP settings for a Wi-Fi-connected ESP32 on the local network."""

    base_url: str
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.base_url)
            port = parsed.port
        except ValueError as error:
            raise ValueError("ESP32 URL must be a valid HTTP URL.") from error
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or any(character.isspace() for character in self.base_url)
            or parsed.username is not None
            or parsed.password is not None
            or port == 0
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "ESP32 URL must be a plain HTTP base URL, such as http://192.168.1.50."
            )
        if self.timeout_seconds <= 0:
            raise ValueError("ESP32 HTTP timeout must be positive.")

    @property
    def command_url(self) -> str:
        """Return the URL accepted by the ESP32 command handler."""
        return f"{self.base_url.rstrip('/')}{COMMAND_PATH}"

    @property
    def health_url(self) -> str:
        """Return the URL used to verify the ESP32 configuration at startup."""
        return f"{self.base_url.rstrip('/')}{HEALTH_PATH}"


class LampController:
    """Send button-pulse commands to the ESP32 over local Wi-Fi."""

    def __init__(self, config: LampControllerConfig) -> None:
        self._config = config

    def __enter__(self) -> Self:
        self._request(self._config.health_url)
        logger.info("Connected to ESP32 at %s over Wi-Fi.", self._config.base_url)
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def press_power_button(self) -> None:
        """Tell the ESP32 to pulse its power-button output once."""
        self._press_button(POWER_COMMAND, "power")

    def press_brightness_up_button(self) -> None:
        """Tell the ESP32 to pulse its brightness-up output once."""
        self._press_button(BRIGHTNESS_UP_COMMAND, "brightness-up")

    def press_brightness_down_button(self) -> None:
        """Tell the ESP32 to pulse its brightness-down output once."""
        self._press_button(BRIGHTNESS_DOWN_COMMAND, "brightness-down")

    def _press_button(self, command: str, name: str) -> None:
        body = urlencode({"command": command}).encode()
        self._request(
            self._config.command_url,
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        logger.info("Sent ESP32 %s-button command over Wi-Fi.", name)

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = Request(
            url,
            data=data,
            headers=headers,
            method="POST" if data is not None else "GET",
        )
        try:
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                if response.status != 200:
                    raise LampControllerError(
                        f"ESP32 returned unexpected HTTP status {response.status}."
                    )
        except HTTPError as error:
            raise LampControllerError(f"ESP32 returned HTTP status {error.code}.") from error
        except (OSError, ValueError) as error:
            raise LampControllerError(
                f"Could not reach ESP32 at {self._config.base_url!r}."
            ) from error

    def close(self) -> None:
        """Finish Wi-Fi control; HTTP requests do not keep a connection open."""
        logger.info("Stopped ESP32 Wi-Fi control.")
