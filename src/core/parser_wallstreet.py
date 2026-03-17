from decimal import Decimal
from datetime import datetime
from typing import Optional
from src.core.models import WSEntry


# Default WallStreet column names (matches standard WallStreet paste format).
# Override individual keys via wallstreet_column_mapping in config.json
# to accommodate users with different column orders or renamed headers.
DEFAULT_WS_COLUMNS = {
    "deal_type":      "Deal Type",
    "value_date":     "Value Date",
    "counterparty":   "Customer",
    "pay_ccy":        "Pay Ccy",
    "pay_amount":     "Pay Amount",
    "rec_ccy":        "Rec Ccy",
    "rec_amount":     "Rec Amount",
    "rate":           "Rate",
    "trader":         "Trader",
    "wallstreet_ref": "Deal #",
    "external_ref":   "Ext Deal #",
}


def parse_wallstreet_paste(
    pasted_text: str,
    col_map_override: Optional[dict] = None,
) -> tuple[list[WSEntry], Optional[str]]:
    """Parse tab-separated WallStreet data from clipboard paste.

    Column order is determined by header names, not position, so the paste
    works regardless of how the user has arranged columns in WallStreet.

    col_map_override: dict of {field_key: column_header_name} to override
                      any of the DEFAULT_WS_COLUMNS entries.

    Returns (list of WSEntry, detected counterparty name).
    Deduplicates rows by external_ref (Ext Deal #) — WallStreet often
    pastes the same data twice in sorted order.
    """
    mapping = {**DEFAULT_WS_COLUMNS, **(col_map_override or {})}

    text = pasted_text.strip()
    if not text:
        return [], None

    lines = [l for l in text.splitlines() if l.strip()]

    # Find the header row: the line that contains the value_date column name
    header_line_idx = None
    vd_col_name = mapping["value_date"]
    for i, line in enumerate(lines):
        if vd_col_name in line:
            header_line_idx = i
            break

    if header_line_idx is None:
        raise ValueError(
            f"Could not find WallStreet header row "
            f"(looking for column '{vd_col_name}')"
        )

    headers = lines[header_line_idx].split("\t")
    # Build lookup: column_header_name → index
    col_idx = {v.strip(): i for i, v in enumerate(headers)}

    def get(cells: list[str], field_key: str) -> str:
        col_name = mapping[field_key]
        idx = col_idx.get(col_name)
        if idx is None or idx >= len(cells):
            return ""
        return cells[idx].strip()

    seen_external_refs: set[str] = set()
    entries: list[WSEntry] = []
    detected_counterparty: Optional[str] = None

    for line in lines[header_line_idx + 1:]:
        cells = line.split("\t")
        if len(cells) < 3:
            continue

        ext_ref = get(cells, "external_ref")
        if not ext_ref:
            continue

        # Deduplicate: WallStreet pastes often contain sorted duplicates
        if ext_ref in seen_external_refs:
            continue
        seen_external_refs.add(ext_ref)

        deal_type = get(cells, "deal_type")
        if deal_type and deal_type.upper() != "FX":
            continue  # Skip non-FX rows

        counterparty = get(cells, "counterparty")
        if detected_counterparty is None and counterparty:
            detected_counterparty = counterparty

        raw_vd = get(cells, "value_date")
        # Support both "18 Mar 2026" and ISO "2026-03-18" formats
        try:
            value_date = datetime.strptime(raw_vd, "%d %b %Y").date()
        except ValueError:
            value_date = datetime.strptime(raw_vd, "%Y-%m-%d").date()

        entry = WSEntry(
            value_date=value_date,
            counterparty=counterparty,
            pay_ccy=get(cells, "pay_ccy"),
            pay_amount=Decimal(get(cells, "pay_amount").replace(",", "")),
            rec_ccy=get(cells, "rec_ccy"),
            rec_amount=Decimal(get(cells, "rec_amount").replace(",", "")),
            rate=Decimal(get(cells, "rate").replace(",", "")),
            trader=get(cells, "trader"),
            wallstreet_ref=get(cells, "wallstreet_ref"),
            external_ref=ext_ref,
            deal_type=deal_type or "FX",
        )
        entries.append(entry)

    return entries, detected_counterparty
