import csv
from decimal import Decimal
from datetime import datetime
from typing import Optional
from src.core.models import GPGPayment


def parse_gpg_csv(
    file_path: str,
    column_mapping: dict,
    date_format: str,
    bank_code_column: str = "Bank Code"
) -> tuple[list[GPGPayment], Optional[str]]:
    """Parse a GPG CSV file into GPGPayment records.

    Returns (list of payments, detected bank code).
    """
    records = []
    detected_bank_code = None

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Detect bank code from first row
            if detected_bank_code is None and bank_code_column in row:
                detected_bank_code = row[bank_code_column].strip()

            # Parse status code (may contain "DT06,SOME MESSAGE")
            raw_status = row.get(column_mapping.get("status_code", ""), "").strip()
            status_code = None
            status_message = None
            if raw_status:
                parts = raw_status.split(",", 1)
                status_code = parts[0].strip()
                status_message = parts[1].strip() if len(parts) > 1 else None

            payment = GPGPayment(
                payment_id=row[column_mapping["payment_id"]].strip(),
                confirmation_number=row[column_mapping["confirmation_number"]].strip(),
                buy_currency=row[column_mapping["buy_currency"]].strip(),
                buy_amount=Decimal(row[column_mapping["buy_amount"]].strip().replace(",", "")),
                value_date=datetime.strptime(
                    row[column_mapping["value_date"]].strip(), date_format
                ).date(),
                status_code=status_code,
                status_message=status_message,
                counterparty=row.get(bank_code_column, "").strip(),
                raw_row=dict(row),
            )
            records.append(payment)

    return records, detected_bank_code
