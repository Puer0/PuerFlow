import importlib.util
import socket
from pathlib import Path

import pytest


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_url_for_ssrf_blocks_non_http_schemes():
    root = Path(__file__).resolve().parents[3]
    mod = _load_module(
        "playwright_service_security",
        root / "python" / "playwright-service" / "security.py",
    )

    with pytest.raises(ValueError, match="Only HTTP/HTTPS"):
        mod.validate_url_for_ssrf("file:///etc/passwd")


def test_validate_url_for_ssrf_blocks_unresolvable_hosts(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    mod = _load_module(
        "playwright_service_security_unresolvable",
        root / "python" / "playwright-service" / "security.py",
    )

    def _raise(*args, **kwargs):
        raise socket.gaierror()

    monkeypatch.setattr(mod.socket, "getaddrinfo", _raise)
    with pytest.raises(ValueError, match="does not resolve"):
        mod.validate_url_for_ssrf("https://example.com")


@pytest.mark.parametrize(
    "ips,should_allow",
    [
        (["127.0.0.1"], False),
        (["10.0.0.1"], False),
        (["169.254.10.10"], False),
        (["93.184.216.34"], True),  # example.com
        (["93.184.216.34", "10.0.0.1"], False),
    ],
)
def test_validate_url_for_ssrf_blocks_non_global_ips(monkeypatch, ips, should_allow):
    root = Path(__file__).resolve().parents[3]
    mod = _load_module(
        f"playwright_service_security_{'_'.join(ips)}",
        root / "python" / "playwright-service" / "security.py",
    )

    def _fake_getaddrinfo(*args, **kwargs):
        out = []
        for ip in ips:
            out.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)))
        return out

    monkeypatch.setattr(mod.socket, "getaddrinfo", _fake_getaddrinfo)
    if should_allow:
        mod.validate_url_for_ssrf("https://example.com")
    else:
        with pytest.raises(ValueError, match="internal"):
            mod.validate_url_for_ssrf("https://example.com")


def test_validate_url_for_ssrf_blocks_ip_literals():
    root = Path(__file__).resolve().parents[3]
    mod = _load_module(
        "playwright_service_security_ip_literal",
        root / "python" / "playwright-service" / "security.py",
    )

    with pytest.raises(ValueError, match="internal"):
        mod.validate_url_for_ssrf("http://127.0.0.1")

