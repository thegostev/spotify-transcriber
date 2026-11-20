"""Read secrets from the macOS Keychain.

Secret values never enter logs or exception messages; callers get the value or
a KeychainError that names only the service and account.
"""

from __future__ import annotations

import subprocess

SECURITY_COMMAND = "security"


class KeychainError(Exception):
    """A Keychain lookup failed; the message never contains the secret."""


def get_secret(service: str, account: str) -> str:
    """Return the Keychain password for one service and account.

    Args:
        service: Keychain item service, e.g. ``ollama-cloud``.
        account: Keychain item account, e.g. ``api-key``.

    Returns:
        The secret value without its trailing newline.

    Raises:
        KeychainError: The lookup failed or returned an empty value.
    """
    command = [SECURITY_COMMAND, "find-generic-password", "-s", service, "-a", account, "-w"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise KeychainError(f"could not run security for service={service} account={account}") from exc
    if result.returncode != 0:
        raise KeychainError(f"Keychain has no secret for service={service} account={account}") from None
    value = result.stdout.rstrip("\n")
    if not value:
        raise KeychainError(f"Keychain secret for service={service} account={account} is empty") from None
    return value
