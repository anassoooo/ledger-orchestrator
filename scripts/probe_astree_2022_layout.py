"""Extract local ASTREE 2022 balance candidates without production admission.

The output contains confidential candidate amounts and evidence, all marked
unapproved. It reads only the two balance pages and does not modify the PDF,
template, production profile, or extractor registry.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

import pdfplumber


EXPECTED_RECENT = Path("outputs/historical_headers_20261012/qualification.json")
ASSET_NET = (460, 520)
ASSET_COMPARATIVE = (520, 570)
LIABILITY_CURRENT = (440, 490)
LIABILITY_COMPARATIVE = (510, 570)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def code_for(row, asset):
    from ledger_orchestrator.extraction.core import normalize

    label = " ".join(w["text"] for w in row if w["x0"] < (310 if asset else 345))
    norm = normalize(label)
    match = re.match(r"^(AC|CP|PA)\s*(\d+(?:,\d+)*)", norm)
    code = match.group(1) + match.group(2).replace(",", "_") if match else None
    if asset and norm.startswith("ACACTIFS INCORPORELS"):
        code = "AC1"
    if asset and norm.startswith(("ACPART", "AC PART")) and "PROVISIONS TECHNIQUES" in norm:
        code = "AC5"
    if norm.startswith("TOTAL DE L'ACTIF"):
        code = "TOTAL_ASSET"
    elif norm.startswith("TOTAL CAPITAUX PROPRES AVANT RESULTAT"):
        code = "EQUITY_BEFORE"
    elif norm.startswith("TOTAL CAPITAUX PROPRES AVANT AFFECTATION"):
        code = "EQUITY"
    elif norm.startswith("TOTAL DES CAPITAUX PROPRES ET DU PASSIF"):
        code = "TOTAL_EQUITY_LIABILITY"
    return code, label


def value_in_band(row, band, width):
    from ledger_orchestrator.extraction.core import numeric_groups

    groups = numeric_groups(row, width)
    overlaps = [(value, x0, x1) for value, x0, x1 in groups
                if x0 < band[1] and x1 > band[0]]
    selected = [(value, x0, x1) for value, x0, x1 in groups
                if band[0] <= x0 and x1 <= band[1]]
    crossing = [(value, x0, x1) for value, x0, x1 in overlaps
                if not (band[0] <= x0 and x1 <= band[1])]
    if crossing:
        spans = [[round(x0, 2), round(x1, 2)] for _, x0, x1 in crossing]
        return None, "numeric_group_crosses_boundary", spans
    if not selected:
        in_band = [w for w in row if band[0] <= (w["x0"] + w["x1"]) / 2 < band[1]]
        dash_words = [w for w in in_band if w["text"].strip() in ("-", "–", "—", "−")]
        if dash_words:
            return None, "published_dash", [
                round(min(w["x0"] for w in dash_words), 2),
                round(min(w["top"] for w in dash_words), 2),
                round(max(w["x1"] for w in dash_words), 2),
                round(max(w["bottom"] for w in dash_words), 2),
            ]
        other_tokens = [w for w in in_band if not re.fullmatch(r"[()\d,.−-]+", w["text"].strip())]
        if other_tokens:
            return None, "unrecognized_column_text", [
                round(min(w["x0"] for w in other_tokens), 2),
                round(min(w["top"] for w in other_tokens), 2),
                round(max(w["x1"] for w in other_tokens), 2),
                round(max(w["bottom"] for w in other_tokens), 2),
            ]
        return None, "blank", None
    if len(selected) != 1:
        spans = [[round(x0, 2), round(x1, 2)] for _, x0, x1 in selected]
        return None, "ambiguous_multiple_groups", spans
    value, x0, x1 = selected[0]
    return value, "numeric", [round(x0, 2), round(x1, 2)]


def extract_section(page, year, asset):
    from ledger_orchestrator.extraction.core import lines, normalize

    title = "ACTIF DU BILAN" if asset else "CAPITAUX PROPRES ET PASSIF DU BILAN"
    text = normalize(page.extract_text(x_tolerance=2) or "")
    if abs(page.width - 595.22) > 1 or abs(page.height - 842) > 1:
        raise ValueError("Unsupported ASTREE 2022 balance page geometry")
    if title not in text or "DINARS TUNISIEN" not in text:
        raise ValueError("Unconfirmed ASTREE balance identity/title/unit")
    current_year = str(year)
    prior_year = str(year - 1)
    words = page.extract_words(x_tolerance=2)
    header_words = [w for w in words if w["top"] < 215]
    date_words = [w for w in header_words
                  if w["text"] in (current_year, f"31/12/{year}", f"31/12/{year-1}")]
    current_heading = [w for w in date_words if w["text"] in (current_year, f"31/12/{year}")]
    prior_heading = [w for w in date_words if w["text"] == f"31/12/{year-1}"]
    if len(current_heading) != 1 or len(prior_heading) != 1:
        raise ValueError("Unconfirmed unique current/comparative headings")
    current_center = (current_heading[0]["x0"] + current_heading[0]["x1"]) / 2
    prior_center = (prior_heading[0]["x0"] + prior_heading[0]["x1"]) / 2
    if not 430 <= current_center < 475 or not 510 <= prior_center < 565:
        raise ValueError("Unexpected ASTREE 2022 period-column positions")

    current_band = ASSET_NET if asset else LIABILITY_CURRENT
    prior_band = ASSET_COMPARATIVE if asset else LIABILITY_COMPARATIVE
    manifest = []
    values = {}
    for row in lines(words):
        code, label = code_for(row, asset)
        if not code:
            continue
        current, current_state, current_bbox = value_in_band(row, current_band, page.width)
        prior, prior_state, prior_bbox = value_in_band(row, prior_band, page.width)
        if code in values:
            raise ValueError(f"Duplicate balance row code: {code}")
        values[code] = current
        manifest.append({
            "code": code,
            "label": label,
            "bbox": [round(min(w["x0"] for w in row), 2),
                     round(min(w["top"] for w in row), 2),
                     round(max(w["x1"] for w in row), 2),
                     round(max(w["bottom"] for w in row), 2)],
            "current_state": current_state,
            "current_numeric_group_bbox": current_bbox,
            "comparative_state": prior_state,
            "comparative_numeric_group_bbox": prior_bbox,
            "published_zero": current_state == "numeric" and current == 0,
            "_current_value": current,
            "_comparative_value": prior,
        })

    if asset:
        left, right = "TOTAL_ASSET", "TOTAL_ASSET"
        components = ("AC1", "AC2", "AC3", "AC5", "AC6", "AC7")
    else:
        left, right = "TOTAL_EQUITY_LIABILITY", "TOTAL_EQUITY_LIABILITY"
        components = ("EQUITY", "PA2", "PA3", "PA5", "PA6", "PA7")
    complete = all(values.get(code) is not None for code in (*components, left, right))
    delta = sum(values[c] for c in components) - values[right] if complete else None
    return {
        "page": page.page_number,
        "page_size_points": [round(page.width, 2), round(page.height, 2)],
        "current_heading": current_heading[0]["text"],
        "current_heading_center_x": round((current_heading[0]["x0"] + current_heading[0]["x1"]) / 2, 2),
        "comparative_heading": prior_heading[0]["text"],
        "comparative_heading_center_x": round((prior_heading[0]["x0"] + prior_heading[0]["x1"]) / 2, 2),
        "current_value_band_points": list(current_band),
        "comparative_value_band_points": list(prior_band),
        "rows": manifest,
        "top_level_reconciliation": {
            "components": list(components),
            "complete": complete,
            "delta_tnd": delta,
            "exact_match": delta == 0 if complete else False,
        },
        "_printed_current_total": values.get(right),
        "unapproved": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--headers", type=Path, default=EXPECTED_RECENT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    source = root / "data/sources/ASTREE/2022.pdf"
    headers_path = args.headers if args.headers.is_absolute() else root / args.headers
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists():
        raise ValueError("Choose a new output directory; existing evidence is never overwritten")
    before_source = sha256(source)
    before_headers = sha256(headers_path)
    headers = json.loads(headers_path.read_text(encoding="utf-8"))
    identity = [d for d in headers["documents"]
                if d["company"] == "ASTREE" and d["filename_year"] == 2022]
    if len(identity) != 1 or identity[0]["sha256"] != before_source:
        raise ValueError("ASTREE 2022 identity/source hash does not match header evidence")
    if identity[0]["status"] != "native_identity_and_balance_periods_observed":
        raise ValueError("ASTREE 2022 identity or balance periods are not qualified")

    with pdfplumber.open(source) as pdf:
        sections = {
            "asset": extract_section(pdf.pages[1], 2022, True),
            "equity_liability": extract_section(pdf.pages[2], 2022, False),
        }
    if sha256(source) != before_source or sha256(headers_path) != before_headers:
        raise ValueError("A read-only input changed during inspection")

    candidate_facts = []
    for statement, section in (("asset", sections["asset"]),
                               ("equity_liability", sections["equity_liability"])):
        for row in section["rows"]:
            for period, field, state_field, bbox_field, source_column, source_kind in (
                (2022, "_current_value", "current_state", "current_numeric_group_bbox", "current", "native_current"),
                (2021, "_comparative_value", "comparative_state", "comparative_numeric_group_bbox", "previous", "native_comparative"),
            ):
                amount = row[field]
                if row[state_field] != "numeric" or amount is None:
                    continue
                candidate_facts.append({
                    "schema_version": 1,
                    "company": "ASTREE",
                    "year": period,
                    "statement": statement,
                    "code": row["code"],
                    "source_amount": str(int(amount)) if float(amount).is_integer() else str(amount),
                    "target_amount": None,
                    "source_unit": "TND",
                    "target_unit": "TND",
                    "conversion_factor": "1",
                    "approved": False,
                    "evidence": {
                        "source": "sources/ASTREE/2022.pdf",
                        "sha256": before_source,
                        "document_year": 2022,
                        "source_kind": source_kind,
                        "source_column": source_column,
                        "page": section["page"],
                        "method": "native",
                        "bbox": row[bbox_field],
                        "row_bbox": row["bbox"],
                        "source_label": row["label"],
                    },
                })
            row.pop("_current_value")
            row.pop("_comparative_value")

    from ledger_orchestrator.extraction.astree_candidate import ASSET_CODES, LIABILITY_CODES

    code_sets = {}
    for key, expected in (("asset", ASSET_CODES), ("equity_liability", LIABILITY_CODES)):
        actual = {row["code"] for row in sections[key]["rows"]}
        code_sets[key] = {"matches_recent_manifest": actual == expected,
                          "missing_from_2022": sorted(expected - actual),
                          "additional_in_2022": sorted(actual - expected)}
    asset_total = sections["asset"]["rows"]
    # Cross-balance control is based only on the printed total rows.
    a_total = next((r for r in asset_total if r["code"] == "TOTAL_ASSET"), None)
    l_total = next((r for r in sections["equity_liability"]["rows"]
                    if r["code"] == "TOTAL_EQUITY_LIABILITY"), None)
    asset_value = sections["asset"]["_printed_current_total"]
    liability_value = sections["equity_liability"]["_printed_current_total"]
    cross_delta = asset_value - liability_value if asset_value is not None and liability_value is not None else None
    for section in sections.values():
        section.pop("_printed_current_total")
    result = {
        "company": "ASTREE",
        "filename_year": 2022,
        "source": "sources/ASTREE/2022.pdf",
        "source_sha256": before_source,
        "header_evidence_sha256": before_headers,
        "identity_and_periods_prequalified": True,
        "sections": sections,
        "candidate_facts": candidate_facts,
        "row_manifest_comparison": code_sets,
        "printed_total_rows_present": bool(a_total and l_total),
        "printed_asset_minus_equity_liability_tnd": cross_delta,
        "printed_totals_match": cross_delta == 0 if cross_delta is not None else False,
        "production_admitted": False,
        "approved": False,
        "financial_amounts_persisted": True,
        "scope": "Local, unapproved balance candidates; no workbook or production changes",
    }
    output.mkdir(parents=True)
    (output / "qualification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "output": str(output),
        "asset_rows": len(sections["asset"]["rows"]),
        "liability_rows": len(sections["equity_liability"]["rows"]),
        "asset_recent_manifest_matches": code_sets["asset"]["matches_recent_manifest"],
        "liability_recent_manifest_matches": code_sets["equity_liability"]["matches_recent_manifest"],
        "asset_reconciliation_exact": sections["asset"]["top_level_reconciliation"]["exact_match"],
        "liability_reconciliation_exact": sections["equity_liability"]["top_level_reconciliation"]["exact_match"],
        "printed_totals_match": result["printed_totals_match"],
        "printed_asset_minus_equity_liability_tnd": cross_delta,
        "published_zero_codes": [row["code"] for section in sections.values()
                                 for row in section["rows"] if row["published_zero"]],
        "candidate_fact_count": len(candidate_facts),
        "approved": False,
        "production_admitted": False,
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
