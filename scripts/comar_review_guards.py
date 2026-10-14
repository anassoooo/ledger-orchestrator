"""Destination checks for the inspected COMAR review template, not admission."""

# The readers live in the package; this script remains the standalone entry point.
from ledger_orchestrator.extraction.comar import (  # noqa: F401
    CONTRACT_PATH,
    validate_template,
)
