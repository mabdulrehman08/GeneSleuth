"""Errors that can safely appear in investigation traces."""


class InvestigationError(RuntimeError):
    """A deliberate diagnostic suitable for logs and application clients."""


def safe_error(error: Exception) -> str:
    """Avoid exposing provider payloads, file paths and keys in application diagnostics."""
    if isinstance(error, InvestigationError):
        return str(error)
    if isinstance(error, ValueError) and str(error) in {
        "Unknown investigation mode",
        "Unknown investigation profile",
        "A completed full result and a reviewer request are required",
        "The case has no candidate variants",
    }:
        return str(error)
    return f"Investigation failed ({type(error).__name__})"
