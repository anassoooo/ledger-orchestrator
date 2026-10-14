#!/bin/sh
# Run the full suite in the project image (Tesseract + LibreOffice) with the
# working tree mounted read-only and no network.
cd "$(dirname "$0")/.." || exit 1
MSYS_NO_PATHCONV=1 docker run --rm --network none \
  -v "$PWD/src:/app/src:ro" -v "$PWD/config:/app/config:ro" \
  -v "$PWD/scripts:/app/scripts:ro" -v "$PWD/tests:/app/tests:ro" \
  ledger-orchestrator:local python -m unittest discover -s tests -q
