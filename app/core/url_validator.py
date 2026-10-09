"""SSRF and URL Security Validator for media processing and network requests."""

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.exceptions import AppException

# Forbidden internal hostnames commonly found in Docker/Kubernetes/LAN
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "redis",
        "docker",
        "postgres",
        "postgresql",
        "supabase",
        "minio",
        "localstack",
    }
)


def _check_ip_is_safe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Validate that IP is public and not private, loopback, or cloud-metadata."""
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise AppException(
            status_code=400,
            detail="Access to loopback, private, link-local or cloud metadata IP ranges is forbidden.",
        )


def validate_safe_url(url: str) -> str:
    """Validate that a URL is safe to fetch and not attempting SSRF or argument injection.

    Rules:
    1. Must not start with '-' or command switches.
    2. Must be http or https scheme (no file://, gopher://, ftp://, etc.).
    3. Hostname must be present and not in internal blocklist.
    4. Must resolve to public IP addresses (blocking 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12,
       192.168.0.0/16, 169.254.169.254, ::1, etc.).
    """
    if not url or not isinstance(url, str):
        raise AppException(status_code=400, detail="URL must be a non-empty string.")

    cleaned_url = url.strip()

    # Chặn argument injection (flags/switches như --exec, -o, ...)
    if cleaned_url.startswith("-"):
        raise AppException(
            status_code=400,
            detail="Invalid URL: URLs cannot begin with a hyphen or command flag.",
        )

    try:
        parsed = urlparse(cleaned_url)
    except Exception as exc:
        raise AppException(status_code=400, detail=f"Invalid URL structure: {exc!s}") from exc

    if parsed.scheme.lower() not in ("http", "https"):
        raise AppException(
            status_code=400,
            detail=f"Invalid URL scheme '{parsed.scheme}'. Only http and https are allowed.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise AppException(status_code=400, detail="URL missing valid hostname.")

    hostname_lower = hostname.lower()

    if hostname_lower in BLOCKED_HOSTNAMES or hostname_lower.endswith(
        (".local", ".internal", ".localhost", ".lan")
    ):
        raise AppException(
            status_code=400,
            detail=f"Access to private/internal host '{hostname}' is forbidden.",
        )

    # Check if hostname is directly an IP literal
    try:
        ip = ipaddress.ip_address(hostname_lower)
        _check_ip_is_safe(ip)
        return cleaned_url
    except ValueError:
        pass

    # Resolve hostname to verify destination IP addresses
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        addr_infos = socket.getaddrinfo(
            hostname, port, proto=socket.IPPROTO_TCP
        )
        if not addr_infos:
            raise AppException(status_code=400, detail=f"Could not resolve host '{hostname}'.")
        for item in addr_infos:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            _check_ip_is_safe(ip)
    except socket.gaierror as exc:
        raise AppException(
            status_code=400, detail=f"Could not resolve hostname '{hostname}': {exc!s}"
        ) from exc

    return cleaned_url
