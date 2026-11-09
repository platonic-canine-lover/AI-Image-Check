"""One check of one image: credentials, labels, verdict."""

from __future__ import annotations

from . import credentials, labels, report, trust


def check_bytes(data: bytes, name: str, trust_settings: dict | None = None) -> report.Report:
    cred = credentials.read(data, trust=trust_settings)
    found, read_error = labels.find(data)
    return report.build(name, cred, found, read_error=read_error)


def default_trust() -> dict | None:
    """The cached trust lists, if `aiimagecheck update-trust` has been run."""
    return trust.settings()
