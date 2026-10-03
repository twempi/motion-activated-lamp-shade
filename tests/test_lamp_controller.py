"""Hardware-free checks for the ESP32 Wi-Fi lamp controller."""

from __future__ import annotations

from urllib.error import HTTPError, URLError

import pytest

from gesturelight import lamp_controller as lamp_controller_module
from gesturelight.lamp_controller import LampController, LampControllerConfig, LampControllerError


class FakeResponse:
    status = 200

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_health_check_and_button_commands_use_local_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []

    def fake_urlopen(request: object, *, timeout: float) -> FakeResponse:
        assert timeout == 1.5
        requests.append(request)
        return FakeResponse()

    monkeypatch.setattr(lamp_controller_module, "urlopen", fake_urlopen)

    with LampController(
        LampControllerConfig(
            base_url="http://192.168.1.50/",
            timeout_seconds=1.5,
        )
    ) as controller:
        controller.press_power_button()
        controller.press_brightness_up_button()
        controller.press_brightness_down_button()

    assert [(request.get_method(), request.full_url, request.data) for request in requests] == [
        ("GET", "http://192.168.1.50/health", None),
        ("POST", "http://192.168.1.50/command", b"command=p"),
        ("POST", "http://192.168.1.50/command", b"command=u"),
        ("POST", "http://192.168.1.50/command", b"command=d"),
    ]
    assert [dict(request.header_items()) for request in requests] == [
        {},
        {"Content-type": "application/x-www-form-urlencoded"},
        {"Content-type": "application/x-www-form-urlencoded"},
        {"Content-type": "application/x-www-form-urlencoded"},
    ]


def test_connection_errors_are_reported_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_connect(*_: object, **__: object) -> None:
        raise URLError("host unavailable")

    monkeypatch.setattr(lamp_controller_module, "urlopen", fail_to_connect)

    with pytest.raises(LampControllerError, match="Could not reach ESP32"):
        LampController(LampControllerConfig("http://192.168.1.50")).__enter__()


def test_http_errors_are_reported_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_request(request: object, **_: object) -> None:
        raise HTTPError(request.full_url, 404, "Not Found", None, None)

    monkeypatch.setattr(lamp_controller_module, "urlopen", reject_request)

    with pytest.raises(LampControllerError, match="HTTP status 404"):
        LampController(LampControllerConfig("http://192.168.1.50")).__enter__()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": ""},
        {"base_url": "https://192.168.1.50"},
        {"base_url": "http://192.168.1.50/path"},
        {"base_url": "http://192.168.1.50:not-a-port"},
        {"base_url": "http://192.168.1.50", "timeout_seconds": 0},
    ],
)
def test_lamp_configuration_rejects_invalid_values(kwargs: dict[str, str | float]) -> None:
    with pytest.raises(ValueError):
        LampControllerConfig(**kwargs)
