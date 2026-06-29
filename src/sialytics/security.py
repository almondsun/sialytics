"""Políticas de navegación y de salida para los límites de confianza."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

SIA_HOST = "sia.unal.edu.co"
UNAL_SUFFIX = ".unal.edu.co"
KNOWN_AUTHENTICATION_HOSTS = frozenset({"autenticasia.unal.edu.co"})


class NavigationDenied(RuntimeError):
    pass


class NavigationPolicy:
    """Lista exacta de hosts UNAL; no interpreta comodines."""

    def __init__(self, authentication_hosts: set[str] | None = None) -> None:
        hosts = KNOWN_AUTHENTICATION_HOSTS.union(authentication_hosts or set())
        normalized = {self._validate_institutional_host(host) for host in hosts}
        self._navigation_hosts = frozenset({SIA_HOST, *normalized})

    @classmethod
    def from_environment(cls) -> NavigationPolicy:
        raw = os.environ.get("SIALYTICS_AUTH_HOSTS", "")
        return cls({item.strip() for item in raw.split(",") if item.strip()})

    @staticmethod
    def _validate_institutional_host(host: str) -> str:
        normalized = host.strip().rstrip(".").lower()
        if "://" in normalized or "/" in normalized or "*" in normalized:
            raise ValueError("Configure hosts exactos, sin esquema, ruta ni comodines")
        if normalized != "unal.edu.co" and not normalized.endswith(UNAL_SUFFIX):
            raise ValueError(f"El host no pertenece al dominio institucional UNAL: {host}")
        return normalized

    @property
    def navigation_hosts(self) -> frozenset[str]:
        return self._navigation_hosts

    def assert_navigation_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host not in self._navigation_hosts:
            raise NavigationDenied(f"Navegación bloqueada hacia {parsed.scheme}://{host}")

    @staticmethod
    def assert_academic_source(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != SIA_HOST:
            raise NavigationDenied("Los datos académicos solo pueden extraerse de sia.unal.edu.co")


def secure_output_permissions(path: Path) -> None:
    """Aplica permisos de usuario cuando la plataforma los soporta."""

    try:
        path.chmod(0o600)
    except OSError:
        # El archivo ya existe y es válido; algunos sistemas no implementan chmod.
        pass


def safe_spreadsheet_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
