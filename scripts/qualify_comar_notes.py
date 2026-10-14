"""Read the inspected 2024 AC7 note without inventing a balance-page row."""

# The readers live in the package; this script remains the standalone entry point.
from ledger_orchestrator.extraction.comar import (  # noqa: F401
    extract_notes,
    note_reading,
)
