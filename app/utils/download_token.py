"""Secure download-token helpers for public/anonymous jobs.

Flow:
  1. On job creation (anonymous): call ``generate_download_token()``
     → returns (plain_token, token_hash).
  2. Store ``token_hash`` in ``job_metadata["download_token_hash"]``.
  3. Return ``plain_token`` to the client inside ``JobAccepted.download_token``.
  4. On download: client passes ``?token=<plain_token>``.
  5. Call ``verify_download_token(plain_token, stored_hash)`` → True/False.
"""

import hashlib
import secrets


def generate_download_token() -> tuple[str, str]:
    """Generate a cryptographically secure random download token.

    Returns:
        (plain_token, token_hash) — store only the hash; return plain to client.
    """
    plain = secrets.token_urlsafe(32)
    digest = _hash_token(plain)
    return plain, digest


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def verify_download_token(plain: str, stored_hash: str) -> bool:
    """Return True if HMAC-safe comparison of hash(plain) == stored_hash."""
    return secrets.compare_digest(_hash_token(plain), stored_hash)
