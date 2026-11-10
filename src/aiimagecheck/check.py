"""One check of one file: credentials, labels, verdict."""

from __future__ import annotations

from . import credentials, labels, pdf, report, trust


def check_bytes(data: bytes, name: str, trust_settings: dict | None = None) -> report.Report:
    cred = credentials.read(data, trust=trust_settings)
    if pdf.is_pdf(data):
        found, document, read_error = pdf.find(data)
        return report.build(name, cred, found, read_error=read_error, kind=report.PDF, document=document)
    found, read_error = labels.find(data)
    return report.build(name, cred, found, read_error=read_error)


def default_trust() -> dict | None:
    """The cached trust lists, if `aiimagecheck update-trust` has been run."""
    return trust.settings()
